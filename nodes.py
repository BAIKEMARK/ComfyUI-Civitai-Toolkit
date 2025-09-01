# import requests
# import json
# import os
# from collections import Counter
# from concurrent.futures import ThreadPoolExecutor, as_completed
# import folder_paths
# import time
# import statistics
# from . import utils
#
# # --- Lora Trigger Words ---
# class LoraTriggerWords:
#     @classmethod
#     def INPUT_TYPES(cls):
#         return { "required": { "lora_name": (folder_paths.get_filename_list("loras"),), "force_refresh": (["no", "yes"], {"default": "no"}), } }
#
#     RETURN_TYPES = ("STRING", "STRING")
#     RETURN_NAMES = ("metadata_triggers", "civitai_triggers")
#     FUNCTION = "execute"
#     CATEGORY = "Civitai"
#
#     def execute(self, lora_name, force_refresh):
#         file_path = folder_paths.get_full_path("loras", lora_name)
#         if not file_path:
#             return ("", "")
#
#         # 调用 utils 中的函数
#         metadata_triggers_list = utils.sort_tags_by_frequency(
#             utils.get_metadata(lora_name, "loras")
#         )
#         civitai_triggers_list = []
#         try:
#             # 调用 utils 中的函数
#             file_hash = utils.CivitaiAPIUtils.get_cached_sha256(file_path)
#             # 调用 utils 中的新函数，替换掉内部逻辑
#             civitai_triggers_list = utils.get_civitai_triggers(
#                 lora_name, file_hash, force_refresh
#             )
#         except Exception as e:
#             print(f"[{self.__class__.__name__}] Failed to get civitai triggers: {e}")
#
#         metadata_triggers_str = (", ".join(metadata_triggers_list) if metadata_triggers_list else "[Empty: No trigger words found in metadata]")
#         civitai_triggers_str = (", ".join(civitai_triggers_list) if civitai_triggers_list else "[Empty: No trigger words found on Civitai API]")
#         return (metadata_triggers_str, civitai_triggers_str)
#
# # --- Data Fetcher Nodes ---
# class BaseDataFetcher:
#     FOLDER_KEY = None
#     @classmethod
#     def INPUT_TYPES(cls):
#         return { "required": { "model_name": (folder_paths.get_filename_list(cls.FOLDER_KEY),), "max_pages": ("INT", {"default": 3, "min": 1, "max": 50}), "sort": (["Most Reactions", "Most Comments", "Newest"], {"default": "Most Reactions"}), "retries": ("INT", {"default": 2, "min": 0, "max": 5}), "timeout": ("INT", {"default": 10, "min": 1, "max": 60}), "force_refresh": (["no", "yes"], {"default": "no"}), } }
#     RETURN_TYPES = ("CIVITAI_DATA", "STRING")
#     RETURN_NAMES = ("civitai_data", "fetch_summary")
#     FUNCTION = "execute"
#     CATEGORY = "Civitai/Fetcher"
#
#     def _fetch_page(self, url, params, timeout):
#         resp = requests.get(url, params=params, timeout=timeout)
#         resp.raise_for_status()
#         return resp.json()
#
#     def execute(self, model_name, max_pages, sort, retries, timeout, force_refresh):
#         file_path = folder_paths.get_full_path(self.FOLDER_KEY, model_name)
#         defaults = (None, "No data fetched.")
#         if not file_path: return defaults
#         try:
#             file_hash = utils.CivitaiAPIUtils.get_cached_sha256(file_path)
#         except Exception: return defaults
#         cache_file = os.path.join(utils.CivitaiAPIUtils.CACHE_DIR, f"{file_hash}_{sort}_{max_pages}_raw_data.json")
#         if force_refresh == "no" and os.path.exists(cache_file):
#             print(f"[{self.__class__.__name__}] Loading raw data from cache.")
#             with open(cache_file, "r", encoding="utf-8") as f: raw_data = json.load(f)
#             summary = f"Loaded {raw_data.get('total_images', 0)} images from cache."
#             return (raw_data, summary)
#         model_info = utils.CivitaiAPIUtils.get_model_version_info_by_hash(file_hash)
#         if not model_info or not model_info.get("id"): return defaults
#         model_version_id = model_info.get("id")
#         all_metas = []
#         def fetch_page_with_retries(page_num):
#             url, params = "https://civitai.com/api/v1/images", {"modelVersionId": model_version_id, "limit": 100, "page": page_num, "sort": sort}
#             attempt = 0
#             while attempt <= retries:
#                 try: return self._fetch_page(url, params, timeout)
#                 except requests.exceptions.RequestException as e:
#                     attempt += 1; print(f"[{self.__class__.__name__}] Network error on page {page_num}, attempt {attempt}/{retries + 1}: {e}")
#                     if attempt > retries: print(f"[{self.__class__.__name__}] All retries failed for page {page_num}."); return {"items": []}
#                     time.sleep(0.5)
#             return {"items": []}
#         with ThreadPoolExecutor(max_workers=min(10, max_pages)) as executor:
#             pages = range(1, max_pages + 1)
#             futures = [executor.submit(fetch_page_with_retries, p) for p in pages]
#             for future in as_completed(futures):
#                 try:
#                     data = future.result()
#                     for item in data.get("items", []):
#                         if meta := item.get("meta"): all_metas.append(meta)
#                 except Exception as e: print(f"[{self.__class__.__name__}] Error processing page result: {e}")
#         raw_data = {"metas": all_metas, "total_images": len(all_metas), "model_name": os.path.splitext(model_name)[0]}
#         with open(cache_file, "w", encoding="utf-8") as f: json.dump(raw_data, f)
#         summary = f"Fetched metadata from {len(all_metas)} images across {max_pages} pages."
#         return (raw_data, summary)
#
# class CivitaiDataFetcherCKPT(BaseDataFetcher): FOLDER_KEY = "checkpoints"
# class CivitaiDataFetcherLORA(BaseDataFetcher): FOLDER_KEY = "loras"
#
# # --- Analyzers ---
# class PromptAnalyzer:
#     @classmethod
#     def INPUT_TYPES(cls):
#         return { "required": { "civitai_data": ("CIVITAI_DATA",), "summary_top_n": ("INT", {"default": 10, "min": 1, "max": 100}), } }
#     RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("STRING", "STRING"), ("positive_prompt", "negative_prompt"), "execute", "Civitai/Analyzers"
#     def execute(self, civitai_data, summary_top_n):
#         if not civitai_data or not civitai_data.get("metas"): return ("", "")
#         pos_tokens, neg_tokens = [], []
#         for meta in civitai_data["metas"]:
#             pos_tokens.extend(utils.CivitaiAPIUtils._parse_prompts(meta.get("prompt", "")))
#             neg_tokens.extend(utils.CivitaiAPIUtils._parse_prompts(meta.get("negativePrompt", "")))
#         pos_text = utils.CivitaiAPIUtils._format_tags_with_counts(Counter(pos_tokens).most_common(), summary_top_n)
#         neg_text = utils.CivitaiAPIUtils._format_tags_with_counts(Counter(neg_tokens).most_common(), summary_top_n)
#         return (pos_text, neg_text)
#
# class ParameterAnalyzerBase:
#     FUNCTION, CATEGORY = "execute", "Civitai/Analyzers"
#     @classmethod
#     def INPUT_TYPES(cls):
#         return { "required": { "civitai_data": ("CIVITAI_DATA",), "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}), } }
#     def run_analysis(self, civitai_data):
#         if not civitai_data or not civitai_data.get("metas"): return None
#         metas, total_images = civitai_data["metas"], civitai_data["total_images"]
#         param_counters = {key: Counter() for key in ["sampler", "cfgScale", "steps", "Size", "Hires upscaler", "Denoising strength", "clipSkip", "VAE"]}
#         for meta in metas:
#             for key in param_counters:
#                 if val := meta.get(key): param_counters[key].update([str(val)])
#         defaults = {"sampler": "Euler a", "cfg": 7.0, "steps": 30, "width": 512, "height": 512, "upscaler": "None", "denoise": 0.3, "clip": -1, "vae": "None"}
#         param_counts_dict = {k: dict(v) for k, v in param_counters.items()}
#         top_sampler = Counter(param_counts_dict.get("sampler", {})).most_common(1)[0][0] if param_counts_dict.get("sampler") else defaults["sampler"]
#         top_cfg = float(Counter(param_counts_dict.get("cfgScale", {})).most_common(1)[0][0]) if param_counts_dict.get("cfgScale") else defaults["cfg"]
#         top_steps = int(Counter(param_counts_dict.get("steps", {})).most_common(1)[0][0]) if param_counts_dict.get("steps") else defaults["steps"]
#         top_size_str = Counter(param_counts_dict.get("Size", {})).most_common(1)[0][0] if param_counts_dict.get("Size") else "512x512"
#         try: top_width, top_height = map(int, top_size_str.split("x"))
#         except: top_width, top_height = defaults["width"], defaults["height"]
#         top_hires_upscaler = Counter(param_counts_dict.get("Hires upscaler", {})).most_common(1)[0][0] if param_counts_dict.get("Hires upscaler") else defaults["upscaler"]
#         top_denoising = float(Counter(param_counts_dict.get("Denoising strength", {})).most_common(1)[0][0]) if param_counts_dict.get("Denoising strength") else defaults["denoise"]
#         top_clip_skip = -int(Counter(param_counts_dict.get("clipSkip", {})).most_common(1)[0][0]) if param_counts_dict.get("clipSkip") else defaults["clip"]
#         top_vae = Counter(param_counts_dict.get("VAE", {})).most_common(1)[0][0] if param_counts_dict.get("VAE") else defaults["vae"]
#         return {"counts": param_counts_dict, "total_images": total_images, "top_values": {"sampler": top_sampler, "cfg": top_cfg, "steps": top_steps, "width": top_width, "height": top_height, "upscaler": top_hires_upscaler, "denoise": top_denoising, "clip": top_clip_skip, "vae": top_vae}}
#
# class ParameterAnalyzerCKPT(ParameterAnalyzerBase):
#     RETURN_TYPES, RETURN_NAMES = ("STRING", "STRING", "FLOAT", "INT", "INT", "INT", "STRING", "FLOAT", "INT", "STRING"), ("parameter_stats", "top_sampler_name", "top_cfg", "top_steps", "top_width", "top_height", "top_hires_upscaler", "top_denoising_strength", "top_clip_skip", "top_vae_name")
#     def execute(self, civitai_data, summary_top_n=5):
#         results = self.run_analysis(civitai_data)
#         if not results: return ("[No data]", "Euler a", 7.0, 30, 512, 512, "None", 0.3, -1, "None")
#         summary = utils.CivitaiAPIUtils._format_parameter_stats(results["counts"], results["total_images"], summary_top_n, include_vae=True)
#         top = results["top_values"]
#         return (summary, top["sampler"], top["cfg"], top["steps"], top["width"], top["height"], top["upscaler"], top["denoise"], top["clip"], top["vae"])
#
# class ParameterAnalyzerLORA(ParameterAnalyzerBase):
#     RETURN_TYPES, RETURN_NAMES = ("STRING", "STRING", "FLOAT", "INT", "INT", "INT", "STRING", "FLOAT", "INT"), ("parameter_stats", "top_sampler_name", "top_cfg", "top_steps", "top_width", "top_height", "top_hires_upscaler", "top_denoising_strength", "top_clip_skip")
#     def execute(self, civitai_data, summary_top_n=5):
#         results = self.run_analysis(civitai_data)
#         if not results: return ("[No data]", "Euler a", 7.0, 30, 512, 512, "None", 0.3, -1)
#         summary = utils.CivitaiAPIUtils._format_parameter_stats(results["counts"], results["total_images"], summary_top_n, include_vae=False)
#         top = results["top_values"]
#         return (summary, top["sampler"], top["cfg"], top["steps"], top["width"], top["height"], top["upscaler"], top["denoise"], top["clip"])
#
# class ResourceAnalyzer:
#     @classmethod
#     def INPUT_TYPES(cls):
#         return { "required": { "civitai_data": ("CIVITAI_DATA",), "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}), } }
#     RETURN_TYPES, RETURN_NAMES, FUNCTION, CATEGORY = ("STRING", "STRING", "FLOAT", "STRING", "FLOAT", "STRING", "FLOAT"), ("associated_resources_stats", "assoc_lora_1_name", "assoc_lora_1_weight", "assoc_lora_2_name", "assoc_lora_2_weight", "assoc_lora_3_name", "assoc_lora_3_weight"), "execute", "Civitai/Analyzers"
#     def execute(self, civitai_data, summary_top_n=5):
#         defaults = ("[No data]", "None", 0.0, "None", 0.0, "None", 0.0)
#         if not civitai_data or not civitai_data.get("metas"): return defaults
#         metas, total_images, model_name_to_exclude, assoc_stats = civitai_data["metas"], civitai_data["total_images"], civitai_data.get("model_name"), {"lora": {}, "model": {}}
#         for meta in metas:
#             for res in meta.get("resources", []):
#                 res_name, res_type = res.get("name"), res.get("type")
#                 if res_type in ["lora", "model"] and res_name and res_name != model_name_to_exclude:
#                     stats_dict = assoc_stats[res_type]
#                     if res_name not in stats_dict: stats_dict[res_name] = {"count": 0, "weights": [], "modelId": None}
#                     stats_dict[res_name]["count"] += 1
#                     if res.get("weight") is not None and res_type == "lora": stats_dict[res_name]["weights"].append(res.get("weight"))
#                     if res.get("modelId") and not stats_dict[res_name].get("modelId"): stats_dict[res_name]["modelId"] = res.get("modelId")
#         summary = utils.CivitaiAPIUtils._format_associated_resources(assoc_stats, total_images, summary_top_n)
#         lora_stats = assoc_stats.get("lora", {})
#         sorted_assoc = sorted(lora_stats.items(), key=lambda item: item[1]["count"], reverse=True)
#         top_3_loras = []
#         for name, data in sorted_assoc[:3]:
#             common_weight = statistics.mode(data["weights"]) if data.get("weights") else 0.0
#             top_3_loras.append((name, round(float(common_weight), 2)))
#         while len(top_3_loras) < 3: top_3_loras.append(("None", 0.0))
#         return (summary, top_3_loras[0][0], top_3_loras[0][1], top_3_loras[1][0], top_3_loras[1][1], top_3_loras[2][0], top_3_loras[2][1])
#
# # --- Node Mappings ---
# NODE_CLASS_MAPPINGS = {
#     "LoraTriggerWords": LoraTriggerWords,
#     "CivitaiDataFetcherCKPT": CivitaiDataFetcherCKPT,
#     "CivitaiDataFetcherLORA": CivitaiDataFetcherLORA,
#     "PromptAnalyzer": PromptAnalyzer,
#     "ParameterAnalyzerCKPT": ParameterAnalyzerCKPT,
#     "ParameterAnalyzerLORA": ParameterAnalyzerLORA,
#     "ResourceAnalyzer": ResourceAnalyzer,
# }
# NODE_DISPLAY_NAME_MAPPINGS = {
#     "LoraTriggerWords": "Lora Trigger Words",
#     "CivitaiDataFetcherCKPT": "Data Fetcher (CKPT)",
#     "CivitaiDataFetcherLORA": "Data Fetcher (LORA)",
#     "PromptAnalyzer": "Prompt Analyzer",
#     "ParameterAnalyzerCKPT": "Parameter Analyzer (CKPT)",
#     "ParameterAnalyzerLORA": "Parameter Analyzer (LORA)",
#     "ResourceAnalyzer": "Resource Analyzer",
# }
import requests
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import folder_paths
import time
import statistics

