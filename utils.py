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
from concurrent.futures import ThreadPoolExecutor, as_completed

# 智能导入 orjson，如果失败则回退到标准 json 库
try:
    import orjson as json_lib

    print("[Civitai Utils] orjson library found, using for faster JSON operations.")
    IS_ORJSON = True
except ImportError:
    import json as json_lib

    print("[Civitai Utils] orjson not found, falling back to standard json library.")
    IS_ORJSON = False

# 哈希缓存的智能刷新间隔（秒）。默认设置为 3600 秒 = 1 小时
HASH_CACHE_REFRESH_INTERVAL = 3600

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(CACHE_DIR, exist_ok=True)

# 基于文件的配置管理
CONFIG_FILE = os.path.join(CACHE_DIR, "config.json")


def _load_config():
    """Loads configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Civitai Utils] Error loading config: {e}")
        return {}


def _save_config(data):
    """Saves configuration to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[Civitai Utils] Error saving config: {e}")


def _get_active_domain() -> str:
    """
    Reads the config and returns the currently used Civitai domain.
    (读取配置并返回当前应使用的 Civitai 域名)
    """
    config = _load_config()
    network_choice = config.get("network_choice", "com")  # Default to 'com'
    if network_choice == "work":
        return "civitai.work"
    return "civitai.com"



# --- Civitai名称到ComfyUI名称的翻译字典 ---
SAMPLER_SCHEDULER_MAP = {
    # Samplers
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
    # Schedulers
    "normal": "normal",
    "karras": "karras",
    "Karras": "karras",  # 兼容大小写
    "exponential": "exponential",
    "sgm_uniform": "sgm_uniform",
    "simple": "simple",
    "ddim_uniform": "ddim_uniform",
    "turbo": "turbo",
}

# --- JSON 处理器 ---
def save_json_to_file(filepath, data):
    """使用最优的库将字典保存为JSON文件。"""
    try:
        with open(
            filepath,
            "wb" if IS_ORJSON else "w",
            encoding=None if IS_ORJSON else "utf-8",
        ) as f:
            if IS_ORJSON:
                f.write(json_lib.dumps(data, option=json_lib.OPT_INDENT_2))
            else:
                json_lib.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Civitai Utils] Error saving JSON to {filepath}: {e}")


