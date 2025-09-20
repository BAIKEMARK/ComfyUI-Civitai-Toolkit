# import threading
# import os
# from collections import Counter
# import folder_paths
# import comfy
# import time
# import re
# import urllib.request
# import urllib.parse
# import io
# from PIL import Image
# import numpy as np
# import torch
# import server
# from aiohttp import web
# from . import utils
#
#
# # =================================================================================
# # 1. 核心节点：Civitai Recipe Gallery
# # =================================================================================
# class CivitaiRecipeGallery:
#     @classmethod
#     def IS_CHANGED(cls, **kwargs):
#         # 依赖于数据库中的时间戳来判断是否刷新
#         return utils.db_manager.get_setting("last_selection_time", time.time())
#
#     @classmethod
#     def INPUT_TYPES(cls):
#         # 保持不变，动态加载模型列表
#         checkpoints = [
#             "CKPT/" + f for f in folder_paths.get_filename_list("checkpoints")
#         ]
#         loras = ["LORA/" + f for f in folder_paths.get_filename_list("loras")]
#         return {
#             "required": {
#                 "model_name": (checkpoints + loras,),
#                 "sort": (["Most Reactions", "Most Comments", "Newest"],),
#                 "nsfw_level": (["None", "Soft", "Mature", "X"],),
#                 "image_limit": ("INT", {"default": 32, "min": 1, "max": 100}),
#                 "filter_type": (["all", "image", "video"], {"default": "image"}),
#             },
#             "hidden": {"unique_id": "UNIQUE_ID"},
#         }
#
#     RETURN_TYPES = ("IMAGE", "STRING", "RECIPE_PARAMS")
#     RETURN_NAMES = ("image", "info_md", "recipe_params")
#     FUNCTION = "execute"
#     CATEGORY = "Civitai"
#     OUTPUT_NODE = True
#
#     def execute(
#         self, model_name, sort, nsfw_level, image_limit, filter_type, unique_id
#     ):
#         # 使用新的数据库支持的函数获取模型哈希映射
#         lora_hash_map, lora_name_map = utils.get_local_model_maps("loras")
#         ckpt_hash_map, _ = utils.get_local_model_maps("checkpoints")
#
#         selections = utils.load_selections()
#         node_selection = selections.get(str(unique_id), {})
#         item_data = node_selection.get("item", {})
#         should_download = node_selection.get("download_image", False)
#         meta = item_data.get("meta", {})
#         if not isinstance(meta, dict):
#             meta = {}
#
#
#         extracted = utils.extract_resources_from_meta(meta, lora_name_map)
#         recipe_loras, ckpt_hash = extracted["loras"], extracted["ckpt_hash"]
#
#         ckpt_name = "unknown"
#         if ckpt_hash:
#             # 兼容处理可能不完整的哈希
#             for full_hash, filename in ckpt_hash_map.items():
#                 if full_hash.startswith(ckpt_hash.lower()):
#                     ckpt_name = filename
#                     break
#         if ckpt_name == "unknown":
#             ckpt_name = extracted.get("ckpt_name", "unknown")
#
#         image_url = item_data.get("url")
#         image_tensor = torch.zeros(1, 64, 64, 3)  # 默认空图像
#         if should_download and image_url:
#             clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
#             image_tensor = self.download_image(clean_url)
#
#         # 调用更新后的函数，不再需要传递 cache 和 lock
#         info_md = utils.format_info_as_markdown(meta, recipe_loras, lora_hash_map)
#         params_pack = self.pack_recipe_params(meta, ckpt_name)
#
#         return (image_tensor, info_md, params_pack)
#
#     def pack_recipe_params(self, meta, ckpt_name):
#         if not meta:
#             return ()
#         sampler_raw = meta.get("sampler", "Euler a")
#         scheduler_raw = meta.get("scheduler", "normal")
#         final_sampler, final_scheduler = sampler_raw, scheduler_raw
#         known_schedulers = ["Karras"]
#         for sched in known_schedulers:
#             suffix = f" {sched}"
#             if sampler_raw.endswith(suffix):
#                 final_sampler, final_scheduler = sampler_raw[: -len(suffix)], sched
#                 break
#         try:
#             width, height = map(int, meta.get("Size").split("x"))
#         except:
#             width, height = 512, 512
#         return (
#             ckpt_name,
#             meta.get("prompt", ""),
#             meta.get("negativePrompt", ""),
#             int(meta.get("seed", -1)),
#             int(meta.get("steps", 25)),
#             float(meta.get("cfgScale", 7.0)),
#             utils.SAMPLER_SCHEDULER_MAP.get(final_sampler, final_sampler),
#             utils.SAMPLER_SCHEDULER_MAP.get(final_scheduler, final_scheduler),
#             width,
#             height,
#             float(meta.get("Denoising strength", 1.0)),
#         )
#
#     def download_image(self, url):
#         try:
#             req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
#             with urllib.request.urlopen(req, timeout=20) as response:
#                 img_data = response.read()
#             img = Image.open(io.BytesIO(img_data)).convert("RGB")
#             img_np = np.array(img).astype(np.float32) / 255.0
#             return torch.from_numpy(img_np)[None,]
#         except Exception as e:
#             print(f"[CivitaiRecipeGallery] Failed to download image from {url}: {e}")
#             return torch.zeros(1, 64, 64, 3)
#
#
# # =================================================================================
# # 2. 配套节点：Recipe Params Parser
# # =================================================================================
# class RecipeParamsParser:
#     @classmethod
#     def INPUT_TYPES(cls):
#         return {"required": {"recipe_params": ("RECIPE_PARAMS",)}}
#
#     RETURN_TYPES = (
#         folder_paths.get_filename_list("checkpoints"),
#         "STRING",
#         "STRING",
#         "INT",
#         "INT",
#         "FLOAT",
#         comfy.samplers.KSampler.SAMPLERS,
#         comfy.samplers.KSampler.SCHEDULERS,
#         "INT",
#         "INT",
#         "FLOAT",
#     )
#     RETURN_NAMES = (
#         "ckpt_name",
#         "positive_prompt",
#         "negative_prompt",
#         "seed",
#         "steps",
#         "cfg",
#         "sampler_name",
#         "scheduler",
#         "width",
#         "height",
#         "denoise[hires.fix]",
#     )
#     FUNCTION = "execute"
#     CATEGORY = "Civitai/Utils"
#
#     def execute(self, recipe_params):
#         if not recipe_params or len(recipe_params) < 11:
#             checkpoints = folder_paths.get_filename_list("checkpoints")
#             default_ckpt = checkpoints[0] if checkpoints else "none"
#             return (
#                 default_ckpt,
#                 "",
#                 "",
#                 -1,
#                 25,
#                 7.0,
#                 "euler_ancestral",
#                 "normal",
#                 512,
#                 512,
#                 1.0,
#             )
#         return recipe_params
#
#
# # =================================================================================
# # 3. 后端 API 路由
# # =================================================================================
# prompt_server = server.PromptServer.instance
#
#
# @prompt_server.routes.get("/civitai_recipe_finder/fetch_data")
# async def fetch_data(request):
#     try:
#         model_name, sort, nsfw_level, limit, filter_type = (
#             request.query.get("model_name"),
#             request.query.get("sort"),
#             request.query.get("nsfw_level"),
#             int(request.query.get("limit", 32)),
#             request.query.get("filter_type"),
#         )
#         model_type_str, model_filename = model_name.split("/", 1)
#         model_type = "checkpoints" if model_type_str == "CKPT" else "loras"
#
#         # 使用新的数据库支持的哈希查找
#         _, filename_to_hash = utils.get_local_model_maps(model_type)
#         model_hash = filename_to_hash.get(model_filename)
#
#         if not model_hash:
#             raise FileNotFoundError(f"Model hash not found for: {model_filename}")
#
#         # 调用新的、支持分页和筛选的 fetch 函数
#         gallery_data = utils.fetch_civitai_data_by_hash(
#             model_hash,
#             sort,
#             limit,
#             nsfw_level,
#             filter_type if filter_type != "all" else None,
#         )
#         return web.json_response({"status": "ok", "images": gallery_data})
#     except Exception as e:
#         print(f"Error in fetch_data: {e}")
#         return web.json_response({"status": "error", "message": str(e)}, status=500)
#
#
# @prompt_server.routes.post("/civitai_recipe_finder/set_selection")
# async def set_selection(request):
#     try:
#         data = await request.json()
#         node_id, item, download_image = (
#             str(data.get("node_id")),
#             data.get("item"),
#             data.get("download_image", False),
#         )
#
#         selections = utils.load_selections()
#         selections[node_id] = {"item": item, "download_image": download_image}
#         utils.save_selections(selections)
#
#         # 更新时间戳以触发 IS_CHANGED
#         utils.db_manager.set_setting("last_selection_time", time.time())
#
#         return web.json_response({"status": "ok"})
#     except Exception as e:
#         return web.json_response({"status": "error", "message": str(e)}, status=500)
#
#
# @prompt_server.routes.post("/civitai_recipe_finder/save_original_image")
# async def save_original_image(request):
#     try:
#         data = await request.json()
#         image_url = data.get("url")
#         if not image_url:
#             return web.json_response(
#                 {"status": "error", "message": "URL is missing"}, status=400
#             )
#
#         clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
#
#         # 使用数据库检查文件是否存在
#         image_record = utils.db_manager.get_image_by_url(clean_url)
#         if image_record and image_record["local_filename"]:
#             local_path = os.path.join(
#                 folder_paths.get_output_directory(), image_record["local_filename"]
#             )
#             if os.path.exists(local_path):
#                 print(
#                     f"[Civitai Utils] Image already exists: {image_record['local_filename']}"
#                 )
#                 return web.json_response(
#                     {
#                         "status": "exists",
#                         "message": f"Image already exists: {image_record['local_filename']}",
#                     }
#                 )
#
#         headers = {"User-Agent": "Mozilla/5.0"}
#         req = urllib.request.Request(clean_url, headers=headers)
#         filename = f"civitai_{int(time.time())}_{os.path.basename(urllib.parse.urlparse(clean_url).path)}"
#         output_path = os.path.join(folder_paths.get_output_directory(), filename)
#
#         with urllib.request.urlopen(req, timeout=20) as response:
#             with open(output_path, "wb") as f:
#                 f.write(response.read())
#
#         # 下载成功后，更新数据库
#         utils.db_manager.add_downloaded_image(url=clean_url, local_filename=filename)
#         return web.json_response(
#             {"status": "ok", "message": f"Image saved as {filename}"}
#         )
#     except Exception as e:
#         return web.json_response({"status": "error", "message": str(e)}, status=500)
#
#
# @prompt_server.routes.post("/civitai_recipe_finder/get_workflow_source")
# async def get_workflow_source(request):
#     try:
#         data = await request.json()
#         image_url = data.get("url")
#         if not image_url:
#             return web.Response(status=400, text="URL is missing")
#
#         clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
#
#         # 从数据库检查本地文件
#         image_record = utils.db_manager.get_image_by_url(clean_url)
#         if image_record and image_record["local_filename"]:
#             local_path = os.path.join(
#                 folder_paths.get_output_directory(), image_record["local_filename"]
#             )
#             if os.path.exists(local_path):
#                 print(
#                     f"[Civitai Utils] Workflow source found locally: {image_record['local_filename']}"
#                 )
#                 with open(local_path, "rb") as f:
#                     image_data = f.read()
#                 ext = os.path.splitext(image_record["local_filename"])[1].lower()
#                 content_type = {
#                     ".png": "image/png",
#                     ".jpg": "image/jpeg",
#                     ".jpeg": "image/jpeg",
#                     ".webp": "image/webp",
#                 }.get(ext, "image/png")
#                 return web.Response(body=image_data, content_type=content_type)
#
#         # 本地没有，则下载
#         print(
#             f"[Civitai Utils] Workflow source not found. Downloading from: {clean_url}"
#         )
#         headers = {"User-Agent": "Mozilla/5.0"}
#         req = urllib.request.Request(clean_url, headers=headers)
#         with urllib.request.urlopen(req, timeout=20) as response:
#             image_data = response.read()
#             content_type = response.headers.get("Content-Type", "image/png")
#
#         filename_base = os.path.basename(urllib.parse.urlparse(clean_url).path)
#         filename = f"civitai_{int(time.time())}_{filename_base}"
#         if not any(
#             filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]
#         ):
#             ext = "." + content_type.split("/")[-1] if "/" in content_type else ".png"
#             filename += ext
#
#         output_path = os.path.join(folder_paths.get_output_directory(), filename)
#         with open(output_path, "wb") as f:
#             f.write(image_data)
#
#         # 更新数据库
#         utils.db_manager.add_downloaded_image(url=clean_url, local_filename=filename)
#
#         return web.Response(body=image_data, content_type=content_type)
#
#     except Exception as e:
#         print(f"[Civitai Utils] Error in get_workflow_source: {e}")
#         return web.Response(status=500, text=str(e))
#
#
# @prompt_server.routes.get("/civitai_recipe_finder/get_config")
# async def get_config(request):
#     config = {"network_choice": utils.db_manager.get_setting("network_choice", "com")}
#     return web.json_response(config)
#
#
# @prompt_server.routes.post("/civitai_recipe_finder/set_config")
# async def set_config(request):
#     try:
#         data = await request.json()
#         if "network_choice" in data:
#             utils.db_manager.set_setting("network_choice", data["network_choice"])
#         return web.json_response({"status": "ok"})
#     except Exception as e:
#         return web.json_response({"status": "error", "message": str(e)}, status=500)
#
#
# # =================================================================================
# # 4. 最终的节点映射
# # =================================================================================
# NODE_CLASS_MAPPINGS = {
#     "CivitaiRecipeGallery": CivitaiRecipeGallery,
#     "RecipeParamsParser": RecipeParamsParser,
# }
# NODE_DISPLAY_NAME_MAPPINGS = {
#     "CivitaiRecipeGallery": "Civitai Recipe Gallery",
#     "RecipeParamsParser": "Recipe Params Parser",
# }