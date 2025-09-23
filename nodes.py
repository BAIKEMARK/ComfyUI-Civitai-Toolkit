import threading
import os
import re
import urllib.request
import urllib.parse
import io
import time
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

import folder_paths
import comfy.samplers
import torch
import server
from aiohttp import web
from PIL import Image
import numpy as np
from tqdm import tqdm

from . import utils

# [新增] 专门从数据库获取模型列表的函数，确保数据源统一
def get_db_model_list(model_type: str):
    # force_sync=True 确保每次加载UI时，列表都是最新的
    return utils.get_model_filenames_from_db(model_type, force_sync=True)

# =================================================================================
# 1. 核心交互节点
# =================================================================================
class CivitaiRecipeGallery:
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return utils.db_manager.get_setting("last_selection_time", time.time())

    @classmethod
    def INPUT_TYPES(cls):
        # [核心修正] 从我们可靠的数据库中获取列表
        checkpoints = ["CKPT/" + f for f in get_db_model_list("checkpoints")]
        loras = ["LORA/" + f for f in get_db_model_list("loras")]
        return {
            "required": {
                "model_name": (checkpoints + loras,),
                "sort": (["Most Reactions", "Most Comments", "Newest"],),
                "nsfw_level": (["None", "Soft", "Mature", "X"],),
                "image_limit": ("INT", {"default": 32, "min": 1, "max": 100}),
                "filter_type": (["all", "image", "video"], {"default": "image"}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("IMAGE", "STRING", "RECIPE_PARAMS")
    RETURN_NAMES = ("image", "info_md", "recipe_params")
    FUNCTION = "execute"
    CATEGORY = "Civitai/🖼️ Gallery"
    OUTPUT_NODE = True

    def execute(self, model_name, sort, nsfw_level, image_limit, filter_type, unique_id):
        lora_hash_map, lora_name_map = utils.get_local_model_maps("loras")
        ckpt_hash_map, _ = utils.get_local_model_maps("checkpoints")
        selections = utils.load_selections()
        node_selection = selections.get(str(unique_id), {})
        item_data = node_selection.get("item", {})
        should_download = node_selection.get("download_image", False)
        meta = item_data.get("meta", {})
        if not isinstance(meta, dict): meta = {}

        session_cache = {}
        extracted = utils.extract_resources_from_meta(meta, lora_name_map, session_cache)

        final_ckpt_name = None
        ckpt_hash = extracted.get("ckpt_hash")

        model_type_str, main_model_filename = model_name.split("/", 1)
        fallback_ckpt_name = main_model_filename
        if model_type_str != "CKPT":
            # [核心修正] 从可靠的数据库列表中获取备选项
            checkpoints = get_db_model_list("checkpoints")
            fallback_ckpt_name = checkpoints[0] if checkpoints else "model_not_found.safetensors"

        if ckpt_hash:
            found_local_name = ckpt_hash_map.get(ckpt_hash.lower())
            if found_local_name:
                final_ckpt_name = found_local_name
            else:
                print(f"[Civitai Utils] Warning: Checkpoint with hash {ckpt_hash[:12]} from recipe not found locally. Falling back to main selected model.")
                final_ckpt_name = fallback_ckpt_name
        else:
            print(f"[Civitai Utils] Info: No checkpoint hash in recipe, using main selected model as fallback.")
            final_ckpt_name = fallback_ckpt_name

        recipe_loras = extracted["loras"]

        image_url = item_data.get("url")
        image_tensor = torch.zeros(1, 64, 64, 3)
        if should_download and image_url:
            clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
            image_tensor = self.download_image(clean_url)

        info_md = utils.format_info_as_markdown(meta, recipe_loras, lora_hash_map)
        params_pack = self.pack_recipe_params(meta, final_ckpt_name)
        return (image_tensor, info_md, params_pack)

    def pack_recipe_params(self, meta, ckpt_name):
        if not meta: return ()
        sampler_raw, scheduler_raw = meta.get("sampler", "Euler a"), meta.get("scheduler", "normal")
        final_sampler, final_scheduler = sampler_raw, scheduler_raw
        for sched in ["Karras", "SGM Uniform"]:
            if sampler_raw.endswith(f" {sched}"):
                final_sampler, final_scheduler = sampler_raw[:-len(f" {sched}")], sched
                break
        try: width, height = map(int, meta.get("Size").split("x"))
        except: width, height = 512, 512
        return (ckpt_name, meta.get("prompt", ""), meta.get("negativePrompt", ""),
                int(meta.get("seed", -1)), int(meta.get("steps", 25)), float(meta.get("cfgScale", 7.0)),
                utils.SAMPLER_SCHEDULER_MAP.get(final_sampler.strip(), "euler_ancestral"),
                utils.SAMPLER_SCHEDULER_MAP.get(final_scheduler.strip(), "normal"),
                width, height, float(meta.get("Denoising strength", 1.0)))

    def download_image(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                img_data = response.read()
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
            img_np = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(img_np)[None,]
        except Exception as e:
            print(f"[CivitaiRecipeGallery] Failed to download image from {url}: {e}")
            return torch.zeros(1, 64, 64, 3)

class RecipeParamsParser:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"recipe_params": ("RECIPE_PARAMS",)}}

    RETURN_TYPES = (get_db_model_list("checkpoints"), "STRING", "STRING", "INT", "INT", "FLOAT", comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS, "INT", "INT", "FLOAT")
    RETURN_NAMES = ("ckpt_name", "positive_prompt", "negative_prompt", "seed", "steps", "cfg", "sampler_name", "scheduler", "width", "height", "denoise(Hires. Fix)")
    FUNCTION = "execute"
    CATEGORY = "Civitai/🖼️ Gallery"

    def execute(self, recipe_params):
        if not recipe_params or len(recipe_params) < 11:
            checkpoints = get_db_model_list("checkpoints")
            default_ckpt = checkpoints[0] if checkpoints else "none"
            return (default_ckpt, "", "", -1, 25, 7.0, "euler_ancestral", "normal", 512, 512, 1.0)
        return recipe_params

class LoraTriggerWords:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"lora_name": (get_db_model_list("loras"),), "force_refresh": (["no", "yes"], {"default": "no"})}}

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("metadata_triggers", "civitai_triggers", "triggers_md")
    FUNCTION = "execute"
    CATEGORY = "Civitai"
    def execute(self, lora_name, force_refresh):
        metadata_triggers_list = utils.sort_tags_by_frequency(utils.get_metadata(lora_name, "loras"))
        civitai_triggers_list = []
        try:
            _, filename_to_hash = utils.get_local_model_maps("loras")
            file_hash = filename_to_hash.get(lora_name)
            if file_hash:
                civitai_triggers_list = utils.get_civitai_triggers(lora_name, file_hash, force_refresh)
            else:
                print(f"[{self.__class__.__name__}] Could not find hash for {lora_name} in DB.")
        except Exception as e:
            print(f"[{self.__class__.__name__}] Failed to get civitai triggers: {e}")
        metadata_triggers_str = (", \n".join(metadata_triggers_list) if metadata_triggers_list else "[No Data Found]")
        civitai_triggers_str = (", ".join(civitai_triggers_list) if civitai_triggers_list else "[No Data Found]")
        def create_trigger_table(trigger_list, title):
            if not trigger_list: return f"| {title} |\n|:---|\n| *[No Data Found]* |"
            lines = [f"| {title} |", "|:---|"]
            lines.extend([f"| `{tag}` |" for tag in trigger_list])
            return "\n".join(lines)
        metadata_table = create_trigger_table(metadata_triggers_list, "Triggers from Metadata")
        civitai_table = create_trigger_table(civitai_triggers_list, "Triggers from Civitai API")
        triggers_md = f"{metadata_table}\n\n{civitai_table}"
        return (metadata_triggers_str, civitai_triggers_str, triggers_md)

