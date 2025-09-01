# # """Top-level package for civitai_prompt_stats."""
#
# __author__ = """Mark_Bai"""
# __email__ = "zdl510510@126.com"
# __version__ = "2.0.0"
#
# from .nodes import NODE_CLASS_MAPPINGS as ANALYZER_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as ANALYZER_DISPLAY_MAPPINGS
# from .nodes_gallery import NODE_CLASS_MAPPINGS as GALLERY_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS as GALLERY_DISPLAY_MAPPINGS
#
# NODE_CLASS_MAPPINGS = {**ANALYZER_MAPPINGS, **GALLERY_MAPPINGS}
# NODE_DISPLAY_NAME_MAPPINGS = {**ANALYZER_DISPLAY_MAPPINGS, **GALLERY_DISPLAY_MAPPINGS}
#
# WEB_DIRECTORY = "./js"
#
# __all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

# 从 gallery 节点文件导入
from .nodes_gallery import NODE_CLASS_MAPPINGS as gallery_mappings, NODE_DISPLAY_NAME_MAPPINGS as gallery_display_mappings
# 从 analysis 节点文件导入
from .nodes import NODE_CLASS_MAPPINGS as fa_mappings, NODE_DISPLAY_NAME_MAPPINGS as fa_display_mappings
# 从 display 节点文件导入
from .nodes_display import NODE_CLASS_MAPPINGS as display_mappings, NODE_DISPLAY_NAME_MAPPINGS as display_display_mappings

# 合并所有节点的映射
NODE_CLASS_MAPPINGS = {**gallery_mappings, **fa_mappings, **display_mappings}
NODE_DISPLAY_NAME_MAPPINGS = {**gallery_display_mappings, **fa_display_mappings, **display_display_mappings}


WEB_DIRECTORY = "./js"
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS',WEB_DIRECTORY]

print("--------------------------------------------------")
print("Civitai Project Nodes successfully loaded.")
print(f"  - Loaded {len(gallery_mappings)} nodes from Gallery.")
print(f"  - Loaded {len(fa_mappings)} nodes from Fetcher/Analyzer.")
print(f"  - Loaded {len(display_mappings)} nodes from Display.")
print("--------------------------------------------------")