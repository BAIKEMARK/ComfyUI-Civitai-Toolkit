// 文件名: civitai_browser.js
// 版本：最终功能增强版 (已优化详情页布局与信息流)

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

// --- 状态管理对象 ---
const browserState = {
    models: [],
    filters: {
        limit: 24,
        sort: 'Most Downloaded',
        period: 'AllTime',
        query: '',
        types: null,
        baseModels: null,
    },
    network: 'com',
    isLoading: false,
    nextCursor: null,
    localHashes: new Set(),
    currentView: 'list',
    currentModelDetail: null,
};

// --- Civitai API支持的筛选选项 ---
const CIVITAI_MODEL_TYPES = ["Checkpoint", "TextualInversion", "Hypernetwork", "LORA", "LoCon", "VAE", "Controlnet", "Upscaler", "MotionModule", "AestheticGradient", "DoRA", "Workflow"];
const CIVITAI_BASE_MODELS = [
    "SD 1.4", "SD 1.5", "SD 1.5 LCM", "SD 1.5 Hyper", "SD 2.0", "SD 2.1",
    "SDXL 1.0", "SDXL Lightning", "SDXL Hyper", "SD 3", "SD 3.5", "SD 3.5 Large", "SD 3.5 Large Turbo", "SD 3.5 Medium",
    "SVD", "Pony", "AuraFlow", "Chroma", "CogVideoX", "Flux.1 S", "Flux.1 D", "Flux.1 Krea", "Flux.1 Kontext",
    "HiDream", "Hunyuan 1", "Hunyuan Video", "Illustrious", "Kolors", "LTXV", "Lumina", "Mochi",
    "NoobAI", "PixArt α", "PixArt Σ", "Qwen",
    "Wan Video 1.3B t2v", "Wan Video 14B t2v", "Wan Video 14B i2v 480p", "Wan Video 14B i2v 720p",
    "Wan Video 2.2 TI2V-5B", "Wan Video 2.2 I2V-A14B", "Wan Video 2.2 T2V-A14B", "Wan Video 2.5 T2V", "Wan Video 2.5 I2V",
    "Other"
];

// --- 获取模型完整信息的函数 ---
async function fetchModelDetails(modelId) {
    if (browserState.isLoading) return;
    browserState.isLoading = true;
    try {
        const baseUrl = `https://civitai.${browserState.network}/api/v1/models/${modelId}`;
        const response = await fetch(baseUrl);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } finally {
        browserState.isLoading = false;
    }
}

// --- [已修改] 渲染图片画廊和默认信息面板的辅助函数 ---
function renderVersionDetails(modelData, versionId, galleryContainer, infoContainer) {
    const version = modelData.modelVersions.find(v => v.id == versionId);
    if (!version) return;

    // 渲染图片画廊
    if (!version.images || version.images.length === 0) {
        galleryContainer.innerHTML = '<p class="detail-empty-msg">No images found for this version.</p>';
    } else {
        galleryContainer.innerHTML = '';
        version.images.forEach(image => {
            const item = document.createElement('div');
            item.className = 'gallery-item';
            const img = document.createElement('img');
            img.src = image.url.replace('/width=dpr', '/width=450');
            img.loading = 'lazy';
            img.onclick = () => { // 点击图片，在右侧显示Prompt
                galleryContainer.querySelectorAll('.gallery-item.selected').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                renderImageMeta(image, infoContainer, modelData, versionId, galleryContainer);
            };
            item.appendChild(img);
            galleryContainer.appendChild(item);
        });
    }

    // [新增] 默认在右侧渲染版本信息
    const filesHTML = version.files.map(file => `
        <div class="file-item">
            <span class="file-name" title="${file.name}">${file.name} (${(file.sizeKB / 1024).toFixed(2)} MB)</span>
            <span class="file-base-model">${version.baseModel}</span>
        </div>
    `).join('');

    const triggersHTML = version.trainedWords && version.trainedWords.length > 0
        ? `<div class="triggers-container">${version.trainedWords.map(tag => `<code class="trigger-word">${tag}</code>`).join(' ')}</div>`
        : '<em>None specified</em>';

    const versionDescriptionHTML = version.description ? new DOMParser().parseFromString(version.description, "text/html").body.innerHTML : "";

    infoContainer.innerHTML = `
        <div class="info-panel-content">
            <div class="info-section">
                <h4>Trigger Words</h4>
                ${triggersHTML}
            </div>
            <div class="info-section">
                <h4>Files</h4>
                <div class="file-list">${filesHTML}</div>
            </div>
            ${versionDescriptionHTML ? `
            <div class="info-section">
                <h4>Version Notes</h4>
                <div class="model-description-content">${versionDescriptionHTML}</div>
            </div>` : ''}
        </div>
    `;
}

