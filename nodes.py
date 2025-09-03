import requests
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import folder_paths
import time
from tqdm import tqdm
import statistics
import threading
from . import utils

# --- Lora Trigger Words ---
class LoraTriggerWords:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_name": (folder_paths.get_filename_list("loras"),),
                "force_refresh": (["no", "yes"], {"default": "no"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("metadata_triggers", "civitai_triggers", "triggers_md")
    FUNCTION = "execute"
    CATEGORY = "Civitai"

    def execute(self, lora_name, force_refresh):
        file_path = folder_paths.get_full_path("loras", lora_name)
        if not file_path:
            return ("", "", "No LoRA file found.")

        metadata_triggers_list = utils.sort_tags_by_frequency(
            utils.get_metadata(lora_name, "loras")
        )
        civitai_triggers_list = []
        try:
            session_cache = {"version_info": {}, "id_to_hash": {}}
            lock = threading.Lock()
            file_hash = utils.CivitaiAPIUtils.get_cached_sha256(file_path)
            civitai_triggers_list = utils.get_civitai_triggers(
                lora_name, file_hash, force_refresh, session_cache, lock
            )
        except Exception as e:
            print(f"[{self.__class__.__name__}] Failed to get civitai triggers: {e}")

        metadata_triggers_str = (
            ", \n".join(metadata_triggers_list)
            if metadata_triggers_list
            else "[No Data Found]"
        )
        civitai_triggers_str = (
            ", ".join(civitai_triggers_list)
            if civitai_triggers_list
            else "[No Data Found]"
        )

        def create_trigger_table(trigger_list, title):
            """一个辅助函数，用于从列表生成单列表格的Markdown字符串。"""
            if not trigger_list:
                return f"| {title} |\n|:---|\n| *[No Data Found]* |"
            lines = [f"| {title} |", "|:---|"]
            for tag in trigger_list:
                lines.append(f"| `{tag}` |")
            return "\n".join(lines)

        metadata_table = create_trigger_table(
            metadata_triggers_list, "Triggers from Metadata"
        )
        civitai_table = create_trigger_table(
            civitai_triggers_list, "Triggers from Civitai API"
        )
        triggers_md = f"{metadata_table}\n\n{civitai_table}"

        return (metadata_triggers_str, civitai_triggers_str, triggers_md)

# --- Data Fetcher Nodes ---
class BaseDataFetcher:
    FOLDER_KEY = None
    @classmethod
    def INPUT_TYPES(cls):
        return { "required": { "model_name": (folder_paths.get_filename_list(cls.FOLDER_KEY),), "max_pages": ("INT", {"default": 3, "min": 1, "max": 50}), "sort": (["Most Reactions", "Most Comments", "Newest"], {"default": "Most Reactions"}), "retries": ("INT", {"default": 2, "min": 0, "max": 5}), "timeout": ("INT", {"default": 10, "min": 1, "max": 60}), "force_refresh": (["no", "yes"], {"default": "no"}), } }
    RETURN_TYPES = ("CIVITAI_DATA", "STRING")
    RETURN_NAMES = ("civitai_data", "fetch_summary")
    FUNCTION = "execute"
    CATEGORY = "Civitai/Fetcher"

    def _fetch_page(self, url, params, timeout):
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def execute(self, model_name, max_pages, sort, retries, timeout, force_refresh):
        file_path = folder_paths.get_full_path(self.FOLDER_KEY, model_name)
        defaults = (None, "No data fetched.")
        if not file_path:
            return defaults

        try:
            file_hash = utils.CivitaiAPIUtils.get_cached_sha256(file_path)
        except Exception:
            return defaults

        cache_file = os.path.join(
            utils.CACHE_DIR, f"{file_hash}_{sort}_{max_pages}_raw_data.json"
        )

        if force_refresh == "no" and os.path.exists(cache_file):
            print(f"[{self.__class__.__name__}] Loading raw data from cache.")
            # 使用我们优化的 orjson 加载器
            raw_data = utils.load_json_from_file(cache_file)
            if raw_data:
                summary = f"Loaded {raw_data.get('total_images', 0)} images from cache."
                return (raw_data, summary)

        # --- 核心修正：为本次独立的API调用，创建临时的缓存和锁 ---
        session_cache = {"version_info": {}, "id_to_hash": {}}
        lock = threading.Lock()
        # --- 修正结束 ---

        # 将创建的缓存和锁，传递给API调用函数
        model_info = utils.CivitaiAPIUtils.get_model_version_info_by_hash(
            file_hash, session_cache, lock
        )

        if not model_info or not model_info.get("id"):
            return defaults

        model_version_id = model_info.get("id")
        all_metas = []

        def fetch_page_with_retries(page_num):
            url, params = (
                "https://civitai.com/api/v1/images",
                {
                    "modelVersionId": model_version_id,
                    "limit": 100,
                    "page": page_num,
                    "sort": sort,
                },
            )
            attempt = 0
            while attempt <= retries:
                try:
                    return self._fetch_page(url, params, timeout)
                except requests.exceptions.RequestException as e:
                    attempt += 1
                    print(
                        f"[{self.__class__.__name__}] Network error on page {page_num}, attempt {attempt}/{retries + 1}: {e}"
                    )
                    if attempt > retries:
                        print(
                            f"[{self.__class__.__name__}] All retries failed for page {page_num}."
                        )
                        return {"items": []}
                    time.sleep(0.5)
            return {"items": []}

        with ThreadPoolExecutor(max_workers=min(10, max_pages)) as executor:
            pages = range(1, max_pages + 1)
            futures = [executor.submit(fetch_page_with_retries, p) for p in pages]
            for future in as_completed(futures):
                try:
                    data = future.result()
                    for item in data.get("items", []):
                        if meta := item.get("meta"):
                            all_metas.append(meta)
                except Exception as e:
                    print(
                        f"[{self.__class__.__name__}] Error processing page result: {e}"
                    )

        raw_data = {
            "metas": all_metas,
            "total_images": len(all_metas),
            "model_name": os.path.splitext(model_name)[0],
        }

        # 使用我们优化的 orjson 保存器
        utils.save_json_to_file(cache_file, raw_data)

        summary = f"Fetched metadata from {len(all_metas)} images across {max_pages} pages."
        return (raw_data, summary)

class CivitaiDataFetcherCKPT(BaseDataFetcher): FOLDER_KEY = "checkpoints"
class CivitaiDataFetcherLORA(BaseDataFetcher): FOLDER_KEY = "loras"

# --- Analyzers ---
class PromptAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return { "required": { "civitai_data": ("CIVITAI_DATA",), "summary_top_n": ("INT", {"default": 10, "min": 1, "max": 100}), } }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt", "tag_stats_md")
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data, summary_top_n):
        if not civitai_data or not civitai_data.get("metas"):
            return ("", "", "No data.") # Add default for new output

        pos_tokens, neg_tokens = [], []
        for meta in civitai_data["metas"]:
            pos_tokens.extend(utils.CivitaiAPIUtils._parse_prompts(meta.get("prompt", "")))
            neg_tokens.extend(utils.CivitaiAPIUtils._parse_prompts(meta.get("negativePrompt", "")))

        pos_common = Counter(pos_tokens).most_common()
        neg_common = Counter(neg_tokens).most_common()

        # Keep old plain text output
        pos_text = utils.CivitaiAPIUtils._format_tags_with_counts(pos_common, summary_top_n)
        neg_text = utils.CivitaiAPIUtils._format_tags_with_counts(neg_common, summary_top_n)

        # Generate new Markdown output
        tag_stats_md = utils.format_tags_as_markdown(
            pos_common, neg_common, summary_top_n
        )

        return (pos_text, neg_text, tag_stats_md)

class ParameterAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}),
            }
        }

    RETURN_TYPES = (
        "STRING",
        "STRING",
        "FLOAT",
        "INT",
        "INT",
        "INT",
        "STRING",
        "FLOAT",
        "INT",
        "STRING",
        "STRING",
    )
    RETURN_NAMES = (
        "parameter_stats",
        "top_sampler_name",
        "top_cfg",
        "top_steps",
        "top_width",
        "top_height",
        "top_hires_upscaler",
        "top_denoising_strength",
        "top_clip_skip",
        "top_vae_name",
        "parameter_stats_md",
    )

    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def run_analysis(self, civitai_data):
        if not civitai_data or not civitai_data.get("metas"):
            return None
        metas, total_images = civitai_data["metas"], civitai_data["total_images"]
        param_counters = {
            key: Counter()
            for key in [
                "sampler",
                "cfgScale",
                "steps",
                "Size",
                "Hires upscaler",
                "Denoising strength",
                "clipSkip",
                "VAE",
            ]
        }
        for meta in metas:
            for key in param_counters:
                if val := meta.get(key):
                    param_counters[key].update([str(val)])
        defaults = {
            "sampler": "Euler a",
            "cfg": 7.0,
            "steps": 25,
            "width": 512,
            "height": 512,
            "upscaler": "None",
            "denoise": 0.3,
            "clip": -1,
            "vae": "None",
        }
        param_counts_dict = {k: dict(v) for k, v in param_counters.items()}
        top_sampler = (
            Counter(param_counts_dict.get("sampler", {})).most_common(1)[0][0]
            if param_counts_dict.get("sampler")
            else defaults["sampler"]
        )
        top_cfg = (
            float(Counter(param_counts_dict.get("cfgScale", {})).most_common(1)[0][0])
            if param_counts_dict.get("cfgScale")
            else defaults["cfg"]
        )
        top_steps = (
            int(Counter(param_counts_dict.get("steps", {})).most_common(1)[0][0])
            if param_counts_dict.get("steps")
            else defaults["steps"]
        )
        top_size_str = (
            Counter(param_counts_dict.get("Size", {})).most_common(1)[0][0]
            if param_counts_dict.get("Size")
            else "512x512"
        )
        try:
            top_width, top_height = map(int, top_size_str.split("x"))
        except:
            top_width, top_height = defaults["width"], defaults["height"]
        top_hires_upscaler = (
            Counter(param_counts_dict.get("Hires upscaler", {})).most_common(1)[0][0]
            if param_counts_dict.get("Hires upscaler")
            else defaults["upscaler"]
        )
        top_denoising = (
            float(
                Counter(param_counts_dict.get("Denoising strength", {})).most_common(1)[0][0])
            if param_counts_dict.get("Denoising strength")
            else defaults["denoise"]
        )
        top_clip_skip = (
            -int(Counter(param_counts_dict.get("clipSkip", {})).most_common(1)[0][0])
            if param_counts_dict.get("clipSkip")
            else defaults["clip"]
        )
        top_vae = (
            Counter(param_counts_dict.get("VAE", {})).most_common(1)[0][0]
            if param_counts_dict.get("VAE")
            else defaults["vae"]
        )
        return {
            "counts": param_counts_dict,
            "total_images": total_images,
            "top_values": {
                "sampler": top_sampler,
                "cfg": top_cfg,
                "steps": top_steps,
                "width": top_width,
                "height": top_height,
                "upscaler": top_hires_upscaler,
                "denoise": top_denoising,
                "clip": top_clip_skip,
                "vae": top_vae,
            },
        }

    def execute(self, civitai_data, summary_top_n=5):
        results = self.run_analysis(civitai_data)
        if not results:
            return ("[No data]","Euler a",7.0,25,512,512,"None",0.3,-1,"None","No data.",)

        summary = utils.CivitaiAPIUtils._format_parameter_stats(
            results["counts"], results["total_images"], summary_top_n, include_vae=True
        )
        summary_md = utils.format_parameters_as_markdown(
            results["counts"], results["total_images"], summary_top_n, include_vae=True
        )

        top = results["top_values"]
        return (summary, top["sampler"], top["cfg"], top["steps"], top["width"], top["height"], top["upscaler"], top["denoise"], top["clip"], top["vae"], summary_md)

class ResourceAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}),
            }
        }

    RETURN_TYPES = (
        "STRING",
        "STRING",
        "FLOAT",
        "STRING",
        "FLOAT",
        "STRING",
        "FLOAT",
        "STRING",
    )
    RETURN_NAMES = (
        "associated_resources_stats",
        "assoc_lora_1_name",
        "assoc_lora_1_weight",
        "assoc_lora_2_name",
        "assoc_lora_2_weight",
        "assoc_lora_3_name",
        "assoc_lora_3_weight",
        "associated_resources_stats_md",
    )
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data, summary_top_n=5):
        defaults = ("[No data]", "None", 0.0, "None", 0.0, "None", 0.0, "No data.")
        if not civitai_data or not civitai_data.get("metas"):
            return defaults

        # --- 最终优化：创建并加载所有缓存到内存中的“会话缓存” ---
        SESSION_CACHE = {
            "version_info": utils.load_json_from_file(
                os.path.join(utils.CACHE_DIR, "version_info_cache.json")
            )
            or {},
            "id_to_hash": utils.load_json_from_file(
                os.path.join(utils.CACHE_DIR, "id_to_hash_cache.json")
            )
            or {},
        }
        # --- 核心修正：创建一个线程锁来保护共享的 SESSION_CACHE ---
        cache_lock = threading.Lock()

        _, filename_to_lora_hash_map = utils.update_model_hash_cache("loras")

        metas, total_images = civitai_data["metas"], civitai_data["total_images"]
        assoc_stats = {"lora": {}, "model": {}}

        version_ids_to_check = set()
        for meta in metas:
            if isinstance(meta.get("civitaiResources"), list):
                for res in meta["civitaiResources"]:
                    if isinstance(res, dict) and res.get("modelVersionId"):
                        version_ids_to_check.add(res["modelVersionId"])

        # 在检查之前先获取锁
        with cache_lock:
            new_ids_to_fetch = [
                vid
                for vid in version_ids_to_check
                if str(vid) not in SESSION_CACHE["version_info"]
            ]

        if new_ids_to_fetch:
            print(
                f"[ResourceAnalyzer] Pre-fetching info for {len(new_ids_to_fetch)} new resources..."
            )

            def fetch_worker(version_id):
                time.sleep(0.1)
                # 将锁和缓存一起传递给工作函数
                return utils.CivitaiAPIUtils.get_model_version_info_by_id(
                    version_id, SESSION_CACHE, cache_lock
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(fetch_worker, vid) for vid in new_ids_to_fetch
                ]
                for _ in tqdm(
                    as_completed(futures),
                    total=len(new_ids_to_fetch),
                    desc="Fetching Civitai Info",
                ):
                    pass
            print(f"[ResourceAnalyzer] Pre-fetching complete.")
        else:
            print("[ResourceAnalyzer] All required resources already in memory cache.")

        for meta in metas:
            # 每次调用都传入同一个SESSION_CACHE和锁
            extracted = utils.extract_resources_from_meta(
                meta, filename_to_lora_hash_map, SESSION_CACHE, cache_lock
            )
            for lora_info in extracted.get("loras", []):
                key = lora_info.get("hash") or lora_info.get("name")
                if not key:
                    continue
                stats_dict = assoc_stats["lora"]
                if key not in stats_dict:
                    stats_dict[key] = {
                        "count": 0,
                        "weights": [],
                        "name": lora_info.get("name") or key,
                        "modelId": lora_info.get("modelId"),
                    }
                stats_dict[key]["count"] += 1
                stats_dict[key]["weights"].append(lora_info.get("weight", 1.0))
                if not stats_dict[key].get("modelId") and lora_info.get(
                    "modelVersionId"
                ):
                    version_info = utils.CivitaiAPIUtils.get_model_version_info_by_id(
                        lora_info.get("modelVersionId"), SESSION_CACHE, cache_lock
                    )
                    if version_info and "modelId" in version_info:
                        stats_dict[key]["modelId"] = version_info["modelId"]
                        if version_info.get("model", {}).get("name"):
                            stats_dict[key]["name"] = version_info["model"]["name"]

        # 在所有操作结束后，加锁进行一次性回写
        with cache_lock:
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "version_info_cache.json"),
                SESSION_CACHE["version_info"],
            )
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "id_to_hash_cache.json"),
                SESSION_CACHE["id_to_hash"],
            )

        summary = utils.CivitaiAPIUtils._format_associated_resources(
            assoc_stats, total_images, summary_top_n
        )
        summary_md = utils.format_resources_as_markdown(
            assoc_stats, total_images, summary_top_n
        )
        lora_stats = assoc_stats.get("lora", {})
        sorted_assoc = sorted(
            lora_stats.values(), key=lambda data: data["count"], reverse=True
        )
        top_3_loras = []
        for data in sorted_assoc[:3]:
            name = data.get("name", "Unknown")
            common_weight = (
                statistics.mode(data["weights"]) if data.get("weights") else 0.0
            )
            top_3_loras.append((name, round(float(common_weight), 2)))
        while len(top_3_loras) < 3:
            top_3_loras.append(("None", 0.0))

        return (
            summary,
            top_3_loras[0][0], top_3_loras[0][1],
            top_3_loras[1][0], top_3_loras[1][1],
            top_3_loras[2][0], top_3_loras[2][1],
            summary_md
        )

# --- Node Mappings ---
NODE_CLASS_MAPPINGS = {
    "LoraTriggerWords": LoraTriggerWords,
    "CivitaiDataFetcherCKPT": CivitaiDataFetcherCKPT,
    "CivitaiDataFetcherLORA": CivitaiDataFetcherLORA,
    "PromptAnalyzer": PromptAnalyzer,
    "ParameterAnalyzer": ParameterAnalyzer,
    "ResourceAnalyzer": ResourceAnalyzer,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraTriggerWords": "Lora Trigger Words",
    "CivitaiDataFetcherCKPT": "Data Fetcher (CKPT)",
    "CivitaiDataFetcherLORA": "Data Fetcher (LORA)",
    "PromptAnalyzer": "Prompt Analyzer",
    "ParameterAnalyzer": "Parameter Analyzer",
    "ResourceAnalyzer": "Resource Analyzer",
}