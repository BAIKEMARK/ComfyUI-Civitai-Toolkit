# Civitai Recipe Finder

> 👉 [点击这里查看中文文档](./README_ZH.md)

## Overview

To create stunning AI artworks, the key lies in finding the perfect **recipe**—the ideal combination of models, trigger words, prompts, and generation parameters. **Civitai Recipe Finder** is a powerful set of custom nodes for ComfyUI, designed to uncover these recipes by deeply analyzing community data from Civitai or providing instant visual feedback for your local models.

This toolkit provides multiple dimensions to explore creative recipes:

* **Visual Recipe Discovery**: Select a local model and instantly browse a gallery of popular community works created with it. With a single click, you can apply the complete recipe—including prompts, parameters, and LoRA combinations—and even load the original workflow.
* **Instant Trigger Words Lookup**: Quickly retrieve both official trigger words and metadata-based trigger words for any LoRA model.
* **Community Trends Discovery**: Analyze hundreds of community images to find the most frequently used positive and negative prompts.
* **Best Parameters Identification**: Detect the most common generation parameters (sampler, CFG, steps, etc.) used by the community for a specific model.
* **“Golden Combos” Exploration**: Discover which LoRA models are most often paired with your selected model.

The entire toolkit is built on a modular philosophy, enabling both fast visual exploration and complex, in-depth analysis workflows—while ensuring maximum efficiency.

---

## Node Suite Overview

The Recipe Finder consists of three independent groups of tools tailored to different needs.

### 1. Visual Recipe Finder

#### `Civitai Recipe Gallery`

* **Purpose**: Select a local model to visually explore popular community examples and instantly reproduce their full recipes.
* **New Features**:

  * **🚀 Load Workflow**: The “Load Workflow” button instantly and safely loads the original workflow from an image. If **ComfyUI-Manager** is detected, it will automatically open in a **new workflow tab** to protect your current work.
  * **💾 Save Original**: The “Save Original” button downloads the **unaltered original image** (including full workflow metadata) to your ComfyUI `output` folder for archiving.
* **Inputs**: `model_name`, `sort`, `nsfw_level`, `image_limit`
* **Outputs**:

| Output Port     | Type            | Description                                                                                                                                                |
| :-------------- | :-------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `image`         | `IMAGE`         | The selected example image, for preview or re-processing in the current workflow.                                                                          |
| `info_md`       | `STRING`        | A **unified, comprehensive report** describing all recipe parameters and your local LoRA availability. Connect this to a `MarkdownPresenter` node to view. |
| `recipe_params` | `RECIPE_PARAMS` | A **data pipeline** containing all core parameters for advanced automation workflows. Connect this to the `Recipe Params Parser` node to unpack.           |

> \[!NOTE]
> ⚠️ **First Run Performance Notice**
>
> * On first run, the tool will compute **hashes** for all your local models. This may take time, please be patient.
> * Results are cached in **`Civitai_Recipe_Finder/data`**.
> * Only missing models will be hashed in future runs.

---

![gallery example](./image/gallery.png)

#### `Recipe Params Parser`

* **Purpose**: A required companion node for `GalleryNode`. It **unpacks** the `recipe_params` pipeline into multiple standalone outputs. All outputs are normalized for direct compatibility with downstream nodes such as `KSampler`.
* **Input**: `recipe_params`
* **Outputs**: `positive_prompt`, `negative_prompt`, `seed`, `steps`, `cfg`, `sampler_name`, `scheduler`, `ckpt_name`, `width`, `height`, `denoise`.

---

### 2. Lightweight Tool

A standalone node designed for frequent, everyday use.

#### `Lora Trigger Words`

* **Purpose**: Instantly retrieve two sets of trigger words for any LoRA model, with minimal processing.
* **Inputs**: `lora_name`, `force_refresh`
* **Outputs**:

| Output Port         | Type     | Description                                                                                 |
| :------------------ | :------- | :------------------------------------------------------------------------------------------ |
| `metadata_triggers` | `STRING` | Trigger words extracted from local file metadata.                                           |
| `civitai_triggers`  | `STRING` | Official trigger words fetched from the Civitai API.                                        |
| **`triggers_md`**   | `STRING` | A formatted Markdown report comparing the two sources. Connect this to `MarkdownPresenter`. |

---

![lora\_trigger\_words example](./image/lora_trigger_words.png)

---

### 3. Analyzer Pipeline

A modular, powerful pipeline for in-depth statistical analysis of models.

#### `Civitai Data Fetcher (CKPT / LORA)`

* **Purpose**: The engine of the pipeline. It fetches all community image metadata for a specified model and outputs it as a dataset. **This is the only node in the pipeline performing heavy network requests.**
* **Inputs**: `model_name`, `max_pages`, `sort`, `retries`, `timeout`, `force_refresh`
* **Outputs**: `civitai_data` (dataset), `fetch_summary` (STRING).

#### `Prompt Analyzer`, `Parameter Analyzer`, `Resource Analyzer`

* **Purpose**: Specialized analysis nodes that connect to the `civitai_data` output from the fetcher.
* **Outputs**:

  * All three analyzers now provide a **single primary Markdown report output** (`..._report_md`). Connect this to a `MarkdownPresenter` node to view results.
  * For convenience, `ParameterAnalyzer` also outputs a small set of core parameters (`sampler`, `steps`, `cfg`) for direct workflow automation.

---

![Fetcher-Analyzer example](./image/F-A_workflow.png)

---

## Installation

1. Place the project folder inside ComfyUI’s `custom_nodes` directory, e.g.:

   ```bash
   ComfyUI/custom_nodes/CivitaiProject/
   ```
2. **Install required dependencies**. Run the following in your ComfyUI environment terminal:

   ```bash
   pip install -r requirements.txt
   ```
3. Restart ComfyUI. You will find all new nodes under the `Civitai` menu and its submenus.

> \[!TIP]
> The `MarkdownPresenter` node can be found under the `Display` menu, or by searching its name in the node search box.

## Workflow Examples

We’ve included ready-to-use workflow examples to make it easier for you to get started.

* **In ComfyUI**: Navigate to *Templates → Custom Nodes → ComfyUI-Civitai-Recipe*.
* **In the repository**: Check the `./example_workflows` folder here: [ComfyUI-Civitai-Recipe/example\_workflows](./example_workflows).

---
## Acknowledgements

This project was inspired by and builds upon the following excellent open-source projects:

* Trigger word logic and partial code were inspired by [Extraltodeus/LoadLoraWithTags](https://github.com/Extraltodeus/LoadLoraWithTags) and [idrirap/ComfyUI-Lora-Auto-Trigger-Words](https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words).
* The design of the gallery node was inspired by [Firetheft/ComfyUI\_Civitai\_Gallery](https://github.com/Firetheft/ComfyUI_Civitai_Gallery).

Sincere thanks to the authors of these projects!

---