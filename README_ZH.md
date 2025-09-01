# Civitai Recipe Finder (Civitai 配方查找器)

## 功能说明

要创作出惊艳的 AI 艺术作品，关键在于找到完美的“**配方 (Recipe)**”——即模型、触发词、提示词和生成参数的理想组合。**Civitai Recipe Finder** 是一套为 ComfyUI 设计的强大节点工具集，旨在通过深度分析 Civitai 社区数据或为您本地模型提供即时视觉反馈，帮你揭示这些创作配方。

本节点套件提供多维度的方式来探索创作配方：

  * **可视化查找配方**: 选择您本地的一个模型，即时浏览由它创作的热门社区作品画廊。单击一下即可应用完整的配方——包括提示词、参数和LoRA组合。
  * **即时查找触发词**: 快速获取任何 LoRA 模型的官方推荐触发词和元数据触发词。
  * **发现社区趋势**: 分析数百张社区图片，找到使用频率最高的正、负向提示词。
  * **揭示最佳参数**: 识别社区针对特定模型最常用的生成参数（采样器、CFG、步数等）。
  * **发掘“黄金组合”**: 发现哪些其他的 LoRA 模型最常与你选择的模型搭配使用。

整个套件基于模块化的设计哲学，让您既能进行快速的视觉查找，也能构建复杂深度的分析工作流，同时确保了最高效率。

## 节点套件说明

Recipe Finder 由三组独立的工具构成，以匹配您的不同需求。

### 1\. 可视化配方查找器 (Visual Recipe Finder)

这是本套件的旗舰节点，专为快速、直观、且以模型为中心的工作流而设计。

#### `Civitai Recipe Gallery` (Civitai 配方画廊)

  * **用途**: 选择一个本地模型文件（Checkpoint 或 LoRA），并可视化地浏览用它创作的热门社区作品。在画廊中单击任意图片，即可将其完整的“配方”应用到节点的输出端口上。
  * **核心特性**:
      * **万能解析引擎**: 智能解析Civitai上多种混乱的元数据格式，以提取配方信息。
      * **本地LoRA匹配**: 自动查找您本地与配方哈希值相匹配的LoRA文件。
      * **缺失LoRA报告**: 如果您缺少配方所需的LoRA，它会提供其名称和Civitai下载链接。
      * **按需图片下载**: 仅当`image`输出端口被连接时，才会下载预览图。
      * **即时刷新**: 内置“刷新”按钮，无需运行整个工作流即可获取新图片。
  * **输入**: `model_name` (模型名称), `sort` (排序方式), `nsfw_level` (NSFW等级), `image_limit` (图片数量)
  * **输出**:

| 输出端口 | 类型 | 说明 |
| :--- | :--- | :--- |
| **核心内容** | | |
| `positive_prompt` | `STRING` | 配方中的正向提示词。 |
| `negative_prompt` | `STRING` | 配方中的负向提示词。 |
| `seed` | `INT` | 生成种子。 |
| **采样参数** | | |
| `steps` | `INT` | 采样步数。 |
| `cfg` | `FLOAT` | CFG Scale 值。 |
| `sampler_name` | `STRING` | 使用的采样器名称。 |
| `scheduler` | `STRING` | 使用的调度器名称。 |
| **核心资产** | | |
| `image` | `IMAGE` | 所选的范例图片，可直接用于预览。 |
| `ckpt_name` | `STRING` | 配方中使用的主模型（Checkpoint）名称。 |
| **图像尺寸** | | |
| `width` | `INT` | 图片宽度。 |
| `height` | `INT` | 图片高度。 |
| **高级/信息** | | |
| `denoise` | `FLOAT` | Denoise 值 (如果可用)。 |
| `info` | `STRING` | 完整的、未经处理的原始元数据(JSON格式)。 |
| `loras_info` | `STRING` | 一份清晰的LoRA使用报告，会标明`[FOUND]`(本地已找到)或`[MISSING]`(本地缺失)，并为后者提供下载信息。 |

![gallery example](./image/gallery.png)

> [!WARNING]  
> ⚠️ **注意 (Note)**  
> - 第一次运行时会自动计算本地所有模型的 **hash**，可能会耗时较长，请耐心等待。  
> - 计算结果会保存在 **`Civitai_Recipe_Finder/data`** 目录下。  
> - 之后仅会对缺失的模型进行计算。  

### 2\. 轻量级工具 (Lightweight Tool)

这个独立节点专为高频、日常使用场景设计。

#### `Lora Trigger Words` (Lora 触发词)

  * **用途**: 无需任何重度处理，即时获取一个 LoRA 模型的两组核心触发词。
  * **输入**: `lora_name`, `force_refresh`
  * **输出**:

| 输出端口 | 类型 | 说明 |
| :--- | :--- | :--- |
| `metadata_triggers` | `STRING` | 从本地文件元数据 (`ss_tag_frequency`) 提取的触发词。反映了训练数据。 |
| `civitai_triggers` | `STRING` | 从 Civitai API (`trainedWords`) 获取的官方触发词。反映了模型作者的明确推荐。 |

![lora_trigger_words example](./image/lora_trigger_words.png)

### 3\. 分析器流水线 (Analyzer Pipeline)

这是一套为深度模型统计分析设计的强大、模块化的流水线。

#### `Civitai Data Fetcher (CKPT / LORA)` (数据获取器)

  * **用途**: 流水线的引擎。它为指定的模型获取所有社区图片元数据，并将其打包成一个数据包输出。**这是流水线中唯一进行重度网络请求的节点。**
  * **输入**: `model_name`, `max_pages`, `sort`, `retries`, `timeout`, `force_refresh`
  * **输出**: `civitai_data` (数据包), `fetch_summary` (STRING)。

#### `Prompt Analyzer` (提示词分析器), `Parameter Analyzer` (参数分析器), `Resource Analyzer` (关联资源分析器)

  * **用途**: 这些节点连接到获取器的`civitai_data`输出，分别对提示词、生成参数和关联LoRA的使用情况进行深度统计分析。

![Fetcher-Analyzer example](./image/F-A_workflow.png)

## 安装

1.  将项目文件夹放入 ComfyUI 的 `custom_nodes` 目录，例如：
    ```
    ComfyUI/custom_nodes/CivitaiProject/
    ```
2.  重启 ComfyUI。你将在 `Civitai` 菜单及其子菜单中找到所有新节点。

## 鸣谢

本项目在开发过程中参考并借鉴了以下优秀开源项目：

* 获取触发词的逻辑，灵感与部分代码实现来源于 [Extraltodeus/LoadLoraWithTags](https://github.com/Extraltodeus/LoadLoraWithTags) 与 [idrirap/ComfyUI-Lora-Auto-Trigger-Words](https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words)。
* 画廊节点的设计思路参考了 [Firetheft/ComfyUI\_Civitai\_Gallery](https://github.com/Firetheft/ComfyUI_Civitai_Gallery)。

在此向以上项目及其作者们致以诚挚的感谢！

---