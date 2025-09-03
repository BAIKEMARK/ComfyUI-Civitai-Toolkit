import threading

import folder_paths
import torch
import server
import json
from aiohttp import web
import urllib.request
import io
from PIL import Image
import numpy as np
import os

from . import utils


class CivitaiRecipeGallery:
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if os.path.exists(utils.SELECTIONS_FILE):
            return os.path.getmtime(utils.SELECTIONS_FILE)
        return float("inf")

    @classmethod
    def INPUT_TYPES(s):
        checkpoints = ["CKPT/" + f for f in folder_paths.get_filename_list("checkpoints")]
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

    # RETURN_TYPES AND RETURN_NAMES in CivitaiRecipeGallery class
    RETURN_TYPES = (
        "STRING","STRING","INT","INT","FLOAT","STRING","STRING","IMAGE",
        "STRING","INT","INT","FLOAT",
        "STRING","STRING",  # info, loras_info
        "STRING","STRING",)  # info_md, loras_info_md
    RETURN_NAMES = (
        "positive_prompt","negative_prompt","seed","steps","cfg","sampler_name","scheduler","image",
        "ckpt_name","width","height","denoise",
        "info","loras_info",
        "info_md","loras_info_md",
    )

    FUNCTION = "execute"
    CATEGORY = "Civitai"
    OUTPUT_NODE = True

    # def execute(self, model_name, sort, nsfw_level, image_limit, unique_id):
    #     selections = utils.load_selections()
    #     node_selection = selections.get(str(unique_id), {})
    #     item_data = node_selection.get("item", {})
    #     should_download = node_selection.get("download_image", False)
    #
    #     meta = item_data.get("meta", {})
    #     if not isinstance(meta, dict):
    #         meta = {}
    #
    #     # 调用“万能解析引擎”，并传入反向映射表
    #     extracted_resources = utils.extract_resources_from_meta(
    #         meta, self.lora_name_map
    #     )
    #     recipe_loras = extracted_resources["loras"]
    #     ckpt_hash = extracted_resources["ckpt_hash"]
    #
    #     ckpt_name_from_hash = "unknown"
    #     if ckpt_hash:
    #         for full_hash, filename in self.ckpt_hash_map.items():
    #             if full_hash.startswith(ckpt_hash.lower()):
    #                 ckpt_name_from_hash = filename
    #                 break
    #     if ckpt_name_from_hash == "unknown":
    #         ckpt_name_from_hash = extracted_resources.get("ckpt_name", "unknown")
    #
    #     parsed_meta = self.parse_metadata(meta)
    #     parsed_meta["ckpt_name"] = ckpt_name_from_hash
    #
    #     info_dict = meta.copy()
    #     info_dict.pop("prompt", None)
    #     info_dict.pop("negativePrompt", None)
    #     info_string = json.dumps(info_dict, indent=4, ensure_ascii=False)
    #
    #     image_tensor = torch.zeros(1, 64, 64, 3)
    #     if should_download:
    #         image_url = item_data.get("url")
    #         if image_url:
    #             image_tensor = self.download_image(image_url)
    #
    #     loras_info_report, found_loras_report, missing_loras_report = [], [], []
    #     if not recipe_loras:
    #         loras_info_report.append("--- No LoRAs Used in Recipe ---")
    #     else:
    #         for lora_hash, strength in recipe_loras.items():
    #             lora_filename = self.lora_hash_map.get(lora_hash.lower())
    #             strength_val = utils.safe_float_conversion(strength)
    #             if lora_filename:
    #                 found_loras_report.append(
    #                     f"[FOUND] {lora_filename} (Strength: {strength_val:.2f})"
    #                 )
    #             else:
    #                 info = utils.get_civitai_info_from_hash(lora_hash)
    #                 if info:
    #                     missing_loras_report.append(
    #                         f"[MISSING] {info['name']} (Strength: {strength_val:.2f})\n  - Hash: {lora_hash}\n  - URL: {info['url']}"
    #                     )
    #                 else:
    #                     missing_loras_report.append(
    #                         f"[MISSING] Unknown LoRA (Strength: {strength_val:.2f})\n  - Hash: {lora_hash}\n  - URL: Not Found"
    #                     )
    #         loras_info_report.append("--- LoRAs Used in Recipe ---")
    #         if found_loras_report:
    #             loras_info_report.extend(found_loras_report)
    #         if missing_loras_report:
    #             (
    #                 loras_info_report.append("\n--- Missing LoRAs ---"),
    #                 loras_info_report.extend(missing_loras_report),
    #             )
    #
    #     final_loras_report = "\n".join(loras_info_report)
    #
    #     return (
    #         parsed_meta["positive_prompt"],
    #         parsed_meta["negative_prompt"],
    #         parsed_meta["seed"],
    #         parsed_meta["steps"],
    #         parsed_meta["cfg"],
    #         parsed_meta["sampler_name"],
    #         parsed_meta["scheduler"],
    #         image_tensor,
    #         parsed_meta["ckpt_name"],
    #         parsed_meta["width"],
    #         parsed_meta["height"],
    #         parsed_meta["denoise"],
    #         info_string,
    #         final_loras_report,
    #     )
    # execute method in CivitaiRecipeGallery class

    def execute(self, model_name, sort, nsfw_level, image_limit, unique_id):
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
        # --- 为GalleryNode也创建一个线程锁，保持逻辑一致和安全 ---
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

        # --- 核心修正：调用函数时，传入 session_cache 和 lock ---
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

        parsed_meta = self.parse_metadata(meta)
        parsed_meta["ckpt_name"] = ckpt_name
        image_tensor = (
            self.download_image(item_data.get("url"))
            if should_download and item_data.get("url")
            else torch.zeros(1, 64, 64, 3)
        )

        info_string = json.dumps(meta, indent=2, ensure_ascii=False) if meta else "{}"
        info_md = utils.format_info_as_markdown(meta)

        # (LoRA报告生成逻辑保持不变，但其内部的API调用现在会通过session_cache和lock，变得更安全高效)
        loras_info_parts, loras_md_parts = [], []
        if not recipe_loras:
            loras_info_parts.append("--- No LoRAs Used ---")
            loras_md_parts.append("### No LoRAs Used")
        else:
            found_loras, missing_loras = [], []
            found_loras_md, missing_loras_md = [], []
            for lora in recipe_loras:
                lora_hash = lora.get("hash")
                strength_val = utils.safe_float_conversion(lora.get("weight", 1.0))
                filename = lora_hash_map.get(lora_hash.lower()) if lora_hash else None
                if filename:
                    found_loras.append(
                        f"[FOUND] {filename} (Strength: {strength_val:.2f})"
                    )
                    found_loras_md.append(
                        f"- **[FOUND]** `{filename}` (Strength: **{strength_val:.2f}**)"
                    )
                else:
                    civitai_info = None
                    version_id = lora.get("modelVersionId")
                    if version_id:
                        version_info = (
                            utils.CivitaiAPIUtils.get_model_version_info_by_id(
                                version_id, SESSION_CACHE, cache_lock
                            )
                        )
                        if version_info and version_info.get("modelId"):
                            parent_model_id = version_info.get("modelId")
                            model_name = version_info.get("model", {}).get("name")
                            civitai_info = {
                                "name": model_name,
                                "url": f"https://civitai.com/models/{parent_model_id}",
                            }
                    if not civitai_info and lora_hash:
                        # 虽然get_civitai_info_from_hash没有直接使用lock，但其内部调用的函数现在会用
                        civitai_info = utils.get_civitai_info_from_hash(
                            lora_hash, SESSION_CACHE, cache_lock
                        )
                    if civitai_info:
                        missing_loras.append(
                            f"[MISSING] {civitai_info['name']} (Strength: {strength_val:.2f})\n  - URL: {civitai_info['url']}"
                        )
                        missing_loras_md.append(
                            f"- **[MISSING]** [{civitai_info['name']}]({civitai_info['url']}) (Strength: **{strength_val:.2f}**)"
                        )
                    else:
                        name_to_show = lora.get("name") or "Unknown LoRA"
                        details = (
                            f"Hash: {lora_hash}" if lora_hash else "(Hash not found)"
                        )
                        missing_loras.append(
                            f"[MISSING] {name_to_show} (Strength: {strength_val:.2f})\n  - {details}"
                        )
                        missing_loras_md.append(
                            f"- **[MISSING]** `{name_to_show}` (Strength: **{strength_val:.2f}**) *({details})*"
                        )
            if found_loras:
                loras_info_parts.extend(["--- Found LoRAs ---"] + found_loras)
                loras_md_parts.extend(["### Found LoRAs"] + found_loras_md)
            if missing_loras:
                loras_info_parts.extend(["\n--- Missing LoRAs ---"] + missing_loras)
                loras_md_parts.extend(["\n### Missing LoRAs"] + missing_loras_md)

        final_loras_report = "\n".join(loras_info_parts)
        final_loras_md_report = "\n".join(loras_md_parts)

        # --- 在末尾一次性回写更新后的缓存 ---
        with cache_lock:
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "version_info_cache.json"),
                SESSION_CACHE["version_info"],
            )
            utils.save_json_to_file(
                os.path.join(utils.CACHE_DIR, "id_to_hash_cache.json"),
                SESSION_CACHE["id_to_hash"],
            )

        return (
            parsed_meta["positive_prompt"],
            parsed_meta["negative_prompt"],
            parsed_meta["seed"],
            parsed_meta["steps"],
            parsed_meta["cfg"],
            parsed_meta["sampler_name"],
            parsed_meta["scheduler"],
            image_tensor,
            parsed_meta["ckpt_name"],
            parsed_meta["width"],
            parsed_meta["height"],
            parsed_meta["denoise"],
            info_string,
            final_loras_report,
            info_md,
            final_loras_md_report,
        )

    def parse_metadata(self, meta):
        def safe_int(value, default):
            if isinstance(value, int):
                return value
            try:
                return int(float(value))
            except (ValueError, TypeError, AttributeError):
                return default

        def safe_float(value, default):
            if isinstance(value, (float, int)):
                return float(value)
            try:
                return float(value)
            except (ValueError, TypeError, AttributeError):
                return default

        return {
            "positive_prompt": meta.get("prompt", ""),
            "negative_prompt": meta.get("negativePrompt", ""),
            "seed": safe_int(meta.get("seed"), -1),
            "steps": safe_int(meta.get("steps"), 30),
            "cfg": safe_float(meta.get("cfgScale"), 7.0),
            "sampler_name": meta.get("sampler", "euler"),
            "scheduler": meta.get("scheduler", "normal"),
            "denoise": safe_float(meta.get("Denoising strength"), 1.0),
            "width": safe_int(meta.get("width"), 512),
            "height": safe_int(meta.get("height"), 512),
            "ckpt_name": "unknown",
        }

    def download_image(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                img_data = response.read()
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
            img_np = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(img_np)[None,]
        except Exception as e:
            print(f"[CivitaiRecipeFinder] Failed to download image from {url}: {e}")
            return torch.zeros(1, 64, 64, 3)


# --- API Routes ---
prompt_server = server.PromptServer.instance

@prompt_server.routes.post("/civitai_recipe_finder/set_selection")
async def set_selection(request):
    try:
        data = await request.json()
        node_id = str(data.get("node_id"))
        selections = utils.load_selections()
        selections[node_id] = {
            "item": data.get("item"),
            "download_image": data.get("download_image", False),
        }
        utils.save_selections(selections)
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@prompt_server.routes.get("/civitai_recipe_finder/fetch_data")
async def fetch_data(request):
    try:
        model_name = request.query.get("model_name")
        sort = request.query.get("sort")
        nsfw_level = request.query.get("nsfw_level")
        limit = int(request.query.get("limit", 32))
        model_type_str, model_filename = model_name.split("/", 1)
        model_type = "checkpoints" if model_type_str == "CKPT" else "loras"
        model_path = folder_paths.get_full_path(model_type, model_filename)
        if not model_path:
            raise FileNotFoundError(f"Model not found: {model_filename}")
        model_hash = utils.CivitaiAPIUtils.get_cached_sha256(model_path)
        gallery_data = utils.fetch_civitai_data_by_hash(
            model_hash, sort, limit, nsfw_level
        )
        prompt_server.send_sync("civitai-recipe-gallery-data", {"images": gallery_data})
        return web.json_response(
            {"status": "ok", "message": f"Data pushed for {model_filename}"}
        )
    except Exception as e:
        print(f"[CivitaiRecipeFinder] Error on refresh: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# --- Node Mappings ---

NODE_CLASS_MAPPINGS = {
    "CivitaiRecipeGallery": CivitaiRecipeGallery,
    }
NODE_DISPLAY_NAME_MAPPINGS = {
    "CivitaiRecipeGallery": "Civitai Recipe Gallery",
    }