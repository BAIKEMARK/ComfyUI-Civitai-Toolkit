# Civitai Recipe Finder

## Description

Finding the perfect "recipe" — the ideal combination of a model, trigger words, prompts, and generation parameters — is the key to creating stunning AI art. The **Civitai Recipe Finder** is a powerful suite of ComfyUI nodes designed to uncover these recipes by deeply analyzing data from the Civitai community.

This node suite moves beyond simple prompt statistics, transforming into a comprehensive analysis toolkit that helps you:

  * **Instantly Find Trigger Words**: Quickly get official and metadata-based trigger words for any LoRA model.
  * **Discover Community Trends**: Analyze hundreds of community images to find the most frequently used positive and negative prompts.
  * **Uncover Optimal Parameters**: Identify the most common generation parameters (Sampler, CFG, Steps, Size, etc.) used by the community for a specific model.
  * **Reveal "Golden Combos"**: Discover which other LoRA models are most frequently used in combination with your selected model, along with their optimal weights.

The entire suite is built on a modular, pipeline-based philosophy, allowing you to perform quick lookups or build complex, in-depth analysis workflows with maximum efficiency and zero redundant data fetching.

## The Node Suite

The Recipe Finder is composed of two distinct toolsets to match your specific needs: a lightweight tool for quick lookups, and a powerful pipeline for deep analysis.

### Lightweight Tool (轻量级工具)

This standalone node is designed for high-frequency, everyday use.

#### `Lora Trigger Words`

  * **Purpose**: Instantly fetches the two most important sets of trigger words for a LoRA model without any heavy processing.
  * **Inputs**: `lora_name`, `force_refresh`
  * **Outputs**:

| Output | Type | Description |
| :--- | :--- | :--- |
| `metadata_triggers` | `STRING` | Trigger words from the local file's metadata (`ss_tag_frequency`). Reflects the actual training data. |
| `civitai_triggers` | `STRING` | Official trigger words from the Civitai API (`trainedWords`). Reflects the author's recommendation. |

### Analyzer Pipeline (分析器流水线)

This is a powerful, modular pipeline for deep model analysis. The workflow starts with a **Fetcher** node, which does all the heavy lifting of gathering data once. Its output can then be connected to one or more **Analyzer** nodes.

#### `1. Civitai Data Fetcher (CKPT / LORA)`

  * **Purpose**: The engine of the pipeline. It fetches all community image metadata for a given model and outputs it as a single data package. **This is the only node in the pipeline that performs heavy network requests.**
  * **Inputs**: `model_name`, `max_pages`, `sort`, `retries`, `timeout`, `force_refresh`
  * **Outputs**:

| Output | Type | Description |
| :--- | :--- | :--- |
| `civitai_data` | `CIVITAI_DATA` | A data package containing all fetched raw metadata, ready to be passed to analyzer nodes. |
| `fetch_summary` | `STRING` | A simple summary of the fetch operation, e.g., "Fetched metadata from 257 images". |

#### `2. Prompt Analyzer`

  * **Purpose**: Connect to the Fetcher to analyze community prompt usage.
  * **Inputs**: `civitai_data`, `top_n`
  * **Outputs**:

| Output | Type | Description |
| :--- | :--- | :--- |
| `positive_prompt` | `STRING` | A ranked list of the most used positive prompts. |
| `negative_prompt` | `STRING` | A ranked list of the most used negative prompts. |

#### `3. Parameter Analyzer (CKPT / LORA)`

  * **Purpose**: Connect to the Fetcher to analyze common generation parameters.
  * **Inputs**: `civitai_data`
  * **Outputs (LORA Version - 9 total)**:
      * `parameter_stats` (STRING), `top_sampler_name` (STRING), `top_cfg` (FLOAT), `top_steps` (INT), `top_width` (INT), `top_height` (INT), `top_hires_upscaler` (STRING), `top_denoising_strength` (FLOAT), `top_clip_skip` (INT).
  * **Outputs (CKPT Version - 10 total)**:
      * All of the above, plus `top_vae_name` (STRING).