# =================================================================================
# 2. 新的全能分析节点与参数管道
# =================================================================================
class CivitaiModelAnalyzer:
    FOLDER_KEY = None

    @classmethod
    def IS_CHANGED(cls, model_name, image_limit, sort, nsfw_level, filter_type, force_refresh, **kwargs):
        if force_refresh == "yes":
            return time.time()

        data_identity = f"{model_name}-{image_limit}-{sort}-{nsfw_level}-{filter_type}"
        return hashlib.sha256(data_identity.encode()).hexdigest()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_name": (get_db_model_list(cls.FOLDER_KEY),),
                "image_limit": ("INT", {"default": 100, "min": 1, "max": 1000}),
                "sort": (["Most Reactions", "Most Comments", "Newest"],),
                "nsfw_level": (["None", "Soft", "Mature", "X"],),
                "filter_type": (["all", "image", "video"],),
                "summary_top_n": ("INT", {"default": 10, "min": 1, "max": 100}),
                "force_refresh": (["no", "yes"],),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "CIVITAI_PARAMS")
    RETURN_NAMES = ("full_report_md", "fetch_summary", "params_pipe")
    FUNCTION = "execute"
    CATEGORY = "Civitai/📊 Analyzer"

    def _get_analysis_data(self, model_name, image_limit, sort, nsfw_level, filter_type, force_refresh):
        data_fingerprint = self.IS_CHANGED(model_name, image_limit, sort, nsfw_level, filter_type, "no")

        if force_refresh == "no":
            cached_data = utils.db_manager.get_analysis_cache(data_fingerprint)
            if cached_data:
                print("[Civitai Utils] Analysis data found in DB cache. Skipping fetch and analysis.")
                return cached_data

        _, filename_to_hash = utils.get_local_model_maps(self.FOLDER_KEY)
        file_hash = filename_to_hash.get(model_name)

        if not file_hash:
            print(f"[Civitai Utils] Hash for '{model_name}' not found. Forcing a refresh of the local file list...")
            _, filename_to_hash = utils.get_local_model_maps(self.FOLDER_KEY, force_sync=True)
            file_hash = filename_to_hash.get(model_name)
            if not file_hash:
                 raise Exception(f"Hash for '{model_name}' still not in DB after refresh. Please check the file.")

        fetched_items = utils.fetch_civitai_data_by_hash(file_hash, sort, image_limit, nsfw_level, filter_type if filter_type != "all" else None)
        all_metas = [item["meta"] for item in fetched_items if "meta" in item]
        if not all_metas:
            raise Exception("No images with metadata found on Civitai.")

        _, filename_to_lora_hash_map = utils.get_local_model_maps("loras")
        session_cache = {}
        required_version_ids = set()
        for meta in all_metas:
            if isinstance(meta.get("civitaiResources"), list):
                for res in meta["civitaiResources"]:
                    if isinstance(res, dict) and (version_id := res.get("modelVersionId")):
                        required_version_ids.add(version_id)

        domain = utils._get_active_domain()

        if required_version_ids:
            print(f"[Civitai Utils] Pre-caching {len(required_version_ids)} unique resource details...")
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(utils.CivitaiAPIUtils.get_model_version_info_by_id, vid, domain): vid for vid in required_version_ids}
                for future in tqdm(as_completed(futures), total=len(futures), desc="Pre-caching Resources"):
                    version_info = future.result()
                    vid = futures[future]
                    if version_info:
                        file_hash_val = version_info.get("files", [{}])[0].get("hashes", {}).get("SHA256")
                        session_cache[str(vid)] = {"info": version_info, "hash": file_hash_val.lower() if file_hash_val else None}

        assoc_stats = {"lora": {}, "model": {}}
        for meta in tqdm(all_metas, desc="Analyzing Resources (Fast)"):
            extracted = utils.extract_resources_from_meta(meta, filename_to_lora_hash_map, session_cache)
            for lora_info in extracted.get("loras", []):
                key = lora_info.get("hash") or lora_info.get("name")
                if not key: continue
                stats_dict = assoc_stats["lora"]
                if key not in stats_dict:
                    stats_dict[key] = {"count": 0, "weights": [], "name": lora_info.get("name") or key, "modelId": lora_info.get("modelId")}
                stats_dict[key]["count"] += 1
                stats_dict[key]["weights"].append(lora_info.get("weight", 1.0))
                if not stats_dict[key].get("modelId") and (vid := lora_info.get("modelVersionId")):
                     cached_resource = session_cache.get(str(vid))
                     if cached_resource and (version_info := cached_resource.get("info")):
                        if "modelId" in version_info:
                            stats_dict[key]["modelId"] = version_info["modelId"]
                            if version_info.get("model", {}).get("name"):
                                stats_dict[key]["name"] = version_info["model"]["name"]

        pos_tokens, neg_tokens = [], []
        for meta in all_metas:
            pos_tokens.extend(utils.CivitaiAPIUtils._parse_prompts(meta.get("prompt", "")))
            neg_tokens.extend(utils.CivitaiAPIUtils._parse_prompts(meta.get("negativePrompt", "")))
        pos_common = Counter(pos_tokens).most_common()
        neg_common = Counter(neg_tokens).most_common()

        param_counters = {key: Counter() for key in ["sampler", "scheduler", "cfgScale", "steps", "Size", "Denoising strength"]}
        for meta in all_metas:
            for key in param_counters:
                if val := meta.get(key): param_counters[key].update([str(val)])

        analysis_result = {
            "pos_common": pos_common, "neg_common": neg_common,
            "assoc_stats": assoc_stats,
            "param_counters": {k: dict(v) for k, v in param_counters.items()},
            "total_images": len(all_metas),
        }
        utils.db_manager.set_analysis_cache(data_fingerprint, analysis_result)
        return analysis_result

    def execute(self, model_name, image_limit, sort, nsfw_level, filter_type, summary_top_n, force_refresh):
        try:
            analysis_data = self._get_analysis_data(model_name, image_limit, sort, nsfw_level, filter_type, force_refresh)
            if not analysis_data:
                return ("Analysis failed.", "No data.", ())

            pos_common = analysis_data["pos_common"]
            neg_common = analysis_data["neg_common"]
            assoc_stats = analysis_data["assoc_stats"]
            param_counts_dict = analysis_data["param_counters"]
            total_images = analysis_data["total_images"]

            tag_report_md = utils.format_tags_as_markdown(pos_common, neg_common, summary_top_n)
            resource_report_md = utils.format_resources_as_markdown(assoc_stats, total_images, summary_top_n)
            param_report_md = utils.format_parameters_as_markdown(param_counts_dict, total_images, summary_top_n)

            top_sampler_raw = Counter(param_counts_dict.get("sampler", {})).most_common(1)[0][0] if param_counts_dict.get("sampler") else "Euler a"
            top_scheduler_raw = Counter(param_counts_dict.get("scheduler", {})).most_common(1)[0][0] if param_counts_dict.get("scheduler") else "Karras"
            final_sampler, final_scheduler = top_sampler_raw, top_scheduler_raw
            for sched in ["Karras", "SGM Uniform"]:
                if top_sampler_raw.endswith(f" {sched}"):
                    final_sampler, final_scheduler = top_sampler_raw[:-len(f" {sched}")], sched
                    break
            top_sampler_cleaned = utils.SAMPLER_SCHEDULER_MAP.get(final_sampler.strip(), "euler_ancestral")
            top_scheduler_cleaned = utils.SAMPLER_SCHEDULER_MAP.get(final_scheduler.strip(), "karras")
            top_steps = int(Counter(param_counts_dict.get("steps", {})).most_common(1)[0][0]) if param_counts_dict.get("steps") else 25
            top_cfg = float(Counter(param_counts_dict.get("cfgScale", {})).most_common(1)[0][0]) if param_counts_dict.get("cfgScale") else 7.0
            top_size_str = Counter(param_counts_dict.get("Size", {})).most_common(1)[0][0] if param_counts_dict.get("Size") else "512x512"
            try: top_width, top_height = map(int, top_size_str.split("x"))
            except: top_width, top_height = 512, 512
            top_denoise = float(Counter(param_counts_dict.get("Denoising strength", {})).most_common(1)[0][0]) if param_counts_dict.get("Denoising strength") else 1.0

            full_report_md = f"# Civitai Analysis for: {model_name}\n\n" + param_report_md + "\n\n" + resource_report_md + "\n\n" + tag_report_md
            summary = f"Analyzed {total_images} items for '{model_name}'."
            params_pipe = (model_name, "", "", -1, top_steps, top_cfg, top_sampler_cleaned, top_scheduler_cleaned, top_width, top_height, top_denoise)

            return (full_report_md, summary, params_pipe)

        except Exception as e:
            print(f"[{self.__class__.__name__}] An error occurred: {e}")
            import traceback; traceback.print_exc()
            return (f"Error: {e}", "Execution failed.", ())

