# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2025-08-31

This is the **Ultimate Edition** release, focusing on maximum compatibility, usability, and robustness by introducing a universal parsing engine and several key user-requested features.

### Added

* **New Node**: `Civitai Recipe Gallery` – By selecting a local model file (Checkpoint or LoRA), you can visually browse popular community creations made with it. Clicking on any image in the gallery will apply its complete “recipe” directly to the node’s output ports.  
* **Universal Parsing Engine**: The gallery node can now intelligently parse Civitai metadata from various inconsistent sources and formats (e.g., `civitaiResources`, `resources` lists, `AddNet` format, etc.), accurately extracting LoRA and Checkpoint information.  
* **Model Version ID to Hash Conversion & Caching**: Introduced a new local cache (`id_to_hash_cache.json`) that maps model version IDs to their corresponding hashes, significantly reducing unnecessary API requests.  
* **Unified Hash Cache**: All nodes in the project now share a single, more robust hash computation mechanism (`data/hash_cache.json`).  

### Changed

* **Refactored `utils.py`**: All common utility functions have been consolidated into a single, powerful `utils.py` toolbox for better modularity and maintainability.
* **Optimized Model Hash Caching**: The model hashing logic was rewritten to be more generic and efficient, safely handling both Checkpoints and LoRAs, as well as external model paths and file modifications.

## [1.1.0] - 2025-08-30

### Changed

* **Enhanced Analyzer Functionality**: Added the `summary_top_n` parameter to `Civitai Analyzer` nodes, allowing users to customize the number of entries in analysis reports, and optimized the resource analysis logic.

### Fixed

* **Critical Node Loading Failure**: Fixed an initialization error that prevented the custom nodes from being loaded by ComfyUI.

## [1.0.0] - Initial Release

### Added

* **Civitai Fetcher**: A data fetcher node to gather all community image metadata for a specified model and output it as a single data package.
* **Civitai Analyzer Suite**: Includes `Prompt Analyzer`, `Parameter Analyzer`, and `Resource Analyzer` to perform in-depth statistical analysis on prompts, generation parameters, and associated LoRA usage.
* **Lora Trigger Words**: A node to instantly fetch metadata-based and official trigger words for any LoRA model.

---

# 更新日志

本项目所有重要的更改都将记录在此文件中。

## [2.0.0] - 2025-08-31

### 新增

* **全新节点**:`Civitai Recipe Gallery` (Civitai 配方画廊)，通过选择一个本地模型文件（Checkpoint 或 LoRA），你能够可视化地浏览用它创作的热门社区作品。在画廊中单击任意图片，即可将其完整的“配方”应用到节点的输出端口上。
* **万能解析引擎**: 画廊节点现在可以智能解析多种来源不一、格式混乱的Civitai元数据（如 `civitaiResources`, `resources` 列表, `AddNet` 格式等），以精准提取LoRA和Checkpoint信息。
* **模型版本ID到哈希的转换与缓存**: 引入了新的本地缓存 (`id_to_hash_cache.json`)，用于通过模型版本ID查询并存储其对应的哈希值，极大减少了不必要的API请求。
* **统一的哈希缓存**: 现在项目中的所有节点共享一个统一且更健壮的哈希计算机制 (`data/hash_cache.json`)。

### 变更

* **重构 `utils.py`**: 将所有节点文件中的通用功能函数全部整合到一个统一、强大的`utils.py`工具箱中，实现了代码的模块化，提升了可维护性。
* **优化模型哈希缓存**: 重写了模型哈希缓存的逻辑，使其能同时支持Checkpoints和LoRAs，并能安全地处理外部模型路径和文件删改，变得更通用、更高效。

## [1.1.0] - 2025-08-30

### 变更

* **增强分析功能**: 为 `Civitai Analyzer` 节点新增 `summary_top_n` 参数，允许用户自定义分析报告的条目数量，并优化了关联资源分析的逻辑。

### 修复

* **修复了严重的节点加载失败问题**: 解决了因“初始化”配置错误而导致的插件无法被ComfyUI正常加载的问题。

## [1.0.0] - 初始版本

### 新增

* **Civitai Fetcher (数据获取器)**: 为指定的模型获取所有社区图片元数据，并将其打包成一个数据包输出。
* **Civitai Analyzer (分析器套件)**: 包括`Prompt Analyzer`(提示词分析器), `Parameter Analyzer`(参数分析器), `Resource Analyzer`(关联资源分析器)。分别对提示词、生成参数和关联LoRA的使用情况进行深度统计分析。
* **Lora Trigger Words (Lora 触发词)**: 即时获取一个 LoRA 模型的元数据触发词和官方推荐触发词。
