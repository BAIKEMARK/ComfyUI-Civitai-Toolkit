# # """Top-level package for civitai_prompt_stats."""

__author__ = """Mark_Bai"""
__email__ = "zdl510510@126.com"
__version__ = "4.0.1"

import asyncio
from .nodes import (
    NODE_CLASS_MAPPINGS as fa_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as fa_display_mappings,
)
from .nodes_display import (
    NODE_CLASS_MAPPINGS as display_mappings,
    NODE_DISPLAY_NAME_MAPPINGS as display_display_mappings,
)
from . import api
from . import utils

NODE_CLASS_MAPPINGS = {**fa_mappings, **display_mappings}
NODE_DISPLAY_NAME_MAPPINGS = {**fa_display_mappings, **display_display_mappings}

try:
    main_loop = asyncio.get_event_loop()
    utils.initiate_background_scan(main_loop)
    print("Civitai Toolkit background scan initiated.")
except RuntimeError:
    print("[Civitai Toolkit] Could not get asyncio event loop. Background scan may not have started.")
    print("This can happen during certain startup modes. The scan will trigger on first UI interaction instead.")


WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", WEB_DIRECTORY, api]

print("--------------------------------------------------")
print("[Civitai-Toolkit]Civitai Project Nodes successfully loaded.")
print("--------------------------------------------------")
