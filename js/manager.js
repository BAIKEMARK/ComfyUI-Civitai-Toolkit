// file: manager.js (重构优化版)

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

// --- 状态管理对象 ---
const state = {
    models: [],       // 存储从后端获取的原始模型列表
    searchTerm: "",   // 当前搜索框的文本
    activeType: null, // 当前激活的分类 (e.g., 'checkpoints', 'loras')
};

// --- 辅助函数：构建文件树 (无改动) ---
function buildFileTree(files) {
    const tree = {};
    files.forEach(file => {
        const pathParts = file.filename.replace(/\\/g, '/').split('/');
        let currentLevel = tree;
        pathParts.forEach((part, index) => {
            if (index === pathParts.length - 1) {
                currentLevel[part] = file;
            } else {
                currentLevel[part] = currentLevel[part] || {};
                currentLevel = currentLevel[part];
            }
        });
    });
    return tree;
}

// --- 辅助函数：递归渲染树 (无改动) ---
function renderTree(container, treeNode) {
    const sortedKeys = Object.keys(treeNode).sort((a, b) => {
        const aIsFile = typeof treeNode[a].model_type !== 'undefined';
        const bIsFile = typeof treeNode[b].model_type !== 'undefined';
        if (aIsFile && !bIsFile) return 1;
        if (!aIsFile && bIsFile) return -1;
        return a.localeCompare(b);
    });

    for (const key of sortedKeys) {
        const node = treeNode[key];
        const isFile = typeof node.model_type !== 'undefined';

        if (isFile) {
            const card = renderModelCard(node);
            container.appendChild(card);
        } else {
            const details = document.createElement('details');
            details.className = 'folder-item';
            const summary = document.createElement('summary');
            summary.textContent = key;
            details.appendChild(summary);
            const subContainer = document.createElement('div');
            subContainer.className = 'folder-content';
            details.appendChild(subContainer);
            renderTree(subContainer, node);
            container.appendChild(details);
        }
    }
}

// --- 辅助函数：渲染单个模型卡片 (无改动) ---
function renderModelCard(model) {
    const card = document.createElement("div");
    card.className = "manager-model-card";
    const displayName = model.filename.split('/').pop().split('\\').pop();
    card.dataset.searchText = `${displayName} ${model.civitai_model_name || ''}`.toLowerCase();
    card.dataset.modelType = model.model_type.toLowerCase();

    card.innerHTML = `
        <div class="preview-container">
            <div class="preview-placeholder"></div>
        </div>
        <div class="model-info">
            <span class="model-filename" title="${model.filename}">${displayName}</span>
            <span class="model-type-badge model-type-${model.model_type}">${model.model_type}</span>
        </div>`;

    const previewUrl = model.local_cover_path || '';
    const placeholder = card.querySelector('.preview-placeholder');
    const previewContainer = card.querySelector('.preview-container');

    if (previewUrl) {
        const img = document.createElement('img');
        img.className = 'preview-img';
        img.alt = 'preview';
        img.loading = 'lazy';
        img.onload = () => { placeholder.style.display = 'none'; img.style.display = 'block'; };
        img.onerror = () => {
            const urlForLog = previewUrl.startsWith("data:image") ? previewUrl.substring(0, 100) + '...' : previewUrl;
            console.error(`[Civitai Manager] Failed to load cover image. URL: ${urlForLog}`);
            placeholder.style.display = 'flex'; placeholder.innerHTML = '⚠️'; img.remove();
        };
        img.src = previewUrl;
        previewContainer.prepend(img);
        if (img.complete) img.onload();
    } else {
        placeholder.style.display = 'flex';
    }

    card.onclick = () => createModelInfoPopup(displayName, model);
    return card;
}