#### `4. Resource Analyzer`

  * **Purpose**: Connect to the Fetcher to discover which LoRA models are frequently used together.
  * **Inputs**: `civitai_data`
  * **Outputs (7 total)**:
      * `associated_resources_stats` (STRING) - A formatted summary of the top associated LoRAs and their weights.
      * `assoc_lora_1_name` (STRING), `assoc_lora_1_weight` (FLOAT)
      * `assoc_lora_2_name` (STRING), `assoc_lora_2_weight` (FLOAT)
      * `assoc_lora_3_name` (STRING), `assoc_lora_3_weight` (FLOAT)

## Workflow Examples

### Workflow 1: Quick Trigger Word Lookup

For when you just need the triggers for a LoRA, instantly.

`[Lora Trigger Words]` → `[Show Text]`

### Workflow 2: Full Model Deep Dive

Use the pipeline to get a complete picture of a model's community recipe.

```
                                                     +--> [Prompt Analyzer]
                                                     |
[Civitai Data Fetcher] --> [civitai_data] --+--> [Parameter Analyzer]
                                                     |
                                                     +--> [Resource Analyzer]
```

## Installation

1.  Place this project under ComfyUI’s `custom_nodes` directory, for example:
    ```
    ComfyUI/custom_nodes/Civitai_Recipe_Finder
    ```
2.  Restart ComfyUI. You will find the new nodes in the menu under the `Civitai` category and its subcategories.

## Acknowledgement