def load_json_from_file(filepath):
    """使用最优的库从JSON文件加载数据。"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(
            filepath,
            "rb" if IS_ORJSON else "r",
            encoding=None if IS_ORJSON else "utf-8",
        ) as f:
            if IS_ORJSON:
                return json_lib.loads(f.read())
            else:
                return json_lib.load(f)
    except Exception as e:
        print(f"[Civitai Utils] Error loading JSON from {filepath}: {e}")
        return None


# --- 元数据与标签处理 ---
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
            header_json = json_lib.loads(header)
            return header_json.get("__metadata__")
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


# --- Civitai API 核心工具类 ---
class CivitaiAPIUtils:
    CACHE_DIR = CACHE_DIR
    HASH_CACHE_FILE = os.path.join(CACHE_DIR, "hash_cache.json")
    CIVITAI_TRIGGERS_CACHE = os.path.join(CACHE_DIR, "civitai_triggers_cache.json")

    @staticmethod
    def calculate_sha256(file_path):
        print(
            f"[Civitai Utils] Calculating SHA256 for: {os.path.basename(file_path)}..."
        )
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @classmethod
    def get_cached_sha256(cls, file_path):
        try:
            mtime, size = os.path.getmtime(file_path), os.path.getsize(file_path)
            cache_key = f"{file_path}|{mtime}|{size}"
            hash_cache = load_json_from_file(cls.HASH_CACHE_FILE) or {}
            if cache_key in hash_cache:
                return hash_cache[cache_key]
            file_hash = cls.calculate_sha256(file_path)
            hash_cache[cache_key] = file_hash
            save_json_to_file(cls.HASH_CACHE_FILE, hash_cache)
            return file_hash
        except Exception as e:
            print(f"[Civitai Utils] Error handling hash cache: {e}")
            return cls.calculate_sha256(file_path)

    @classmethod
    def get_model_version_info_by_id(cls, version_id, session_cache, lock, timeout=10):
        with lock:
            if str(version_id) in session_cache["version_info"]:
                return session_cache["version_info"][str(version_id)]

        domain = _get_active_domain()
        url = f"https://{domain}/api/v1/model-versions/{version_id}"
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data:
                with lock:
                    session_cache["version_info"][str(version_id)] = data
                return data
        except Exception as e:
            print(
                f"[Civitai Utils] Failed to fetch info for version ID {version_id}: {e}"
            )
            with lock:
                session_cache["version_info"][str(version_id)] = {}
        return None

    @classmethod
    def get_model_version_info_by_hash(
        cls, sha256_hash, session_cache, lock, timeout=10
    ):
        with lock:
            for info in session_cache["version_info"].values():
                if info and any(
                    f.get("hashes", {}).get("SHA256", "").lower() == sha256_hash.lower()
                    for f in info.get("files", [])
                ):
                    return info

        domain = _get_active_domain()
        url = f"https://{domain}/api/v1/model-versions/by-hash/{sha256_hash}"
        print(
            f"[Civitai Utils] API Call: Fetching info for hash: {sha256_hash[:12]}..."
        )
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if data and data.get("id"):
                with lock:
                    session_cache["version_info"][str(data.get("id"))] = data
            return data
        except Exception as e:
            print(f"[Civitai Utils] Failed to fetch model version info by hash: {e}")
            return None

    @classmethod
    def get_hash_from_model_version_id(
        cls, version_id, session_cache, lock, timeout=10
    ):
        with lock:
            if str(version_id) in session_cache["id_to_hash"]:
                return session_cache["id_to_hash"][str(version_id)]
            if str(version_id) in session_cache["version_info"]:
                version_info = session_cache["version_info"][str(version_id)]
                if (
                    version_info
                    and "files" in version_info
                    and len(version_info["files"]) > 0
                ):
                    file_hash = (
                        version_info["files"][0]
                        .get("hashes", {})
                        .get("SHA256", "")
                        .lower()
                    )
                    if file_hash:
                        session_cache["id_to_hash"][str(version_id)] = file_hash
                        return file_hash

        version_info = cls.get_model_version_info_by_id(
            version_id, session_cache, lock, timeout
        )
        if version_info and "files" in version_info and len(version_info["files"]) > 0:
            file_hash = (
                version_info["files"][0].get("hashes", {}).get("SHA256", "").lower()
            )
            if file_hash:
                with lock:
                    session_cache["id_to_hash"][str(version_id)] = file_hash
                return file_hash

        with lock:
            session_cache["id_to_hash"][str(version_id)] = None
        return None

    @classmethod
    def get_civitai_info_from_hash(cls, model_hash, session_cache, lock):
        try:
            data = CivitaiAPIUtils.get_model_version_info_by_hash(
                model_hash, session_cache, lock
            )
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

    @staticmethod
    def _format_tags_with_counts(items, top_n):
        return "\n".join(
            [f'{i} : "{tag}" ({count})' for i, (tag, count) in enumerate(items[:top_n])]
        )

    @staticmethod
    def _format_parameter_stats(
        param_counts, total_images, summary_top_n=5, include_vae=True
    ):
        if total_images == 0:
            return "[No parameter data found]"
        output = "--- Top Generation Parameters ---\n"
        param_map = {
            "sampler": "[Sampler]",
            "cfgScale": "[CFG Scale]",
            "steps": "[Steps]",
            "Size": "[Size]",
            "Hires upscaler": "[Hires Upscaler]",
            "Denoising strength": "[Denoising Strength]",
            "clipSkip": "[Clip Skip]",
        }
        if include_vae:
            param_map["VAE"] = "[VAE]"
        for key, title in param_map.items():
            output += f"\n{title}\n"
            stats = Counter(param_counts.get(key, {})).most_common(summary_top_n)
            if not stats:
                output += " (No data)\n"
                continue
            for i, (value, count) in enumerate(stats):
                percentage = (count / total_images) * 100
                output += f"{i + 1}. {value} ({count} | {percentage:.1f}%)\n"
        return output

    @staticmethod
    def _format_associated_resources(assoc_stats, total_images, summary_top_n=5):
        output = "--- Associated Resources Analysis ---\n"
        for res_type in ["lora", "model"]:
            stats_dict = assoc_stats.get(res_type, {})
            title = "LoRAs" if res_type == "lora" else "Checkpoints"
            output += f"\n[Top {summary_top_n} Associated {title}]\n"
            if not stats_dict or total_images == 0:
                output += "(No data found)\n"
                continue
            sorted_resources = sorted(
                stats_dict.values(), key=lambda item: item["count"], reverse=True
            )
            for i, data in enumerate(sorted_resources[:summary_top_n]):
                actual_name, count = data.get("name", "Unknown"), data["count"]
                percentage = (count / total_images) * 100
                output += f"{i + 1}. {actual_name} (in {percentage:.1f}% of images)\n"
                if res_type == "lora":
                    weights = data.get("weights", [])
                    avg_weight = statistics.mean(weights) if weights else 0
                    common_weight = statistics.mode(weights) if weights else 0
                    output += f"   └─ Avg. Weight: {avg_weight:.2f}, Most Common: {common_weight:.2f}\n"
        return output


# --- 全局辅助函数 ---
SELECTIONS_FILE = os.path.join(CACHE_DIR, "selections.json")


def load_selections():
    return load_json_from_file(SELECTIONS_FILE) or {}


def save_selections(data):
    save_json_to_file(SELECTIONS_FILE, data)


def update_model_hash_cache(model_type: str):
    if model_type not in ["loras", "checkpoints"]:
        return {}, {}
    cache_file_path = os.path.join(CACHE_DIR, f"{model_type}_hash_cache.json")
    if os.path.exists(cache_file_path):
        cache_age = time.time() - os.path.getmtime(cache_file_path)
        if cache_age < HASH_CACHE_REFRESH_INTERVAL:
            cache_data = load_json_from_file(cache_file_path) or {}
            hash_to_filename = {
                v["hash"]: k for k, v in cache_data.items() if "hash" in v
            }
            filename_to_hash = {
                k: v["hash"] for k, v in cache_data.items() if "hash" in v
            }
            return hash_to_filename, filename_to_hash

    print(
        f"[Civitai Utils] Hash cache is stale or missing. Performing full scan for {model_type}..."
    )
    current_files = set(folder_paths.get_filename_list(model_type))
    old_cache = load_json_from_file(cache_file_path) or {}
    new_cache, files_to_hash = {}, []
    for model_file in current_files:
        filepath = folder_paths.get_full_path(model_type, model_file)
        if filepath and os.path.exists(filepath) and not os.path.isdir(filepath):
            try:
                mtime = os.path.getmtime(filepath)
                if (
                    model_file in old_cache
                    and old_cache[model_file].get("mtime") == mtime
                ):
                    new_cache[model_file] = old_cache[model_file]
                else:
                    files_to_hash.append((model_file, filepath, mtime))
            except Exception as e:
                print(
                    f"[Civitai Utils] Warning: Could not process file {model_file}: {e}"
                )

    if files_to_hash:
        print(
            f"[Civitai Utils] Found {len(files_to_hash)} new/modified {model_type} files. Hashing in parallel..."
        )

        def hash_worker(model_file, filepath, mtime):
            hash_value = CivitaiAPIUtils.get_cached_sha256(filepath)
            return model_file, hash_value, mtime

        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
            future_to_info = {
                executor.submit(hash_worker, mf, fp, mt): mf
                for mf, fp, mt in files_to_hash
            }
            for future in tqdm(
                as_completed(future_to_info),
                total=len(files_to_hash),
                desc=f"Hashing {model_type}",
            ):
                try:
                    model_file, hash_value, mtime = future.result()
                    if hash_value:
                        new_cache[model_file] = {"hash": hash_value, "mtime": mtime}
                except Exception as exc:
                    print(
                        f"[Civitai Utils] Hashing for {future_to_info[future]} generated an exception: {exc}"
                    )
    save_json_to_file(cache_file_path, new_cache)
    if files_to_hash:
        print(f"[Civitai Utils] {model_type.capitalize()} hash cache updated.")
    hash_to_filename = {v["hash"]: k for k, v in new_cache.items() if "hash" in v}
    filename_to_hash = {k: v["hash"] for k, v in new_cache.items() if "hash" in v}
    return hash_to_filename, filename_to_hash


def fetch_civitai_data_by_hash(model_hash, sort, limit, nsfw_level):
    print(f"[CivitaiRecipeFinder] Fetching data for hash: {model_hash[:12]}...")
    session_cache = {"version_info": {}, "id_to_hash": {}}
    lock = threading.Lock()
    version_info = CivitaiAPIUtils.get_model_version_info_by_hash(
        model_hash, session_cache, lock
    )
    if not version_info or "id" not in version_info:
        raise ValueError(
            "Could not find model version ID on Civitai using provided hash."
        )
    version_id = version_info["id"]
    domain = _get_active_domain()
    api_url_images = f"https://{domain}/api/v1/images?modelVersionId={version_id}&limit={limit}&sort={sort}&nsfw={nsfw_level}"
    response = requests.get(api_url_images, timeout=15)
    response.raise_for_status()
    items = response.json().get("items", [])
    items_with_meta = [img for img in items if img.get("meta")]
    print(
        f"[CivitaiRecipeFinder] API returned {len(items)} images, {len(items_with_meta)} have metadata."
    )
    return items_with_meta


def safe_float_conversion(value, default=1.0):
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def extract_resources_from_meta(meta, filename_to_lora_hash_map, session_cache, lock):
    if not isinstance(meta, dict):
        return {"ckpt_hash": None, "ckpt_name": "unknown", "loras": []}
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
            if not isinstance(res, dict):
                continue
            version_id = res.get("modelVersionId")
            if not version_id:
                continue
            res_type = res.get("type", "").lower()
            version_info = None
            if not res_type:
                version_info = CivitaiAPIUtils.get_model_version_info_by_id(
                    version_id, session_cache, lock
                )
                if version_info:
                    res_type = version_info.get("model", {}).get("type", "").lower()
            if res_type == "lora":
                if not version_info:
                    version_info = CivitaiAPIUtils.get_model_version_info_by_id(
                        version_id, session_cache, lock
                    )
                res_hash = None
                if (
                    version_info
                    and "files" in version_info
                    and len(version_info["files"]) > 0
                ):
                    res_hash = (
                        version_info["files"][0]
                        .get("hashes", {})
                        .get("SHA256", "")
                        .lower()
                    )
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
                ckpt_hash = CivitaiAPIUtils.get_hash_from_model_version_id(
                    version_id, session_cache, lock
                )
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
                        "modelId": res.get("modelId"),
                        "modelVersionId": res.get("modelVersionId"),
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
    for i in range(1, 9):
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


def get_civitai_triggers(file_name, file_hash, force_refresh, session_cache, lock):
    trigger_cache = load_json_from_file(CivitaiAPIUtils.CIVITAI_TRIGGERS_CACHE) or {}
    if force_refresh == "no" and file_name in trigger_cache:
        return trigger_cache[file_name]
    print(f"[Civitai Utils] Requesting civitai triggers from API for: {file_name}")
    model_info = CivitaiAPIUtils.get_model_version_info_by_hash(
        file_hash, session_cache, lock
    )
    triggers = (
        model_info.get("trainedWords", [])
        if model_info and isinstance(model_info.get("trainedWords"), list)
        else []
    )
    trigger_cache[file_name] = triggers
    save_json_to_file(CivitaiAPIUtils.CIVITAI_TRIGGERS_CACHE, trigger_cache)
    return triggers


# --- Markdown 格式化函数 ---
def format_tags_as_markdown(pos_items, neg_items, top_n):
    md_lines = ["## Prompt Tag Analysis\n"]
    if pos_items:
        md_lines.append("### Positive Tags\n")
        md_lines.append("| Rank | Tag | Count |")
        md_lines.append("|:----:|:----|:-----:|")
        for i, (tag, count) in enumerate(pos_items[:top_n]):
            md_lines.append(f"| {i + 1} | `{tag}` | **{count}** |")
    else:
        md_lines.append("_No positive tags found._")
    md_lines.append("\n")
    if neg_items:
        md_lines.append("### Negative Tags\n")
        md_lines.append("| Rank | Tag | Count |")
        md_lines.append("|:----:|:----|:-----:|")
        for i, (tag, count) in enumerate(neg_items[:top_n]):
            md_lines.append(f"| {i + 1} | `{tag}` | **{count}** |")
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
        "Denoising strength": "Denoising Strength",
        "clipSkip": "Clip Skip",
        "VAE": "VAE",
    }
    for key, title in param_map.items():
        md_lines.append(f"#### {title}\n")
        stats = Counter(param_counts.get(key, {})).most_common(summary_top_n)
        if not stats:
            md_lines.append("_No data found._\n")
            continue
        md_lines.append("| Rank | Value | Count (Usage) |")
        md_lines.append("|:----:|:------|:-------------:|")
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
            md_lines.append("| Rank | LoRA Name | Usage | Avg. Weight | Mode Weight |")
            md_lines.append("|:----:|:----------|:-----:|:-----------:|:-----------:|")
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
            md_lines.append("| Rank | Checkpoint Name | Usage |")
            md_lines.append("|:----:|:----------------|:-----:|")
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


def format_info_as_markdown(meta, recipe_loras, lora_hash_map, session_cache, lock):
    """
    生成Gallery节点专属的、统一的、包含所有信息的Markdown报告。
    """
    if not meta:
        return "No metadata available."

    def create_table(data_dict):
        filtered_data = {k: v for k, v in data_dict.items() if v is not None}
        if not filtered_data:
            return ""
        lines = ["| Parameter | Value |", "|:---|:---|"]
        for key, value in filtered_data.items():
            lines.append(f"| **{key}** | `{value}` |")
        return "\n".join(lines)

    md_parts = []

    # --- Section 1: 模型信息 (Models & VAE) ---
    model_name, model_hash = meta.get("Model"), meta.get("Model hash")
    if not model_name:
        resources = meta.get("resources", []) + meta.get("civitaiResources", [])
        for r in resources:
            if r and r.get("type") in ["model", "checkpoint"]:
                model_name = r.get("name") or r.get("modelVersionName")
                if r.get("hash"):
                    model_hash = r.get("hash")
                break

    model_params = {
        "Model": model_name,
        "Model Hash": model_hash,
        "VAE": meta.get("VAE"),
        "Clip Skip": meta.get("Clip skip") or meta.get("clipSkip"),
    }
    md_parts.append("### Models & VAE")
    md_parts.append(create_table(model_params))

    # --- Section 2: 核心参数 (Core Parameters) ---
    core_params = {
        "Seed": meta.get("seed"),
        "Steps": meta.get("steps"),
        "CFG Scale": meta.get("cfgScale"),
        "Sampler": meta.get("sampler"),
        "Scheduler": meta.get("scheduler"),
        "Size": meta.get("Size"),
    }
    md_parts.append("\n### Core Parameters")
    md_parts.append(create_table(core_params))

    # --- Section 3: 高清修复 (Hires. Fix) ---
    hires_params = {
        "Upscaler": meta.get("Hires upscaler"),
        "Upscale By": meta.get("Hires upscale"),
        "Hires Steps": meta.get("Hires steps"),
        "Denoising": meta.get("Denoising strength"),
    }
    if any(hires_params.values()):
        md_parts.append("\n### Hires. Fix")
        md_parts.append(create_table(hires_params))

    # --- Section 4: LoRA 本地诊断 (Local Diagnosis) ---
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
                civitai_info = None
                version_id = lora.get("modelVersionId")
                if version_id:
                    version_info = CivitaiAPIUtils.get_model_version_info_by_id(
                        version_id, session_cache, lock
                    )
                    if version_info and version_info.get("modelId"):
                        domain = _get_active_domain()
                        parent_model_id = version_info.get("modelId")
                        model_name = version_info.get("model", {}).get("name")
                        civitai_info = {
                            "name": model_name,
                            "url": f"https://{domain}/models/{parent_model_id}",
                        }
                if not civitai_info and lora_hash:
                    civitai_info = CivitaiAPIUtils.get_civitai_info_from_hash(
                        lora_hash, session_cache, lock
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

    # --- Section 5: 提示词 (Prompts) ---
    positive_prompt, negative_prompt = (
        meta.get("prompt", ""),
        meta.get("negativePrompt", ""),
    )
    md_parts.append("\n\n### Prompts")
    if positive_prompt: md_parts.append("<details><summary>📦 Positive Prompt</summary>\n\n```\n" + positive_prompt + "\n```\n</details>")
    if negative_prompt: md_parts.append("<details><summary>📦 Negative Prompt</summary>\n\n```\n" + negative_prompt + "\n```\n</details>")

    # --- Section 6: 完整JSON数据 (Full JSON Data) ---
    try:
        if IS_ORJSON:
            full_json_string = json_lib.dumps(meta, option=json_lib.OPT_INDENT_2).decode('utf-8')
        else:
            full_json_string = json_lib.dumps(meta, indent=2, ensure_ascii=False)
    except:
        full_json_string = json.dumps(meta, indent=2, ensure_ascii=False)
    md_parts.append("\n\n### Original JSON Data")
    md_parts.append("\n<details><summary>📄 Metadata</summary>\n\n```json\n" + full_json_string + "\n```\n</details>")

    return "\n".join(md_parts)