class CivitaiModelAnalyzerCKPT(CivitaiModelAnalyzer):
    FOLDER_KEY = "checkpoints"

class CivitaiModelAnalyzerLORA(CivitaiModelAnalyzer):
    FOLDER_KEY = "loras"

class CivitaiParameterUnpacker:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"params_pipe": ("CIVITAI_PARAMS",)}}

    RETURN_TYPES = (get_db_model_list("checkpoints"), "STRING", "STRING", "INT", "INT", "FLOAT", comfy.samplers.KSampler.SAMPLERS, comfy.samplers.KSampler.SCHEDULERS, "INT", "INT", "FLOAT")
    RETURN_NAMES = ("ckpt_name", "positive_prompt", "negative_prompt", "seed", "steps", "cfg", "sampler", "scheduler", "width", "height", "denoise")
    FUNCTION = "execute"
    CATEGORY = "Civitai/📊 Analyzer"

    def execute(self, params_pipe):
        if not params_pipe or len(params_pipe) < 11:
            checkpoints = get_db_model_list("checkpoints")
            default_ckpt = checkpoints[0] if checkpoints else "none"
            return (default_ckpt, "", "", -1, 25, 7.0, "euler_ancestral", "karras", 512, 512, 1.0)

        (ckpt_name, pos, neg, seed, steps, cfg, sampler, scheduler, w, h, denoise) = params_pipe
        return (ckpt_name, pos, neg, seed, steps, cfg, sampler, scheduler, w, h, denoise)

