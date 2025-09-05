# Changelog

All notable changes to this project will be documented in this file.

好的 👍 下面是翻译成英文的 `CHANGELOG`：

---

## \[3.0.0] - 2025-09-05

### Added

* **New Node**: `Recipe Params Parser` – a companion node for the `Gallery` node. It can “unpack” the new `recipe_params` data pipeline into standalone, type-correct parameter outputs, enabling advanced workflow automation.
* **One-Click Workflow Loading**: The `Civitai Recipe Gallery` node now features a “🚀 Load Workflow” button. It intelligently detects if ComfyUI-Manager is installed to safely load the recipe into a **new workflow tab**. If not, it falls back to a safe, confirmation-popup-based loading mode in the current tab.
* **Save Original File**: The `Gallery` node now includes a “💾 Save Original” button that allows you to download the original image—with full metadata—directly into your `output` folder for archiving.
* **Advanced Parameter & Resource Reports**: All `Analyzer` nodes can now output beautifully formatted, detailed multi-table Markdown reports for deeper insights. These reports are powered by the new `Markdown Presenter` node.
* **Scheduler Statistics**: `ParameterAnalyzer` now includes full statistical analysis of `Scheduler`.
* **A1111 Format Compatibility**: `ParameterAnalyzer` can now intelligently parse mixed sampler names from Stable Diffusion WebUI metadata (e.g., "DPM++ 2M Karras") and correctly separate them into sampler and scheduler.
* **High-Performance Caching**: Introduced the `orjson` library to significantly speed up JSON cache read/write operations. Local model hashing now uses `tqdm` progress bars with parallel processing and employs smart refresh mechanisms to minimize disk I/O. API call caching is now fully thread-safe.

### Changed

* **Complete Redesign of `Civitai Recipe Gallery`**:

  * **Drastically Simplified Outputs**: Outputs reduced from 16 to just 3 core ports: `image` (image), `info_md` (unified report), and `recipe_params` (data pipeline).
  * **Unified `info_md` Report**: The main Markdown report now embeds local LoRA diagnostic information (`[FOUND]` / `[MISSING]`), replacing the previous standalone `loras_info_md`.
* **Refined `Analyzer` Series Nodes**:

  * `PromptAnalyzer` and `ResourceAnalyzer` are now pure reporting tools, each with a single Markdown output and crystal-clear responsibilities.
  * All `..._stats_md` outputs have been renamed to the more intuitive `..._report_md`.

### Fixed

* **Corrected Output Types**: All parameters output from `Recipe Params Parser` and `Prompt Analyzer` (e.g., `sampler`, `scheduler`, `ckpt_name`) are now properly typed as `COMBO`, ensuring direct compatibility with nodes like `KSampler`.

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

## [3.0.0] - 2025-09-05

### 新增

* **新增节点**: `Recipe Params Parser` (配方参数解析器) - 作为`Gallery`节点的必要配套节点，它能“解包”新的`recipe_params`数据管道，为高级工作流自动化提供独立的、类型修正后的参数输出。
* **一键加载工作流**: `Civitai Recipe Gallery` 节点现在拥有一个“🚀 Load Workflow”按钮。它能智能检测ComfyUI-Manager是否存在，以安全地将配方加载到一个**新的工作流标签页**中。如果不存在，它会回退到安全的、带弹窗确认的当前页加载模式。
* **保存源文件**: `Gallery`节点新增了一个“💾 Save Original”按钮，可以将包含完整元数据的原始图片，一键下载到您的`output`文件夹进行归档。
* **高级参数与资源报告**: 所有的`Analyzer`(分析器)节点现在都能输出排版精美、信息详尽的多表格Markdown报告，提供更深刻的洞察。这由新增的`Markdown Presenter`(Markdown展示器)节点驱动。
* **Scheduler统计**: `ParameterAnalyzer`(参数分析器)现在包含了对`Scheduler`(调度器)的完整统计分析。
* **兼容A1111格式**: `ParameterAnalyzer`现在可以智能解析来自Stable Diffusion WebUI元数据中的混合式采样器名称（例如 "DPM++ 2M Karras"），并将其正确拆分为采样器和调度器。
* **高性能缓存**: 引入了`orjson`库，显著加快了JSON缓存的读写速度。本地模型哈希计算现在使用`tqdm`进度条进行并行处理，并采用智能刷新机制以最小化磁盘IO。API调用缓存现在是完全线程安全的。

### 变更

* **`Civitai Recipe Gallery` 的彻底重新设计**:
    * **输出端口极致精简**: 输出从16个骤减至3个核心端口：`image`（图片）、`info_md`（统一报告）、`recipe_params`（数据管道）。
    * **统一的`info_md`报告**: 主要的Markdown报告现在内置了LoRA的本地诊断功能（`[FOUND]` / `[MISSING]`），取代了之前独立的`loras_info_md`。
* **`Analyzer` 系列节点精炼**:
    * `PromptAnalyzer` 和 `ResourceAnalyzer` 现在是纯粹的报告工具，各自只有一个Markdown输出，职责无比清晰。
    * 所有 `..._stats_md` 输出被重命名为更直观的 `..._report_md`。

### 修复

* **修复输出类型**: 从`Recipe Params Parser`和`Prompt Analyzer`输出的所有参数（如 `sampler`, `scheduler`, `ckpt_name`）现在都是正确的`COMBO`类型，确保能与`KSampler`等节点直接连接。


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