// [修改] renderImageMeta 现在会添加“返回”按钮，并接收更多参数
function renderImageMeta(image, infoContainer, modelData, versionId, galleryContainer){
    let metaHtml = '<p class="detail-empty-msg">No prompt data available for this image.</p>';
    if (image.meta) {
        const meta = image.meta;
        const prompt = meta.prompt || '';
        const negPrompt = meta.negativePrompt || '';

        metaHtml = `
            <div class="prompt-section">
                <div class="prompt-header">
                    <h4>Positive Prompt</h4>
                    <button class="copy-prompt-btn" data-prompt-type="positive">Copy</button>
                </div>
                <textarea readonly id="positive-prompt-text">${prompt}</textarea>
            </div>
            <div class="prompt-section">
                <div class="prompt-header">
                    <h4>Negative Prompt</h4>
                    <button class="copy-prompt-btn" data-prompt-type="negative">Copy</button>
                </div>
                <textarea readonly id="negative-prompt-text">${negPrompt}</textarea>
            </div>
            <div class="meta-grid">
                <span><strong>Seed:</strong> ${meta.seed || 'N/A'}</span>
                <span><strong>Sampler:</strong> ${meta.sampler || 'N/A'}</span>
                <span><strong>Steps:</strong> ${meta.steps || 'N/A'}</span>
                <span><strong>CFG:</strong> ${meta.cfgScale || 'N/A'}</span>
            </div>
        `;
    }

    // [新增] 创建返回按钮和容器，并将 metaHtml 放入
    infoContainer.innerHTML = `
        <div class="info-panel-header">
            <button id="back-to-version-info-btn">&larr; Back to Version Info</button>
        </div>
        <div class="info-panel-content">
            ${metaHtml}
        </div>
    `;

    // [新增] 为返回按钮添加事件监听
    infoContainer.querySelector("#back-to-version-info-btn").onclick = () => {
        galleryContainer.querySelectorAll('.gallery-item.selected').forEach(i => i.classList.remove('selected'));
        renderVersionDetails(modelData, versionId, galleryContainer, infoContainer);
    };

    infoContainer.querySelectorAll('.copy-prompt-btn').forEach(btn => {
        btn.onclick = (e) => {
            const type = e.target.dataset.promptType;
            const text = infoContainer.querySelector(`#${type}-prompt-text`).value;
            navigator.clipboard.writeText(text).then(() => {
                e.target.textContent = 'Copied!';
                setTimeout(() => { e.target.textContent = 'Copy'; }, 1500);
            });
        };
    });
}

// --- [已修改] 渲染详情视图的函数 ---
function renderDetailView(modelData, container) {
    const detailContainer = container.querySelector("#civitai-browser-detail-view");

    const versionOptions = modelData.modelVersions
        .sort((a,b) => new Date(b.createdAt) - new Date(a.createdAt))
        .map(v => `<option value="${v.id}">${v.name}</option>`)
        .join('');

    const creatorName = modelData.creator.username || 'Unknown';
    const tags = modelData.tags.map(tag => `<span class="detail-tag">${tag}</span>`).join('');
    const descriptionHTML = modelData.description ? new DOMParser().parseFromString(modelData.description, "text/html").body.innerHTML : "";

    detailContainer.innerHTML = `
        <div class="detail-view-header">
            <button id="detail-back-btn">&larr; Back to List</button>
            <h3 title="${modelData.name}">${modelData.name}</h3>
        </div>

        <div class="detail-meta-info">
            <span class="detail-creator">by ${creatorName}</span>
            <div class="detail-tags">${tags}</div>
        </div>

        ${descriptionHTML ? `
        <details class="detail-description-section">
            <summary>Model Description</summary>
            <div class="model-description-content">${descriptionHTML}</div>
        </details>` : ''}

        <div class="detail-view-controls">
            <label for="detail-version-selector">Version:</label>
            <select id="detail-version-selector">${versionOptions}</select>
        </div>
        <div class="detail-view-content">
            <div id="detail-image-gallery" class="image-gallery"></div>
            <div id="detail-info-panel" class="image-info-panel"></div>
        </div>
    `;

    const galleryContainer = detailContainer.querySelector("#detail-image-gallery");
    const infoContainer = detailContainer.querySelector("#detail-info-panel");

    const initialVersionId = modelData.modelVersions[0].id;
    renderVersionDetails(modelData, initialVersionId, galleryContainer, infoContainer);

    detailContainer.querySelector("#detail-version-selector").addEventListener('change', (e) => {
        renderVersionDetails(modelData, e.target.value, galleryContainer, infoContainer);
    });

    detailContainer.querySelector("#detail-back-btn").onclick = () => {
        const listContainer = container.querySelector("#civitai-browser-list-view");
        detailContainer.style.display = 'none';
        listContainer.style.display = 'flex';
        browserState.currentView = 'list';
        browserState.currentModelDetail = null;
    };
}

