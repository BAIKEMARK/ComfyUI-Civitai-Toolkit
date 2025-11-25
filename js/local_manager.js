import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const state = { models: [], searchTerm: "", activeType: null };
let managerUiContainer = null; // 用于存储UI容器的引用


// --- 辅助函数：构建文件树 ---
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

// --- 辅助函数：递归渲染树 ---
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
            container.appendChild(renderModelCard(node));
        } else {
            const details = document.createElement('details');
            details.className = 'folder-item';
            details.innerHTML = `<summary>${key}</summary><div class="folder-content"></div>`;
            renderTree(details.querySelector('.folder-content'), node);
            container.appendChild(details);
        }
    }
}

// --- 辅助函数：渲染单个模型卡片 ---
function renderModelCard(model) {
    const card = document.createElement("div");
    card.className = "manager-model-card";
    const displayName = model.filename.split('/').pop().split('\\').pop();

    card.dataset.searchText = `${displayName} ${model.civitai_model_name || ''} ${model.base_model || ''}`.toLowerCase();
    card.dataset.modelType = model.model_type.toLowerCase();

    // 使用带有额外信息的UI布局
    card.innerHTML = `
        <div class="preview-container"><div class="preview-placeholder"></div></div>
        <div class="model-info">
            <span class="model-civitai-name" title="${model.civitai_model_name || 'Name not found on Civitai'}">${model.civitai_model_name || displayName}</span>
            <span class="model-filename" title="${model.filename}">${(model.civitai_model_name && model.civitai_model_name.toLowerCase() !== displayName.toLowerCase()) ? displayName : ''}</span>
            <div class="model-badges">
                <span class="model-type-badge model-type-${model.model_type}">${model.model_type}</span>
                ${model.base_model && model.base_model !== 'N/A' ? `<span class="model-base-badge">${model.base_model}</span>` : ''}
            </div>
        </div>`;

    const placeholder = card.querySelector('.preview-placeholder');
    const previewContainer = card.querySelector('.preview-container');

    const previewUrl = model.local_cover_path || '';

    if (previewUrl) {
        const img = new Image();
        img.className = 'preview-img';
        img.alt = 'preview';
        img.loading = 'lazy';
        img.onload = () => { placeholder.style.display = 'none'; img.style.display = 'block'; };
        img.onerror = () => {
            console.error(`[Civitai Manager] Failed to load cover image. URL: ${previewUrl}`);
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


// --- 辅助函数：创建模型信息弹窗 ---
function createModelInfoPopup(title, model) {
    const existing = document.querySelector('.civitai-manager-popup');
    if (existing) existing.remove();
    const popup = document.createElement('div');
    popup.className = 'civitai-manager-popup';
    const data = model;

    const copyToClipboard = (text, targetElement) => {
        navigator.clipboard.writeText(text).then(() => {
            const originalText = targetElement.innerHTML;
            targetElement.innerHTML = 'Copied!';
            targetElement.classList.add('copied');
            setTimeout(() => {
                targetElement.innerHTML = originalText;
                targetElement.classList.remove('copied');
            }, 1500);
        }).catch(err => console.error('Failed to copy text: ', err));
    };

    const parseHtml = (htmlString) => new DOMParser().parseFromString(htmlString, "text/html").body.innerHTML;

    const versionDescriptionHTML = data.version_description ? parseHtml(data.version_description) : "";
    const modelDescriptionHTML = data.model_description ? parseHtml(data.model_description) : "<em>No description available.</em>";

    const triggersHTML = data.trained_words && data.trained_words.length > 0
        ? data.trained_words.map(tag => `<code class="trigger-word" title="Click to copy">${tag}</code>`).join('')
        : '<em>None specified</em>';

    const copyAllTriggersBtn = (data.trained_words && data.trained_words.length > 0)
        ? `<button class="copy-all-btn" data-text="${data.trained_words.join(', ')}">Copy All</button>` : '';

    const tagsHTML = data.tags && data.tags.length > 0
        ? `<div class="detail-tags">${data.tags.map(tag => `<span class="detail-tag">${tag}</span>`).join('')}</div>`
        : '<em>No tags found.</em>';

    popup.innerHTML = `
        <div class="popup-content">
            <div class="popup-header">
                <h2>${title}</h2>
                <span class="popup-close" title="Close">&times;</span>
            </div>
            <div class="popup-body">
                <div class="info-grid">
                    <div class="info-item"><strong>Civitai Name:</strong> <span>${data.civitai_model_name || 'N/A'}</span></div>
                    <div class="info-item"><strong>Version:</strong> <span>${data.version_name || 'N/A'}</span></div>
                    <div class="info-item"><strong>Base Model:</strong> <span>${data.base_model || 'N/A'}</span></div>
                    <div class="info-item"><strong>Downloads:</strong> <span>${data.civitai_stats?.downloadCount || 0}</span></div>
                    <div class="info-item"><strong>Rating:</strong> <span>${(data.civitai_stats?.rating !== undefined) ? (data.civitai_stats.rating.toFixed(1) + ' (' + data.civitai_stats.ratingCount + ')') : ('👍 ' + (data.civitai_stats?.thumbsUpCount || 0))}</span></div>
                </div>
                <div class="info-section">
                    <h4>Tags</h4>
                    ${tagsHTML}
                </div>
                <div class="info-section">
                    <div class="section-header">
                        <h4>Trigger Words</h4>
                        ${copyAllTriggersBtn}
                    </div>
                    <div class="triggers-container">${triggersHTML}</div>
                </div>
                ${versionDescriptionHTML ? `
                <div class="info-section">
                    <h4>Version Description</h4>
                    <div class="model-description-content version-desc">${versionDescriptionHTML}</div>
                </div>
                ` : ''}
                <div class="info-section">
                     <details class="description-details" open>
                        <summary>Model Description</summary>
                        <div class="model-description-content">${modelDescriptionHTML}</div>
                     </details>
                </div>
                <div class="info-section hash-section">
                    <strong>Hash:</strong> 
                    <code class="hash-code">${data.hash || 'N/A'}</code>
                    <button class="copy-btn" data-text="${data.hash || ''}">Copy</button>
                </div>
            </div>
        </div>`;

    document.body.appendChild(popup);

    const close = () => popup.remove();
    popup.querySelector('.popup-close').onclick = close;
    popup.onclick = (e) => { if (e.target === popup) close(); };

    popup.querySelectorAll('.trigger-word').forEach(el => {
        el.onclick = () => copyToClipboard(el.textContent, el);
    });
    const copyAllBtn = popup.querySelector('.copy-all-btn');
    if (copyAllBtn) {
        copyAllBtn.onclick = (e) => copyToClipboard(e.target.dataset.text, e.target);
    }
    const copyHashBtn = popup.querySelector('.hash-section .copy-btn');
    if (copyHashBtn) {
        copyHashBtn.onclick = (e) => copyToClipboard(e.target.dataset.text, e.target);
    }
}


// --- 核心UI渲染函数 ---
function render(container) {
    const listContainer = container.querySelector("#manager-model-list");
    const emptyMessage = container.querySelector(".empty-message");
    const tabs = container.querySelectorAll("#manager-filter-tabs button");

    let filteredModels = state.models;
    if (state.searchTerm) {
        const term = state.searchTerm.toLowerCase();
        filteredModels = filteredModels.filter(m => {
            const displayName = m.filename.split('/').pop().split('\\').pop();
            const searchText = `${displayName} ${m.civitai_model_name || ''} ${m.base_model || ''}`.toLowerCase();
            return searchText.includes(term);
        });
    }
    if (state.activeType) {
        filteredModels = filteredModels.filter(m => m.model_type.toLowerCase() === state.activeType);
    }

    listContainer.innerHTML = '';
    if (filteredModels.length === 0) {
        emptyMessage.style.display = 'block';
    } else {
        emptyMessage.style.display = 'none';
        const modelsByType = filteredModels.reduce((acc, model) => {
            const type = model.model_type;
            if (!acc[type]) acc[type] = [];
            acc[type].push(model);
            return acc;
        }, {});
        const sortedTypes = Object.keys(modelsByType).sort();
        for (const modelType of sortedTypes) {
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

    tabs.forEach(t => {
        t.classList.toggle('active', t.dataset.type === state.activeType);
    });
}


// --- 数据加载函数 ---
async function loadModels(container, forceRefresh = false) {
    // 如果已有模型数据且不是强制刷新，则直接渲染，避免不必要的API请求
    if (state.models.length > 0 && !forceRefresh) {
        render(container);
        return;
    }

    const listContainer = container.querySelector("#manager-model-list");
    const spinner = container.querySelector(".loading-spinner");
    const emptyMessage = container.querySelector(".empty-message");

    listContainer.innerHTML = '';
    spinner.style.display = 'block';
    emptyMessage.style.display = 'none';
    container.querySelector("#manager-model-list").innerHTML = '';

    try {
        const response = await api.fetchApi(`/civitai_utils/get_local_models?force_refresh=${forceRefresh}`);
        const data = await response.json();
        if (data.status !== 'ok' || !data.models) {
            throw new Error(data.message || "Failed to load models.");
        }

        if (data.models.length === 0) {
            // 如果模型列表为空，检查后台扫描状态
            const statusRes = await api.fetchApi('/civitai_utils/get_scan_status');
            const statusData = await statusRes.json();
            if (statusData.is_scanning) {
                emptyMessage.innerHTML = 'Initial model indexing is in progress in the background, please wait... <br>The list will be refreshed automatically when completed.';
            } else {
                emptyMessage.innerHTML = 'No models found.';
            }
        }

        state.models = data.models;
        const tabs = container.querySelectorAll("#manager-filter-tabs button");
        if (tabs.length > 0 && !state.activeType && !state.searchTerm) { // 仅在初次加载时设置
            state.activeType = tabs[0].dataset.type;
        }
    } catch (e) {
        console.error(e);
        emptyMessage.textContent = `Error loading models: ${e.message}`;
        emptyMessage.style.display = 'block';
        state.models = [];
    } finally {
        spinner.style.display = 'none';
        render(container);
    }
}


app.registerExtension({
    name: "Comfy.Civitai.LocalManager",
    async setup() {
        // 监听后台扫描完成的 WebSocket 消息
        const originalOnMessage = api.socket.onmessage;
        api.socket.onmessage = function(event) {
            if(originalOnMessage) originalOnMessage.apply(this, arguments);
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "scan_complete" && msg.data.success) {
                    if (managerUiContainer) {
                        // 自动触发一次强制刷新来显示最新结果
                        console.log("[Civitai Toolkit] Background scan complete. Auto-refreshing Local Manager.");
                        loadModels(managerUiContainer, true);
                    }
                }
            } catch(e) {}
        };

        const styleId = "civitai-manager-styles";
        if (!document.getElementById(styleId)) {
            const style = document.createElement("style");
            style.id = styleId;
            style.textContent = `
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                .loading-spinner { border: 4px solid var(--border-color); border-top: 4px solid var(--accent-color); border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 40px auto; display: none; }
                .empty-message { text-align: center; color: var(--desc-text-color); margin-top: 40px; display: none; }
                #civitai-manager-container-wrapper { padding: 5px; box-sizing: border-box; display: flex; flex-direction: column; height: 100%;}
                #manager-model-list { flex-grow: 1; overflow-y: auto; }
                .folder-item summary { cursor: pointer; padding: 4px; border-radius: 4px; list-style: none; }
                .folder-item summary::before { content: '📁'; margin-right: 5px; }
                .folder-item[open] > summary::before { content: '📂'; }
                .folder-content { margin-left: 20px; border-left: 1px solid #444; padding-left: 10px; }
                .model-type-header { margin: 10px 0 5px 0; font-size: 1.1em; color: var(--fg-color); border-bottom: 1px solid var(--border-color); padding-bottom: 5px; }
                .manager-header { display: flex; gap: 5px; margin-bottom: 10px; }
                #manager-search-input { flex-grow: 1; }
                #manager-filter-tabs { display: flex; gap: 5px; margin-bottom: 10px; flex-wrap: wrap; }
                #manager-filter-tabs button { background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 12px; padding: 4px 12px; cursor: pointer; font-size: 0.9em; transition: all 0.2s ease-in-out; }
                #manager-filter-tabs button:hover:not(.active) { border-color: var(--desc-text-color); }
                #manager-filter-tabs button.active { background: var(--accent-color); color: white; border-color: var(--accent-color); }
                .manager-model-card { display: flex; align-items: center; gap: 10px; padding: 8px; background: var(--comfy-box-bg); border-radius: 5px; cursor: pointer; border: 1px solid transparent; transition: all 0.2s ease-in-out; }
                .manager-model-card:hover { border-color: var(--accent-color); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
                .preview-container { width: 60px; height: 80px; flex-shrink: 0; position: relative; display: flex; justify-content: center; align-items: center; background: #333; border-radius: 4px; overflow: hidden; }
                .preview-img { width: 100%; height: 100%; object-fit: cover;}
                .preview-placeholder { font-size: 1.5em; color: #555; display: flex; }
                .model-info { display: flex; flex-direction: column; gap: 5px; overflow: hidden; }
                .model-civitai-name { font-weight: bold; color: var(--fg-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .model-filename { font-size: 0.8em; color: var(--desc-text-color); opacity: 0.7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .model-badges { display: flex; gap: 6px; }
                .model-type-badge, .model-base-badge { font-size: 0.75em; padding: 2px 6px; border-radius: 8px; color: white; width: fit-content; text-transform: capitalize; }
                .model-base-badge { background-color: #666; }
                .model-type-checkpoints { background-color: #4A90E2; } .model-type-loras { background-color: #50E3C2; } .model-type-vae { background-color: #B8860B; } .model-type-embeddings { background-color: #9055E9; }

                /* --- 弹窗样式 --- */
                .civitai-manager-popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); z-index: 10000; display: flex; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
                .civitai-manager-popup .popup-content { background: var(--comfy-menu-bg); padding: 0; border-radius: 8px; max-width: 800px; width: 95%; border: 1px solid var(--border-color); display: flex; flex-direction: column; max-height: 90vh; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
                .civitai-manager-popup .popup-header { display: flex; align-items: center; padding: 12px 20px; border-bottom: 1px solid var(--border-color); }
                .civitai-manager-popup .popup-header h2 { margin: 0; flex-grow: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .civitai-manager-popup .popup-close { font-size: 28px; cursor: pointer; color: var(--fg-color); margin-left: 15px; line-height: 1; transition: color .2s; }
                .civitai-manager-popup .popup-close:hover { color: #f44; }
                .civitai-manager-popup .popup-body { overflow-y: auto; word-break: break-word; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
                .civitai-manager-popup .model-description-content { font-size: 13px; background: rgba(0,0,0,0.2); padding: 12px; border-radius: 5px; overflow: visible; height: auto; max-height: none; }
                .civitai-manager-popup .model-description-content.version-desc { background: rgba(80, 80, 0, 0.2); }
                .civitai-manager-popup .model-description-content img { max-width: 100%; height: auto; border-radius: 5px; margin-top: 10px; }
                .civitai-manager-popup .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
                .civitai-manager-popup .info-item { background: var(--comfy-box-bg); padding: 8px; border-radius: 5px; font-size: 0.9em; }
                .civitai-manager-popup .info-item strong { color: var(--desc-text-color); margin-right: 8px; }
                .civitai-manager-popup .info-section { display: flex; flex-direction: column; gap: 10px; }
                .civitai-manager-popup .section-header { display: flex; justify-content: space-between; align-items: center; }
                .civitai-manager-popup h4 { margin: 0; }
                .civitai-manager-popup .detail-tags, .triggers-container { display: flex; flex-wrap: wrap; gap: 8px; }
                .civitai-manager-popup .detail-tag { background: var(--comfy-input-bg); padding: 4px 10px; border-radius: 12px; font-size: 12px; }
                .civitai-manager-popup .trigger-word { background: var(--comfy-input-bg); padding: 5px 10px; border-radius: 5px; border: 1px solid var(--border-color); cursor: pointer; transition: all .2s; user-select: none; }
                .civitai-manager-popup .trigger-word:hover { border-color: var(--accent-color); color: var(--accent-color); }
                .civitai-manager-popup .trigger-word.copied { border-color: #5f9; color: #5f9; }
                .copy-btn, .copy-all-btn { background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); padding: 4px 10px; border-radius: 5px; cursor: pointer; transition: all .2s; }
                .copy-btn:hover, .copy-all-btn:hover { border-color: var(--accent-color); color: var(--accent-color); }
                .copy-btn.copied, .copy-all-btn.copied { border-color: #5f9; color: #5f9; }
                .civitai-manager-popup .description-details summary { cursor: pointer; font-weight: bold; font-size: 1.1em; color: var(--fg-color); }
                .civitai-manager-popup .hash-section { display: flex; align-items: center; gap: 10px; background: var(--comfy-box-bg); padding: 10px; border-radius: 5px; }
                .civitai-manager-popup .hash-section strong { flex-shrink: 0; }
                .civitai-manager-popup .hash-code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            `;
            document.head.appendChild(style);
        }

        app.extensionManager.registerSidebarTab({
            id: "civitai.localManager",
            title: "Local Manager",
            icon: "pi pi-folder",
            tooltip: "Local Model Manager",
            render(el) {
                const container = document.createElement('div');
                container.id = "civitai-manager-container-wrapper";
                const tabTypes = ["checkpoints", "loras", "vae", "embeddings", "diffusion_models", "text_encoders", "hypernetworks"];
                const tabButtons = tabTypes.map(t => `<button data-type="${t}">${t.charAt(0).toUpperCase() + t.slice(1)}</button>`).join('');
                container.innerHTML = `
                    <div id="civitai-manager-container">
                        <div class="manager-header">
                            <input type="search" id="manager-search-input" placeholder="Search all models...">
                            <button id="manager-refresh-btn" title="Refresh local models">🔄</button>
                        </div>
                        <div id="manager-filter-tabs">${tabButtons}</div>
                        <div id="manager-model-list"></div>
                        <div class="loading-spinner"></div>
                        <div class="empty-message">No models found.</div>
                    </div>`;
                const managerUi = container.querySelector("#civitai-manager-container");
                managerUi.querySelector("#manager-search-input").addEventListener("input", (e) => {
                    state.searchTerm = e.target.value;
                    if (state.searchTerm) {
                        state.activeType = null;
                    } else {
                        const firstTab = managerUi.querySelector("#manager-filter-tabs button.active");
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
                        state.searchTerm = '';
                        managerUi.querySelector("#manager-search-input").value = '';
                        state.activeType = tab.dataset.type;
                        render(managerUi);
                    };
                });
                el.appendChild(container);
                loadModels(managerUi); // 初始加载
            }
        });
    }
});