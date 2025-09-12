import threading
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import folder_paths
import comfy
import time
from tqdm import tqdm
import statistics
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
        return {
            "required": {
                "model_name": (folder_paths.get_filename_list(cls.FOLDER_KEY),),
                "max_pages": ("INT", {"default": 3, "min": 1, "max": 50}),
                "sort": (
                    ["Most Reactions", "Most Comments", "Newest"],
                    {"default": "Most Reactions"},
                ),
                "retries": ("INT", {"default": 2, "min": 0, "max": 5}),
                "timeout": ("INT", {"default": 10, "min": 1, "max": 60}),
                "force_refresh": (["no", "yes"], {"default": "no"}),
            }
        }

    RETURN_TYPES = ("CIVITAI_DATA", "STRING")
    RETURN_NAMES = ("civitai_data", "fetch_summary")
    FUNCTION = "execute"
    CATEGORY = "Civitai/Fetcher"

    def _fetch_page(self, url, params, timeout):
        resp = utils.requests.get(url, params=params, timeout=timeout)
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

        if force_refresh == "no":
            raw_data = utils.load_json_from_file(cache_file)
            if raw_data:
                summary = f"Loaded {raw_data.get('total_images', 0)} images from cache."
                return (raw_data, summary)

        session_cache = {"version_info": {}, "id_to_hash": {}}
        lock = threading.Lock()
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
                except utils.requests.exceptions.RequestException as e:
                    attempt += 1
                    print(
                        f"[{self.__class__.__name__}] Network error on page {page_num}, attempt {attempt}/{retries + 1}: {e}"
                    )
                    if attempt > retries:
                        return {"items": []}
                    time.sleep(0.5)
            return {"items": []}

        with ThreadPoolExecutor(max_workers=min(10, max_pages)) as executor:
            futures = [
                executor.submit(fetch_page_with_retries, p)
                for p in range(1, max_pages + 1)
            ]
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
        utils.save_json_to_file(cache_file, raw_data)
        summary = (
            f"Fetched metadata from {len(all_metas)} images across {max_pages} pages."
        )
        return (raw_data, summary)


class CivitaiDataFetcherCKPT(BaseDataFetcher):
    FOLDER_KEY = "checkpoints"


class CivitaiDataFetcherLORA(BaseDataFetcher):
    FOLDER_KEY = "loras"


# --- Analyzers ---
class PromptAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 10, "min": 1, "max": 100}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("tag_report_md",)
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data, summary_top_n):
        if not civitai_data or not civitai_data.get("metas"):
            return ("No data.",)
        pos_tokens, neg_tokens = [], []
        for meta in civitai_data["metas"]:
            pos_tokens.extend(
                utils.CivitaiAPIUtils._parse_prompts(meta.get("prompt", ""))
            )
            neg_tokens.extend(
                utils.CivitaiAPIUtils._parse_prompts(meta.get("negativePrompt", ""))
            )
        pos_common = Counter(pos_tokens).most_common()
        neg_common = Counter(neg_tokens).most_common()
        tag_report_md = utils.format_tags_as_markdown(
            pos_common, neg_common, summary_top_n
        )
        return (tag_report_md,)


class ParameterAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"civitai_data": ("CIVITAI_DATA",)}}

    RETURN_TYPES = (
        "STRING",
        "INT",
        "FLOAT",
        (comfy.samplers.KSampler.SAMPLERS,),
        (comfy.samplers.KSampler.SCHEDULERS,),
        "FLOAT",
        "INT",
        "INT",
    )
    RETURN_NAMES = (
        "parameter_report_md",
        "steps",
        "cfg",
        "sampler",
        "scheduler",
        "denoise",
        "width",
        "height",
    )
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data):
        defaults = ("No data.", "euler_ancestral", "karras", 25, 7.0, 512, 512, 1.0)
        if not civitai_data or not civitai_data.get("metas"):
            return defaults

        metas = civitai_data["metas"]
        param_counters = {
            key: Counter()
            for key in [
                "sampler",
                "scheduler",
                "cfgScale",
                "steps",
                "Size",
                "VAE",
                "denoise[hires.fix]",
            ]
        }
        for meta in metas:
            for key in param_counters:
                if val := meta.get(key):
                    param_counters[key].update([str(val)])

        param_counts_dict = {k: dict(v) for k, v in param_counters.items()}

        # 1. 正常提取最常用的 sampler 和 scheduler
        top_sampler_raw = (
            Counter(param_counts_dict.get("sampler", {})).most_common(1)[0][0]
            if param_counts_dict.get("sampler")
            else "Euler a"
        )
        top_scheduler_raw = (
            Counter(param_counts_dict.get("scheduler", {})).most_common(1)[0][0]
            if param_counts_dict.get("scheduler")
            else "Karras"
        )

        final_sampler = top_sampler_raw
        final_scheduler = top_scheduler_raw

        # 2. 检查 sampler 字符串是否为 WebUI 的合并格式
        known_schedulers = ["Karras"]  # 未来可扩展, e.g., ["Karras", "SGM Uniform"]
        for sched in known_schedulers:
            suffix = f" {sched}"
            if top_sampler_raw.endswith(suffix):
                final_sampler = top_sampler_raw[: -len(suffix)]
                final_scheduler = sched
                break

        top_sampler_cleaned = utils.SAMPLER_SCHEDULER_MAP.get(
            final_sampler, final_sampler
        )
        top_scheduler_cleaned = utils.SAMPLER_SCHEDULER_MAP.get(
            final_scheduler, final_scheduler
        )
        top_steps = (
            int(Counter(param_counts_dict.get("steps", {})).most_common(1)[0][0])
            if param_counts_dict.get("steps")
            else 25
        )
        top_cfg = (
            float(Counter(param_counts_dict.get("cfgScale", {})).most_common(1)[0][0])
            if param_counts_dict.get("cfgScale")
            else 7.0
        )
        top_size_str = (
            Counter(param_counts_dict.get("Size", {})).most_common(1)[0][0]
            if param_counts_dict.get("Size")
            else "512x512"
        )
        try:
            top_width, top_height = map(int, top_size_str.split("x"))
        except:
            top_width, top_height = 512, 512
        top_denoise = (
            float(Counter(param_counts_dict.get("Denoising strength[hires.fix]", {})).most_common(1)[0][0])
            if param_counts_dict.get("Denoising strength")
            else 1.0
        )

        summary_md = utils.format_parameters_as_markdown(param_counts_dict, len(metas), 5)

        return (
            summary_md,
            top_steps,
            top_cfg,
            top_sampler_cleaned,
            top_scheduler_cleaned,
            top_denoise,
            top_width,
            top_height,
        )


class ResourceAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("resource_report_md",)
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data, summary_top_n=5):
        if not civitai_data or not civitai_data.get("metas"):
            return ("No data.",)

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

        for meta in metas:
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

        with cache_lock:
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "version_info_cache.json"),
                SESSION_CACHE["version_info"],
            )
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "id_to_hash_cache.json"),
                SESSION_CACHE["id_to_hash"],
            )

        summary_md = utils.format_resources_as_markdown(assoc_stats, total_images, summary_top_n)
        return (summary_md,)

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