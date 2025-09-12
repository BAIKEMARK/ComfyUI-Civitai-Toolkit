import threading
import folder_paths
import torch
import server
import json
from aiohttp import web
import urllib.request
import urllib.parse
import io
from PIL import Image
import numpy as np
import os
import comfy.samplers
import time
import re
from . import utils


# =================================================================================
# 1. 核心节点：Civitai Recipe Gallery
# =================================================================================
class CivitaiRecipeGallery:
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if os.path.exists(utils.SELECTIONS_FILE):
            return os.path.getmtime(utils.SELECTIONS_FILE)
        return float("inf")

    @classmethod
    def INPUT_TYPES(cls):
        checkpoints = [
            "CKPT/" + f for f in folder_paths.get_filename_list("checkpoints")
        ]
        loras = ["LORA/" + f for f in folder_paths.get_filename_list("loras")]
        return {
            "required": {
                "model_name": (checkpoints + loras,),
                "sort": (["Most Reactions", "Most Comments", "Newest"],),
                "nsfw_level": (["None", "Soft", "Mature", "X"],),
                "image_limit": ("INT", {"default": 32, "min": 1, "max": 100}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    RETURN_TYPES = ("IMAGE", "STRING", "RECIPE_PARAMS")
    RETURN_NAMES = ("image", "info_md", "recipe_params")

    FUNCTION = "execute"
    CATEGORY = "Civitai"
    OUTPUT_NODE = True

    def execute(self, model_name, sort, nsfw_level, image_limit, unique_id):
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
        lora_hash_map, lora_name_map = utils.update_model_hash_cache("loras")
        ckpt_hash_map, _ = utils.update_model_hash_cache("checkpoints")

        selections = utils.load_selections()
        node_selection = selections.get(str(unique_id), {})
        item_data = node_selection.get("item", {})
        should_download = node_selection.get("download_image", False)
        meta = item_data.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        extracted = utils.extract_resources_from_meta(
            meta, lora_name_map, SESSION_CACHE, cache_lock
        )
        recipe_loras, ckpt_hash = extracted["loras"], extracted["ckpt_hash"]
        ckpt_name = "unknown"
        if ckpt_hash:
            for full_hash, filename in ckpt_hash_map.items():
                if full_hash.startswith(ckpt_hash.lower()):
                    ckpt_name = filename
                    break
        if ckpt_name == "unknown":
            ckpt_name = extracted.get("ckpt_name", "unknown")

        image_url = item_data.get("url")
        if should_download and image_url:
            clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
            image_tensor = self.download_image(clean_url)
        else:
            image_tensor = torch.zeros(1, 64, 64, 3)

        info_md = utils.format_info_as_markdown(
            meta, recipe_loras, lora_hash_map, SESSION_CACHE, cache_lock
        )

        params_pack = self.pack_recipe_params(meta, ckpt_name)

        with cache_lock:
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "version_info_cache.json"),
                SESSION_CACHE["version_info"],
            )
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "id_to_hash_cache.json"),
                SESSION_CACHE["id_to_hash"],
            )

        return (image_tensor, info_md, params_pack)

    def pack_recipe_params(self, meta, ckpt_name):
        if not meta:
            return ()
        sampler_raw = meta.get("sampler", "Euler a")
        scheduler_raw = meta.get("scheduler", "normal")
        final_sampler, final_scheduler = sampler_raw, scheduler_raw
        known_schedulers = ["Karras"]
        for sched in known_schedulers:
            suffix = f" {sched}"
            if sampler_raw.endswith(suffix):
                final_sampler, final_scheduler = sampler_raw[: -len(suffix)], sched
                break
        try:
            width, height = map(int, meta.get("Size").split("x"))
        except:
            width, height = 512, 512
        return (
            ckpt_name,
            meta.get("prompt", ""),
            meta.get("negativePrompt", ""),
            int(meta.get("seed", -1)),
            int(meta.get("steps", 25)),
            float(meta.get("cfgScale", 7.0)),
            utils.SAMPLER_SCHEDULER_MAP.get(final_sampler, final_sampler),
            utils.SAMPLER_SCHEDULER_MAP.get(final_scheduler, final_scheduler),
            width,
            height,
            float(meta.get("Denoising strength", 1.0)),
        )

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


