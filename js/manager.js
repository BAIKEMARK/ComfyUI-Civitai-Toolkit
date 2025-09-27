// js/manager.js (Upgraded Version with All New Features)

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

/**
 * 创建一个信息弹窗，展示模型的详细信息
 * @param {string} title - 弹窗标题 (通常是文件名)
 * @param {object} model - 包含模型所有信息的对象
 */
function createModelInfoPopup(title, model) {
    const existing = document.querySelector('.civitai-manager-popup');
    if (existing) existing.remove();

    const popup = document.createElement('div');
    popup.className = 'civitai-manager-popup';

    // 处理描述中的HTML，使其在弹窗中正确显示
    const descriptionHTML = model.description ? new DOMParser().parseFromString(model.description, "text/html").body.innerHTML : "<em>No description available.</em>";

    // 将触发词数组转换为带样式的标签
    const triggersHTML = model.trained_words && model.trained_words.length > 0
        ? model.trained_words.map(tag => `<code class="trigger-word">${tag}</code>`).join(' ')
        : '<em>None</em>';

    popup.innerHTML = `
        <div class="popup-content">
            <span class="popup-close">&times;</span>
            <h2>${title}</h2>
            <div class="popup-body">
                <div class="info-grid">
                    <div><strong>Civitai Name:</strong> ${model.civitai_model_name || 'N/A'}</div>
                    <div><strong>Version:</strong> ${model.version_name || 'N/A'}</div>
                    <div><strong>Base Model:</strong> ${model.base_model}</div>
                    <div><strong>Downloads:</strong> ${model.civitai_stats.downloadCount || 0}</div>
                    <div><strong>Rating:</strong> ${model.civitai_stats.rating ? model.civitai_stats.rating.toFixed(2) : 'N/A'} (${model.civitai_stats.ratingCount || 0} ratings)</div>
                </div>
                <hr>
                <div class="info-section">
                    <h4>Trigger Words</h4>
                    <div class="triggers-container">${triggersHTML}</div>
                </div>
                <hr>
                <div class="info-section">
                    <h4>Description from Civitai</h4>
                    <div class="model-description-content">${descriptionHTML}</div>
                </div>
                <hr>
                <p class="hash-info"><strong>Hash:</strong> ${model.hash}</p>
            </div>
        </div>
    `;
    document.body.appendChild(popup);

    const close = () => {
        popup.remove();
        window.removeEventListener("keydown", onKeyDown);
    };
    popup.querySelector('.popup-close').onclick = close;
    popup.onclick = (e) => { if (e.target === popup) close(); };
    const onKeyDown = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", onKeyDown);
}

