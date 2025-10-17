import sqlite3
import threading
import urllib

import requests
import hashlib
import json
import os
import re
from collections import Counter
import folder_paths
import time
import statistics

from safetensors import safe_open
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from . import api

try:
    import orjson as json_lib

    print("[Civitai Toolkit] orjson library found, using for faster JSON operations.")
except ImportError:
    import json as json_lib

    print("[Civitai Toolkit] orjson not found, falling back to standard json library.")

HASH_CACHE_REFRESH_INTERVAL = 3600
SINGLE_FILE_HASH_TIMEOUT = 90  # 为单个文件哈希设置90秒的超时
SUPPORTED_MODEL_TYPES = { "checkpoints": "checkpoints", "loras": "Lora", "vae": "VAE", "embeddings": "embeddings", "diffusion_models":"diffusion_models", "text_encoders":"text_encoders","hypernetworks": "hypernetworks" }


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
        print(f"[Civitai Toolkit] Database initialized at: {self.db_path}")

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS models (model_id INTEGER PRIMARY KEY, name TEXT NOT NULL, type TEXT)"
            )
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                hash TEXT PRIMARY KEY, version_id INTEGER UNIQUE, model_id INTEGER, model_type TEXT, name TEXT,
                local_path TEXT UNIQUE, local_mtime REAL, trained_words TEXT, api_response TEXT, last_api_check INTEGER,
                FOREIGN KEY (model_id) REFERENCES models (model_id)
            )""")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_versions_model_type ON versions (model_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_versions_version_id ON versions (version_id)"
            )
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
        print("[Civitai Toolkit] Analysis cache cleared.")

    def clear_api_responses(self):
        with self.get_connection() as conn:
            conn.execute("UPDATE versions SET api_response = NULL, last_api_check = 0")
        print("[Civitai Toolkit] All API response caches cleared.")

    def clear_all_triggers(self):
        with self.get_connection() as conn:
            conn.execute("UPDATE versions SET trained_words = NULL")
        print("[Civitai Toolkit] All trigger word caches cleared.")

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

    def add_or_update_version_from_api(self, data, original_hash=None):
        """
        从API数据更新数据库，并精确处理多文件版本。
        """
        model_id = data.get("modelId") or data.get("model", {}).get("id")
        version_id = data.get("id")

        if not version_id or not model_id:
            print(f"[DB Manager] Error: Missing version_id({version_id}) or model_id({model_id}). Aborting.")
            return

        files = data.get("files", [])
        if not files:
            return

        target_file_info = None
        if original_hash:
            for f in files:
                if f.get("hashes", {}).get("SHA256", "").lower() == original_hash.lower():
                    target_file_info = f
                    break

        # 如果找不到匹配的哈希（例如API重定向到其他版本），则默认使用主文件
        if not target_file_info:
            target_file_info = next((f for f in files if f.get("primary")), files[0])

        file_hash = target_file_info.get("hashes", {}).get("SHA256")
        if not file_hash:
            return

        file_hash = file_hash.lower()

        def robust_dumps(data_obj):
            try:
                return json_lib.dumps(data_obj, ensure_ascii=False)
            except TypeError:
                return json_lib.dumps(data_obj)

        api_response_str = robust_dumps(data)
        trained_words_str = robust_dumps(data.get("trainedWords", []))

        with self.get_connection() as conn:
            # 在写入前，删除任何使用相同 version_id 但 hash 不同的旧记录，避免 UNIQUE 冲突
            conn.execute(
                "DELETE FROM versions WHERE version_id = ? AND hash != ?",
                (version_id, file_hash),
            )

            # 使用更可靠的model数据源
            model_data = data.get("model", {})
            conn.execute(
                """
                INSERT INTO models (model_id, name, type) VALUES (?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET name = excluded.name, type = excluded.type
                """,
                (model_id, model_data.get("name"), model_data.get("type")),
            )

            conn.execute(
                """
                INSERT INTO versions (hash, version_id, model_id, name, trained_words, api_response, last_api_check) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET 
                    version_id = excluded.version_id, 
                    model_id = excluded.model_id, 
                    name = excluded.name,
                    trained_words = excluded.trained_words, 
                    api_response = excluded.api_response, 
                    last_api_check = excluded.last_api_check
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
            meta_str = (
                json_lib.dumps(meta).decode("utf-8")
                if meta and isinstance(json_lib.dumps(meta), bytes)
                else json_lib.dumps(meta)
            )
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

    def mark_hash_as_not_found(self, file_hash):
        """为未在Civitai上找到的哈希存入一个空标记，避免重复查询。"""
        with self.get_connection() as conn:
            # 存入一个空的JSON对象作为标记
            empty_response = json_lib.dumps({})
            if isinstance(empty_response, bytes):
                empty_response = empty_response.decode("utf-8")

            conn.execute(
                "UPDATE versions SET api_response = ?, last_api_check = ? WHERE hash = ?",
                (empty_response, int(time.time()), file_hash.lower()),
            )

    def get_version_by_path(self, local_path):
        """通过绝对路径从数据库获取版本信息"""
        if not local_path:
            return None
        # 规范化路径以确保跨平台匹配
        norm_path = os.path.normpath(local_path)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT v.*, m.name AS model_name, v.name as version_name
                FROM versions v
                LEFT JOIN models m ON v.model_id = m.model_id
                WHERE v.local_path = ?
            """,
                (norm_path,),
            )
            return cursor.fetchone()


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
        # 伪装成一个普通的 Windows Chrome 浏览器
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }

        # 从数据库读取 API Key
        api_key = db_manager.get_setting("civitai_api_key")
        if api_key and isinstance(api_key, str):
            headers['Authorization'] = f'Bearer {api_key}'

        for i in range(retries + 1):
            try:
                if params:
                    response = requests.get(
                        url, params=params, timeout=timeout, headers=headers
                    )
                else:
                    response = requests.get(url, timeout=timeout, headers=headers)

                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    print(f"[Civitai Toolkit] API rate limit hit. Waiting for {delay} seconds before retrying...")
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise e
            except requests.exceptions.RequestException as e:
                print(f"[Civitai Toolkit] Network error: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
        raise Exception(f"Failed to fetch data from {url} after {retries} retries.")

    @staticmethod
    def calculate_sha256(file_path):
        print(f"[Civitai Toolkit] Calculating SHA256 for: {os.path.basename(file_path)}...")
        sha256_hash = hashlib.sha256()
        block_size = 1 << 20  # 1MB chunk size
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(block_size):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"[Civitai Toolkit] Error calculating hash for {file_path}: {e}")
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
            print(f"[Civitai Toolkit] API Error (ID {version_id}): {e}")
        return None

    @classmethod
    def get_model_info_by_id(cls, model_id, domain):
        """根据模型ID获取最详细的模型主页信息"""
        if not model_id:
            return None
        url = f"https://{domain}/api/v1/models/{model_id}"
        print(
            f"[Civitai Toolkit] Step 2 Fetch: Getting full model details for ID: {model_id}"
        )
        try:
            resp = cls._request_with_retry(url)
            return resp.json()
        except Exception as e:
            print(f"[Civitai Toolkit] API Error fetching model by ID {model_id}: {e}")
            return None

    @classmethod
    def get_model_version_info_by_hash(cls, sha256_hash, force_refresh=False, more_info=False):
        """
        根据模型文件的 SHA256 哈希值获取对应的模型版本信息，并尝试与完整模型信息进行智能合并。

        此方法首先尝试从缓存中获取数据，如果缓存未命中或强制刷新，则通过 Civitai API 获取模型版本信息，
        并进一步获取完整的模型信息进行合并，保留版本描述和模型主页描述。

        Parameters:
            sha256_hash (str): 模型文件的 SHA256 哈希值，用于唯一标识模型版本。
            force_refresh (bool): 是否跳过缓存直接请求 API，默认为 False。
            more_info (bool): 是否获取并合并完整模型信息，默认为 False。

        Returns:
            dict or None: 包含模型版本信息的字典，若未找到或出错则返回 None。
        """
        if not sha256_hash:
            return None
        sha256_hash = sha256_hash.lower()

        # 尝试从数据库缓存中获取版本信息
        if not force_refresh:
            version_entry = db_manager.get_version_by_hash(sha256_hash)
            if version_entry and version_entry["api_response"] is not None:
                try:
                    cached_data = json_lib.loads(version_entry["api_response"])
                    if cached_data == {}:
                        return None
                    print(
                        f"[Civitai Toolkit] Using cache for hash: {sha256_hash[:12]}"
                    )
                    return cached_data
                except Exception:
                    pass

        domain = _get_active_domain()
        try:
            # 第一步：通过哈希获取模型版本信息
            url_by_hash = (
                f"https://{domain}/api/v1/model-versions/by-hash/{sha256_hash}"
            )
            print(
                f"[Civitai Toolkit] Step 1 Fetch: Getting version info for hash: {sha256_hash[:12]}..."
            )
            resp_version = cls._request_with_retry(url_by_hash)
            version_data = resp_version.json()

            if not version_data or not version_data.get("id"):
                db_manager.mark_hash_as_not_found(sha256_hash)
                return None

            final_data = version_data
            model_id = version_data.get("modelId")
            merge_successful = False

            # 第二步：如果存在 modelId，尝试获取完整模型信息并合并
            if more_info:
                if model_id:
                    full_model_data = cls.get_model_info_by_id(model_id, domain)

                    if full_model_data:
                        print(f"[Civitai Toolkit] Step 2 Success: Merging data for model ID: {model_id}")

                        # 保留版本描述和模型主页描述
                        final_data["version_description"] = final_data.pop("description", "")
                        final_data["model_description"] = full_model_data.get("description", "")

                        # 替换为完整模型对象（包含 tags 等信息）
                        final_data["model"] = full_model_data

                        merge_successful = True

                # 如果合并成功或无 modelId，将结果缓存到数据库
                if merge_successful or not model_id:
                    db_manager.add_or_update_version_from_api(final_data, original_hash=sha256_hash)
                else:
                    print(f"[Civitai Toolkit] Merge failed for model ID {model_id}, API response will not be cached to allow retries.")

            return final_data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                print(f"[Civitai Toolkit] Hash not found on Civitai: {sha256_hash[:12]}.")
                db_manager.mark_hash_as_not_found(sha256_hash)
            else:
                print(f"[Civitai Toolkit] API HTTP Error (hash {sha256_hash[:12]}): {e}")
            return None
        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"[Civitai Toolkit] General Error on API call (hash {sha256_hash[:12]}): {e}")
            return None

    @classmethod
    def get_civitai_info_from_hash(cls, model_hash):
        try:
            data = CivitaiAPIUtils.get_model_version_info_by_hash(model_hash)
            if data and data.get("modelId"):
                domain = _get_active_domain()
                model_id, model_name = (
                    data.get("modelId"),
                    data.get("model", {}).get("name", "Unknown Name"),
                )
                return {
                    "name": model_name,
                    "url": f"https://{domain}/models/{model_id}",
                }
        except Exception as e:
            print(
                f"[CivitaiRecipeFinder] Could not fetch info for hash {model_hash[:12]}: {e}"
            )
        return None

    @staticmethod
    def _parse_prompts(prompt_text: str):
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            return []
        pattern = re.compile(r"\(.+?:\d+\.\d+\)|<[^>]+>|\[[^\]]+\]|\([^)]+\)|[^,]+")
        tags = pattern.findall(prompt_text)
        return [tag.strip() for tag in tags if tag.strip()]


def scan_all_supported_model_types(force=False):
    """遍历所有支持的模型类型并与数据库同步"""
    print("[Civitai Toolkit] Starting scan for all supported model types...")
    # The keys of SUPPORTED_MODEL_TYPES are what folder_paths uses (e.g., "checkpoints", "loras")
    for model_type in SUPPORTED_MODEL_TYPES.keys():
        try:
            if folder_paths.get_filename_list(model_type) is not None:
                sync_local_files_with_db(model_type, force=force)
            else:
                print(
                    f"[Civitai Toolkit] Skipping scan for '{model_type}', directory not found."
                )
        except Exception as e:
            print(
                f"[Civitai Toolkit] Skipping scan for '{model_type}', directory not configured or error occurred: {e}"
            )


def update_hash_in_db(file_info):
    """
    一个线程安全的函数，用于将单个文件的哈希结果写入数据库。
    它在自己的上下文中获取数据库连接。
    """
    if not file_info or not file_info.get("hash"):
        return

    try:
        with db_manager.get_connection() as conn:
            conn.execute(
                "UPDATE versions SET local_path = NULL, local_mtime = NULL WHERE local_path = ?",
                (file_info["path"],),
            )
            conn.execute(
                """
                INSERT INTO versions (hash, local_path, local_mtime, name, model_type) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET
                    local_path = excluded.local_path,
                    local_mtime = excluded.local_mtime,
                    model_type = excluded.model_type
                """,
                (file_info["hash"].lower(), file_info["path"], file_info["mtime"], os.path.basename(file_info["path"]), file_info["model_type"]),
            )
            conn.commit()
        return True
    except Exception as e:
        print(f"\n[Civitai Toolkit] Database write error for {os.path.basename(file_info['path'])}: {e}")
        return False


def sync_local_files_with_db(model_type: str, force=False):
    if model_type not in SUPPORTED_MODEL_TYPES:
        return {"new": 0, "modified": 0, "hashed": 0}

    # 当 force=False 时，使用时间间隔缓存避免不必要的重复扫描
    last_sync_key = f"last_sync_{model_type}"
    last_sync_time = db_manager.get_setting(last_sync_key, 0)
    if not force and time.time() - last_sync_time < HASH_CACHE_REFRESH_INTERVAL:
        return {"skipped": True}

    print(f"[Civitai Toolkit] Performing smart sync for local {model_type}...")
    local_files_on_disk = folder_paths.get_filename_list(model_type)

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT local_path, local_mtime FROM versions WHERE model_type = ?", (model_type,))
        db_files = {
            os.path.normcase(os.path.normpath(row["local_path"])): row["local_mtime"]
            for row in cursor.fetchall() if row["local_path"]
        }

    files_to_hash = []
    for relative_path in local_files_on_disk:
        full_path = folder_paths.get_full_path(model_type, relative_path)
        if not full_path or not os.path.exists(full_path) or os.path.isdir(full_path):
            continue

        norm_full_path = os.path.normcase(os.path.normpath(full_path))
        try:
            mtime = os.path.getmtime(norm_full_path)
            # 关键逻辑：文件是全新的，或者修改时间不一致时，才需要哈希
            if norm_full_path not in db_files or db_files[norm_full_path] != mtime:
                files_to_hash.append({"path": full_path, "mtime": mtime})
        except Exception as e:
            print(f"[Civitai Toolkit] Warning: Could not process file {relative_path}: {e}")

    if not files_to_hash:
        db_manager.set_setting(last_sync_key, time.time())
        print(f"[Civitai Toolkit] Smart sync for {model_type} complete. No new or modified files found.")
        return {"found": 0, "hashed": 0}

    print(f"[Civitai Toolkit] Found {len(files_to_hash)} new/modified {model_type} files. Hashing now...")

    def hash_worker(file_info):
        return {**file_info, "hash": CivitaiAPIUtils.calculate_sha256(file_info["path"])}

    hashed_count = 0
    with ThreadPoolExecutor(max_workers=(os.cpu_count()/2 or 4)) as executor:
        # 创建所有哈希计算的future
        futures = {executor.submit(hash_worker, f): f for f in files_to_hash}

        for future in tqdm(as_completed(futures), total=len(files_to_hash), desc=f"Hashing {model_type}"):
            try:
                res = future.result(timeout=SINGLE_FILE_HASH_TIMEOUT)
                if res and res.get("hash"):
                    res['model_type'] = model_type
                    if update_hash_in_db(res):
                        hashed_count += 1
            except TimeoutError:
                failed_file_info = futures[future]
                print(f"\n[Civitai Toolkit] Hashing timed out for file: {os.path.basename(failed_file_info['path'])}. Skipping.")
            except Exception as e:
                failed_file_info = futures[future]
                print(f"\n[Civitai Toolkit] Error hashing file {os.path.basename(failed_file_info['path'])}: {e}. Skipping.")

    db_manager.set_setting(last_sync_key, time.time())
    print(f"[Civitai Toolkit] Smart sync for {model_type} complete. Hashed {hashed_count} files.")
    return {"found": len(files_to_hash), "hashed": hashed_count}


def get_local_model_maps(model_type: str, force_sync=False):
    sync_local_files_with_db(model_type, force=force_sync)

    # 1. 从数据库获取所有已知文件的绝对路径 -> 哈希映射
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT hash, local_path FROM versions WHERE hash IS NOT NULL AND local_path IS NOT NULL AND model_type = ?",
            (model_type,),
        )
        rows = cursor.fetchall()

    abs_path_to_hash = {
        os.path.normpath(row["local_path"]): row["hash"] for row in rows
    }

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


def get_model_filenames_from_db_cached_only(model_type: str):
    """
    一个绝对安全的函数，只从数据库缓存中读取模型列表，绝不触发扫描。
    专门用于UI加载，确保启动速度。
    """
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT local_path FROM versions WHERE model_type = ? AND local_path IS NOT NULL ORDER BY local_path ASC",
            (model_type,),
        )
        rows = cursor.fetchall()

    known_relative_paths = folder_paths.get_filename_list(model_type)
    if not known_relative_paths:
        return []

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
                    ON CONFLICT(hash) DO UPDATE SET 
                        local_path = excluded.local_path, 
                        local_mtime = excluded.local_mtime,
                        model_type = excluded.model_type
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
                    ON CONFLICT(hash) DO UPDATE SET 
                        local_path = excluded.local_path, 
                        local_mtime = excluded.local_mtime,
                        model_type = excluded.model_type
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
        "message": f"Migration complete! Migrated: {total_migrated}, Skipped: {total_skipped}. Old cache files have been renamed to '.migrated'. A restart of ComfyUI is recommended.",
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
                print(f"[Civitai Toolkit] Halting fetch due to persistent API error: {e}")
                break

            if not items:
                print("[Civitai Toolkit] Reached the end of available results from API.")
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
    loras, vaes, seen_hashes, seen_names = [], [], set(), set()

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

        is_new_hash_format = any(':' in k for k in meta['hashes'].keys())

        if is_new_hash_format:
            print("[Civitai Toolkit] Detected new hash format, applying special parsing logic.")
            for key, short_hash in meta['hashes'].items():
                key_lower = key.lower()

                if key_lower.startswith("lora:"):
                    # 从键名中提取文件名，并清理路径分隔符
                    lora_filename = key[5:].replace('\\', '/').split('/')[-1]
                    # 通过文件名反查完整的哈希值
                    full_hash = filename_to_lora_hash_map.get(lora_filename)

                    if not full_hash:
                        print(f"[Civitai Toolkit] Warning: LoRA '{lora_filename}' found in metadata, but not in local file map. Cannot get full hash.")

                    add_lora({
                        "hash": full_hash or short_hash, # 优先使用完整的哈希
                        "name": lora_filename,
                        "weight": 1.0, # 这种格式没有提供权重，默认为 1.0
                    })

                elif key_lower.startswith("model:"):
                    ckpt_hash = short_hash
                    ck_name = key[6:]  # 提取模型名
                elif key_lower == "model":
                    if not ckpt_hash:
                        ckpt_hash = short_hash
                elif "vae" in key_lower:
                    vaes.append({
                        "hash": short_hash,
                        "name": key,})

        # 保留原有的逻辑以兼容旧格式
        elif isinstance(meta["hashes"].get("lora"), dict):
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

    return {"ckpt_hash": ckpt_hash, "ckpt_name": ck_name, "loras": loras, "vaes": vaes}


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
            f"[Civitai Toolkit] Error reading metadata from {os.path.basename(filepath)}: {e}"
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
        print(f"[Civitai Toolkit] Error parsing tag frequency: {e}")
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

    print(f"[Civitai Toolkit] Requesting civitai triggers from API for: {file_name}")
    model_info = CivitaiAPIUtils.get_model_version_info_by_hash(
        file_hash, force_refresh=False
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

    for res_type in ["lora", "model", "vae"]:
        stats_dict = assoc_stats.get(res_type, {})
        title = "LoRAs"
        if res_type == "model":
            title = "Checkpoints"
        elif res_type == "vae":
            title = "VAEs"
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
                    f"| Rank | {title.rstrip('s')} Name | Usage |",
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


def format_info_as_markdown(meta, recipe_loras, lora_hash_map, missing_ckpt_hash=None):
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

    if (not model_name or not model_hash) and isinstance(meta.get("hashes"), dict):
        for key, hash_val in meta['hashes'].items():
            if key.lower().startswith("model:"):
                model_name = key[6:]
                model_hash = hash_val
                break
        if not model_hash:
            model_hash = meta['hashes'].get("model")


    vae_info = meta.get("VAE")
    if not vae_info and isinstance(meta.get("hashes"), dict):
        for key in meta['hashes']:
            if "vae" in key.lower():
                vae_info = f"{key} (hash: {meta['hashes'][key]})"
                break

    model_params = {
        "Model": model_name,
        "Model Hash": model_hash,
        "VAE": vae_info,
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


    md_parts.append("\n### Local Checkpoint Diagnosis\n")
    if missing_ckpt_hash:
        civitai_info = CivitaiAPIUtils.get_civitai_info_from_hash(missing_ckpt_hash)
        if civitai_info:
            md_parts.append(
                f"- ❌ **[MISSING]** [{civitai_info['name']}]({civitai_info['url']})"
            )
        else:
            md_parts.append(
                f"- ❓ **[UNKNOWN]** Checkpoint with hash `{missing_ckpt_hash}` used, but not found locally or on Civitai."
            )
    else:
        md_parts.append("✅ Recipe checkpoint found locally or not specified.")

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
        md_parts.append(
            "<details><summary>📦 Negative Prompt</summary>\n\n```\n"
            + negative_prompt
            + "\n```\n</details>"
        )

    try:
        full_json_string = json_lib.dumps(meta, indent=2, ensure_ascii=False)
    except TypeError:
        import json

        full_json_string = json.dumps(meta, indent=2, ensure_ascii=False)
    if isinstance(full_json_string, bytes):
        full_json_string = full_json_string.decode("utf-8")
    md_parts.append("\n\n### Original JSON Data")
    md_parts.append(
        "\n<details><summary>📄 Metadata</summary>\n\n```json\n"
        + full_json_string
        + "\n```\n</details>"
    )

    return "\n".join(md_parts)


def fetch_missing_model_info_from_civitai():
    """
    联网为数据库中缺少API信息的模型获取数据。
    这个函数会阻塞，直到所有后台的获取和写入任务都完成。
    """
    print("[Civitai Toolkit] Checking for models missing Civitai info...")

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        # 查找那些 api_response 字段为 NULL 的模型
        cursor.execute(
            "SELECT hash FROM versions WHERE hash IS NOT NULL AND api_response IS NULL"
        )
        hashes_to_fetch = [row["hash"] for row in cursor.fetchall()]

    if not hashes_to_fetch:
        print("[Civitai Toolkit] All models have Civitai info, nothing to fetch.")
        return

    print(f"[Civitai Toolkit] Found {len(hashes_to_fetch)} models to fetch info for...")

    def fetch_worker(model_hash):
        # 每个线程独立调用 get_model_version_info_by_hash。
        # 该函数内部会自己处理数据库的写入和提交操作。
        CivitaiAPIUtils.get_model_version_info_by_hash(model_hash,more_info= True)
        return model_hash  # 返回哈希以便记录错误

    with ThreadPoolExecutor(max_workers=5) as executor:
        # 创建所有 future 任务
        futures = {executor.submit(fetch_worker, h): h for h in hashes_to_fetch}

        # 使用 as_completed 迭代，每完成一个任务就更新一次进度条
        # 由于 fetch_worker 内部的函数会自行提交数据库，这里只需等待任务完成即可
        for future in tqdm(as_completed(futures), total=len(hashes_to_fetch), desc="Fetching Civitai Info"):
            try:
                # .result() 会等待该任务完成，并在此处重新引发在线程中发生的任何异常
                future.result()
            except Exception as e:
                # 记录在获取单个模型信息时发生的错误，但不会中断整个流程
                failed_hash = futures[future]
                print(f"\n[Civitai Toolkit] Error fetching info for hash {failed_hash[:12]}: {e}")

    print("[Civitai Toolkit] Finished fetching and caching missing model info.")


def download_image_safely(job):
    final_path = job["path"]
    temp_path = final_path + ".tmp"
    if os.path.exists(temp_path):
        os.remove(temp_path)
    try:
        with requests.get(
            job["url"].split("?")[0] + "?width=450&format=png", stream=True, timeout=15
        ) as r:
            r.raise_for_status()
            expected_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0
            with open(temp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_size += len(chunk)
        if expected_size != 0 and downloaded_size != expected_size:
            raise IOError(
                f"Incomplete download. Expected {expected_size}, got {downloaded_size}"
            )
        os.rename(temp_path, final_path)
        return True
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False


def download_missing_covers():
    """
    为数据库中已有API信息但本地缺少封面的模型下载封面图。
    """
    print("[Civitai Toolkit] Checking for models missing local cover images...")

    # 1. 查询所有需要检查的模型
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.local_path, v.model_type, v.api_response
            FROM versions v
            WHERE v.local_path IS NOT NULL AND v.api_response IS NOT NULL AND v.api_response != '{}'
        """)
        all_versions = cursor.fetchall()

    download_jobs = []

    # 2. 遍历模型，检查封面是否存在
    for version in tqdm(all_versions, desc="Checking for Missing Covers"):
        try:
            name_no_ext = os.path.splitext(os.path.basename(version["local_path"]))[0]
            cover_filename = f"{name_no_ext}.png"
            cover_abs_path = os.path.join(os.path.dirname(version['local_path']), cover_filename)

            # 如果本地封面已存在，则跳过
            if os.path.exists(cover_abs_path):
                continue

            api_data = json_lib.loads(version['api_response'])
            images = api_data.get("images", [])
            if not images:
                continue

            # 选择一个合适的图片URL
            sfw_images = [i for i in images if i.get("nsfw") == "None" or i.get("nsfwLevel") == 1]
            target_image = (sfw_images[0] if sfw_images else images[0])
            img_url = target_image.get("url")

            if img_url:
                download_jobs.append({"url": img_url, "path": cover_abs_path})

        except Exception as e:
            print(f"Error preparing cover download for {version['local_path']}: {e}")

    if not download_jobs:
        print("[Civitai Toolkit] All existing models have local covers.")
        return

    print(f"[Civitai Toolkit] Found {len(download_jobs)} missing covers to download...")
    # 3. 多线程下载
    with ThreadPoolExecutor(max_workers=10) as executor:
        list(
            tqdm(
                executor.map(download_image_safely, download_jobs),
                total=len(download_jobs),
                desc="Downloading Missing Covers",
            )
        )
    print("[Civitai Toolkit] Finished downloading missing covers.")

