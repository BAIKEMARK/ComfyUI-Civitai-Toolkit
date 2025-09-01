# Civitai Recipe Finder

> 👉 [点击这里查看中文文档](./README_ZH.md)

## Description

Finding the perfect "recipe" — the ideal combination of a model, trigger words, prompts, and generation parameters — is the key to creating stunning AI art. The **Civitai Recipe Finder** is a powerful suite of ComfyUI nodes designed to uncover these recipes by deeply analyzing data from the Civitai community or providing instant visual feedback for your local models.

This node suite offers a multi-faceted approach to recipe discovery:

  * **Visually Find Recipes**: Select one of your local models and instantly see a gallery of top community creations. Apply a complete recipe—prompts, parameters, and LoRAs—with a single click.
  * **Instantly Find Trigger Words**: Quickly get official and metadata-based trigger words for any LoRA model.
  * **Discover Community Trends**: Analyze hundreds of community images to find the most frequently used positive and negative prompts.
  * **Uncover Optimal Parameters**: Identify the most common generation parameters (Sampler, CFG, Steps, etc.) used for a specific model.
  * **Reveal "Golden Combos"**: Discover which other LoRA models are most frequently used in combination with your selected model.

The entire suite is built on a modular philosophy, allowing you to perform quick visual lookups or build complex, in-depth analysis workflows with maximum efficiency.

## The Node Suite

The Recipe Finder is composed of three distinct toolsets to match your specific needs.

### 1\. Visual Recipe Finder

This is the flagship node of the suite, designed for a fast, intuitive, and model-centric workflow.

#### `Civitai Recipe Gallery`

  * **Purpose**: To select a local model file (Checkpoint or LoRA) and visually browse top community example images made with it. A single click on any image instantly applies its full "recipe" to the node's outputs.
  * **Features**:
      * **Smart Parsing Engine**: Intelligently parses multiple, chaotic metadata formats from Civitai to extract recipe information.
      * **Local LoRA Matching**: Automatically finds your local LoRA files that match the hashes in a recipe.
      * **Missing LoRA Reporting**: If you don't have a required LoRA, it provides its name and a direct Civitai download link.
      * **On-Demand Image Download**: Only downloads the preview image if the `image` output is connected.
      * **Instant Refresh**: A dedicated "Refresh" button lets you fetch new images without running the entire workflow.
  * **Inputs**: `model_name`, `sort`, `nsfw_level`, `image_limit`
  * **Outputs**:

| Output | Type | Description |
| :--- | :--- | :--- |
| **Core Content** | | |
| `positive_prompt` | `STRING` | The positive prompt from the recipe. |
| `negative_prompt` | `STRING` | The negative prompt from the recipe. |
| `seed` | `INT` | The generation seed. |
| **Sampling Params** | | |
| `steps` | `INT` | Number of sampling steps. |
| `cfg` | `FLOAT` | CFG Scale value. |
| `sampler_name` | `STRING` | Name of the sampler used. |
| `scheduler` | `STRING` | Name of the scheduler used. |
| **Core Assets** | | |
| `image` | `IMAGE` | The selected example image, ready for preview. |
| `ckpt_name` | `STRING` | The name of the base checkpoint model used. |
| **Dimensions** | | |
| `width` | `INT` | Image width. |
| `height` | `INT` | Image height. |
| **Advanced/Info** | | |
| `denoise` | `FLOAT` | The denoise value (if available). |
| `info` | `STRING` | The complete, raw metadata in JSON format. |
| `loras_info` | `STRING` | A clean report of all LoRAs used, indicating if they are `[FOUND]` locally or `[MISSING]`, and providing download info for the latter. |

![gallery example](./image/gallery.png)

> [!WARNING]  
> ⚠️ **Note**  
> - On the first run, the program will automatically calculate the **hash** for all local models. This may take some time, so please be patient.  
> - The results will be stored in **`Civitai_Recipe_Finder/data`**.  
> - In subsequent runs, only missing models will be calculated.  

### 2\. Lightweight Tool

This standalone node is designed for high-frequency, everyday use.

#### `Lora Trigger Words`

  * **Purpose**: Instantly fetches the two most important sets of trigger words for a LoRA model without any heavy processing.
  * **Inputs**: `lora_name`, `force_refresh`
  * **Outputs**:

| Output | Type | Description |
| :--- | :--- | :--- |
| `metadata_triggers` | `STRING` | Trigger words from the local file's metadata (`ss_tag_frequency`). Reflects the actual training data. |
| `civitai_triggers` | `STRING` | Official trigger words from the Civitai API (`trainedWords`). Reflects the author's recommendation. |

![lora_trigger_words example](./image/lora_trigger_words.png)

### 3\. Analyzer Pipeline

This is a powerful, modular pipeline for deep statistical model analysis.

#### `Civitai Data Fetcher (CKPT / LORA)`

  * **Purpose**: The engine of the pipeline. It fetches all community image metadata for a given model and outputs it as a single data package. **This is the only node in the pipeline that performs heavy network requests.**
  * **Inputs**: `model_name`, `max_pages`, `sort`, `retries`, `timeout`, `force_refresh`
  * **Outputs**: `civitai_data` (Data package), `fetch_summary` (STRING).

#### `Prompt Analyzer`, `Parameter Analyzer`, `Resource Analyzer`

  * **Purpose**: These nodes connect to the `civitai_data` output of the Fetcher to perform deep statistical analysis on prompts, parameters, and associated LoRA usage, respectively.

![Fetcher-Analyzer example](./image/F-A_workflow.png)

## Installation

1.  Place this project folder under ComfyUI’s `custom_nodes` directory, for example:
    ```
    ComfyUI/custom_nodes/CivitaiProject/
    ```
2.  Restart ComfyUI. You will find the new nodes in the menu under the `Civitai` category and its subcategories.

## Acknowledgements

During the development of this project, we drew inspiration and code references from the following excellent open-source projects:

* The logic for obtaining trigger words was inspired by and partially implemented based on [Extraltodeus/LoadLoraWithTags](https://github.com/Extraltodeus/LoadLoraWithTags) and [idrirap/ComfyUI-Lora-Auto-Trigger-Words](https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words).
* The design concept of the gallery node was inspired by [Firetheft/ComfyUI\_Civitai\_Gallery](https://github.com/Firetheft/ComfyUI_Civitai_Gallery).

We sincerely thank the authors of these projects for their valuable contributions!

---