# 导入统一的工具箱
from . import utils


# --- Lightweight Node: Lora Trigger Words ---
class LoraTriggerWords:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_name": (folder_paths.get_filename_list("loras"),),
                "force_refresh": (["no", "yes"], {"default": "no"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("metadata_triggers", "civitai_triggers")
    FUNCTION = "execute"
    CATEGORY = "Civitai"

    def execute(self, lora_name, force_refresh):
        file_path = folder_paths.get_full_path("loras", lora_name)
        if not file_path:
            return ("", "")

        metadata_triggers_list = utils.sort_tags_by_frequency(
            utils.get_metadata(lora_name, "loras")
        )
        civitai_triggers_list = []
        try:
            file_hash = utils.CivitaiAPIUtils.get_cached_sha256(file_path)
            # 调用 utils 中的函数
            civitai_triggers_list = utils.get_civitai_triggers(
                lora_name, file_hash, force_refresh
            )
        except Exception as e:
            print(f"[{self.__class__.__name__}] Failed to get civitai triggers: {e}")

        metadata_triggers_str = (
            ", ".join(metadata_triggers_list)
            if metadata_triggers_list
            else "[Empty: No trigger words found in metadata]"
        )
        civitai_triggers_str = (
            ", ".join(civitai_triggers_list)
            if civitai_triggers_list
            else "[Empty: No trigger words found on Civitai API]"
        )
        return (metadata_triggers_str, civitai_triggers_str)


# --- Heavyweight Pipeline: Data Fetcher Nodes ---
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
            utils.CivitaiAPIUtils.CACHE_DIR,
            f"{file_hash}_{sort}_{max_pages}_raw_data.json",
        )
        if force_refresh == "no" and os.path.exists(cache_file):
            print(f"[{self.__class__.__name__}] Loading raw data from cache.")
            with open(cache_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            summary = f"Loaded {raw_data.get('total_images', 0)} images from cache."
            return (raw_data, summary)

        model_info = utils.CivitaiAPIUtils.get_model_version_info_by_hash(file_hash)
        if not model_info or not model_info.get("id"):
            return defaults
        model_version_id = model_info.get("id")

        all_metas = []

        def fetch_page_with_retries(page_num):
            url = "https://civitai.com/api/v1/images"
            params = {
                "modelVersionId": model_version_id,
                "limit": 100,
                "page": page_num,
                "sort": sort,
            }
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
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_data, f)
        summary = (
            f"Fetched metadata from {len(all_metas)} images across {max_pages} pages."
        )
        return (raw_data, summary)


class CivitaiDataFetcherCKPT(BaseDataFetcher):
    FOLDER_KEY = "checkpoints"


class CivitaiDataFetcherLORA(BaseDataFetcher):
    FOLDER_KEY = "loras"


# --- Heavyweight Pipeline: Prompt Analyzer ---
class PromptAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}),
            }
        }

    # 更新: 新增 _md 输出
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "positive_prompt",
        "negative_prompt",
        "positive_prompt_md",
        "negative_prompt_md",
    )
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data, summary_top_n):
        if not civitai_data or not civitai_data.get("metas"):
            return ("", "", "", "")
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

        # 旧的纯文本输出
        pos_text = utils.CivitaiAPIUtils._format_tags_with_counts(
            pos_common, summary_top_n
        )
        neg_text = utils.CivitaiAPIUtils._format_tags_with_counts(
            neg_common, summary_top_n
        )

        # 新的Markdown输出
        pos_md = utils.format_tags_as_markdown(pos_common, summary_top_n)
        neg_md = utils.format_tags_as_markdown(neg_common, summary_top_n)

        return (pos_text, neg_text, pos_md, neg_md)