# =================================================================================
# 2. 配套节点：Recipe Params Parser
# =================================================================================
class RecipeParamsParser:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"recipe_params": ("RECIPE_PARAMS",)}}

    RETURN_TYPES = (
        folder_paths.get_filename_list("checkpoints"),
        "STRING",
        "STRING",
        "INT",
        "INT",
        "FLOAT",
        comfy.samplers.KSampler.SAMPLERS,
        comfy.samplers.KSampler.SCHEDULERS,
        "INT",
        "INT",
        "FLOAT",
    )
    RETURN_NAMES = (
        "ckpt_name",
        "positive_prompt",
        "negative_prompt",
        "seed",
        "steps",
        "cfg",
        "sampler_name",
        "scheduler",
        "width",
        "height",
        "denoise[hires.fix]",
    )
    FUNCTION = "execute"
    CATEGORY = "Civitai/Utils"

    def execute(self, recipe_params):
        if not recipe_params or len(recipe_params) < 11:
            checkpoints = folder_paths.get_filename_list("checkpoints")
            default_ckpt = checkpoints[0] if checkpoints else "none"
            return (
                default_ckpt,
                "",
                "",
                -1,
                25,
                7.0,
                "euler_ancestral",
                "normal",
                512,
                512,
                1.0,
            )
        return recipe_params


# =================================================================================
# 3. 后端 API 路由
# =================================================================================
prompt_server = server.PromptServer.instance


@prompt_server.routes.get("/civitai_recipe_finder/fetch_data")
async def fetch_data(request):
    try:
        model_name, sort, nsfw_level, limit = (
            request.query.get("model_name"),
            request.query.get("sort"),
            request.query.get("nsfw_level"),
            int(request.query.get("limit", 32)),
        )
        model_type_str, model_filename = model_name.split("/", 1)
        model_type = "checkpoints" if model_type_str == "CKPT" else "loras"
        model_path = folder_paths.get_full_path(model_type, model_filename)
        if not model_path:
            raise FileNotFoundError(f"Model not found: {model_filename}")
        model_hash = utils.CivitaiAPIUtils.get_cached_sha256(model_path)
        gallery_data = utils.fetch_civitai_data_by_hash(
            model_hash, sort, limit, nsfw_level
        )
        return web.json_response({"status": "ok", "images": gallery_data})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@prompt_server.routes.post("/civitai_recipe_finder/set_selection")
async def set_selection(request):
    try:
        data = await request.json()
        node_id, item, download_image = (
            str(data.get("node_id")),
            data.get("item"),
            data.get("download_image", False),
        )
        selections = utils.load_selections()
        selections[node_id] = {"item": item, "download_image": download_image}
        utils.save_selections(selections)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@prompt_server.routes.post("/civitai_recipe_finder/save_original_image")
