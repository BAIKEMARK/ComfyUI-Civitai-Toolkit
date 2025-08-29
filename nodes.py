from inspect import cleandoc
import requests
import hashlib
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import folder_paths
import time
import statistics


# --- 1. Utility Functions & Class ---
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
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    CACHE_DIR = os.path.join(PROJECT_ROOT, "data")
    os.makedirs(CACHE_DIR, exist_ok=True)
    HASH_CACHE_FILE = os.path.join(CACHE_DIR, "hash_cache.json")
    CIVITAI_TRIGGERS_CACHE = os.path.join(CACHE_DIR, "civitai_triggers_cache.json")

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

    @staticmethod
    def _parse_prompts(prompt_text: str):
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            return []
        pattern = re.compile(r"<[^>]+>|\[[^\]]+\]|\([^)]+\)|[^,]+")
        tags = pattern.findall(prompt_text)
        return [tag.strip() for tag in tags if tag.strip()]

    @staticmethod
    def _format_tags_with_counts(items, top_n):
        return "\n".join(
            [f'{i} : "{tag}" ({count})' for i, (tag, count) in enumerate(items[:top_n])]
        )

    @staticmethod
    def _format_parameter_stats(param_counts, total_images, include_vae=True):
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
            stats = Counter(param_counts.get(key, {})).most_common(5)
            if not stats:
                output += " (No data)\n"
                continue
            for i, (value, count) in enumerate(stats):
                percentage = (count / total_images) * 100
                output += f"{i + 1}. {value} ({count} | {percentage:.1f}%)\n"
        return output

    @staticmethod
    def _format_associated_resources(assoc_res_stats, total_images):
        if not assoc_res_stats or total_images == 0:
            return "[No associated LoRAs found]"
        output = "--- Associated Resources Analysis ---\n\n[Top 5 Associated LoRAs]\n"
        sorted_resources = sorted(
            assoc_res_stats.items(), key=lambda item: item[1]["count"], reverse=True
        )
        for i, (name, data) in enumerate(sorted_resources[:5]):
            count, weights = data["count"], data.get("weights", [])
            percentage = (count / total_images) * 100
            avg_weight = statistics.mean(weights) if weights else 0
            common_weight = statistics.mode(weights) if data.get("weights") else 0
            output += f"{i + 1}. {name} (in {percentage:.1f}% of images)\n   └─ Avg. Weight: {avg_weight:.2f}, Most Common: {common_weight:.2f}\n"
        return output


# --- 2. Lightweight Node: Lora Trigger Words ---
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
    CATEGORY = "Civitai"  # Top-level category

    def _get_civitai_triggers(self, file_name, file_hash, force_refresh):
        try:
            with open(
                CivitaiAPIUtils.CIVITAI_TRIGGERS_CACHE, "r", encoding="utf-8"
            ) as f:
                trigger_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            trigger_cache = {}
        if force_refresh == "no" and file_name in trigger_cache:
            return trigger_cache[file_name]

        print(
            f"[{self.__class__.__name__}] Requesting civitai triggers from API for: {file_name}"
        )
        model_info = CivitaiAPIUtils.get_model_version_info_by_hash(file_hash)
        triggers = (
            model_info.get("trainedWords", [])
            if model_info and isinstance(model_info.get("trainedWords"), list)
            else []
        )
        trigger_cache[file_name] = triggers
        try:
            with open(
                CivitaiAPIUtils.CIVITAI_TRIGGERS_CACHE, "w", encoding="utf-8"
            ) as f:
                json.dump(trigger_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(
                f"[{self.__class__.__name__}] Failed to save civitai triggers cache: {e}"
            )
        return triggers

    def execute(self, lora_name, force_refresh):
        file_path = folder_paths.get_full_path("loras", lora_name)
        if not file_path:
            return ("", "")

        metadata_triggers_list = sort_tags_by_frequency(
            get_metadata(lora_name, "loras")
        )
        civitai_triggers_list = []
        try:
            file_hash = CivitaiAPIUtils.get_cached_sha256(file_path)
            civitai_triggers_list = self._get_civitai_triggers(
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


# --- 3. Heavyweight Pipeline: Data Fetcher Nodes ---
class BaseDataFetcher:
    FOLDER_KEY = None  # To be defined by subclasses

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
    CATEGORY = "Civitai/Fetcher"  # Sub-level category

    def _fetch_page(self, url, params, timeout):
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def execute(self, model_name, max_pages, sort, retries, timeout, force_refresh):
        file_path = folder_paths.get_full_path(self.FOLDER_KEY, model_name)
        defaults = ([], "No data fetched.")

        if not file_path:
            return defaults
        try:
            file_hash = CivitaiAPIUtils.get_cached_sha256(file_path)
        except Exception:
            return defaults

        cache_file = os.path.join(
            CivitaiAPIUtils.CACHE_DIR, f"{file_hash}_{sort}_{max_pages}_raw_data.json"
        )
        if force_refresh == "no" and os.path.exists(cache_file):
            print(f"[{self.__class__.__name__}] Loading raw data from cache.")
            with open(cache_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            summary = f"Loaded {raw_data['total_images']} images from cache."
            return (raw_data, summary)

        model_info = CivitaiAPIUtils.get_model_version_info_by_hash(file_hash)
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


# --- 4. Heavyweight Pipeline: Prompt Analyzer ---
class PromptAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "civitai_data": ("CIVITAI_DATA",),
                "top_n": ("INT", {"default": 20, "min": 1, "max": 200}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive_prompt", "negative_prompt")
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data, top_n):
        if not civitai_data or not civitai_data.get("metas"):
            return ("", "")
        pos_tokens, neg_tokens = [], []
        for meta in civitai_data["metas"]:
            pos_tokens.extend(CivitaiAPIUtils._parse_prompts(meta.get("prompt", "")))
            neg_tokens.extend(
                CivitaiAPIUtils._parse_prompts(meta.get("negativePrompt", ""))
            )

        pos_text = CivitaiAPIUtils._format_tags_with_counts(
            Counter(pos_tokens).most_common(), top_n
        )
        neg_text = CivitaiAPIUtils._format_tags_with_counts(
            Counter(neg_tokens).most_common(), top_n
        )
        return (pos_text, neg_text)


# --- 5. Heavyweight Pipeline: Parameter Analyzers ---
class ParameterAnalyzerBase:
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"civitai_data": ("CIVITAI_DATA",)}}

    def run_analysis(self, civitai_data):
        if not civitai_data or not civitai_data.get("metas"):
            return None
        metas, total_images = civitai_data["metas"], civitai_data["total_images"]
        param_counters = {
            "sampler": Counter(),
            "cfgScale": Counter(),
            "steps": Counter(),
            "Size": Counter(),
            "Hires upscaler": Counter(),
            "Denoising strength": Counter(),
            "clipSkip": Counter(),
            "VAE": Counter(),
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
        "top_vae_name",
    )

    def execute(self, civitai_data):
        results = self.run_analysis(civitai_data)
        if not results:
            return ("[No data]", "Euler a", 7.0, 30, 512, 512, "None", 0.3, -1, "None")
        summary = CivitaiAPIUtils._format_parameter_stats(
            results["counts"], results["total_images"], include_vae=True
        )
        top = results["top_values"]
        return (
            summary,
            top["sampler"],
            top["cfg"],
            top["steps"],
            top["width"],
            top["height"],
            top["upscaler"],
            top["denoise"],
            top["clip"],
            top["vae"],
        )


class ParameterAnalyzerLORA(ParameterAnalyzerBase):
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
    )

    def execute(self, civitai_data):
        results = self.run_analysis(civitai_data)
        if not results:
            return ("[No data]", "Euler a", 7.0, 30, 512, 512, "None", 0.3, -1)
        summary = CivitaiAPIUtils._format_parameter_stats(
            results["counts"], results["total_images"], include_vae=False
        )
        top = results["top_values"]
        return (
            summary,
            top["sampler"],
            top["cfg"],
            top["steps"],
            top["width"],
            top["height"],
            top["upscaler"],
            top["denoise"],
            top["clip"],
        )