# --- Heavyweight Pipeline: Parameter Analyzers ---
class ParameterAnalyzerBase:
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}),
            }
        }

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
            for key in param_counters.keys():
                if val := meta.get(key):
                    param_counters[key].update([str(val)])
        defaults = {
            "sampler": "Euler a",
            "cfg": 7.0,
            "steps": 30,
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
                Counter(param_counts_dict.get("Denoising strength", {})).most_common(1)[
                    0
                ][0]
            )
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


class ParameterAnalyzerCKPT(ParameterAnalyzerBase):
    # 更新: 新增 _md 输出
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

    def execute(self, civitai_data, summary_top_n=5):
        results = self.run_analysis(civitai_data)
        if not results:
            return (
                "[No data]",
                "Euler a",
                7.0,
                30,
                512,
                512,
                "None",
                0.3,
                -1,
                "None",
                "No data",
            )

        summary_text = utils.CivitaiAPIUtils._format_parameter_stats(
            results["counts"], results["total_images"], summary_top_n, include_vae=True
        )
        summary_md = utils.format_parameters_as_markdown(
            results["counts"], results["total_images"], summary_top_n, include_vae=True
        )

        top = results["top_values"]
        return (
            summary_text,
            top["sampler"],
            top["cfg"],
            top["steps"],
            top["width"],
            top["height"],
            top["upscaler"],
            top["denoise"],
            top["clip"],
            top["vae"],
            summary_md,
        )