// --- 辅助函数：创建模型信息弹窗 (无改动) ---
function createModelInfoPopup(title, model) {
    const existing = document.querySelector('.civitai-manager-popup');
    if (existing) existing.remove();
    const popup = document.createElement('div');
    popup.className = 'civitai-manager-popup';
    const data = model;
    const descriptionHTML = data.description ? new DOMParser().parseFromString(data.description, "text/html").body.innerHTML : "<em>No Civitai description.</em>";
    const triggersHTML = data.trained_words && data.trained_words.length > 0
        ? data.trained_words.map(tag => `<code class="trigger-word">${tag}</code>`).join(' ') : '<em>None</em>';
    popup.innerHTML = `
        <div class="popup-content">
            <span class="popup-close">&times;</span><h2>${title}</h2>
            <div class="popup-body">
                <div class="info-grid">
                    <div><strong>Civitai Name:</strong> ${data.civitai_model_name || 'N/A'}</div>
                    <div><strong>Version:</strong> ${data.version_name || 'N/A'}</div>
                    <div><strong>Base Model:</strong> ${data.base_model || 'N/A'}</div>
                    <div><strong>Downloads:</strong> ${data.civitai_stats?.downloadCount || 0}</div>
                    <div><strong>Rating:</strong> ${data.civitai_stats?.rating?.toFixed(2) || 'N/A'} (${data.civitai_stats?.ratingCount || 0} ratings)</div>
                </div><hr>
                <div class="info-section"><h4>Trigger Words</h4><div class="triggers-container">${triggersHTML}</div></div><hr>
                <div class="info-section"><h4>Description</h4><div class="model-description-content">${descriptionHTML}</div></div><hr>
                <p class="hash-info"><strong>Hash:</strong> ${data.hash || 'N/A'}</p>
            </div>
        </div>`;
    const close = () => { popup.remove(); window.removeEventListener("keydown", onKeyDown); };
    const onKeyDown = (e) => { if (e.key === "Escape") close(); };
    popup.onclick = (e) => { if (e.target === popup) close(); };
    window.addEventListener("keydown", onKeyDown);
    popup.querySelector('.popup-close').onclick = close;
    document.body.appendChild(popup);
}


// --- 核心UI渲染函数 ---
function render(container) {
    const listContainer = container.querySelector("#manager-model-list");
    const emptyMessage = container.querySelector(".empty-message");
    const tabs = container.querySelectorAll("#manager-filter-tabs button");

    // 1. 过滤模型
    let filteredModels = state.models;
    if (state.searchTerm) {
        const term = state.searchTerm.toLowerCase();
        filteredModels = filteredModels.filter(m => {
            const displayName = m.filename.split('/').pop().split('\\').pop();
            const searchText = `${displayName} ${m.civitai_model_name || ''}`.toLowerCase();
            return searchText.includes(term);
        });
    }
    // 如果不是在全局搜索模式下，则按分类过滤
    if (state.activeType) {
        filteredModels = filteredModels.filter(m => m.model_type.toLowerCase() === state.activeType);
    }

    // 2. 更新UI
    listContainer.innerHTML = ''; // 清空列表

    if (filteredModels.length === 0) {
        emptyMessage.style.display = 'block'; // 显示空状态
    } else {
        emptyMessage.style.display = 'none'; // 隐藏空状态

        // 按模型类型分组
        const modelsByType = filteredModels.reduce((acc, model) => {
            const type = model.model_type;
            if (!acc[type]) acc[type] = [];
            acc[type].push(model);
            return acc;
        }, {});

        // 渲染分组后的模型
        const sortedTypes = Object.keys(modelsByType).sort();
        for (const modelType of sortedTypes) {
            // 仅在全局搜索时才显示分组标题
            if (!state.activeType) {
                 const typeHeader = document.createElement('h3');
                 typeHeader.className = 'model-type-header';
                 typeHeader.textContent = modelType.charAt(0).toUpperCase() + modelType.slice(1);
                 listContainer.appendChild(typeHeader);
            }

            const fileTree = buildFileTree(modelsByType[modelType]);
            renderTree(listContainer, fileTree);
        }
    }

    // 3. 更新标签的激活状态
    tabs.forEach(t => {
        t.classList.toggle('active', t.dataset.type === state.activeType);
    });
}