# =================================================================================
# 3. 后端 API 路由
# =================================================================================
prompt_server = server.PromptServer.instance

def sanitize_filename(filename):
    filename = filename.replace("..", "").replace("\0", "")
    illegal_chars = r'<>:"/\\|?*\t\n\r'
    sanitized = re.sub(f'[{re.escape(illegal_chars)}]', '_', filename)
    name, ext = os.path.splitext(sanitized)
    name = name[:150]
    return f"{name}{ext}"

@prompt_server.routes.post("/civitai_utils/clear_cache")
async def clear_cache(request):
    try:
        data = await request.json()
        cache_type = data.get("cache_type")

        if cache_type == "analysis":
            utils.db_manager.clear_analysis_cache()
            message = "Analyzer cache cleared successfully."
        elif cache_type == "api_responses":
            utils.db_manager.clear_api_responses()
            message = "API response cache cleared successfully."
        elif cache_type == "triggers":
            utils.db_manager.clear_all_triggers()
            message = "Trigger word cache cleared successfully."
        elif cache_type == "all":
            utils.db_manager.clear_analysis_cache()
            utils.db_manager.clear_api_responses()
            utils.db_manager.clear_all_triggers()
            message = "All caches have been cleared."
        else:
            return web.json_response({"status": "error", "message": "Invalid cache type"}, status=400)

        return web.json_response({"status": "ok", "message": message})
    except Exception as e:
        print(f"[Civitai Utils] Error clearing cache: {e}")
        import traceback; traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@prompt_server.routes.get("/civitai_recipe_finder/fetch_data")