The logic for fetching trigger words was inspired by and uses parts of both [Extraltodeus/LoadLoraWithTags](https://github.com/Extraltodeus/LoadLoraWithTags) and [idrirap/ComfyUI-Lora-Auto-Trigger-Words](https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words). Special thanks to the original authors.

-----

-----

## 功能说明

要创作出惊艳的 AI 艺术作品，关键在于找到完美的“**配方 (Recipe)**”——即模型、触发词、提示词和生成参数的理想组合。**Civitai Recipe Finder** 是一套为 ComfyUI 设计的强大节点工具集，旨在通过深度分析 Civitai 社区数据，帮你揭示这些创作配方。

本节点套件已超越了简单的提示词统计，演变成一个全面的分析工具箱，可以帮你：

  * **即时查找触发词**: 快速获取任何 LoRA 模型的官方推荐触发词和元数据触发词。
  * **发现社区趋势**: 分析数百张社区图片，找到使用频率最高的正、负向提示词。
  * **揭示最佳参数**: 识别社区针对特定模型最常用的生成参数（采样器、CFG、步数、尺寸等）。
  * **发掘“黄金组合”**: 发现哪些其他的 LoRA 模型最常与你选择的模型搭配使用，以及它们的最佳权重。

整个套件基于模块化的“流水线”设计哲学，让你既能进行快速查找，也能构建复杂深度的分析工作流，同时确保了最高效率，杜绝了任何重复的数据获取。

## 节点套件说明

Recipe Finder 由两组独立的工具构成，以匹配你的不同需求：一组用于快速查找的轻量级工具，和一套用于深度分析的强大流水线。

### 轻量级工具 (Lightweight Tool)

这个独立节点专为高频、日常使用场景设计。

#### `Lora Trigger Words` (Lora 触发词)

  * **用途**: 无需任何重度处理，即时获取一个 LoRA 模型的两组核心触发词。
  * **输入**: `lora_name`, `force_refresh`
  * **输出**:

| 输出端口 | 类型 | 说明 |
| :--- | :--- | :--- |
| `metadata_triggers` | `STRING` | 从本地文件元数据 (`ss_tag_frequency`) 提取的触发词。反映了训练数据。 |
| `civitai_triggers` | `STRING` | 从 Civitai API (`trainedWords`) 获取的官方触发词。反映了模型作者的明确推荐。 |

### 分析器流水线 (Analyzer Pipeline)

这是一套为深度模型分析设计的强大、模块化的流水线。工作流由一个 **Fetcher (获取器)** 节点开始，它负责一次性完成所有重度的数据采集工作，其输出可以连接到一个或多个 **Analyzer (分析器)** 节点。

#### `1. Civitai Data Fetcher (CKPT / LORA)` (数据获取器)

  * **用途**: 流水线的引擎。它为指定的模型获取所有社区图片元数据，并将其打包成一个数据包输出。**这是流水线中唯一进行重度网络请求的节点。**
  * **输入**: `model_name`, `max_pages`, `sort`, `retries`, `timeout`, `force_refresh`
  * **输出**:

| 输出端口 | 类型 | 说明 |
| :--- | :--- | :--- |
| `civitai_data` | `CIVITAI_DATA` | 包含所有已获取的原始元数据的数据包，可供下游的分析器节点使用。 |
| `fetch_summary` | `STRING` | 对获取操作的简单总结，例如：“已从3个页面获取257张图片的元数据。” |

#### `2. Prompt Analyzer` (提示词分析器)

  * **用途**: 连接到 Fetcher 节点，用于分析社区提示词的使用情况。
  * **输入**: `civitai_data`, `top_n`
  * **输出**:

| 输出端口 | 类型 | 说明 |
| :--- | :--- | :--- |
| `positive_prompt` | `STRING` | 使用频率最高的正向提示词排序列表。 |
| `negative_prompt` | `STRING` | 使用频率最高的负向提示词排序列表。 |

#### `3. Parameter Analyzer (CKPT / LORA)` (参数分析器)

  * **用途**: 连接到 Fetcher 节点，用于分析常见的生成参数。
  * **输入**: `civitai_data`
  * **输出 (LORA 版 - 共9个)**:
      * `parameter_stats` (STRING), `top_sampler_name` (STRING), `top_cfg` (FLOAT), `top_steps` (INT), `top_width` (INT), `top_height` (INT), `top_hires_upscaler` (STRING), `top_denoising_strength` (FLOAT), `top_clip_skip` (INT)。
  * **输出 (CKPT 版 - 共10个)**:
      * 包含 LORA 版所有输出，并额外增加 `top_vae_name` (STRING)。

#### `4. Resource Analyzer` (关联资源分析器)

  * **用途**: 连接到 Fetcher 节点，用于发现哪些 LoRA 模型经常被组合使用。
  * **输入**: `civitai_data`
  * **输出 (共7个)**:
      * `associated_resources_stats` (STRING) - 格式化好的、关于热门关联 LoRA 及其权重的总结报告。
      * `assoc_lora_1_name` (STRING), `assoc_lora_1_weight` (FLOAT)
      * `assoc_lora_2_name` (STRING), `assoc_lora_2_weight` (FLOAT)
      * `assoc_lora_3_name` (STRING), `assoc_lora_3_weight` (FLOAT)

## 工作流示例

### 工作流 1: 快速查找触发词

当你只想立刻知道一个 LoRA 的触发词时使用。

`[Lora Trigger Words]` → `[Show Text]`

### 工作流 2: 模型深度挖掘

使用流水线来全面了解一个模型的社区“配方”。

```
                                                     +--> [Prompt Analyzer]
                                                     |
[Civitai Data Fetcher] --> [civitai_data] --+--> [Parameter Analyzer]
                                                     |
                                                     +--> [Resource Analyzer]
```

## 安装

1.  将项目文件夹放入 ComfyUI 的 `custom_nodes` 目录，例如：
    ```
    ComfyUI/custom_nodes/Civitai_Recipe_Finder
    ```
2.  重启 ComfyUI。你将在 `Civitai` 菜单及其子菜单中找到所有新节点。

## 鸣谢

本项目中获取触发词的逻辑，其灵感和部分代码实现来源于 [Extraltodeus/LoadLoraWithTags](https://github.com/Extraltodeus/LoadLoraWithTags) 和 [idrirap/ComfyUI-Lora-Auto-Trigger-Words](https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words)。在此特别感谢原作者们。
