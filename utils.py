import sqlite3
import threading
import requests
import hashlib
import json
import os
import re
from collections import Counter
import folder_paths
import time
import statistics
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor

try:

    import orjson as json_lib

    print("[Civitai Utils] orjson library found, using for faster JSON operations.")
except ImportError:
    import json as json_lib

    print("[Civitai Utils] orjson not found, falling back to standard json library.")

HASH_CACHE_REFRESH_INTERVAL = 3600


# =================================================================================
# 1. 核心数据库管理器 (Core Database Manager)
# =================================================================================
class DatabaseManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        project_root = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(project_root, "data", "civitai_helper.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()
        self._initialized = True
        print(f"[Civitai Utils] Database initialized at: {self.db_path}")

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS models (model_id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT)")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                hash TEXT PRIMARY KEY, version_id INTEGER UNIQUE, model_id INTEGER, model_type TEXT, name TEXT,
                local_path TEXT UNIQUE, local_mtime REAL, trained_words TEXT, api_response TEXT, last_api_check INTEGER,
                FOREIGN KEY (model_id) REFERENCES models (model_id)
            )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_model_type ON versions (model_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_versions_version_id ON versions (version_id)")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                image_id INTEGER PRIMARY KEY, version_id INTEGER, url TEXT UNIQUE NOT NULL, meta TEXT, local_filename TEXT,
                FOREIGN KEY (version_id) REFERENCES versions (version_id)
            )""")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_url ON images (url)")
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_cache (
                fingerprint TEXT PRIMARY KEY,
                analysis_data TEXT,
                last_updated INTEGER
            )""")

    def get_setting(self, key, default=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
        if row and row["value"]:
            try:
                return json_lib.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    def set_setting(self, key, value):
        with self.get_connection() as conn:
            value_str = (
                json_lib.dumps(value).decode("utf-8")
                if isinstance(json_lib.dumps(value), bytes)
                else json_lib.dumps(value)
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value_str),
            )

    def get_analysis_cache(self, fingerprint):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT analysis_data FROM analysis_cache WHERE fingerprint = ?",
                (fingerprint,),
            )
            row = cursor.fetchone()
        if row and row["analysis_data"]:
            return json_lib.loads(row["analysis_data"])
        return None

    def set_analysis_cache(self, fingerprint, data):
        with self.get_connection() as conn:
            data_str = (
                json_lib.dumps(data).decode("utf-8")
                if isinstance(json_lib.dumps(data), bytes)
                else json_lib.dumps(data)
            )
            conn.execute(
                "INSERT OR REPLACE INTO analysis_cache (fingerprint, analysis_data, last_updated) VALUES (?, ?, ?)",
                (fingerprint, data_str, int(time.time())),
            )

    def clear_analysis_cache(self):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM analysis_cache")
        print("[Civitai Utils] Analysis cache cleared.")

    def clear_api_responses(self):
        with self.get_connection() as conn:
            conn.execute("UPDATE versions SET api_response = NULL, last_api_check = 0")
        print("[Civitai Utils] All API response caches cleared.")

    def clear_all_triggers(self):
        with self.get_connection() as conn:
            conn.execute("UPDATE versions SET trained_words = NULL")
        print("[Civitai Utils] All trigger word caches cleared.")

    def get_version_by_hash(self, file_hash):
        if not file_hash:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM versions WHERE hash = ?", (file_hash.lower(),)
            )
            return cursor.fetchone()

    def get_version_by_id(self, version_id):
        if not version_id:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM versions WHERE version_id = ?", (version_id,))
            return cursor.fetchone()

    def get_model_by_id(self, model_id):
        if not model_id:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM models WHERE model_id = ?", (model_id,))
            return cursor.fetchone()

    def get_image_by_url(self, url):
        if not url:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM images WHERE url = ?", (url,))
            return cursor.fetchone()

    def add_or_update_version_from_api(self, data):
        model_data = data.get("model", {})
        model_id = model_data.get("id")
        with self.get_connection() as conn:
            if model_id:
                conn.execute("INSERT OR IGNORE INTO models (model_id, name, type) VALUES (?, ?, ?)", (model_id, model_data.get("name"), model_data.get("type")))
                conn.execute("UPDATE models SET name = ?, type = ? WHERE model_id = ?", (model_data.get("name"), model_data.get("type"), model_id))
            version_id = data.get("id")
            if not version_id or not model_id:
                return
            file_info = data.get("files", [{}])[0]
            file_hash = file_info.get("hashes", {}).get("SHA256")
            if not file_hash:
                return
            file_hash = file_hash.lower()
            api_response_str = (
                json_lib.dumps(data).decode("utf-8")
                if isinstance(json_lib.dumps(data), bytes)
                else json_lib.dumps(data)
            )
            trained_words_str = (
                json_lib.dumps(data.get("trainedWords")).decode("utf-8")
                if isinstance(json_lib.dumps(data.get("trainedWords")), bytes)
                else json_lib.dumps(data.get("trainedWords"))
            )

            conn.execute(
                """
                INSERT INTO versions (hash, version_id, model_id, name, trained_words, api_response, last_api_check) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET version_id = excluded.version_id, model_id = excluded.model_id, name = excluded.name,
                trained_words = excluded.trained_words, api_response = excluded.api_response, last_api_check = excluded.last_api_check
            """,
                (
                    file_hash,
                    version_id,
                    model_id,
                    data.get("name"),
                    trained_words_str,
                    api_response_str,
                    int(time.time()),
                ),
            )

    def add_downloaded_image(self, url, local_filename, version_id=None, meta=None):
        with self.get_connection() as conn:
            meta_str = json_lib.dumps(meta).decode("utf-8") if meta and isinstance(json_lib.dumps(meta), bytes) else json_lib.dumps(meta)
            conn.execute(
                """
                INSERT INTO images (url, local_filename, version_id, meta) VALUES (?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET local_filename = excluded.local_filename,
                version_id = COALESCE(excluded.version_id, version_id), meta = COALESCE(excluded.meta, meta)
            """,
                (url, local_filename, version_id, meta_str),
            )

    def get_db_stats(self):
        stats = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 统计各类模型的数量
            for model_type in ["checkpoints", "loras"]:
                cursor.execute(
                    "SELECT COUNT(*) FROM versions WHERE model_type = ? AND local_path IS NOT NULL",
                    (model_type,),
                )
                count = cursor.fetchone()[0]
                stats[model_type] = count
        return stats

    def get_scanned_models(self, model_type):
        """从数据库中获取指定类型的所有模型相对路径列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT local_path FROM versions WHERE model_type = ? AND local_path IS NOT NULL ORDER BY local_path ASC",
                (model_type,),
            )
            rows = cursor.fetchall()

        known_relative_paths = folder_paths.get_filename_list(model_type)
        full_path_map = {
            os.path.normpath(folder_paths.get_full_path(model_type, f)): f
            for f in known_relative_paths
        }

        db_relative_paths = []
        for row in rows:
            full_path = os.path.normpath(row["local_path"])
            relative_path = full_path_map.get(full_path)
            if relative_path:
                db_relative_paths.append(relative_path)
        return db_relative_paths

db_manager = DatabaseManager()

# =================================================================================
# 2. 配置与全局函数
# =================================================================================
def _get_active_domain() -> str:
    network_choice = db_manager.get_setting("network_choice", "com")
    return "civitai.work" if network_choice == "work" else "civitai.com"


def load_selections():
    return db_manager.get_setting("selections", {})


def save_selections(data):
    db_manager.set_setting("selections", data)


SAMPLER_SCHEDULER_MAP = {
    "Euler a": "euler_ancestral",
    "Euler": "euler",
    "LMS": "lms",
    "Heun": "heun",
    "DPM2": "dpm_2",
    "DPM2 a": "dpm_2_ancestral",
    "DPM++ 2S a": "dpmpp_2s_ancestral",
    "DPM++ 2M": "dpmpp_2m",
    "DPM++ SDE": "dpmpp_sde",
    "DPM++ 2M SDE": "dpmpp_2m_sde",
    "DPM fast": "dpm_fast",
    "DPM adaptive": "dpm_adaptive",
    "DDIM": "ddim",
    "PLMS": "plms",
    "UniPC": "uni_pc",
    "normal": "normal",
    "karras": "karras",
    "Karras": "karras",
    "exponential": "exponential",
    "sgm_uniform": "sgm_uniform",
    "simple": "simple",
    "ddim_uniform": "ddim_uniform",
    "turbo": "turbo",
}


# =================================================================================
# 3. Civitai API & 本地文件核心工具
# =================================================================================
class CivitaiAPIUtils:
    @staticmethod
    def _request_with_retry(url, params=None, timeout=15, retries=3, delay=5):
        for i in range(retries + 1):
            try:
                if params:
                    response = requests.get(url, params=params, timeout=timeout)
                else:
                    response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print(
                        f"[Civitai Utils] API rate limit hit. Waiting for {delay} seconds before retrying..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise e
            except requests.exceptions.RequestException as e:
                print(
                    f"[Civitai Utils] Network error: {e}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
        raise Exception(f"Failed to fetch data from {url} after {retries} retries.")

    @staticmethod
    def calculate_sha256(file_path):
        print(
            f"[Civitai Utils] Calculating SHA256 for: {os.path.basename(file_path)}..."
        )
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"[Civitai Utils] Error calculating hash for {file_path}: {e}")
            return None

    @classmethod
    def get_model_version_info_by_id(cls, version_id, domain, force_refresh=False):
        if not version_id:
            return None
        if not force_refresh:
            version = db_manager.get_version_by_id(version_id)
            if version and version["api_response"]:
                return json_lib.loads(version["api_response"])

        url = f"https://{domain}/api/v1/model-versions/{version_id}"
        try:
            resp = cls._request_with_retry(url)
            data = resp.json()
            if data:
                db_manager.add_or_update_version_from_api(data)
            return data
        except Exception as e:
            print(f"[Civitai Utils] API Error (ID {version_id}): {e}")
        return None

    @classmethod
    def get_model_version_info_by_hash(cls, sha256_hash, force_refresh=False):
        if not sha256_hash:
            return None
        if not force_refresh:
            version = db_manager.get_version_by_hash(sha256_hash)
            if version and version["api_response"]:
                return json_lib.loads(version["api_response"])

        domain = _get_active_domain()
        url = f"https://{domain}/api/v1/model-versions/by-hash/{sha256_hash}"
        print(
            f"[Civitai Utils] API Call: Fetching info for hash: {sha256_hash[:12]}..."
        )
        try:
            resp = cls._request_with_retry(url)
            data = resp.json()
            if data and data.get("id"):
                db_manager.add_or_update_version_from_api(data)
            return data
        except Exception as e:
            print(f"[Civitai Utils] API Error (hash {sha256_hash[:12]}): {e}")
        return None

    @staticmethod
    def _parse_prompts(prompt_text: str):
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            return []
        pattern = re.compile(r"\(.+?:\d+\.\d+\)|<[^>]+>|\[[^\]]+\]|\([^)]+\)|[^,]+")
        tags = pattern.findall(prompt_text)
        return [tag.strip() for tag in tags if tag.strip()]

def sync_local_files_with_db(model_type: str, force=False):
    if model_type not in ["loras", "checkpoints"]:
        return {"found": 0, "hashed": 0}

    last_sync_key = f"last_sync_{model_type}"
    last_sync_time = db_manager.get_setting(last_sync_key, 0)
    if not force and time.time() - last_sync_time < HASH_CACHE_REFRESH_INTERVAL:
        return {"found": 0, "hashed": 0, "skipped": True}

    print(f"[Civitai Utils] Syncing local {model_type} with database...")
    local_files_on_disk = folder_paths.get_filename_list(model_type)

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT local_path, local_mtime FROM versions WHERE model_type = ?", (model_type,))
        # [核心修正] 在构建字典时进行最严格的规范化
        db_files = {os.path.normcase(os.path.normpath(row["local_path"])): row["local_mtime"] for row in cursor.fetchall()}

    files_to_hash = []
    for relative_path in local_files_on_disk:
        full_path = folder_paths.get_full_path(model_type, relative_path)
        if not full_path or not os.path.exists(full_path) or os.path.isdir(full_path):
            continue

        # [核心修正] 在比较前也进行最严格的规范化
        norm_full_path = os.path.normcase(os.path.normpath(full_path))

        try:

            mtime = os.path.getmtime(norm_full_path)
            # 使用规范化后的路径进行所有判断
            if (force and db_files.get(norm_full_path) == 0) or norm_full_path not in db_files or db_files[norm_full_path] != mtime:
                files_to_hash.append({"path": full_path, "mtime": mtime}) # 存入数据库的仍然是原始大小写路径
        except Exception as e:
            print(f"[Civitai Utils] Warning: Could not process file {relative_path}: {e}")

    hashed_count = 0
    if files_to_hash:
        print(f"[Civitai Utils] Found {len(files_to_hash)} new/modified {model_type} files. Hashing...")
        def hash_worker(file_info):
            return {**file_info, "hash": CivitaiAPIUtils.calculate_sha256(file_info["path"])}

        with ThreadPoolExecutor(max_workers=(os.cpu_count() or 4)) as executor:
            results = list(tqdm(executor.map(hash_worker, files_to_hash), total=len(files_to_hash), desc=f"Hashing {model_type}"))

        hashed_count = len(results)
        with db_manager.get_connection() as conn:
            for res in results:
                if res["hash"]:
                    # 使用原始大小写路径进行数据库操作
                    conn.execute("UPDATE versions SET local_path = NULL, local_mtime = NULL WHERE local_path = ?", (res["path"],))
                    conn.execute("""
                        INSERT INTO versions (hash, local_path, local_mtime, name, model_type) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(hash) DO UPDATE SET local_path = excluded.local_path, local_mtime = excluded.local_mtime
                    """, (res["hash"].lower(), res["path"], res["mtime"], os.path.basename(res["path"]), model_type))

    db_manager.set_setting(last_sync_key, time.time())
    print(f"[Civitai Utils] Sync for {model_type} complete.")

    # 返回扫描结果
    return {"found": len(files_to_hash), "hashed": hashed_count}

def get_local_model_maps(model_type: str, force_sync=False):
    sync_local_files_with_db(model_type, force=force_sync)

    # 1. 从数据库获取所有已知文件的绝对路径 -> 哈希映射
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT hash, local_path FROM versions WHERE hash IS NOT NULL AND local_path IS NOT NULL AND model_type = ?", (model_type,))
        rows = cursor.fetchall()

    abs_path_to_hash = {os.path.normpath(row["local_path"]): row["hash"] for row in rows}

    # 2. 获取ComfyUI认可的相对路径列表
    known_relative_paths = folder_paths.get_filename_list(model_type)

    hash_to_filename = {}
    filename_to_hash = {}

    # 3. 遍历列表，构建新的映射
    for relative_path in known_relative_paths:
        full_path = os.path.normpath(
            folder_paths.get_full_path(model_type, relative_path)
        )

        # 从我们的数据库中查找这个文件的哈希
        file_hash = abs_path_to_hash.get(full_path)

        if file_hash:

            hash_to_filename[file_hash] = relative_path
            filename_to_hash[relative_path] = file_hash

    return hash_to_filename, filename_to_hash


def get_model_filenames_from_db(model_type: str, force_sync=False):
    """
    这是获取模型列表的权威函数。
    它确保数据库已同步，然后基于数据库内容构建列表，
    并与ComfyUI的已知路径交叉引用以确保准确性。
    """
    sync_local_files_with_db(model_type, force=force_sync)

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT local_path FROM versions WHERE model_type = ? AND local_path IS NOT NULL ORDER BY local_path ASC",
            (model_type,),
        )
        rows = cursor.fetchall()

    known_relative_paths = folder_paths.get_filename_list(model_type)
    full_path_map = {
        os.path.normpath(folder_paths.get_full_path(model_type, f)): f
        for f in known_relative_paths
    }

    db_relative_paths = []
    for row in rows:
        full_path = os.path.normpath(row["local_path"])
        relative_path = full_path_map.get(full_path)
        if relative_path:
            db_relative_paths.append(relative_path)

    return sorted(list(set(db_relative_paths)))


def get_legacy_cache_files():
    """返回所有存在的旧版缓存文件的路径字典"""
    project_root = os.path.dirname(__file__)
    data_dir = os.path.join(project_root, "data")

    files_to_check = {
        "checkpoints_format1": os.path.join(data_dir, "hash_cache.json"),
        "loras_format2": os.path.join(data_dir, "loras_hash_cache.json"),
    }

    return {key: path for key, path in files_to_check.items() if os.path.exists(path)}


def check_legacy_cache_exists():
    """检查任何一种旧版缓存文件是否存在"""
    return bool(get_legacy_cache_files())


def migrate_legacy_caches():
    """统一的迁移函数，现在精确处理两种指定的旧JSON缓存"""
    legacy_files = get_legacy_cache_files()
    if not legacy_files:
        return {
            "migrated": 0,
            "skipped": 0,
            "message": "No legacy cache files found to migrate.",
        }

    total_migrated = 0
    total_skipped = 0

    with db_manager.get_connection() as conn:
        # 处理格式1: hash_cache.json (Checkpoints)
        if "checkpoints_format1" in legacy_files:
            path = legacy_files["checkpoints_format1"]
            model_type = "checkpoints"
            print(f"Migrating {model_type} from {os.path.basename(path)}...")
            with open(path, "r", encoding="utf-8") as f:
                hash_data = json.load(f)

            for key, hash_value in hash_data.items():
                try:
                    parts = key.split("|")
                    if len(parts) != 3:
                        total_skipped += 1
                        continue
                    file_path, mtime_str, _ = parts
                    file_path = os.path.normpath(file_path)

                    # 直接将此文件中的所有条目视为checkpoints
                    conn.execute(
                        """
                        INSERT INTO versions (hash, local_path, local_mtime, name, model_type) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(hash) DO UPDATE SET local_path = excluded.local_path, local_mtime = excluded.local_mtime
                    """,
                        (
                            hash_value.lower(),
                            file_path,
                            float(mtime_str),
                            os.path.basename(file_path),
                            model_type,
                        ),
                    )
                    total_migrated += 1
                except Exception:
                    total_skipped += 1
            os.rename(path, path + ".migrated")

        # 处理格式2: loras_hash_cache.json (LoRAs)
        if "loras_format2" in legacy_files:
            path = legacy_files["loras_format2"]
            model_type = "loras"
            print(f"Migrating {model_type} from {os.path.basename(path)}...")
            with open(path, "r", encoding="utf-8") as f:
                hash_data = json.load(f)

            for relative_path, data in hash_data.items():
                try:
                    full_path = folder_paths.get_full_path(model_type, relative_path)
                    if not full_path or not os.path.exists(full_path):
                        total_skipped += 1
                        continue

                    conn.execute(
                        """
                        INSERT INTO versions (hash, local_path, local_mtime, name, model_type) VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(hash) DO UPDATE SET local_path = excluded.local_path, local_mtime = excluded.local_mtime
                    """,
                        (
                            data["hash"].lower(),
                            os.path.normpath(full_path),
                            data["mtime"],
                            os.path.basename(full_path),
                            model_type,
                        ),
                    )
                    total_migrated += 1
                except Exception:
                    total_skipped += 1
            os.rename(path, path + ".migrated")

    return {
        "migrated": total_migrated,
        "skipped": total_skipped,
        "message": f"Migration complete! Migrated: {total_migrated}, Skipped: {total_skipped}. Old cache files have been renamed to '.migrated'. A restart of ComfyUI is recommended."
    }

def prepare_models_and_get_list(model_type: str, force_sync=True):
    sync_local_files_with_db(model_type, force=force_sync)

    # 直接使用 folder_paths 作为最可靠的列表来源
    return folder_paths.get_filename_list(model_type)

# =================================================================================
# 4. 数据获取与处理
# =================================================================================
def fetch_civitai_data_by_hash(model_hash, sort, limit, nsfw_level, filter_type=None):
    version_info = CivitaiAPIUtils.get_model_version_info_by_hash(model_hash)
    if not version_info or "id" not in version_info:
        raise ValueError(
            "Could not find model version ID on Civitai using provided hash."
        )

    version_id = version_info["id"]
    domain = _get_active_domain()
    filtered_results, page, API_PAGE_LIMIT = [], 1, 100

    with tqdm(total=limit, desc="Fetching Recipes") as pbar:
        while len(filtered_results) < limit:
            params = {
                "modelVersionId": version_id,
                "limit": API_PAGE_LIMIT,
                "sort": sort,
                "nsfw": nsfw_level,
                "page": page,
            }
            api_url = f"https://{domain}/api/v1/images"
            try:
                response = CivitaiAPIUtils._request_with_retry(api_url, params=params)
                items = response.json().get("items", [])
            except Exception as e:
                print(f"[Civitai Utils] Halting fetch due to persistent API error: {e}")
                break

            if not items:

                print("[Civitai Utils] Reached the end of available results from API.")
                if pbar.n < limit:
                    pbar.update(limit - pbar.n)
                break

            items_with_meta = [img for img in items if img.get("meta")]

            page_filtered = []
            if filter_type == "video":
                page_filtered = [
                    img for img in items_with_meta if img.get("type") == "video"
                ]
            elif filter_type == "image":
                page_filtered = [
                    img for img in items_with_meta if img.get("type") != "video"
                ]
            else:
                page_filtered = items_with_meta

            filtered_results.extend(page_filtered)
            pbar.update(min(len(filtered_results), limit) - pbar.n)
            page += 1
            if len(filtered_results) >= limit:
                break
            time.sleep(0.1)

    final_results = filtered_results[:limit]
    for img in final_results:
        db_manager.add_downloaded_image(
            url=img["url"],
            local_filename=None,
            version_id=version_id,
            meta=img.get("meta"),
        )
    return final_results


def extract_resources_from_meta(meta, filename_to_lora_hash_map, session_cache=None):
    if not isinstance(meta, dict):
        return {"ckpt_hash": None, "ckpt_name": "unknown", "loras": []}
    if session_cache is None:
        session_cache = {}

    ckpt_hash, ck_name = meta.get("Model hash"), meta.get("Model")
    loras, seen_hashes, seen_names = [], set(), set()

    def add_lora(lora_info):
        lora_hash, lora_name = lora_info.get("hash"), lora_info.get("name")
        if lora_hash and lora_hash in seen_hashes:
            return
        if not lora_hash and lora_name and lora_name in seen_names:
            return
        loras.append(lora_info)
        if lora_hash:
            seen_hashes.add(lora_hash)
        if lora_name:
            seen_names.add(lora_name)

    if isinstance(meta.get("civitaiResources"), list):

        for res in meta["civitaiResources"]:
            if not isinstance(res, dict) or not (
                version_id := res.get("modelVersionId")
            ):
                continue

            cached_resource = session_cache.get(str(version_id))
            if not cached_resource:
                continue

            version_info = cached_resource.get("info")
            res_hash = cached_resource.get("hash")

            res_type = res.get("type", "").lower()
            if version_info and not res_type:
                res_type = version_info.get("model", {}).get("type", "").lower()

            if res_type == "lora":

                add_lora(
                    {
                        "hash": res_hash,
                        "name": res.get("modelVersionName")
                        or (
                            version_info.get("model", {}).get("name")
                            if version_info
                            else None
                        ),
                        "weight": safe_float_conversion(res.get("weight")),
                        "modelVersionId": version_id,
                    }
                )
            elif res_type in ["checkpoint", "model"] and not ckpt_hash:
                ckpt_hash = res_hash
                if res.get("modelVersionName") and not ck_name:
                    ck_name = res["modelVersionName"]

    if isinstance(meta.get("resources"), list):

        for res in meta["resources"]:
            if isinstance(res, dict) and res.get("type", "").lower() == "lora":
                lora_name, lora_hash = res.get("name"), res.get("hash")
                if not lora_hash and lora_name:
                    lora_hash = filename_to_lora_hash_map.get(
                        lora_name
                    ) or filename_to_lora_hash_map.get(f"{lora_name}.safetensors")
                add_lora(
                    {
                        "hash": lora_hash,
                        "name": lora_name,
                        "weight": safe_float_conversion(res.get("weight")),
                    }
                )
            elif (
                isinstance(res, dict)
                and res.get("type", "").lower() == "model"
                and not ckpt_hash
            ):
                ckpt_hash, ck_name = res.get("hash"), res.get("name")

    if isinstance(meta.get("hashes"), dict):

        if isinstance(meta["hashes"].get("lora"), dict):
            for hash_val, weight in meta["hashes"]["lora"].items():
                add_lora(
                    {
                        "hash": hash_val,
                        "name": None,
                        "weight": safe_float_conversion(weight),
                    }
                )

    for i in range(1, 10):
        if meta.get(f"AddNet Module {i}") == "LoRA" and f"AddNet Model {i}" in meta:
            model_str = meta.get(f"AddNet Model {i}", "")
            match = re.search(r"\((\w+)\)", model_str)
            if match:
                add_lora(
                    {
                        "hash": match.group(1),
                        "name": model_str.split("(")[0].strip(),
                        "weight": safe_float_conversion(
                            meta.get(f"AddNet Weight A {i}")
                        ),
                    }
                )

    return {"ckpt_hash": ckpt_hash, "ckpt_name": ck_name, "loras": loras}


# =================================================================================
# 5. 格式化与辅助函数 (Formatting & Helper Functions)
# =================================================================================
def get_metadata(filepath, model_type):
    filepath = folder_paths.get_full_path(model_type, filepath)
    if not filepath:
        return None
    try:
        with open(filepath, "rb") as file:
            header_size = int.from_bytes(file.read(8), "little", signed=False)
            if header_size <= 0:
                return None
            header = file.read(header_size)
            return json_lib.loads(header).get("__metadata__")
    except Exception as e:
        print(
            f"[Civitai Utils] Error reading metadata from {os.path.basename(filepath)}: {e}"
        )
        return None


def sort_tags_by_frequency(meta_tags):
    if not meta_tags or "ss_tag_frequency" not in meta_tags:
        return []
    try:
        tag_freq_json = json_lib.loads(meta_tags["ss_tag_frequency"])
        tag_counts = Counter()
        for _, dataset in tag_freq_json.items():
            for tag, count in dataset.items():
                tag_counts[str(tag).strip()] += count
        return [tag for tag, _ in tag_counts.most_common()]
    except Exception as e:
        print(f"[Civitai Utils] Error parsing tag frequency: {e}")
        return []


def safe_float_conversion(value, default=1.0):
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_civitai_triggers(file_name, file_hash, force_refresh):
    if force_refresh == "no":
        version = db_manager.get_version_by_hash(file_hash)
        if version and version["trained_words"]:
            try:
                return json_lib.loads(version["trained_words"])
            except Exception:
                pass

    print(f"[Civitai Utils] Requesting civitai triggers from API for: {file_name}")
    model_info = CivitaiAPIUtils.get_model_version_info_by_hash(
        file_hash, force_refresh=True
    )
    triggers = (
        model_info.get("trainedWords", [])
        if model_info and isinstance(model_info.get("trainedWords"), list)
        else []
    )
    return triggers


def format_tags_as_markdown(pos_items, neg_items, top_n):
    md_lines = ["## Prompt Tag Analysis\n"]
    if pos_items:
        md_lines.extend(
            ["### Positive Tags", "| Rank | Tag | Count |", "|:----:|:----|:-----:|"]
        )
        md_lines.extend(
            [
                f"| {i + 1} | `{tag}` | **{count}** |"
                for i, (tag, count) in enumerate(pos_items[:top_n])
            ]
        )
    else:
        md_lines.append("_No positive tags found._")

    md_lines.append("\n")
    if neg_items:
        md_lines.extend(
            ["### Negative Tags", "| Rank | Tag | Count |", "|:----:|:----|:-----:|"]
        )
        md_lines.extend(
            [
                f"| {i + 1} | `{tag}` | **{count}** |"
                for i, (tag, count) in enumerate(neg_items[:top_n])
            ]
        )
    else:
        md_lines.append("_No negative tags found._")
    return "\n".join(md_lines)


def format_parameters_as_markdown(param_counts, total_images, summary_top_n=5):
    if total_images == 0:
        return "No parameter data found."

    md_lines = ["### Generation Parameters Analysis\n"]
    param_map = {
        "sampler": "Sampler",
        "scheduler": "Scheduler",
        "cfgScale": "CFG Scale",
        "steps": "Steps",
        "Size": "Size",
        "Hires upscaler": "Hires Upscaler",
        "Denoising strength": "Hires Denoising Strength",
        "clipSkip": "Clip Skip",
        "VAE": "VAE",
    }

    for key, title in param_map.items():
        md_lines.append(f"#### {title}\n")
        stats = Counter(param_counts.get(key, {})).most_common(summary_top_n)
        if not stats:
            md_lines.append("_No data found._\n")
            continue
        md_lines.extend(
            ["| Rank | Value | Count (Usage) |", "|:----:|:------|:-------------:|"]
        )
        for i, (value, count) in enumerate(stats):
            percentage = (count / total_images) * 100
            md_lines.append(
                f"| {i + 1} | `{value}` | **{count}** ({percentage:.1f}%) |"
            )
        md_lines.append("\n")
    return "\n".join(md_lines)


def format_resources_as_markdown(assoc_stats, total_images, summary_top_n=5):
    domain = _get_active_domain()
    md_lines = ["### Associated Resources Analysis\n"]

    for res_type in ["lora", "model"]:
        stats_dict = assoc_stats.get(res_type, {})
        title = "LoRAs" if res_type == "lora" else "Checkpoints"
        md_lines.append(f"#### Top {summary_top_n} Associated {title}\n")

        if not stats_dict or total_images == 0:

            md_lines.append("_No data found_\n")
            continue

        sorted_resources = sorted(
            stats_dict.values(), key=lambda item: item["count"], reverse=True
        )

        if res_type == "lora":

            md_lines.extend(
                [
                    "| Rank | LoRA Name | Usage | Avg. Weight | Mode Weight |",
                    "|:----:|:----------|:-----:|:-----------:|:-----------:|",
                ]
            )
            for i, data in enumerate(sorted_resources[:summary_top_n]):
                actual_name, model_id = data.get("name", "Unknown"), data.get("modelId")
                display_name = (
                    f"[{actual_name}](https://{domain}/models/{model_id})"
                    if model_id
                    else f"`{actual_name}`"
                )
                percentage = (data["count"] / total_images) * 100
                weights = data.get("weights", [])
                avg_weight = statistics.mean(weights) if weights else 0
                common_weight = statistics.mode(weights) if weights else 0
                md_lines.append(
                    f"| {i + 1} | {display_name} | **{percentage:.1f}%** | `{avg_weight:.2f}` | `{common_weight:.2f}` |"
                )
        else:
            md_lines.extend(
                [
                    "| Rank | Checkpoint Name | Usage |",
                    "|:----:|:----------------|:-----:|",
                ]
            )
            for i, data in enumerate(sorted_resources[:summary_top_n]):
                actual_name, model_id = data.get("name", "Unknown"), data.get("modelId")
                display_name = (
                    f"[{actual_name}](https://{domain}/models/{model_id})"
                    if model_id
                    else f"`{actual_name}`"
                )
                percentage = (data["count"] / total_images) * 100
                md_lines.append(f"| {i + 1} | {display_name} | **{percentage:.1f}%** |")
        md_lines.append("\n")
    return "\n".join(md_lines)


def format_info_as_markdown(meta, recipe_loras, lora_hash_map):
    if not meta:
        return "No metadata available."

    def create_table(data_dict):
        filtered_data = {
            k: v for k, v in data_dict.items() if v is not None and str(v).strip()
        }
        if not filtered_data:
            return ""
        lines = ["| Parameter | Value |", "|:---|:---|"]
        lines.extend(
            [f"| **{key}** | `{value}` |" for key, value in filtered_data.items()]
        )
        return "\n".join(lines)

    md_parts = []
    model_name, model_hash = meta.get("Model"), meta.get("Model hash")
    model_params = {
        "Model": model_name,
        "Model Hash": model_hash,
        "VAE": meta.get("VAE"),
        "Clip Skip": meta.get("Clip skip") or meta.get("clipSkip"),
    }
    md_parts.append("### Models & VAE\n" + create_table(model_params))

    core_params = {
        "Seed": meta.get("seed"),
        "Steps": meta.get("steps"),
        "CFG Scale": meta.get("cfgScale"),
        "Sampler": meta.get("sampler"),
        "Scheduler": meta.get("scheduler"),
        "Size": meta.get("Size"),
    }
    md_parts.append("\n### Core Parameters\n" + create_table(core_params))

    hires_params = {
        "Upscaler": meta.get("Hires upscaler"),
        "Upscale By": meta.get("Hires upscale"),
        "Hires Steps": meta.get("Hires steps"),
        "Denoising": meta.get("Denoising strength"),
    }
    if any(hires_params.values()):
        md_parts.append("\n### Hires. Fix\n" + create_table(hires_params))

    md_parts.append("\n### Local LoRA Diagnosis\n")
    if not recipe_loras:
        md_parts.append("_No LoRAs Used in Recipe_")
    else:
        for lora in recipe_loras:
            lora_hash, strength_val = (
                lora.get("hash"),
                safe_float_conversion(lora.get("weight", 1.0)),
            )
            filename = lora_hash_map.get(lora_hash.lower()) if lora_hash else None
            if filename:
                md_parts.append(
                    f"- ✅ **[FOUND]** `{filename}` (Strength: **{strength_val:.2f}**)"
                )
            else:
                civitai_info = (
                    CivitaiAPIUtils.get_civitai_info_from_hash(lora_hash)
                    if lora_hash
                    else None
                )
                if civitai_info:
                    md_parts.append(
                        f"- ❌ **[MISSING]** [{civitai_info['name']}]({civitai_info['url']}) (Strength: **{strength_val:.2f}**)"
                    )
                else:
                    name_to_show = lora.get("name") or "Unknown LoRA"
                    details = (
                        f"Hash: `{lora_hash}`" if lora_hash else "*(Hash not found)*"
                    )
                    md_parts.append(
                        f"- ❓ **[UNKNOWN]** `{name_to_show}` (Strength: **{strength_val:.2f}**) - {details}"
                    )

    positive_prompt, negative_prompt = (
        meta.get("prompt", ""),
        meta.get("negativePrompt", ""),
    )
    md_parts.append("\n\n### Prompts")
    if positive_prompt:
        md_parts.append(
            "<details><summary>📦 Positive Prompt</summary>\n\n```\n"
            + positive_prompt
            + "\n```\n</details>"
        )
    if negative_prompt:
        md_parts.append("<details><summary>📦 Negative Prompt</summary>\n\n```\n" + negative_prompt + "\n```\n</details>")

    try:

        full_json_string = json_lib.dumps(meta, indent=2, ensure_ascii=False)
        full_json_string = full_json_string.decode("utf-8") if isinstance(full_json_string, bytes) else full_json_string
    except Exception:
        full_json_string = json.dumps(meta, indent=2, ensure_ascii=False)
    md_parts.append("\n\n### Original JSON Data")
    md_parts.append("\n<details><summary>📄 Metadata</summary>\n\n```json\n" + full_json_string + "\n```\n</details>")

    return "\n".join(md_parts)