// --- 数据加载函数 ---
async function loadModels(container, forceRefresh = false) {
    const listContainer = container.querySelector("#manager-model-list");
    const spinner = container.querySelector(".loading-spinner");
    const emptyMessage = container.querySelector(".empty-message");

    listContainer.innerHTML = '';
    spinner.style.display = 'block';
    emptyMessage.style.display = 'none';

    try {
        const response = await api.fetchApi(`/civitai_utils/get_local_models?force_refresh=${forceRefresh}`);
        const data = await response.json();
        if (data.status !== 'ok' || !data.models) {
            throw new Error(data.message || "Failed to load models.");
        }

        state.models = data.models;

        // 设置默认激活的标签
        const tabs = container.querySelectorAll("#manager-filter-tabs button");
        if (tabs.length > 0) {
            state.activeType = tabs[0].dataset.type;
        } else {
            state.activeType = null;
        }

    } catch (e) {
        console.error(e);
        emptyMessage.textContent = `Error loading models: ${e.message}`;
        emptyMessage.style.display = 'block';
        state.models = [];
    } finally {
        spinner.style.display = 'none';
        render(container); // 初始渲染
    }
}


app.registerExtension({
    name: "Comfy.Civitai.ModelManager",
    async setup() {
        // --- 样式定义 (包含动画和美化) ---
        const styleId = "civitai-manager-styles";
        if (!document.getElementById(styleId)) {
            const style = document.createElement("style");
            style.id = styleId;
            style.textContent = `
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                .loading-spinner { 
                    border: 4px solid var(--border-color); 
                    border-top: 4px solid var(--accent-color); 
                    border-radius: 50%; 
                    width: 40px; height: 40px; 
                    animation: spin 1s linear infinite; 
                    margin: 40px auto; 
                    display: none; 
                }
                .empty-message { 
                    text-align: center; 
                    color: var(--desc-text-color); 
                    margin-top: 40px; 
                    display: none; 
                }
                .empty-message::before {
                    content: '🤷';
                    display: block;
                    font-size: 2em;
                    margin-bottom: 10px;
                }
                .manager-model-card, #manager-filter-tabs button {
                    transition: all 0.2s ease-in-out;
                }
                /* 其余样式保持不变 */
                #civitai-manager-container-wrapper { padding: 5px; box-sizing: border-box; }
                .model-tree-container, .folder-content { display: flex; flex-direction: column; gap: 8px; }
                .folder-item { margin-left: 0; }
                .folder-item summary { cursor: pointer; padding: 4px; border-radius: 4px; list-style: none; display: flex; align-items: center; gap: 5px; margin-left: -5px; }
                .folder-item summary::before { content: '📁'; font-size: 0.9em; }
                .folder-item[open] > summary::before { content: '📂'; }
                .folder-item summary:hover { background-color: var(--comfy-menu-bg); }
                .folder-item[open] > summary { margin-bottom: 8px; }
                .folder-content { margin-left: 15px; border-left: 1px solid #444; padding-left: 10px; }
                .model-type-header { margin: 10px 0 5px 0; font-size: 1.1em; color: var(--fg-color); border-bottom: 1px solid var(--border-color); padding-bottom: 5px; }
                .manager-header { display: flex; gap: 5px; margin-bottom: 10px; }
                #manager-search-input { flex-grow: 1; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); }
                #manager-refresh-btn { flex-shrink: 0; cursor: pointer; background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 4px; }
                .manager-model-card { margin-left: 0 !important; display: flex; align-items: center; gap: 10px; padding: 8px; background: var(--comfy-box-bg); border-radius: 5px; cursor: pointer; border: 1px solid transparent; }
                .manager-model-card:hover { border-color: var(--accent-color); background-color: var(--comfy-menu-bg); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
                .preview-container { width: 60px; height: 80px; flex-shrink: 0; position: relative; display: flex; justify-content: center; align-items: center; }
                .manager-model-card .preview-img { width: 100%; height: 100%; object-fit: cover; border-radius: 4px; }
                .manager-model-card .preview-placeholder { width: 100%; height: 100%; background: #333; border-radius: 4px; display: flex; justify-content: center; align-items: center; font-size: 1.5em; color: #555; }
                .manager-model-card .model-info { display: flex; flex-direction: column; gap: 4px; overflow: hidden; }
                .manager-model-card .model-filename { font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--fg-color); }
                .manager-model-card .model-type-badge { font-size: 0.8em; padding: 2px 6px; border-radius: 8px; color: white; width: fit-content; text-transform: capitalize; }
                .manager-model-card .model-type-checkpoints { background-color: #4A90E2; }
                .manager-model-card .model-type-loras { background-color: #50E3C2; }
                .manager-model-card .model-type-vae { background-color: #B8860B; }
                .manager-model-card .model-type-embeddings { background-color: #9055E9; }
                .manager-model-card .model-type-hypernetworks { background-color: #E95589; }
                #manager-filter-tabs { display: flex; gap: 5px; margin-bottom: 10px; flex-wrap: wrap; }
                #manager-filter-tabs button { background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 12px; padding: 4px 12px; cursor: pointer; font-size: 0.9em; }
                #manager-filter-tabs button:hover:not(.active) { border-color: var(--desc-text-color); }
                #manager-filter-tabs button.active { background: var(--accent-color); color: white; border-color: var(--accent-color); }
                .civitai-manager-popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; justify-content: center; align-items: center; }
                .civitai-manager-popup .popup-content { background: var(--comfy-menu-bg); padding: 20px; border-radius: 8px; max-width: 800px; width: 90%; position: relative; border: 1px solid var(--border-color); display: flex; flex-direction: column; max-height: 90vh; }
                .civitai-manager-popup .popup-close { position: absolute; top: 10px; right: 15px; font-size: 24px; cursor: pointer; color: var(--fg-color); }
                .civitai-manager-popup .popup-body { margin-top: 15px; overflow-y: auto; word-break: break-word; }
                .civitai-manager-popup .model-description-content img { max-width: 100%; height: auto; }
                .civitai-manager-popup .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-bottom: 15px; }
                .civitai-manager-popup .info-section { margin-bottom: 15px; }
                .civitai-manager-popup .triggers-container { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
                .civitai-manager-popup .trigger-word { background: var(--comfy-input-bg); padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border-color); }
                .civitai-manager-popup .hash-info { font-size: 0.9em; opacity: 0.7; margin-top: 15px; }
            `;
            document.head.appendChild(style);
        }

        // --- UI创建和事件绑定 ---
        app.extensionManager.registerSidebarTab({
            id: "civitai.modelManager", title: "Model Manager",
            icon: "pi pi-folder", tooltip: "Local Model Manager",
            type: "custom",
            render(el) {
                const container = document.createElement('div');
                container.id = "civitai-manager-container-wrapper";

                // 移除"All"标签，并动态生成标签页
                const tabTypes = ["checkpoints", "loras", "vae", "embeddings"];
                const tabButtons = tabTypes.map(t => `<button data-type="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</button>`).join('');

                container.innerHTML = `
                    <div id="civitai-manager-container">
                        <div class="manager-header">
                            <input type="search" id="manager-search-input" placeholder="Search all models...">
                            <button id="manager-refresh-btn" title="Force Refresh & Rescan All">🔄</button>
                        </div>
                        <div id="manager-filter-tabs">${tabButtons}</div>
                        <div id="manager-model-list"></div>
                        <div class="loading-spinner"></div>
                        <div class="empty-message">No models found.</div>
                    </div>`;

                const managerUi = container.querySelector("#civitai-manager-container");

                // 绑定事件
                managerUi.querySelector("#manager-search-input").addEventListener("input", (e) => {
                    state.searchTerm = e.target.value;
                    // 输入时，进入全局搜索模式
                    if (state.searchTerm) {
                        state.activeType = null;
                    } else {
                        // 清空搜索时，恢复到默认标签
                        const firstTab = managerUi.querySelector("#manager-filter-tabs button");
                        state.activeType = firstTab ? firstTab.dataset.type : null;
                    }
                    render(managerUi);
                });

                managerUi.querySelector("#manager-refresh-btn").onclick = () => {
                    managerUi.querySelector("#manager-search-input").value = '';
                    state.searchTerm = '';
                    loadModels(managerUi, true);
                };

                managerUi.querySelectorAll("#manager-filter-tabs button").forEach(tab => {
                    tab.onclick = () => {
                        state.activeType = tab.dataset.type;
                        // 点击标签页时，我们认为用户想在该分类下浏览，可以清空搜索词
                        // managerUi.querySelector("#manager-search-input").value = '';
                        // state.searchTerm = '';
                        render(managerUi);
                    };
                });

                el.appendChild(container);
                loadModels(managerUi);
            }
        });
    }
});