def initiate_background_scan(loop):
    if db_manager.get_setting("initial_scan_complete", False):
        print("[Civitai Toolkit] Initial scan already completed. Skipping.")
        return
    scan_thread = threading.Thread(target=background_scan_worker, args=(loop,))
    scan_thread.daemon = True
    scan_thread.start()

def background_scan_worker(loop):
    """
    统一的后台工作流：按顺序执行哈希扫描、信息补全、封面下载。
    """
    print("[Civitai Toolkit] Starting one-time background workflow (Scan, Fetch, Download Covers)...")
    api.send_ws_message("scan_started", {"message": "The first scan in the background starts, and the local model will be indexed ..."})

    try:
        # 阶段一：哈希扫描
        print("\n--- Background Task: Phase 1/3 - Hashing Local Files ---")
        scan_all_supported_model_types(force=True)

        # 阶段二：Civitai 信息补全
        print("\n--- Background Task: Phase 2/3 - Fetching Civitai Info ---")
        fetch_missing_model_info_from_civitai()

        # 阶段三：远程封面下载
        print("\n--- Background Task: Phase 3/3 - Downloading Missing Covers ---")
        download_missing_covers()

        db_manager.set_setting("initial_scan_complete", True)

        print("\n[Civitai Toolkit] Background workflow finished successfully.")
        api.send_ws_message("scan_complete", {
            "success": True,
            "message": "所有本地模型已索引完毕！刷新浏览器即可在菜单和侧边栏中看到它们。"
        })

    except Exception as e:
        print(f"[Civitai Toolkit] Error during background workflow: {e}")
        api.send_ws_message("scan_complete", {
            "success": False,
            "message": f"后台任务发生错误: {e}"
        })
        import traceback
        traceback.print_exc()