class ParameterAnalyzerLORA(ParameterAnalyzerBase):
    # 更新: 新增 _md 输出
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
        "parameter_stats_md",
    )

    def execute(self, civitai_data, summary_top_n=5):
        results = self.run_analysis(civitai_data)
        if not results:
            return (
                "[No data]",
                "Euler a",
                7.0,
                30,
                512,
                512,
                "None",
                0.3,
                -1,
                "No data",
            )

        summary_text = utils.CivitaiAPIUtils._format_parameter_stats(
            results["counts"], results["total_images"], summary_top_n, include_vae=False
        )
        summary_md = utils.format_parameters_as_markdown(
            results["counts"], results["total_images"], summary_top_n, include_vae=False
        )

        top = results["top_values"]
        return (
            summary_text,
            top["sampler"],
            top["cfg"],
            top["steps"],
            top["width"],
            top["height"],
            top["upscaler"],
            top["denoise"],
            top["clip"],
            summary_md,
        )


# --- Heavyweight Pipeline: Resource Analyzer ---
class ResourceAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "summary_top_n": ("INT", {"default": 5, "min": 1, "max": 20}),
            }
        }

    # 更新: 新增 _md 输出
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
        defaults = ("[No data]", "None", 0.0, "None", 0.0, "None", 0.0, "No data")
        if not civitai_data or not civitai_data.get("metas"):
            return defaults

        metas, total_images, model_name_to_exclude, assoc_stats = (
            civitai_data["metas"],
            civitai_data["total_images"],
            civitai_data.get("model_name"),
            {"lora": {}, "model": {}},
        )
        for meta in metas:
            for res in meta.get("resources", []):
                res_name, res_type = res.get("name"), res.get("type")
                if (
                    res_type in ["lora", "model"]
                    and res_name
                    and res_name != model_name_to_exclude
                ):
                    stats_dict = assoc_stats[res_type]
                    if res_name not in stats_dict:
                        stats_dict[res_name] = {
                            "count": 0,
                            "weights": [],
                            "modelId": None,
                        }
                    stats_dict[res_name]["count"] += 1
                    if res.get("weight") is not None and res_type == "lora":
                        stats_dict[res_name]["weights"].append(res.get("weight"))
                    if res.get("modelId") and not stats_dict[res_name].get("modelId"):
                        stats_dict[res_name]["modelId"] = res.get("modelId")

        summary_text = utils.CivitaiAPIUtils._format_associated_resources(
            assoc_stats, total_images, summary_top_n
        )
        summary_md = utils.format_resources_as_markdown(
            assoc_stats, total_images, summary_top_n
        )

        lora_stats = assoc_stats.get("lora", {})
        sorted_assoc = sorted(
            lora_stats.items(), key=lambda item: item[1]["count"], reverse=True
        )
        top_3_loras = []
        for name, data in sorted_assoc[:3]:
            common_weight = (
                statistics.mode(data["weights"]) if data.get("weights") else 0.0
            )
            top_3_loras.append((name, round(float(common_weight), 2)))
        while len(top_3_loras) < 3:
            top_3_loras.append(("None", 0.0))

        return (
            summary_text,
            top_3_loras[0][0],
            top_3_loras[0][1],
            top_3_loras[1][0],
            top_3_loras[1][1],
            top_3_loras[2][0],
            top_3_loras[2][1],
            summary_md,
        )


# --- Node Mappings ---
NODE_CLASS_MAPPINGS = {
    "LoraTriggerWords": LoraTriggerWords,
    "CivitaiDataFetcherCKPT": CivitaiDataFetcherCKPT,
    "CivitaiDataFetcherLORA": CivitaiDataFetcherLORA,
    "PromptAnalyzer": PromptAnalyzer,
    "ParameterAnalyzerCKPT": ParameterAnalyzerCKPT,
    "ParameterAnalyzerLORA": ParameterAnalyzerLORA,
    "ResourceAnalyzer": ResourceAnalyzer,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LoraTriggerWords": "Lora Trigger Words",
    "CivitaiDataFetcherCKPT": "Data Fetcher (CKPT)",
    "CivitaiDataFetcherLORA": "Data Fetcher (LORA)",
    "PromptAnalyzer": "Prompt Analyzer",
    "ParameterAnalyzerCKPT": "Parameter Analyzer (CKPT)",
    "ParameterAnalyzerLORA": "Parameter Analyzer (LORA)",
    "ResourceAnalyzer": "Resource Analyzer",
}