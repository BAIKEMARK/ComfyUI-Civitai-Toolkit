# Changelog

All notable changes to this project will be documented in this file.

---

## [4.1.0] - 2025-10-10

**Summary:**
Enhance model management by adding support for multiple model types and improving API interactions. This version significantly broadens the toolkit's capabilities, allowing users to manage a wider array of local models and more reliably parse complex recipe metadata, while also fixing key network bugs.

### 🚀 Added

* **Expanded Model Type Support:**
    * The **Local Manager** sidebar and the **Recipe Gallery** node now support a much wider range of model types.
    * You can now manage, filter, and select from: `checkpoints`, `loras`, `vae`, `embeddings`, `diffusion_models`, `text_encoders`, and `hypernetworks`.

### ✨ Improvements

* **Advanced Metadata Parsing:**
    * The parsing engine has been significantly upgraded to understand newer, complex metadata formats (especially from ComfyUI workflows).
    * The system is now far more robust at identifying all components of a recipe, including **Checkpoints, LoRAs, and VAEs** that were previously missed.
* **Smarter Diagnostics:**
    * The **Recipe Gallery**'s diagnostic report now provides a direct, clickable link to the Civitai page for any **Checkpoint** that is specified in a recipe but is not found locally, mirroring the popular feature for missing LoRAs.

### 🐞 Fixes

* **China Mirror Endpoint:** Fixed a bug where selecting the "China Mirror" network in the settings did not correctly apply the endpoint for all API requests. All browser and API-related features will now correctly use the selected network.


## [4.0.2] - 2025-10-07

**Summary:**
Adds API Key support to improve reliability, authentication, and request limits for all Civitai API interactions.

### 🚀 Added

#### 🔑 **API Key Management**

* Introduced a brand-new **“API Key Management”** section in the **ComfyUI Settings Panel**.
* Users can now **generate an API Key** from their **Civitai Account Page** and **enter it directly** in the plugin settings.
* Once saved, all plugin requests to Civitai will **automatically include Authorization headers** for authentication.

💡 **Why this matters:**
This feature helps users **increase API rate limits** and **prepare for upcoming Civitai features** that may require authentication.
You can create and manage your API Key on the **Civitai Account Settings** page.


## [4.0.1] - 2025-10-06

### Fixes

* **Startup freeze issue**:
  Some users reported that ComfyUI would hang indefinitely on startup when having a large number of LoRA models (hundreds or more).
  This update fixes the issue by moving the scanning process to the background.

### Improvements

* **Background processing**:

  * Model **hashing** and **Civitai info fetching** now run asynchronously in the background, allowing ComfyUI to start instantly.
  * You can continue using ComfyUI while the system gradually processes your models.

* **Resume support**:

  * Added **progress persistence** — if ComfyUI is closed or crashes during hashing or syncing, it will automatically resume from the last saved state instead of starting over.

### Notes

* This update primarily focuses on optimizing performance for users with large model libraries, resulting in significantly faster startup and better stability.
* Huge thanks to the community for reporting and testing — your feedback helps make Civitai Toolkit better ❤️




## \[4.0.0] - 2025-10-05

### Major Updates

* Officially renamed to **Civitai Toolkit** to reflect its all-in-one suite positioning.
* The original `Recipe Finder` remains as a core module.

### New & Improved

* **Dual Sidebar UI:** introduces `Local Model Manager` and `Civitai Online Browser`.
* **Enhanced UX:** smoother interaction and higher model management efficiency.


## \[3.2.1] - 2025-09-24

### Fixed

* **Error Fix**: Fixed an issue where `type object 'CivitaiAPIUtils' has no attribute 'get_civitai_info_from_hash'`.

### Changed

* **API Code Migration**: Migrated API-related code from `nodes.py` to a standalone `api.py` module for improved clarity and maintainability.

## \[3.2.0] - 2025-09-23

### Added
- **Database Management**: Introduced a new database control panel in the ComfyUI settings menu, allowing users to clear the analyzer, API response, and trigger word caches with a single click.
- **Video Resource Support**: The `Recipe Gallery` and `Model Analyzer` nodes now fully support displaying and analyzing video-type recipes from Civitai.

