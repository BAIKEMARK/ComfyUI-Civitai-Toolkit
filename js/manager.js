// file: manager.js (最终稳定版 - 完整代码)

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

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
                /* 修正双重滚动条: 移除内层容器的高度和滚动条，让外层(el)自己处理 */
                #civitai-manager-container-wrapper { width: 100%; }
                #civitai-manager-container { display: flex; flex-direction: column; padding: 5px; }
                .manager-header { display: flex; gap: 5px; margin-bottom: 10px; }
                #manager-search-input { flex-grow: 1; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); }
                #manager-refresh-btn { flex-shrink: 0; cursor: pointer; background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 4px; }
                #manager-model-list { display: flex; flex-direction: column; gap: 8px; }
                .manager-model-card { display: flex; align-items: center; gap: 10px; padding: 8px; background: var(--comfy-box-bg); border-radius: 5px; cursor: pointer; border: 1px solid transparent; transition: border-color 0.2s, background-color 0.2s; }
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
                container.style.width = "100%";
                container.style.height = "100%";
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

            const listContainer = container.querySelector("#manager-model-list");
            loadModels(listContainer);

            container.querySelector("#manager-search-input").addEventListener("input", () => filterModels(container));
            container.querySelector("#manager-refresh-btn").onclick = () => loadModels(listContainer, true);

            const tabs = container.querySelectorAll("#manager-filter-tabs button");
            tabs.forEach(tab => {
                tab.onclick = () => {
                    tabs.forEach(t => t.classList.remove("active"));
                    tab.classList.add("active");
                    filterModels(container);
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
                renderModels(container, data.models);
                filterModels(container.closest("#civitai-manager-container"));
            } catch (e) {
                container.innerHTML = `<p class="empty-message">Error loading models: ${e.message}</p>`;
                console.error(e);
            }
        }

        function renderModels(container, models) {
            container.innerHTML = "";
            if (models.length === 0) {
                container.innerHTML = '<p class="empty-message">No models to display. Press 🔄 to scan.</p>';
                return;
            }

            models.forEach(model => {
                const card = document.createElement("div");
                card.className = "manager-model-card";
                card.dataset.searchText = `${model.filename} ${model.civitai_model_name || ''}`.toLowerCase();
                card.dataset.modelType = model.model_type.toLowerCase();

                // 核心修正点: 前端始终请求.webp，让后端智能地寻找png或内嵌封面
                const filename = model.filename;
                let previewUrl = model.local_cover_path; // 使用后端已处理好的最终URL

                card.innerHTML = `
                    <div class="preview-container">
                        <img class="preview-img" src="${previewUrl || ''}" alt="preview" loading="lazy">
                        <div class="preview-placeholder"></div>
                    </div>
                    <div class="model-info">
                        <span class="model-filename" title="${filename}">${filename}</span>
                        <span class="model-type-badge model-type-${model.model_type}">${model.model_type}</span>
                    </div>`;

                const img = card.querySelector('.preview-img');
                const placeholder = card.querySelector('.preview-placeholder');

                if (!previewUrl) {
                    placeholder.style.display = 'flex';
                    img.style.display = 'none';
                } else {
                    img.onload = () => {
                        placeholder.style.display = 'none';
                        img.style.display = 'block';
                    };
                    img.onerror = () => {
                        console.error(`[Civitai Manager] Failed to load cover image. URL: ${img.src}`);
                        placeholder.style.display = 'flex';
                        placeholder.innerHTML = '⚠️';
                        img.style.display = 'none';
                    };
                    if (img.complete) { img.onload(); }
                }

                card.onclick = () => createModelInfoPopup(model.filename, model);
                container.appendChild(card);
            });
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
        }
    }
});