app.registerExtension({
    name: "Comfy.Civitai.ModelManager",
    async setup() {
        // 注册侧边栏
        app.extensionManager.registerSidebarTab({
            id: "civitai.modelManager",
            title: "Model Manager",
            icon: "pi pi-folder",
            tooltip: "Local Model Manager",
            type: "custom",
            render(el) {
                el.style.padding = "5px";
                el.style.display = "flex";
                el.style.flexDirection = "column";
                el.style.height = "100%";

                // 新增了包含Tabs的HTML结构
                el.innerHTML = `
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
                    </div>
                `;

                loadModels(el.querySelector("#manager-model-list"));

                // 事件监听
                const searchInput = el.querySelector("#manager-search-input");
                searchInput.addEventListener("input", () => filterModels(el));

                el.querySelector("#manager-refresh-btn").onclick = () => {
                    loadModels(el.querySelector("#manager-model-list"), true);
                };

                // 为Tabs添加点击事件
                const tabs = el.querySelectorAll("#manager-filter-tabs button");
                tabs.forEach(tab => {
                    tab.onclick = () => {
                        tabs.forEach(t => t.classList.remove("active"));
                        tab.classList.add("active");
                        filterModels(el); // 每次点击tab都执行过滤
                    };
                });
            }
        });

        // 注入所有需要的CSS样式
        const styleId = "civitai-manager-styles";
        if (document.getElementById(styleId)) return;
        const style = document.createElement("style");
        style.id = styleId;
        style.textContent = `
            #civitai-manager-container { display: flex; flex-direction: column; height: 100%; box-sizing: border-box; }
            .manager-header { display: flex; gap: 5px; margin-bottom: 10px; }
            #manager-search-input { flex-grow: 1; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); }
            #manager-refresh-btn { flex-shrink: 0; cursor: pointer; background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 4px; }
            #manager-model-list { flex-grow: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
            .manager-model-card { display: flex; align-items: center; gap: 10px; padding: 8px; background: var(--comfy-box-bg); border-radius: 5px; cursor: pointer; border: 1px solid transparent; transition: border-color 0.2s, background-color 0.2s; }
            .manager-model-card:hover { border-color: var(--accent-color); background-color: var(--comfy-menu-bg); }
            .manager-model-card .preview-img { width: 60px; height: 80px; object-fit: cover; background: #333; border-radius: 4px; flex-shrink: 0; }
            .manager-model-card .model-info { display: flex; flex-direction: column; gap: 4px; overflow: hidden; }
            .manager-model-card .model-filename { font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--fg-color); }
            .manager-model-card .model-type-badge { font-size: 0.8em; padding: 2px 6px; border-radius: 8px; color: white; width: fit-content; text-transform: capitalize; }
            .manager-model-card .model-type-checkpoints { background-color: #4A90E2; }
            .manager-model-card .model-type-loras { background-color: #50E3C2; }
            .manager-model-card .model-type-vae { background-color: #B8860B; }
            .manager-model-card .model-type-embeddings { background-color: #9055E9; }
            .manager-model-card .model-type-hypernetworks { background-color: #E95589; }
            .loading-message, .empty-message { text-align: center; color: var(--desc-text-color); margin-top: 20px; }

            /* Tabs 样式 */
            #manager-filter-tabs { display: flex; gap: 5px; margin-bottom: 10px; flex-wrap: wrap; }
            #manager-filter-tabs button { background: var(--comfy-input-bg); border: 1px solid var(--border-color); color: var(--input-text-color); border-radius: 12px; padding: 4px 12px; cursor: pointer; font-size: 0.9em; }
            #manager-filter-tabs button.active { background: var(--accent-color); color: white; border-color: var(--accent-color); }
            
            /* 弹窗样式 */
            .civitai-manager-popup { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; justify-content: center; align-items: center; }
            .civitai-manager-popup .popup-content { background: var(--comfy-menu-bg); padding: 20px; border-radius: 8px; max-width: 800px; width: 90%; position: relative; border: 1px solid var(--border-color); display: flex; flex-direction: column; max-height: 90vh; }
            .civitai-manager-popup .popup-close { position: absolute; top: 10px; right: 15px; font-size: 24px; cursor: pointer; color: var(--fg-color); }
            .civitai-manager-popup .popup-body { margin-top: 15px; overflow-y: auto; word-break: break-all; }
            .civitai-manager-popup .model-description-content img { max-width: 100%; height: auto; }

            /* 新增的弹窗信息样式 */
            .civitai-manager-popup .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-bottom: 15px; }
            .civitai-manager-popup .info-section { margin-bottom: 15px; }
            .civitai-manager-popup .triggers-container { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
            .civitai-manager-popup .trigger-word { background: var(--comfy-input-bg); padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border-color); }
            .civitai-manager-popup .hash-info { font-size: 0.9em; opacity: 0.7; margin-top: 15px; }
        `;
        document.head.appendChild(style);
    }
});

async function loadModels(container, forceRefresh = false) {
    container.innerHTML = `<p class="loading-message">🔄 Scanning for models... This may take a moment.</p>`;
    try {
        const response = await api.fetchApi(`/civitai_utils/get_local_models?force_refresh=${forceRefresh}`);
        const data = await response.json();
        if (data.status !== 'ok' || !data.models) {
            throw new Error(data.message || "Failed to load models.");
        }
        renderModels(container, data.models);
        // 加载后立即应用一次初始过滤
        filterModels(container.closest("#civitai-manager-container"));
    } catch (e) {
        container.innerHTML = `<p class="empty-message">Error: ${e.message}</p>`;
        console.error(e);
    }
}

function renderModels(container, models) {
    container.innerHTML = "";
    if (models.length === 0) {
        container.innerHTML = '<p class="empty-message">No local models found. Use the settings panel to scan/re-scan.</p>';
        return;
    }

    models.forEach(model => {
        const card = document.createElement("div");
        card.className = "manager-model-card";
        card.dataset.searchText = `${model.filename} ${model.civitai_model_name || ''}`.toLowerCase();
        card.dataset.modelType = model.model_type.toLowerCase(); // 为Tab过滤添加数据

        const previewUrl = model.local_cover_path || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1 1'%3E%3C/svg%3E";

        card.innerHTML = `
            <img src="${previewUrl}" class="preview-img" alt="preview" loading="lazy" onerror="this.style.display='none'">
            <div class="model-info">
                <span class="model-filename" title="${model.filename}">${model.filename}</span>
                <span class="model-type-badge model-type-${model.model_type}">${model.model_type}</span>
            </div>
        `;

        card.onclick = () => createModelInfoPopup(model.filename, model);
        container.appendChild(card);
    });
}

// 更新了过滤函数以同时处理搜索和Tab
function filterModels(container) {
    const searchTerm = container.querySelector("#manager-search-input").value.toLowerCase().trim();
    const activeType = container.querySelector("#manager-filter-tabs button.active").dataset.type;

    const cards = container.querySelectorAll(".manager-model-card");
    cards.forEach(card => {
        const matchesSearch = card.dataset.searchText.includes(searchTerm);
        const matchesType = activeType === 'all' || card.dataset.modelType === activeType;

        card.style.display = (matchesSearch && matchesType) ? "flex" : "none";
    });
}