async def save_original_image(request):
    try:
        data = await request.json()
        image_url = data.get("url")
        if not image_url:
            return web.json_response(
                {"status": "error", "message": "URL is missing"}, status=400
            )
        clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)

        # 步骤1：首先检查索引
        download_index = utils.load_download_index()
        if clean_url in download_index:
            existing_file = download_index[clean_url]
            # 验证文件是否仍然存在于磁盘上
            if os.path.exists(os.path.join(folder_paths.get_output_directory(), existing_file)):
                print(f"[CivitaiRecipeGallery] Image already exists: {existing_file}")
                return web.json_response(
                    {"status": "exists", "message": f"Image already exists: {existing_file}"}
                )

        # 步骤2：如果未找到，则继续下载
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(clean_url, headers=headers)
        filename = f"civitai_{int(time.time())}_{os.path.basename(urllib.parse.urlparse(clean_url).path)}"
        output_path = os.path.join(folder_paths.get_output_directory(), filename)
        with urllib.request.urlopen(req, timeout=20) as response:
            with open(output_path, "wb") as f:
                f.write(response.read())
        # 步骤3：下载成功后，更新索引
        download_index[clean_url] = filename
        utils.save_download_index(download_index)
        return web.json_response(
            {"status": "ok", "message": f"Image saved as {filename}"}
        )
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# =================================================================================
# ===== API 接口: 一次性完成保存和获取图片数据，避免重复下载 =====
# =================================================================================
@prompt_server.routes.post("/civitai_recipe_finder/get_workflow_source")
async def get_workflow_source(request):
    """
    智能地提供用于提取工作流的图片数据。先检查本地是否存在副本，如果找不到，再进行下载。
    """
    try:
        data = await request.json()
        image_url = data.get("url")
        if not image_url:
            return web.Response(status=400, text="URL is missing")

        clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)

        # 步骤1：检查索引，看是否存在本地文件
        download_index = utils.load_download_index()
        if clean_url in download_index:
            existing_filename = download_index[clean_url]
            local_path = os.path.join(
                folder_paths.get_output_directory(), existing_filename
            )

            if os.path.exists(local_path):
                print(
                    f"[CivitaiRecipeGallery] Workflow source found locally: {existing_filename}"
                )
                with open(local_path, "rb") as f:
                    image_data = f.read()

                # 尝试从扩展名判断内容类型，默认为 png
                ext = os.path.splitext(existing_filename)[1].lower()
                content_type_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                }
                content_type = content_type_map.get(ext, "image/png")

                return web.Response(body=image_data, content_type=content_type)

        # 步骤2：如果本地找不到，则从 Civitai 下载
        print(
            f"[CivitaiRecipeGallery] Workflow source not found locally. Downloading from: {clean_url}"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(clean_url, headers=headers)

        with urllib.request.urlopen(req, timeout=20) as response:
            image_data = response.read()
            content_type = response.headers.get("Content-Type", "image/png")

        # 步骤3：保存新文件并更新索引
        filename_base = os.path.basename(urllib.parse.urlparse(clean_url).path)
        filename = f"civitai_{int(time.time())}_{filename_base}"
        if not any(
            filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]
        ):
            ext = "." + content_type.split("/")[-1] if "/" in content_type else ".png"
            filename += ext

        output_path = os.path.join(folder_paths.get_output_directory(), filename)
        with open(output_path, "wb") as f:
            f.write(image_data)

        # 更新并保存索引
        download_index[clean_url] = filename
        utils.save_download_index(download_index)

        return web.Response(body=image_data, content_type=content_type)

    except Exception as e:
        print(f"[CivitaiRecipeFinder] Error in get_workflow_source: {e}")
        return web.Response(status=500, text=str(e))

@prompt_server.routes.get("/civitai_recipe_finder/get_config")
async def get_config(request):
    """Gets the current config from the file."""
    config = utils._load_config()
    return web.json_response(config)


@prompt_server.routes.post("/civitai_recipe_finder/set_config")
async def set_config(request):
    """Saves the config to the file."""
    try:
        data = await request.json()
        current_config = utils._load_config()
        if "network_choice" in data:
            current_config["network_choice"] = data["network_choice"]
        utils._save_config(current_config)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


# =================================================================================
# 4. 最终的节点映射
# =================================================================================
NODE_CLASS_MAPPINGS = {
    "CivitaiRecipeGallery": CivitaiRecipeGallery,
    "RecipeParamsParser": RecipeParamsParser,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "CivitaiRecipeGallery": "Civitai Recipe Gallery",
    "RecipeParamsParser": "Recipe Params Parser",
}