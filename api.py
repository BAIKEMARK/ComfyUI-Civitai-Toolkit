import asyncio
import os
import time
import urllib.request
import urllib.parse
import folder_paths
from aiohttp import web
import server
import re

from . import utils


prompt_server = server.PromptServer.instance

def sanitize_filename(filename):
    filename = filename.replace("..", "").replace("\0", "")
    illegal_chars = r'<>:"/\\|?*\t\n\r'
    sanitized = re.sub(f"[{re.escape(illegal_chars)}]", "_", filename)
    name, ext = os.path.splitext(sanitized)
    name = name[:150]
    return f"{name}{ext}"

@prompt_server.routes.get("/civitai_utils/get_db_stats")
async def get_db_stats(request):
    try:
        stats = utils.db_manager.get_db_stats()
        return web.json_response({"status": "ok", "stats": stats})
    except Exception as e:
        print(f"[Civitai Utils] Error getting DB stats: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@prompt_server.routes.get("/civitai_utils/get_scanned_models")
async def get_scanned_models(request):
    """获取数据库中已扫描模型列表的API"""
    model_type = request.query.get("model_type")
    if not model_type or model_type not in ["checkpoints", "loras"]:
        return web.json_response({"status": "error", "message": "Invalid model_type"}, status=400)
    try:
        # force_sync=False 避免不必要的重复扫描
        model_list = utils.get_model_filenames_from_db(model_type, force_sync=False)
        return web.json_response({"status": "ok", "models": model_list})
    except Exception as e:
        print(f"[Civitai Utils] Error getting scanned models: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@prompt_server.routes.get("/civitai_utils/check_legacy_cache")
async def check_legacy_cache(request):
    """检查旧版缓存文件是否存在的API"""
    try:
        exists = utils.check_legacy_cache_exists()
        return web.json_response({"exists": exists})
    except Exception as e:
        return web.json_response({"exists": False, "error": str(e)})


@prompt_server.routes.post("/civitai_utils/force_rescan")
async def force_rescan(request):
    try:
        data = await request.json()
        model_type = data.get("model_type")
        rehash_all = data.get("rehash_all", False)

        if not model_type or model_type not in ["checkpoints", "loras"]:

            return web.json_response(
                {"status": "error", "message": "Invalid model_type"}, status=400
            )

        # 如果是 rehash_all，我们需要先清空数据库中的 mtime
        if rehash_all:
            with utils.db_manager.get_connection() as conn:
                conn.execute(
                    "UPDATE versions SET local_mtime = 0 WHERE model_type = ?",
                    (model_type,),
                )

        # 将计时器清零以确保扫描执行
        utils.db_manager.set_setting(f"last_sync_{model_type}", 0)
        # 执行扫描并捕获结果
        scan_results = utils.sync_local_files_with_db(model_type, force=True)
        found_count = scan_results.get("found", 0)
        hashed_count = scan_results.get("hashed", 0)

        if rehash_all:

            message = (
                f"Re-hash complete! {hashed_count} {model_type} files were re-hashed."
            )
        elif found_count > 0:
            message = f"Rescan complete! Found and processed {hashed_count} new/modified {model_type} files."
        else:
            message = f"Rescan complete. No new or modified {model_type} files found."

        return web.json_response({"status": "ok", "message": message})
    except Exception as e:
        print(f"[Civitai Utils] Error forcing rescan: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# 从旧版JSON迁移哈希的API
@prompt_server.routes.post("/civitai_utils/migrate_hashes")
async def migrate_hashes(request):
    try:
        results = utils.migrate_legacy_caches()
        return web.json_response({"status": "ok", "message": results["message"]})
    except Exception as e:
        print(f"[Civitai Utils] Error migrating hashes: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)


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
        import traceback
        traceback.print_exc()
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
        if not image_url:
            return web.json_response({"status": "error", "message": "URL is missing"}, status=400)
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
        if not image_url:
            return web.Response(status=400, text="URL is missing")
        clean_url = re.sub(r"/(width|height|fit|quality|format)=\w+", "", image_url)
        image_record = utils.db_manager.get_image_by_url(clean_url)
        if image_record and image_record["local_filename"]:
            local_path = os.path.join(folder_paths.get_output_directory(), image_record["local_filename"])
            if os.path.exists(local_path):
                with open(local_path, "rb") as f:
                    image_data = f.read()
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
        with open(output_path, "wb") as f:
            f.write(image_data)
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


@prompt_server.routes.get("/civitai_utils/get_local_models")
async def get_local_models(request):
    """
    一个强大、统一的API，一次性获取所有处理好的模型数据。
    """
    try:
        loop = asyncio.get_event_loop()
        force_refresh = request.query.get("force_refresh", "false").lower() == "true"

        # 将所有耗时的操作放入线程池，避免阻塞主服务器线程
        models = await loop.run_in_executor(
            None, utils.get_all_local_models_with_details, force_refresh
        )

        return web.json_response({"status": "ok", "models": models})
    except Exception as e:
        print(f"[Civitai Utils] FATAL ERROR in get_local_models API: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@prompt_server.routes.get("/civitai_utils/get_local_hashes")
async def get_local_hashes(request):
    """
    一个轻量级的API，仅返回数据库中所有本地文件的哈希列表。
    """
    try:
        with utils.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT hash FROM versions WHERE hash IS NOT NULL AND local_path IS NOT NULL")
            # 使用集合推导式以获得最佳性能
            hashes = {row["hash"] for row in cursor.fetchall()}
        return web.json_response({"status": "ok", "hashes": list(hashes)})
    except Exception as e:
        print(f"[Civitai Utils] Error getting local hashes: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)