import requests
import hashlib
import json
import os
import re
from collections import Counter
import folder_paths
import time
import statistics


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(CACHE_DIR, exist_ok=True)

def get_metadata(filepath, type):
    filepath = folder_paths.get_full_path(type, filepath)
    if not filepath:
        return None
    try:
        with open(filepath, "rb") as file:
            header_size = int.from_bytes(file.read(8), "little", signed=False)
            if header_size <= 0:
                return None
            header = file.read(header_size)
            header_json = json.loads(header)
            return header_json.get("__metadata__")
    except Exception as e:
        print(f"[Civitai Stats] Error reading metadata: {e}")
        return None


def sort_tags_by_frequency(meta_tags):
    if not meta_tags or "ss_tag_frequency" not in meta_tags:
        return []
    try:
        tag_freq_json = json.loads(meta_tags["ss_tag_frequency"])
        tag_counts = Counter()
        for _, dataset in tag_freq_json.items():
            for tag, count in dataset.items():
                tag_counts[str(tag).strip()] += count
        sorted_tags = [tag for tag, _ in tag_counts.most_common()]
        return sorted_tags
    except Exception as e:
        print(f"[Civitai Stats] Error parsing tag frequency: {e}")
        return []


class CivitaiAPIUtils:
    CACHE_DIR = CACHE_DIR  # 将全局CACHE_DIR赋值给类属性

    HASH_CACHE_FILE = os.path.join(CACHE_DIR, "hash_cache.json")
    CIVITAI_TRIGGERS_CACHE = os.path.join(CACHE_DIR, "civitai_triggers_cache.json")
    ID_TO_HASH_CACHE = os.path.join(CACHE_DIR, "id_to_hash_cache.json")

    @staticmethod
    def calculate_sha256(file_path):
        print(
            f"[Civitai Utils] Calculating SHA256 for: {os.path.basename(file_path)}..."
        )
        start_time = time.time()
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        digest = sha256_hash.hexdigest()
        duration = time.time() - start_time
        print(f"[Civitai Utils] SHA256 calculated in {duration:.2f} seconds.")
        return digest

    @classmethod
    def get_cached_sha256(cls, file_path):
        try:
            mtime, size = os.path.getmtime(file_path), os.path.getsize(file_path)
            cache_key = f"{file_path}|{mtime}|{size}"
            try:
                with open(cls.HASH_CACHE_FILE, "r", encoding="utf-8") as f:
                    hash_cache = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                hash_cache = {}
            if cache_key in hash_cache:
                print(
                    f"[Civitai Utils] Loaded hash from cache for: {os.path.basename(file_path)}"
                )
                return hash_cache[cache_key]
            file_hash = cls.calculate_sha256(file_path)
            hash_cache[cache_key] = file_hash
            with open(cls.HASH_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(hash_cache, f, indent=2)
            return file_hash
        except Exception as e:
            print(f"[Civitai Utils] Error handling hash cache: {e}")
            return cls.calculate_sha256(file_path)

    @staticmethod
    def get_model_version_info_by_hash(sha256_hash, timeout=10):
        url = f"https://civitai.com/api/v1/model-versions/by-hash/{sha256_hash}"
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[Civitai Utils] Failed to fetch model version info by hash: {e}")
            return None

    @classmethod
    def get_hash_from_model_version_id(cls, version_id, timeout=10):
        try:
            with open(cls.ID_TO_HASH_CACHE, "r", encoding="utf-8") as f:
                id_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            id_cache = {}
        if str(version_id) in id_cache:
            return id_cache[str(version_id)]
        url = f"https://civitai.com/api/v1/model-versions/{version_id}"
        try:
            print(f"[Civitai Utils] Fetching hash for version ID: {version_id}...")
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if (
                data
                and "files" in data
                and len(data["files"]) > 0
                and "hashes" in data["files"][0]
            ):
                file_hash = data["files"][0]["hashes"].get("SHA256")
                if file_hash:
                    id_cache[str(version_id)] = file_hash.lower()
                    with open(cls.ID_TO_HASH_CACHE, "w", encoding="utf-8") as f:
                        json.dump(id_cache, f, indent=2)
                    return file_hash.lower()
        except Exception as e:
            print(
                f"[Civitai Utils] Failed to fetch hash for version ID {version_id}: {e}"
            )
        return None

    # 补全: 恢复被遗漏的辅助函数
    @staticmethod
    def _parse_prompts(prompt_text: str):
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            return []
        pattern = re.compile(r"<[^>]+>|\[[^\]]+\]|\([^)]+\)|[^,]+")
        tags = pattern.findall(prompt_text)
        return [tag.strip() for tag in tags if tag.strip()]

    # 补全: 恢复被遗漏的辅助函数
    @staticmethod
    def _format_tags_with_counts(items, top_n):
        return "\n".join(
            [f'{i} : "{tag}" ({count})' for i, (tag, count) in enumerate(items[:top_n])]
        )

    # 补全: 恢复被遗漏的辅助函数 (导致您报错的函数)
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
            stats_dict = assoc_stats.get(res_type)
            title = "LoRAs" if res_type == "lora" else "Checkpoints"
            output += f"\n[Top {summary_top_n} Associated {title}]\n"
            if not stats_dict or total_images == 0:
                output += "(No data found)\n"
                continue
            sorted_resources = sorted(
                stats_dict.items(), key=lambda item: item[1]["count"], reverse=True
            )
            for i, (name, data) in enumerate(sorted_resources[:summary_top_n]):
                count, weights = data["count"], data.get("weights", [])
                model_id = data.get("modelId")
                display_name = (
                    f"[{name}](https://civitai.com/models/{model_id})"
                    if model_id
                    else name
                )
                percentage = (count / total_images) * 100
                output += f"{i + 1}. {display_name} (in {percentage:.1f}% of images)\n"
                if res_type == "lora":
                    avg_weight = statistics.mean(weights) if weights else 0
                    common_weight = (
                        statistics.mode(weights) if data.get("weights") else 0
                    )
                    output += f"   └─ Avg. Weight: {avg_weight:.2f}, Most Common: {common_weight:.2f}\n"
        return output


SELECTIONS_FILE = os.path.join(CACHE_DIR, "selections.json")


def load_selections():
    if not os.path.exists(SELECTIONS_FILE):
        return {}
    try:
        with open(SELECTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_selections(data):
    try:
        with open(SELECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[CivitaiRecipeFinder] Error saving selections: {e}")


def update_model_hash_cache(model_type: str):
    if model_type not in ["loras", "checkpoints"]:
        return {}, {}
    cache_file_path = os.path.join(CACHE_DIR, f"{model_type}_hash_cache.json")
    current_files = set(folder_paths.get_filename_list(model_type))
    try:
        with open(cache_file_path, "r") as f:
            old_cache = json.load(f)
    except:
        old_cache = {}
    new_cache = {}
    files_to_hash = []
    for model_file in current_files:
        filepath = folder_paths.get_full_path(model_type, model_file)
        if filepath and os.path.exists(filepath) and not os.path.isdir(filepath):
            try:
                mtime = os.path.getmtime(filepath)
                if model_file in old_cache and old_cache[model_file]["mtime"] == mtime:
                    new_cache[model_file] = old_cache[model_file]
                else:
                    files_to_hash.append((model_file, filepath, mtime))
            except Exception as e:
                print(
                    f"[Civitai Utils] Warning: Could not process file {model_file}: {e}"
                )
    if files_to_hash:
        print(
            f"[Civitai Utils] Found {len(files_to_hash)} new/modified {model_type} files. Updating hashes via shared cache..."
        )
        for model_file, filepath, mtime in files_to_hash:
            hash_value = CivitaiAPIUtils.get_cached_sha256(filepath)
            new_cache[model_file] = {"hash": hash_value, "mtime": mtime}
    with open(cache_file_path, "w") as f:
        json.dump(new_cache, f, indent=4)
    if files_to_hash:
        print(f"[Civitai Utils] {model_type} hash cache updated.")
    hash_to_filename = {v["hash"]: k for k, v in new_cache.items()}
    filename_to_hash = {k: v["hash"] for k, v in new_cache.items()}
    return hash_to_filename, filename_to_hash


def fetch_civitai_data_by_hash(model_hash, sort, limit, nsfw_level):
    print(f"[CivitaiRecipeFinder] Fetching data for hash: {model_hash[:12]}...")
    version_info = CivitaiAPIUtils.get_model_version_info_by_hash(model_hash)
    if not version_info or "id" not in version_info:
        raise ValueError(
            "Could not find model version ID on Civitai using provided hash."
        )
    version_id = version_info["id"]
    sort_map = {
        "Most Reactions": "Most Reactions",
        "Most Comments": "Most Comments",
        "Newest": "Newest",
    }
    api_url_images = f"https://civitai.com/api/v1/images?modelVersionId={version_id}&limit={limit}&sort={sort_map.get(sort, 'Most Reactions')}&nsfw={nsfw_level}"
    response = requests.get(api_url_images, timeout=15)
    response.raise_for_status()
    items = response.json().get("items", [])
    items_with_meta = [img for img in items if img.get("meta")]
    print(
        f"[CivitaiRecipeFinder] API returned {len(items)} images, {len(items_with_meta)} have metadata."
    )
    return items_with_meta


def get_civitai_info_from_hash(model_hash):
    try:
        data = CivitaiAPIUtils.get_model_version_info_by_hash(model_hash)
        if data:
            model_id = data.get("modelId")
            model_name = data.get("model", {}).get("name", "Unknown Name")
            model_url = f"https://civitai.com/models/{model_id}"
            return {"name": model_name, "url": model_url}
    except Exception as e:
        print(
            f"[CivitaiRecipeFinder] Could not fetch info for hash {model_hash[:12]}: {e}"
        )
    return None


def safe_float_conversion(value, default=1.0):
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def extract_resources_from_meta(meta, filename_to_lora_hash_map):
    if not isinstance(meta, dict):
        return {"ckpt_hash": None, "ckpt_name": "unknown", "loras": {}}
    loras, ckpt_hash, ckpt_name = {}, meta.get("Model hash"), meta.get("Model")
    if "hashes" in meta and isinstance(meta["hashes"], dict):
        if "lora" in meta["hashes"] and isinstance(meta["hashes"]["lora"], dict):
            for hash_val, weight in meta["hashes"]["lora"].items():
                loras[hash_val] = loras.get(hash_val, safe_float_conversion(weight))
        for key, hash_val in meta["hashes"].items():
            if key.startswith("lora:"):
                loras[hash_val] = loras.get(hash_val, 1.0)
    if "resources" in meta and isinstance(meta["resources"], list):
        for res in meta["resources"]:
            if isinstance(res, dict):
                res_type, res_hash, res_name = (
                    res.get("type", "").lower(),
                    res.get("hash"),
                    res.get("name"),
                )
                if res_type == "lora":
                    weight = safe_float_conversion(res.get("weight"))
                    if res_hash:
                        loras[res_hash] = loras.get(res_hash, weight)
                    elif res_name:
                        matched_hash = filename_to_lora_hash_map.get(
                            res_name
                        ) or filename_to_lora_hash_map.get(res_name + ".safetensors")
                        if matched_hash:
                            loras[matched_hash] = loras.get(matched_hash, weight)
                if res_type == "model" and res_hash and not ckpt_hash:
                    ckpt_hash = res_hash
                    if "name" in res and not ckpt_name:
                        ckpt_name = res["name"]
    if "civitaiResources" in meta and isinstance(meta["civitaiResources"], list):
        for res in meta["civitaiResources"]:
            if isinstance(res, dict):
                res_type, version_id = (
                    res.get("type", "").lower(),
                    res.get("modelVersionId"),
                )
                if not version_id:
                    continue
                res_hash = CivitaiAPIUtils.get_hash_from_model_version_id(version_id)
                if not res_hash:
                    continue
                weight = safe_float_conversion(res.get("weight"))
                if res_type == "lora":
                    loras[res_hash] = loras.get(res_hash, weight)
                if res_type == "checkpoint" and not ckpt_hash:
                    ckpt_hash = res_hash
                    if "modelVersionName" in res and not ckpt_name:
                        ckpt_name = res["modelVersionName"]
    for i in range(1, 9):
        module_key, model_key, weight_key = (
            f"AddNet Module {i}",
            f"AddNet Model {i}",
            f"AddNet Weight A {i}",
        )
        if meta.get(module_key) == "LoRA" and model_key in meta:
            model_str = meta.get(model_key, "")
            match = re.search(r"\((\w+)\)", model_str)
            if match:
                hash_val, weight = (
                    match.group(1),
                    safe_float_conversion(meta.get(weight_key)),
                )
                loras[hash_val] = loras.get(hash_val, weight)
    return {"ckpt_hash": ckpt_hash, "ckpt_name": ckpt_name, "loras": loras}


def get_civitai_triggers(file_name, file_hash, force_refresh):
    try:
        with open(CivitaiAPIUtils.CIVITAI_TRIGGERS_CACHE, "r", encoding="utf-8") as f:
            trigger_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        trigger_cache = {}
    if force_refresh == "no" and file_name in trigger_cache:
        return trigger_cache[file_name]
    print(f"[Civitai Utils] Requesting civitai triggers from API for: {file_name}")
    model_info = CivitaiAPIUtils.get_model_version_info_by_hash(file_hash)
    triggers = (
        model_info.get("trainedWords", [])
        if model_info and isinstance(model_info.get("trainedWords"), list)
        else []
    )
    trigger_cache[file_name] = triggers
    try:
        with open(CivitaiAPIUtils.CIVITAI_TRIGGERS_CACHE, "w", encoding="utf-8") as f:
            json.dump(trigger_cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Civitai Utils] Failed to save civitai triggers cache: {e}")
    return triggers