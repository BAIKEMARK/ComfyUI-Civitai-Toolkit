// file: manager.js (最终正确版 - 保留外部滚动，移除内滚)

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

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

// --- 辅助函数：渲染单个模型卡片 ---
function renderModelCard(model) {
    const card = document.createElement("div");
    card.className = "manager-model-card";
    const displayName = model.filename.split('/').pop().split('\\').pop();
    card.dataset.searchText = `${displayName} ${model.civitai_model_name || ''}`.toLowerCase();
    card.dataset.modelType = model.model_type.toLowerCase();

    const previewUrl = model.local_cover_path || '';
    card.innerHTML = `
        <div class="preview-container">
            <img class="preview-img" src="${previewUrl}" alt="preview" loading="lazy">
            <div class="preview-placeholder"></div>
        </div>
        <div class="model-info">
            <span class="model-filename" title="${model.filename}">${displayName}</span>
            <span class="model-type-badge model-type-${model.model_type}">${model.model_type}</span>
        </div>`;

    const img = card.querySelector('.preview-img');
    const placeholder = card.querySelector('.preview-placeholder');
    if (!previewUrl) {
        placeholder.style.display = 'flex'; img.style.display = 'none';
    } else {
        img.onload = () => { placeholder.style.display = 'none'; img.style.display = 'block'; };
        img.onerror = () => {
            console.error(`[Civitai Manager] Failed to load cover image. URL: ${img.src}`);
            placeholder.style.display = 'flex'; placeholder.innerHTML = '⚠️'; img.style.display = 'none';
        };
        if (img.complete) { img.onload(); }
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

app.registerExtension({
    name: "Comfy.Civitai.ModelManager",
    async setup() {
        const styleId = "civitai-manager-styles";
        if (!document.getElementById(styleId)) {
            const style = document.createElement("style");
            style.id = styleId;
            style.textContent = `
                /* 🟢 最终正确方案：移除所有高度和内部滚动控制 */
                #civitai-manager-container-wrapper {
                    padding: 5px;
                    box-sizing: border-box;
                }
                
                /* 树状折叠视图样式 */
                .model-tree-container, .folder-content { display: flex; flex-direction: column; gap: 8px; }
                .folder-item { margin-left: 0; }
                .folder-item summary { cursor: pointer; padding: 4px; border-radius: 4px; list-style: none; display: flex; align-items: center; gap: 5px; margin-left: -5px; }
                .folder-item summary::before { content: '📁'; font-size: 0.9em; }
                .folder-item[open] > summary::before { content: '📂'; }
                .folder-item summary:hover { background-color: var(--comfy-menu-bg); }
                .folder-item[open] > summary { margin-bottom: 8px; }
                .folder-content { margin-left: 15px; border-left: 1px solid #444; padding-left: 10px; }
                .model-type-header { margin: 10px 0 5px 0; font-size: 1.1em; color: var(--fg-color); border-bottom: 1px solid var(--border-color); padding-bottom: 5px; }
                
                /* 其余所有样式 (card, popup等) */
                .manager-header { display: flex; gap: 5px; margin-bottom: 10px; }
                #manager-search-input { flex-grow: 1; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); }
                #manager-refresh-btn { flex-shrink: 0; cursor: pointer; background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 4px; }
                .manager-model-card { margin-left: 0 !important; display: flex; align-items: center; gap: 10px; padding: 8px; background: var(--comfy-box-bg); border-radius: 5px; cursor: pointer; border: 1px solid transparent; transition: border-color 0.2s, background-color 0.2s; }
                .manager-model-card:hover { border-color: var(--accent-color); background-color: var(--comfy-menu-bg); }
                .preview-container { width: 60px; height: 80px; flex-shrink: 0; position: relative; }
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
                .loading-message, .empty-message { text-align: center; color: var(--desc-text-color); margin-top: 20px; }
                #manager-filter-tabs { display: flex; gap: 5px; margin-bottom: 10px; flex-wrap: wrap; }
                #manager-filter-tabs button { background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 12px; padding: 4px 12px; cursor: pointer; font-size: 0.9em; }
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

        app.extensionManager.registerSidebarTab({
            id: "civitai.modelManager", title: "Model Manager",
            icon: "pi pi-folder", tooltip: "Local Model Manager",
            type: "custom",
            render(el) {
                const container = document.createElement('div');
                container.id = "civitai-manager-container-wrapper";
                el.appendChild(container);
                renderManager(container);
            }
        });

        function renderManager(container) {
            container.innerHTML = `
                <div id="civitai-manager-container">
                    <div class="manager-header">
                        <input type="search" id="manager-search-input" placeholder="Search models...">
                        <button id="manager-refresh-btn" title="Force Refresh & Rescan All">🔄</button>
                    </div>
                    <div id="manager-filter-tabs">
                        <button class="active" data-type="all">All</button>
                        <button data-type="checkpoints">Checkpoints</button>
                        <button data-type="loras">Loras</button>
                        <button data-type="vae">VAE</button>
                        <button data-type="embeddings">Embeddings</button>
                    </div>
                    <div id="manager-model-list">
                        <p class="loading-message">Loading models...</p>
                    </div>
                </div>`;

            const managerUi = container.querySelector("#civitai-manager-container");
            const listContainer = managerUi.querySelector("#manager-model-list");

            loadModels(listContainer);

            managerUi.querySelector("#manager-search-input").addEventListener("input", () => filterModels(managerUi));
            managerUi.querySelector("#manager-refresh-btn").onclick = () => loadModels(listContainer, true);
            const tabs = managerUi.querySelectorAll("#manager-filter-tabs button");
            tabs.forEach(tab => {
                tab.onclick = () => {
                    tabs.forEach(t => t.classList.remove("active"));
                    tab.classList.add("active");
                    filterModels(managerUi);
                };
            });
        }

        async function loadModels(container, forceRefresh = false) {
            container.innerHTML = `<p class="loading-message">🔄 Fetching all model data from server...</p>`;
            try {
                const response = await api.fetchApi(`/civitai_utils/get_local_models?force_refresh=${forceRefresh}`);
                const data = await response.json();
                if (data.status !== 'ok' || !data.models) {
                    throw new Error(data.message || "Failed to load models.");
                }

                const modelsByType = data.models.reduce((acc, model) => {
                    const type = model.model_type;
                    if (!acc[type]) acc[type] = [];
                    acc[type].push(model);
                    return acc;
                }, {});

                // 闪烁问题不严重了，但为流畅起见，保留此优化
                container.style.visibility = 'hidden';

                const fragment = document.createDocumentFragment();
                const sortedTypes = Object.keys(modelsByType).sort();

                for (const modelType of sortedTypes) {
                    const files = modelsByType[modelType];
                    if (files.length > 0) {
                        const typeHeader = document.createElement('h3');
                        typeHeader.className = 'model-type-header';
                        typeHeader.dataset.modelTypeHeader = modelType.toLowerCase();
                        typeHeader.textContent = modelType.charAt(0).toUpperCase() + modelType.slice(1);
                        fragment.appendChild(typeHeader);

                        const fileTree = buildFileTree(files);
                        const treeContainer = document.createElement('div');
                        treeContainer.className = 'model-tree-container';
                        treeContainer.dataset.modelTypeTree = modelType.toLowerCase();
                        renderTree(treeContainer, fileTree);
                        fragment.appendChild(treeContainer);
                    }
                }

                container.innerHTML = "";
                container.appendChild(fragment);

                filterModels(container.closest("#civitai-manager-container"));

                container.style.visibility = 'visible';

            } catch (e) {
                container.innerHTML = `<p class="empty-message">Error loading models: ${e.message}</p>`;
                container.style.visibility = 'visible';
                console.error(e);
            }
        }

        function filterModels(container) {
            if (!container) return;
            const searchTerm = container.querySelector("#manager-search-input").value.toLowerCase().trim();
            const activeType = container.querySelector("#manager-filter-tabs button.active").dataset.type;

            const cards = container.querySelectorAll(".manager-model-card");
            cards.forEach(card => {
                const matchesSearch = card.dataset.searchText.includes(searchTerm);
                const matchesType = activeType === 'all' || card.dataset.modelType === activeType;
                card.style.display = (matchesSearch && matchesType) ? "flex" : "none";
            });

            const folders = container.querySelectorAll(".folder-item");
            folders.forEach(folder => {
                const hasVisibleChildren = folder.querySelector(".manager-model-card[style*='display: flex']");
                folder.style.display = hasVisibleChildren ? "block" : "none";
            });

            const headers = container.querySelectorAll(".model-type-header");
            headers.forEach(header => {
                const headerType = header.dataset.modelTypeHeader;
                const correspondingTree = container.querySelector(`.model-tree-container[data-model-type-tree='${headerType}']`);
                if (!correspondingTree) return;

                const hasVisibleContent = correspondingTree.querySelector(".manager-model-card[style*='display: flex']");
                const shouldBeVisible = !!hasVisibleContent;

                correspondingTree.style.display = shouldBeVisible ? "block" : "none";

                const shouldShowHeader = shouldBeVisible && activeType === 'all';
                header.style.display = shouldShowHeader ? "block" : "none";
            });
        }
    }
});