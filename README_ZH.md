# Civitai Toolkit（Civitai 工具箱）

<details>
  <summary>🕒 <b>更新日志（点击展开）</b></summary>

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

---

## [4.0.2] - 2025-10-07

### ✨ 新增

#### 🔑 **API Key 管理功能**

* 在 **ComfyUI 设置面板** 中新增了全新的 **「API Key Management」** 区域。  
* 用户现在可以在 **Civitai 账户页面** 创建 API Key，并在此处填写。  
* 保存后，插件发往 Civitai 的所有请求将自动携带 **Authorization** 认证信息。  

💡 **功能说明**：  
该功能可帮助用户突破默认的 API 请求频率限制，并为未来可能需要身份验证的功能提前做好准备。  
您可以前往 Civitai 官网的 **「用户账户设置」** 页面创建并管理您的 API Key。  

---

## [4.0.1] - 2025-10-06

### 🛠 修复  
* **启动卡顿问题**：部分用户在拥有大量 LoRA 模型（约数百个以上）时，报告插件在启动时长时间停留在加载界面。本次更新已修复该问题。  

### ⚡ 优化  
* **后台异步处理**：  
  * 现在模型的 **Hash 计算与信息同步（Fetch Info）** 将在后台自动执行，不再阻塞 ComfyUI 的启动界面。  
  * 用户可在进入 ComfyUI 后继续操作，系统会在后台完成模型信息加载。  
* **断点续连机制**：  
  * 新增 **进度持久化功能**，在哈希或信息同步过程中中断（如崩溃、重启）后，可自动恢复上次的进度，无需重新扫描全部模型。  

### 📘 说明  
* 此次更新主要针对 **模型数量庞大时的性能问题** 进行优化，极大提升了启动速度与稳定性。  
* 感谢社区用户的反馈与耐心测试 ❤️  

---

## [4.0.0] - 2025-10-05

#### 💥 重大变更  
* 项目正式更名为 **Civitai Toolkit**，以体现综合性工具套件定位。  
* 原 `Recipe Finder` 现作为核心功能模块保留。  

#### ✨ 新增与优化  
* **新增双侧边栏 UI**：`本地模型管理器` 与 `Civitai 在线浏览器`。  
* **全面优化交互体验**：模型管理与发现效率显著提升。  

</details>


## 项目简介

**Civitai Toolkit** 是一套专为 **ComfyUI** 打造的 **一站式 Civitai 集成中心**。
它将 **在线浏览与发现**、**本地模型管理**、**配方复现与数据分析** 三大核心功能完美融合，让您在创作工作流中即可完成从灵感发现到最终实现的全过程。

不再需要在浏览器与文件管理器之间反复切换——通过两款强大的 **常驻侧边栏** 与一组专业的 **分析节点工具**，您即可在 ComfyUI 内畅享完整的 Civitai 使用体验。

---

## ✨ 功能亮点

* 🌍 **Civitai 在线浏览器**
  在 ComfyUI 内直接访问 Civitai，搜索、筛选、下载模型一步到位。

* 🗂️ **本地模型管理器**
  轻松浏览、搜索和分类您的本地模型，自动关联 Civitai 社区信息。

* 🔍 **可视化配方查找**
  一键浏览模型的热门作品，快速复现其完整配方（提示词、参数、LoRA 组合等）。

* 📊 **社区趋势分析**
  自动统计社区常用参数，提取最受欢迎的采样器、CFG、提示词等黄金组合。

* 🔗 **黄金组合发现**
  揭示模型间的高频搭配关系，助您挖掘潜在创作灵感。

* ⚡ **即时触发词提取**
  同时提取官方与本地元数据触发词，并生成美观的 Markdown 对照表。

---

## 🧭 两大核心界面：侧边栏系统

### 🌍 Civitai 在线浏览器（Civitai Online Browser）

**核心特性：**

* 🔎 **多维度搜索与筛选**：支持关键词、模型类型、基础模型、排序方式（最热 / 最新 / 最高评分）等。
* 🔄 **本地状态同步**：自动识别已下载模型，并标注“**已下载**”徽章，避免重复下载。
* 🖼️ **沉浸式详情页**：展示模型介绍、版本切换、示例画廊、文件列表与直接下载链接。

<div align="center" style="display: flex; flex-wrap: wrap; justify-content: center;">
  <img src="./image/Civitai_Browser.png" alt="Civitai Browser" width="48%" />
  <img src="./image/Civitai_Browser_pop.png" alt="Civitai Browser Pop" width="48%" />
</div>


---

### 🗂️ 本地模型管理器（Local Model Manager）

**核心特性：**

* 🔍 **自动扫描与识别**：自动索引本地模型并通过 Hash 匹配 Civitai 数据库，获取完整社区信息。
* 💬 **信息展示丰富**：点击模型卡片可查看版本说明、触发词、社区评分、下载量等。
* ⚡ **便捷交互体验**：支持类型筛选、关键词搜索，并提供触发词 / Hash 一键复制。
<div align="center" style="display: flex; flex-wrap: wrap; justify-content: center;">
  <img src="./image/Local_Manager.png" alt="Civitai Browser" width="48%" />
  <img src="./image/Local_Manager_pop.png" alt="Civitai Browser Pop" width="48%" />
