# # """Top-level package for civitai_prompt_stats."""

__author__ = """Mark_Bai"""
__email__ = "zdl510510@126.com"
__version__ = "3.2.0"

from .nodes import NODE_CLASS_MAPPINGS as fa_mappings, NODE_DISPLAY_NAME_MAPPINGS as fa_display_mappings
from .nodes_display import NODE_CLASS_MAPPINGS as display_mappings, NODE_DISPLAY_NAME_MAPPINGS as display_display_mappings

NODE_CLASS_MAPPINGS = {**fa_mappings, **display_mappings}
NODE_DISPLAY_NAME_MAPPINGS = { **fa_display_mappings, **display_display_mappings}

WEB_DIRECTORY = "./js"
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS',WEB_DIRECTORY]

print("--------------------------------------------------")
print("[Civitai-Recipe-Finder]Civitai Project Nodes successfully loaded.")
print("--------------------------------------------------")