// --- 切换视图的辅助函数 ---
function showDetailView(model, card) {
    const container = card.closest('.civitai-browser-container');
    const listContainer = container.querySelector('#civitai-browser-list-view');
    const detailContainer = container.querySelector('#civitai-browser-detail-view');
    const spinner = container.querySelector('#civitai-browser-spinner');

    (async () => {
        try {
            listContainer.style.display = 'none';
            spinner.style.display = 'block';
            const modelDetails = await fetchModelDetails(model.id);
            browserState.currentModelDetail = modelDetails;
            browserState.currentView = 'detail';
            renderDetailView(modelDetails, container);
            detailContainer.style.display = 'flex';
        } catch(e) {
            console.error("Error loading model details:", e);
            listContainer.style.display = 'flex';
        } finally {
            spinner.style.display = 'none';
        }
    })();
}

// --- 辅助函数：创建在线模型卡片 ---
function createCivitaiCard(model) {
    const card = document.createElement("div");
    card.className = "civitai-browser-card";

    const version = model.modelVersions?.[0];
    if (!version) return null;
    const coverImage = version.images?.find(i => i.url) || version.images?.[0];
    const creatorName = model.creator?.username || 'Unknown';
    const file = version.files?.[0];
    const fileHash = file?.hashes?.SHA256?.toLowerCase();
    const isDownloaded = fileHash && browserState.localHashes.has(fileHash);

    card.innerHTML = `
        <div class="browser-preview-container">
            <div class="browser-preview-placeholder"></div>
            <div class="browser-card-badges">
                ${isDownloaded ? '<span class="browser-card-badge downloaded">Downloaded</span>' : ''}
                <span class="browser-card-badge type">${model.type}</span>
            </div>
        </div>
        <div class="browser-model-info">
            <span class="browser-model-name" title="${model.name}">${model.name}</span>
            <span class="browser-model-creator">by ${creatorName}</span>
            <div class="browser-model-stats">
                <span>⭐ ${model.stats.rating.toFixed(1)} (${model.stats.ratingCount})</span>
                <span>🔄 ${model.stats.downloadCount}</span>
            </div>
        </div>
    `;

    const placeholder = card.querySelector('.browser-preview-placeholder');
    const previewContainer = card.querySelector('.browser-preview-container');
    placeholder.style.display = 'flex';

    if (coverImage?.url) {
        const mediaUrl = coverImage.url;
        if (coverImage.type === 'video') {
            const video = document.createElement('video');
            video.className = 'browser-preview-vid';
            video.src = mediaUrl;
            video.loop = true;
            video.muted = true;
            video.playsInline = true;
            video.loading = 'lazy';
            video.onloadeddata = () => { placeholder.style.display = 'none'; };
            video.onerror = () => { video.remove(); };
            card.addEventListener('mouseenter', () => video.play().catch(e => {}));
            card.addEventListener('mouseleave', () => video.pause());
            previewContainer.prepend(video);
        } else {
            const img = document.createElement('img');
            img.className = 'browser-preview-img';
            img.src = mediaUrl;
            img.alt = model.name;
            img.loading = 'lazy';
            img.onload = () => { placeholder.style.display = 'none'; };
            img.onerror = () => { img.remove(); };
            previewContainer.prepend(img);
        }
    }

    card.onclick = () => showDetailView(model, card);

    return card;
}