### Changed
- **Core Architecture Overhaul**: The caching system has been completely refactored from local JSON files to a unified `SQLite` database. This provides significantly faster load times, improved stability, and lays the foundation for future powerful features.
- **Simplified Node Workflow**: The `Data Fetcher` and three separate `Analyzer` nodes have been merged into a single, powerful **`Model Analyzer`** node. You can now go from data fetching to a full analysis report within one node.
- **Node Renaming & Consistency**:
    - `Recipe Params Parser` is now **`Get Parameters from Recipe`**.
    - The parameter unpacker for the analyzer is now **`Get Parameters from Analysis`**.
    - This unifies the naming scheme for clarity and intuitive use.

## \[3.1.2] - 2025-09-12

### Added

* **Workflow Examples**: Added a set of workflow examples to help users get started quickly. You can find them directly in ComfyUI under *Templates → Custom Nodes → ComfyUI-Civitai-Recipe*, or in the repository directory `./example_workflows` at [ComfyUI-Civitai-Recipe/example\_workflows](./example_workflows).

### Fixed

* **Bug fix**: Resolved an issue where `RecipeParamsParser` could fail to detect image width and height.

## \[3.1.1] - 2025-09-11

### Added

* **Local Image Directory**:

  * Images saved with `💾 Save Original` are now cached with their filenames.
  * If a duplicate download is attempted, the user will be notified that the image already exists.
  * When using `🚀 Load Workflow`, the workflow will be loaded directly from the existing local image instead of downloading it again.

### Fixed

* **Bug Fix**: Fixed an issue where `🚀 Load Workflow` failed to open a new tab and overwrote the current workflow.

## \[3.1.0] - 2025-09-10

### Added

* **New Setting**: Introduced **`Civitai Helper Network`** in the settings menu, allowing users to select the network environment used to access Civitai.

  * For users in China, the **`China Mirror`** (official domestic mirror) option is available to provide faster and more stable access.
  * The default option is **`International`**, which is suitable for users on global internet environments.
  * Navigation path: `Settings` → `CivitaiUtils` → `Civitai Helper Network`.

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

本项目的所有重要更新与变更都会记录在此文件中。

---

## [4.1.0] - 2025-10-10

**总结:**
增强模型管理，通过支持多种模型类型和改进 API 交互，提升了整体功能。本次更新显著扩展了工具套件的能力，允许用户管理更多类型的本地模型、更可靠地解析复杂的配方元数据，并修复了关键的网络功能 Bug。

### 🚀 新增

* **扩展模型类型支持**：
    * **本地模型管理器 (Local Manager)** 与 **配方画廊 (Recipe Gallery)** 节点现已支持更广泛的模型类型。
    * 您现在可以管理、筛选和选用包括 `checkpoints`, `loras`, `vae`, `embeddings`, `diffusion_models`, `text_encoders`, `hypernetworks` 在内的多种资源。

### ✨ 优化

* **高级元数据解析**：
    * 大幅升级元数据解析引擎，现可兼容并识别来自 ComfyUI 等工作流的**新型复杂元数据格式**。
    * 系统现在能更稳定地识别出配方中包含的、以往可能被忽略的 **Checkpoint、LoRA 及 VAE** 等全部资源。
* **智能化诊断**：
    * **配方画廊 (Recipe Gallery)** 的诊断报告现已支持为配方中指定但本地不存在的 **Checkpoint** 提供可直接点击的 Civitai 页面链接，与备受好评的缺失 LoRA 诊断功能体验对齐。

### 🐞 修复

* **国内镜像端点**：修复了在设置中选择“China Mirror”网络后，部分 API 请求仍错误地发往默认主站的 Bug。现在所有浏览器及 API 相关功能均会正确应用所选的网络端点。


## [4.0.2] - 2025-10-07

### ✨ 新增

#### 🔑 **API Key 管理功能**

* 在 **ComfyUI 设置面板** 中新增了全新的 **「API Key Management」** 区域。
* 用户现在可以在 **Civitai 账户页面** 创建 API Key，并在此处填写。
* 保存后，插件发往 Civitai 的所有请求将自动携带 **Authorization** 认证信息。

💡 **功能说明**：
该功能可帮助用户突破默认的 API 请求频率限制，并为未来可能需要身份验证的功能提前做好准备。
您可以前往 Civitai 官网的 **「用户账户设置」** 页面创建并管理您的 API Key。




## [4.0.1] - 2025-10-06

### 修复