# --- 6. Heavyweight Pipeline: Resource Analyzer ---
class ResourceAnalyzer:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"civitai_data": ("CIVITAI_DATA",)}}

    RETURN_TYPES = ("STRING", "STRING", "FLOAT", "STRING", "FLOAT", "STRING", "FLOAT")
    RETURN_NAMES = (
        "associated_resources_stats",
        "assoc_lora_1_name",
        "assoc_lora_1_weight",
        "assoc_lora_2_name",
        "assoc_lora_2_weight",
        "assoc_lora_3_name",
        "assoc_lora_3_weight",
    )
    FUNCTION = "execute"
    CATEGORY = "Civitai/Analyzers"

    def execute(self, civitai_data):
        if not civitai_data or not civitai_data.get("metas"):
            return ("[No data]", "None", 0.0, "None", 0.0, "None", 0.0)

        metas, total_images = civitai_data["metas"], civitai_data["total_images"]
        model_name_to_exclude = civitai_data.get("model_name")
        assoc_res_stats = {}

        for meta in metas:
            for res in meta.get("resources", []):
                res_name, res_type = res.get("name"), res.get("type")
                if (
                    res_type == "lora"
                    and res_name
                    and res_name != model_name_to_exclude
                ):
                    if res_name not in assoc_res_stats:
                        assoc_res_stats[res_name] = {"count": 0, "weights": []}
                    assoc_res_stats[res_name]["count"] += 1
                    if res.get("weight") is not None:
                        assoc_res_stats[res_name]["weights"].append(res.get("weight"))

        summary = CivitaiAPIUtils._format_associated_resources(
            assoc_res_stats, total_images
        )

        sorted_assoc = sorted(
            assoc_res_stats.items(), key=lambda item: item[1]["count"], reverse=True
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
            summary,
            top_3_loras[0][0],
            top_3_loras[0][1],
            top_3_loras[1][0],
            top_3_loras[1][1],
            top_3_loras[2][0],
            top_3_loras[2][1],
        )


# --- 7. Node Mappings ---
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
    "CivitaiDataFetcherCKPT": "Civitai Data Fetcher (CKPT)",
    "CivitaiDataFetcherLORA": "Civitai Data Fetcher (LORA)",
    "PromptAnalyzer": "Prompt Analyzer",
    "ParameterAnalyzerCKPT": "Parameter Analyzer (CKPT)",
    "ParameterAnalyzerLORA": "Parameter Analyzer (LORA)",
    "ResourceAnalyzer": "Resource Analyzer",
}