// --- 数据加载函数 (无改动) ---
async function fetchCivitaiModels(container, isLoadMore = false) {
    if (browserState.isLoading) return;
    if (isLoadMore && !browserState.nextCursor) return;
    browserState.isLoading = true;
    const spinner = container.querySelector("#civitai-browser-spinner");
    const emptyMsg = container.querySelector('#civitai-browser-empty-message');
    const loadMoreButton = container.querySelector("#civitai-browser-load-more button");
    const listContainer = container.querySelector("#civitai-browser-list");
    if (!isLoadMore) {
        spinner.style.display = 'block';
        listContainer.innerHTML = '';
    } else {
        loadMoreButton.textContent = 'Loading...';
        loadMoreButton.disabled = true;
    }
    emptyMsg.style.display = 'none';
    try {
        const filters = { ...browserState.filters };
        delete filters.page;
        if (!filters.query) delete filters.query;
        if (!filters.types) delete filters.types;
        if (!filters.baseModels) delete filters.baseModels;
        const params = new URLSearchParams(filters);
        if (isLoadMore && browserState.nextCursor) {
            params.append('cursor', browserState.nextCursor);
        }
        const baseUrl = `https://civitai.${browserState.network}/api/v1/models`;
        const response = await fetch(`${baseUrl}?${params.toString()}`);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`HTTP error! status: ${response.status} - ${errorData?.error?.message || 'Unknown API error'}`);
        }
        const data = await response.json();
        const modelsFromApi = data.items;
        if (!isLoadMore) browserState.models = [];
        browserState.nextCursor = data.metadata.nextCursor || null;
        browserState.models.push(...modelsFromApi);
        for (const model of modelsFromApi) {
            const card = createCivitaiCard(model);
            if(card) listContainer.appendChild(card);
        }
        if (browserState.models.length === 0) emptyMsg.style.display = 'block';
    } catch (e) {
        console.error("Failed to fetch from Civitai:", e);
        emptyMsg.textContent = `Error: ${e.message}. Check console.`;
        emptyMsg.style.display = 'block';
    } finally {
        browserState.isLoading = false;
        spinner.style.display = 'none';
        if (browserState.nextCursor) {
            loadMoreButton.textContent = 'Load More';
            loadMoreButton.style.display = 'block';
            loadMoreButton.disabled = false;
        } else if (browserState.models.length > 0) {
            loadMoreButton.textContent = '✅ No more models';
            loadMoreButton.style.display = 'block';
            loadMoreButton.disabled = true;
        } else {
            loadMoreButton.style.display = 'none';
        }
    }
}