async def fetch_data(request):
    try:
        model_name, sort, nsfw_level, limit, filter_type = (
            request.query.get("model_name"), request.query.get("sort"),
            request.query.get("nsfw_level"), int(request.query.get("limit", 32)),
            request.query.get("filter_type"), )
        model_type_str, model_filename = model_name.split("/", 1)
        model_type = "checkpoints" if model_type_str == "CKPT" else "loras"
        _, filename_to_hash = utils.get_local_model_maps(model_type)
        model_hash = filename_to_hash.get(model_filename)
        if not model_hash:
            raise FileNotFoundError(f"Model hash not found for: {model_filename}")
        gallery_data = utils.fetch_civitai_data_by_hash(model_hash, sort, limit, nsfw_level, filter_type if filter_type != "all" else None,)
        return web.json_response({"status": "ok", "images": gallery_data})
    except Exception as e:
        print(f"Error in fetch_data: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@prompt_server.routes.post("/civitai_recipe_finder/set_selection")
async def set_selection(request):
    try:
        data = await request.json()
        node_id, item, download_image = (str(data.get("node_id")), data.get("item"), data.get("download_image", False))
        selections = utils.load_selections()
        selections[node_id] = {"item": item, "download_image": download_image}
        utils.save_selections(selections)
        utils.db_manager.set_setting("last_selection_time", time.time())
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@prompt_server.routes.post("/civitai_recipe_finder/save_original_image")
async def save_original_image(request):
    try:
        data = await request.json()
        image_url = data.get("url")
        if not image_url: return web.json_response({"status": "error", "message": "URL is missing"}, status=400)
        clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
        image_record = utils.db_manager.get_image_by_url(clean_url)
        if image_record and image_record["local_filename"]:
            local_path = os.path.join(folder_paths.get_output_directory(), image_record["local_filename"])
            if os.path.exists(local_path):
                return web.json_response({"status": "exists", "message": f"Image already exists: {image_record['local_filename']}"})
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(clean_url, headers=headers)

        base_filename = os.path.basename(urllib.parse.urlparse(clean_url).path)
        sanitized_base = sanitize_filename(base_filename)
        filename = f"civitai_{int(time.time())}_{sanitized_base}"

        output_path = os.path.join(folder_paths.get_output_directory(), filename)
        with urllib.request.urlopen(req, timeout=20) as response, open(output_path, "wb") as f:
            f.write(response.read())
        utils.db_manager.add_downloaded_image(url=clean_url, local_filename=filename)
        return web.json_response({"status": "ok", "message": f"Image saved as {filename}"})
    except Exception as e:
        print(f"[Civitai Utils] Error in save_original_image: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)

@prompt_server.routes.post("/civitai_recipe_finder/get_workflow_source")
async def get_workflow_source(request):
    try:
        data = await request.json()
        image_url = data.get("url")
        if not image_url: return web.Response(status=400, text="URL is missing")
        clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
        image_record = utils.db_manager.get_image_by_url(clean_url)
        if image_record and image_record["local_filename"]:
            local_path = os.path.join(folder_paths.get_output_directory(), image_record["local_filename"])
            if os.path.exists(local_path):
                with open(local_path, "rb") as f: image_data = f.read()
                ext = os.path.splitext(image_record["local_filename"])[1].lower()
                content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")
                return web.Response(body=image_data, content_type=content_type)
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(clean_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
            content_type = response.headers.get("Content-Type", "image/png")
        filename_base = os.path.basename(urllib.parse.urlparse(clean_url).path)
        sanitized_base = sanitize_filename(filename_base)
        filename = f"civitai_{int(time.time())}_{sanitized_base}"
        if not any(filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
            ext = "." + content_type.split("/")[-1] if "/" in content_type else ".png"
            filename += ext
        output_path = os.path.join(folder_paths.get_output_directory(), filename)
        with open(output_path, "wb") as f: f.write(image_data)
        utils.db_manager.add_downloaded_image(url=clean_url, local_filename=filename)
        return web.Response(body=image_data, content_type=content_type)
    except Exception as e:
        return web.Response(status=500, text=str(e))

@prompt_server.routes.get("/civitai_recipe_finder/get_config")
async def get_config(request):
    config = {"network_choice": utils.db_manager.get_setting("network_choice", "com")}
    return web.json_response(config)

@prompt_server.routes.post("/civitai_recipe_finder/set_config")
async def set_config(request):
    try:
        data = await request.json()
        if "network_choice" in data:
            utils.db_manager.set_setting("network_choice", data["network_choice"])
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# =================================================================================
# 4. 最终的节点映射
# =================================================================================
NODE_CLASS_MAPPINGS = {
    "CivitaiRecipeGallery": CivitaiRecipeGallery,
    "RecipeParamsParser": RecipeParamsParser,
    "LoraTriggerWords": LoraTriggerWords,
    "CivitaiModelAnalyzerCKPT": CivitaiModelAnalyzerCKPT,
    "CivitaiModelAnalyzerLORA": CivitaiModelAnalyzerLORA,
    "CivitaiParameterUnpacker": CivitaiParameterUnpacker,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "CivitaiRecipeGallery": "Recipe Gallery",
    "RecipeParamsParser": "Get Parameters from Recipe",
    "LoraTriggerWords": "Lora Trigger Words",
    "CivitaiModelAnalyzerCKPT": "Model Analyzer (Checkpoint)",
    "CivitaiModelAnalyzerLORA": "Model Analyzer (LoRA)",
    "CivitaiParameterUnpacker": "Get Parameters from Analysis",
}