* **启动卡顿问题**：部分用户在拥有大量 LoRA 模型（约数百个以上）时，报告插件在启动时长时间停留在加载界面。本次更新已修复该问题。

### 优化

* **后台异步处理**：

  * 现在模型的 **Hash 计算与信息同步（Fetch Info）** 将在后台自动执行，不再阻塞 ComfyUI 的启动界面。
  * 用户可在进入 ComfyUI 后继续操作，系统会在后台完成模型信息加载。

* **断点续连机制**：

  * 新增 **进度持久化功能**，在哈希或信息同步过程中中断（如崩溃、重启）后，可自动恢复上次的进度，无需重新扫描全部模型。

### 说明

* 此次更新主要针对 **模型数量庞大时的性能问题** 进行优化，极大提升了启动速度与稳定性。
* 感谢社区用户的反馈与耐心测试 ❤️




## \[4.0.0] - 2025-10-05

#### 重大变更

* 项目正式更名为 **Civitai Toolkit**，以体现综合性工具套件定位。
* 原 `Recipe Finder` 现作为核心功能模块保留。

#### 新增与优化

* **新增双侧边栏 UI**：`本地模型管理器` 与 `Civitai 在线浏览器`。
* **全面优化交互体验**：模型管理与发现效率显著提升。


## \[3.2.1] - 2025-09-24

### 修复

* **错误修复**: 修复了 `type object 'CivitaiAPIUtils' has no attribute 'get_civitai_info_from_hash'` 的问题。

### 变更

* **API 代码迁移**: 将原本位于 `nodes.py` 的 API 相关代码迁移至独立的 `api.py` 模块，以提升代码结构清晰度和可维护性。

## \[3.2.0] - 2025-09-23

### 新增
- **数据库管理**: 在 ComfyUI 设置菜单中增加了全新的数据库管理面板，现在您可以一键清除分析器、API响应及触发词等各类缓存。
- **视频资源支持**: `Recipe Gallery` 和 `Model Analyzer` 节点现在完全支持展示和分析来自 Civitai 的视频类型配方。

### 变更
- **核心架构重构**: 插件的缓存系统已从零散的本地JSON文件重构为统一的 `SQLite` 数据库。这将带来更快的加载速度、更高的稳定性，并为未来的强大功能奠定基础。
- **节点流程简化**: `Data Fetcher` 和三个独立的 `Analyzer` 节点已被合并为一个强大的**“模型分析器” (`Model Analyzer`)** 节点。现在，您只需一个节点即可完成从数据获取到生成完整分析报告的所有操作。
- **节点重命名与统一**:
    - `Recipe Params Parser` 现已更名为 **`Get Parameters from Recipe`**。
    - 用于解析分析器参数的节点现在是 **`Get Parameters from Analysis`**。
    - 这两个节点统一了命名风格，使其功能更加清晰直观。

## \[3.1.2] - 2025-09-12

### 新增

* **工作流示例**：为方便用户快速上手，新增了一组工作流示例。你可以在 ComfyUI 的「范本 → 自定义节点 → ComfyUI-Civitai-Recipe」中直接找到，或在仓库目录 `./example_workflows` 下查看，即 [ComfyUI-Civitai-Recipe/example\_workflows](./example_workflows)。
### 修复

* **Bug 修复**：修复了 `RecipeParamsParser` 在识别图片宽高时可能失败的问题。
## \[3.1.1] - 2025-09-11

### 新增

* **新增本地图片目录**：

  * 使用 `💾 Save Original` 保存到本地的图片会自动记录文件名。
  * 当尝试重复下载时，会提示用户图片已存在，避免冗余文件。
  * 使用 `🚀 Load Workflow` 获取工作流时，如本地已有对应图片，将直接加载本地文件，而不会再次下载。

### 修复

* **修复 Bug**：解决了 `🚀 Load Workflow` 无法新建标签页、导致覆盖当前工作流的问题。

## \[3.1.0] - 2025-09-10

### 新增

* **新增设置项**: 在设置中加入了 **`Civitai Helper Network`**，用于选择访问 Civitai 时所使用的网络环境。

  * 对于中国用户，可选择 **`China Mirror`**（国内官方镜像）以更快、更稳定地访问 Civitai。
  * 默认选项为 **`International`**，适用于国际互联网环境用户。
  * 路径：`Settings` → `CivitaiUtils` → `Civitai Helper Network`。

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