app.registerExtension({
    name: "Comfy.Civitai.OnlineBrowser",
    async setup() {
        const styleId = "civitai-browser-styles";
        if (!document.getElementById(styleId)) {
            const style = document.createElement("style");
            style.id = styleId;
            style.textContent = `
                .civitai-browser-container { padding: 5px; box-sizing: border-box; display: flex; flex-direction: column; height: 100%; }
                #civitai-browser-list-view, #civitai-browser-detail-view { display: flex; flex-direction: column; flex-grow: 1; min-height: 0; }
                #civitai-browser-list { flex-grow: 1; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; padding: 5px; min-height: 0; }
                .civitai-browser-card { display: flex; flex-direction: column; background: var(--comfy-box-bg); border-radius: 5px; cursor: pointer; border: 1px solid transparent; transition: all 0.2s ease-in-out; }
                .civitai-browser-card:hover { border-color: var(--accent-color); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
                .browser-preview-container { width: 100%; padding-top: 130%; position: relative; background: #333; border-radius: 4px 4px 0 0; overflow: hidden; }
                .browser-preview-img, .browser-preview-vid { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; }
                .browser-preview-placeholder { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; font-size: 2em; color: #555; }
                .browser-model-info { padding: 8px; }
                .browser-model-name { font-weight: bold; color: var(--fg-color); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; min-height: 2.4em; }
                .browser-model-creator { font-size: 0.8em; color: var(--desc-text-color); }
                .browser-model-stats { display: flex; justify-content: space-between; font-size: 0.8em; color: var(--desc-text-color); margin-top: 5px; }
                .civitai-browser-header { display: flex; gap: 5px; margin-bottom: 10px; }
                #civitai-browser-search { flex-grow: 1; }
                #civitai-browser-refresh-btn { flex-shrink: 0; padding: 5px 8px; }
                .civitai-browser-filters { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
                .civitai-browser-filters select, .civitai-browser-filters input { width: 100%; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); box-sizing: border-box; }
                .browser-card-badges { position: absolute; top: 5px; right: 5px; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
                .browser-card-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; color: white; text-transform: capitalize; }
                .browser-card-badge.type { background-color: rgba(0, 0, 0, 0.6); }
                .browser-card-badge.downloaded { background-color: #4CAF50; }
                #civitai-browser-load-more { padding: 10px 0; flex-shrink: 0; }
                #civitai-browser-load-more button { width: 100%; padding: 8px; font-size: 14px; cursor: pointer; }
                #civitai-browser-load-more button:disabled { cursor: not-allowed; opacity: 0.7; }
                /* 详情视图样式 */
                .detail-view-header { display: flex; align-items: center; gap: 15px; margin-bottom: 10px; flex-shrink: 0; }
                .detail-view-header h3 { margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-grow: 1; }
                #detail-back-btn { padding: 5px 10px; font-size: 12px; flex-shrink: 0; }
                .detail-meta-info { margin-bottom: 10px; flex-shrink: 0; }
                .detail-creator { font-size: 0.9em; color: var(--desc-text-color); }
                .detail-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
                .detail-tag { background-color: var(--comfy-input-bg); padding: 2px 8px; border-radius: 10px; font-size: 11px; }
                .detail-description-section { margin-bottom: 10px; flex-shrink: 0; }
                .detail-description-section summary { cursor: pointer; font-weight: bold; margin-bottom: 5px; }
                .model-description-content { font-size: 12px; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto; }
                .model-description-content img, .model-description-content video { max-width: 100%; height: auto; border-radius: 5px; }
                .detail-view-controls { margin-bottom: 10px; flex-shrink: 0; display: flex; align-items: center; gap: 10px; }
                .detail-view-controls label { font-size: 12px; }
                #detail-version-selector { width: 100%; padding: 5px; }
                .detail-view-content { display: flex; flex-grow: 1; gap: 10px; min-height: 0; }
                .image-gallery { flex: 3; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 5px; align-content: flex-start; padding: 5px; background: rgba(0,0,0,0.1); border-radius: 5px; }
                .gallery-item img { width: 100%; height: auto; object-fit: cover; border-radius: 4px; cursor: pointer; transition: transform 0.2s, box-shadow 0.2s; border: 2px solid transparent; }
                .gallery-item img:hover { transform: scale(1.05); }
                .gallery-item.selected img { border-color: var(--accent-color); box-shadow: 0 0 10px var(--accent-color); }
                
                .image-info-panel { flex: 2; display: flex; flex-direction: column; overflow: hidden; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; font-size: 12px; }
                .info-panel-header { flex-shrink: 0; margin-bottom: 10px; }
                #back-to-version-info-btn { width: 100%; padding: 6px; font-size: 11px; }
                .info-panel-content { flex-grow: 1; overflow-y: auto; }

                .detail-empty-msg { color: var(--desc-text-color); margin: auto; text-align: center; }
                .info-section { margin-bottom: 15px; }
                .info-section:last-child { margin-bottom: 0; }
                .info-section h4 { margin: 0 0 8px 0; border-bottom: 1px solid var(--border-color); padding-bottom: 5px; }
                .file-list { display: flex; flex-direction: column; gap: 8px; }
                .file-item { display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2); padding: 5px; border-radius: 3px; }
                .file-name { font-size: 11px; word-break: break-all; }
                .file-base-model { font-size: 10px; background: #555; padding: 2px 5px; border-radius: 3px; flex-shrink: 0; margin-left: 10px; }
                .prompt-section { margin-bottom: 15px; }
                .prompt-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
                .prompt-header h4 { margin: 0; color: var(--fg-color); }
                .copy-prompt-btn { font-size: 10px; padding: 2px 6px; }
                .prompt-section textarea { width: 100%; box-sizing: border-box; height: 120px; resize: vertical; background: var(--comfy-input-bg); color: var(--input-text-color); border: 1px solid var(--border-color); border-radius: 4px; font-family: monospace; }
                .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; color: var(--desc-text-color); }
            `;
            document.head.appendChild(style);
        }

        app.extensionManager.registerSidebarTab({
            id: "civitai.onlineBrowser",
            title: "Civitai Browser",
            icon: "pi pi-globe",
            tooltip: "Online Civitai Browser",
            async render(el) {
                const sortOptions = ['Most Downloaded', 'Highest Rated', 'Newest'].map(o => `<option value="${o}">${o}</option>`).join('');
                const periodOptions = ['AllTime', 'Month', 'Week', 'Day'].map(o => `<option value="${o}">${o}</option>`).join('');
                const typeOptions = ['All', ...CIVITAI_MODEL_TYPES].map(o => `<option value="${o === 'All' ? '' : o}">${o}</option>`).join('');
                const baseModelOptions = ['All', ...CIVITAI_BASE_MODELS].map(o => `<option value="${o === 'All' ? '' : o}">${o}</option>`).join('');


                el.innerHTML = `
                    <div class="civitai-browser-container">
                        <div id="civitai-browser-list-view" style="display: flex; flex-direction: column; flex-grow: 1; min-height: 0;">
                            <div class="civitai-browser-header">
                                <input type="search" id="civitai-browser-search" placeholder="Search Civitai...">
                                <button id="civitai-browser-refresh-btn" title="Refresh">🔄</button>
                            </div>
                            <div class="civitai-browser-filters">
                                <select id="civitai-browser-sort" data-filter-key="sort">${sortOptions}</select>
                                <select id="civitai-browser-period" data-filter-key="period">${periodOptions}</select>
                                <select id="civitai-browser-types" data-filter-key="types"><option value="">All Types</option>${typeOptions.substring(typeOptions.indexOf('</option>')+9)}</select>
                                <select id="civitai-browser-base-models" data-filter-key="baseModels"><option value="">All Base Models</option>${baseModelOptions.substring(baseModelOptions.indexOf('</option>')+9)}</select>
                            </div>
                            <div id="civitai-browser-list"></div>
                            <div id="civitai-browser-load-more"><button style="display: none;">Load More</button></div>
                        </div>

                        <div id="civitai-browser-detail-view" style="display: none;"></div>
                        
                        <div class="loading-spinner" id="civitai-browser-spinner" style="display: none;"></div>
                        <div class="empty-message" id="civitai-browser-empty-message" style="display: none;">No models found.</div>
                    </div>
                `;

                const container = el.querySelector(".civitai-browser-container");

                const syncFiltersFromUI = () => {
                    browserState.filters.query = container.querySelector("#civitai-browser-search").value;
                    container.querySelectorAll(".civitai-browser-filters select").forEach(select => {
                        const key = select.dataset.filterKey;
                        if (key) {
                            browserState.filters[key] = select.value;
                        }
                    });
                };

                const resetAndFetch = () => {
                    browserState.nextCursor = null;
                    fetchCivitaiModels(container, false);
                };

                let debounceTimer;
                container.querySelector("#civitai-browser-search").addEventListener("input", (e) => {
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(() => {
                        syncFiltersFromUI();
                        resetAndFetch();
                    }, 500);
                });

                container.querySelectorAll(".civitai-browser-filters select").forEach(select => {
                    select.addEventListener("change", () => {
                        syncFiltersFromUI();
                        resetAndFetch();
                    });
                });

                container.querySelector("#civitai-browser-refresh-btn").addEventListener("click", () => {
                    syncFiltersFromUI();
                    resetAndFetch();
                });

                container.querySelector("#civitai-browser-load-more button").onclick = () => {
                    fetchCivitaiModels(container, true);
                };

                // ---- 初始化 ----
                try {
                    const configRes = await api.fetchApi('/civitai_recipe_finder/get_config');
                    const config = await configRes.json();
                    browserState.network = config.network_choice || 'com';

                    const hashesRes = await api.fetchApi('/civitai_recipe_finder/get_local_hashes');
                    const hashesData = await hashesRes.json();
                    if(hashesData.status === 'ok' && Array.isArray(hashesData.hashes)){
                        browserState.localHashes = new Set(hashesData.hashes);
                    }

                } catch (e) {
                    console.error("[Civitai Browser] Failed to initialize settings:", e);
                } finally {
                    fetchCivitaiModels(container, false);
                }
            }
        });
    }
});