</div>

---

## 🧩 核心节点套件

### 1️⃣ 可视化配方查找器（Visual Recipe Finder）

#### `Civitai Recipe Gallery`（Civitai 配方画廊）

* 浏览指定模型的热门作品，一键加载其完整配方。
* 🚀 **一键加载工作流**：智能、安全地恢复图片原始工作流（兼容 ComfyUI-Manager）。
* 💾 **保存源文件**：支持下载含元数据的原始图像至 `output` 目录。

| 输出端口            | 类型              | 说明                                         |
| --------------- | --------------- | ------------------------------------------ |
| `image`         | `IMAGE`         | 选中的示例图片                                    |
| `info_md`       | `STRING`        | 配方 Markdown 报告（推荐接入 `MarkdownPresenter`）   |
| `recipe_params` | `RECIPE_PARAMS` | 核心参数管道（配合 `Get Parameters from Recipe` 使用） |

> ⚠️ **首次运行提示**：
> 首次运行会计算本地模型 Hash（可能耗时较长），结果缓存至 `Civitai Toolkit/data`或`Civitai_Recipe_Finder/data`，后续仅增量处理。

![gallery example](./example_workflows/Recipe_Gallery.png)

#### `Get Parameters from Recipe`（从配方获取参数）

解包 `recipe_params` 管道，输出可直接用于 `KSampler` 等节点的生成参数：
`ckpt_name`, `positive_prompt`, `negative_prompt`, `seed`, `steps`, `cfg`, `sampler_name`, `scheduler`, `width`, `height`, `denoise`。

---

### 2️⃣ 模型深度分析（In-Depth Model Analysis）

核心节点：`Model Analyzer (Checkpoint / LoRA)`

**功能特性：**

* 一站式完成数据抓取 → 社区统计 → 参数分析 → 报告输出。
* 替代旧版多节点组合，分析更快更清晰。

**输入**：`model_name`, `image_limit`, `sort`, `nsfw_level`, `filter_type`, `summary_top_n`, `force_refresh`
**输出**：

* `full_report_md`：完整 Markdown 报告
* `fetch_summary`：抓取摘要（如“成功分析 100 个项目”）
* `params_pipe`：社区常用参数（配合 `Get Parameters from Analysis` 解包）

![Model\_DeepResearch example](./example_workflows/Model_DeepResearch.png)

#### `Get Parameters from Analysis` (从分析获取参数)

解包 `params_pipe`，提取社区常用参数。 与 `Get Parameters from Recipe` 相同。

---

### 3️⃣ 轻量级工具（Lightweight Tools）

#### `Lora Trigger Words`（LoRA 触发词）

即时提取 LoRA 模型的触发词：

| 输出端口                | 类型       | 内容           |
| ------------------- | -------- | ------------ |
| `metadata_triggers` | `STRING` | 本地元数据触发词     |
| `civitai_triggers`  | `STRING` | 官方 API 触发词   |
| `triggers_md`       | `STRING` | Markdown 对照表 |

![lora\_trigger\_words example](./example_workflows/LoRA_Trigger_Words.png)

---

## ⚙️ 安装与使用

### ✅ 手动安装

```bash
ComfyUI/custom_nodes/ComfyUI-Civitai-Toolkit/
pip install -r requirements.txt
```

### ✅ ComfyUI Manager 安装

在 ComfyUI Manager 中搜索 **Civitai Toolkit**，点击“安装”，然后重启 ComfyUI。
安装后即可在侧边栏与 `Civitai` 节点菜单中找到工具箱。

> 💡 小贴士：
> `Markdown Presenter` 节点可在 `Display` 分类下找到。

---

## 🧪 工作流示例

* **ComfyUI 内置模板**：`Templates → Custom Nodes → ComfyUI-Civitai-Recipe`
* **仓库示例目录**：[example_workflows](./example_workflows)

---

## 🔧 版本兼容性

* **3.1 及之前版本迁移**：
  打开 `Settings → CivitaiUtils → Migration`，即可将旧版 JSON 缓存迁移到新数据库。

---

## 🌐 国内网络支持

在 `Settings → CivitaiUtils → Civitai Helper Network` 中选择访问环境：

* 🌏 **International（默认）** – 国际访问
* 🇨🇳 **China Mirror** – 国内镜像，加速访问更稳定

![Network\_setting](./image/Network_setting.png)

---

## 🙏 鸣谢

* 触发词逻辑参考：

  * [Extraltodeus/LoadLoraWithTags](https://github.com/Extraltodeus/LoadLoraWithTags)
  * [idrirap/ComfyUI-Lora-Auto-Trigger-Words](https://github.com/idrirap/ComfyUI-Lora-Auto-Trigger-Words)

* 画廊设计思路参考：

  * [Firetheft/ComfyUI_Civitai_Gallery](https://github.com/Firetheft/ComfyUI_Civitai_Gallery)

* 侧边栏设计参考：

  * [BlafKing/sd-civitai-browser-plus](https://github.com/BlafKing/sd-civitai-browser-plus)

> 向以上优秀项目及作者致以诚挚感谢 🙌