def get_local_models_for_ui():
    """
    [功能完整版] 快速为UI提供数据，包含纯本地的封面查找逻辑。
    """
    print("[Civitai Toolkit] Reading model list from database for UI...")
    models_details = []

    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.hash, v.local_path, v.model_type, v.name as version_name, v.api_response, m.name as model_name
            FROM versions v LEFT JOIN models m ON v.model_id = m.model_id
            WHERE v.local_path IS NOT NULL
        """)
        all_versions = cursor.fetchall()

    all_model_paths = {}
    all_base_folders = {}
    for mt in SUPPORTED_MODEL_TYPES.keys():
        relative_paths = folder_paths.get_filename_list(mt)
        if relative_paths:
            all_model_paths[mt] = {
                os.path.normpath(folder_paths.get_full_path(mt, f)): f
                for f in relative_paths
            }
            all_base_folders[mt] = folder_paths.get_folder_paths(mt)

    for db_entry in all_versions:
        model_type = db_entry["model_type"]
        norm_path = os.path.normpath(db_entry["local_path"])
        relative_path = all_model_paths.get(model_type, {}).get(norm_path)
        if not relative_path:
            continue

        api_data = json_lib.loads(db_entry['api_response']) if db_entry['api_response'] else None

        # --- 快速的本地封面查找逻辑 ---
        local_cover_path, found_cover = None, False
        path_index = -1

        base_folders_for_type = all_base_folders.get(model_type, [])
        for i, folder in enumerate(base_folders_for_type):
             if os.path.commonpath([norm_path, os.path.normpath(folder)]) == os.path.normpath(folder):
                path_index = i
                break

        if path_index != -1:
            name_no_ext = os.path.splitext(relative_path)[0]
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                cover_rel_path = name_no_ext + ext
                full_cover_path = folder_paths.get_full_path(model_type, cover_rel_path)
                if full_cover_path and os.path.exists(full_cover_path):
                    encoded = urllib.parse.quote(cover_rel_path, safe="~()*!.'")
                    local_cover_path = f"/api/experiment/models/preview/{model_type}/{path_index}/{encoded}"
                    found_cover = True
                    break

        if not found_cover and norm_path.lower().endswith(".safetensors"):
            try:
                with safe_open(norm_path, framework="pt", device="cpu") as sf:
                    metadata = sf.metadata()
                    if metadata:
                        keys_to_check = [
                            "modelspec.thumbnail",
                            "thumbnail",
                            "image",
                            "icon",
                        ]
                        image_uri = None
                        for key in keys_to_check:
                            if key in metadata and isinstance(metadata[key], str):
                                image_uri = metadata[key]
                                break
                        if image_uri and image_uri.startswith("data:image"):
                            local_cover_path = image_uri
                            found_cover = True
            except Exception:
                pass

        local_metadata = None
        model_info_from_api = api_data.get("model", {}) if api_data else {}
        version_description = api_data.get("version_description") if api_data else None
        model_description = api_data.get("model_description") if api_data else None
        trained_words = api_data.get("trainedWords", []) if api_data else []
        base_model = api_data.get("baseModel") if api_data else None
        tags = model_info_from_api.get("tags", [])
        civitai_model_name = db_entry["model_name"]
        version_name = db_entry["version_name"]

        model_abs_path = norm_path
        if model_abs_path.lower().endswith(".safetensors"):
            try:
                with safe_open(model_abs_path, framework="pt", device="cpu") as sf:
                    metadata = sf.metadata()
                    if metadata:
                        local_metadata = metadata
            except Exception as e:
                print(f"    - [WARNING] Could not read safetensors metadata from {os.path.basename(model_abs_path)}. Error: {e}")

        if local_metadata:
            if not civitai_model_name:
                civitai_model_name = local_metadata.get("modelspec.title")
            if not version_name:
                version_name = local_metadata.get("modelspec.version")
            if not version_description and not model_description:
                local_desc = local_metadata.get("modelspec.description") or local_metadata.get("description")
                if local_desc:
                    model_description = local_desc
            if not trained_words:
                tags_str = local_metadata.get("ss_tag_frequency")
                if tags_str and isinstance(tags_str, str):
                    try:
                        tags_json = json_lib.loads(tags_str)
                        first_category = next(iter(tags_json))
                        trained_words = list(tags_json[first_category].keys())
                    except Exception:
                        trained_words = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
            if not base_model or base_model == "N/A":
                base_model = local_metadata.get("modelspec.architecture") or local_metadata.get("ss_base_model_version")

        full_model_info = {
            "hash": db_entry["hash"], "filename": relative_path, "model_type": model_type,
            "civitai_model_name": civitai_model_name or os.path.basename(norm_path),
            "version_name": version_name, "local_cover_path": local_cover_path,
            "version_description": version_description or "",
            "model_description": model_description or "No description found.",
            "trained_words": trained_words, "base_model": base_model or "N/A",
            "civitai_stats": api_data.get("stats", {}) if api_data else {},
            "tags": tags,
        }
        models_details.append(full_model_info)

    return models_details

def get_all_local_models_with_details(force_refresh=False):
    if force_refresh:
        print("[Civitai Toolkit] Manual refresh triggered: re-scanning, fetching info, and downloading covers...")
        # 手动刷新时，也按顺序执行完整的后台任务流，但这是同步的
        scan_all_supported_model_types(force=True)
        fetch_missing_model_info_from_civitai()
        download_missing_covers()

    # 无论是否刷新，最终都只从数据库快速读取数据给UI
    return get_local_models_for_ui()
