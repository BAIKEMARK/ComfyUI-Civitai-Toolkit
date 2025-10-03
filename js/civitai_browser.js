// 文件名: civitai_browser.js
// 版本：最终功能增强版 (已修复视频预览 + 完整筛选器)

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
    network: 'com', // 默认值，会从后端获取并覆盖
    isLoading: false,
    nextCursor: null,
    localHashes: new Set(),
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

function getOptimizedUrl(url, type = 'image') {
    if (!url) return '';
    try {
        // 尝试从URL中找到关键的UUID部分，例如 '.../ec613457-1caa-4b54-a04f-6f61bb60d406/...'
        const uuidRegex = /([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i;
        const match = url.match(uuidRegex);
        if (!match) return url; // 如果找不到UUID，返回原始URL

        const baseUrl = url.substring(0, url.indexOf(match[0]) + match[0].length);
        if (type === 'video') {
            return `${baseUrl}/width=450,optimized=true`;
        }
        return `${baseUrl}/width=450`;

    } catch (e) {
        console.error("Error parsing Civitai URL, returning original:", e);
        return url; // 解析失败则返回原始URL
    }
}

// --- 辅助函数：创建在线模型卡片 ---
function createCivitaiCard(model) {
    const card = document.createElement("div");
    card.className = "civitai-browser-card";

    const version = model.modelVersions?.[0];
    if (!version) return null;

    const coverImage = version.images?.find(i => i.url) || version.images?.[0];
    const creatorName = model.creator?.username || 'Unknown';

    // 检查模型是否已下载
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

    if (coverImage?.url) {
        if (coverImage.type === 'video' && coverImage.meta?.vcodec) {
            // --- 视频处理逻辑 ---
            const video = document.createElement('video');
            video.className = 'browser-preview-vid';
            video.src = getOptimizedUrl(coverImage.url, 'video');
            video.loop = true;
            video.muted = true;
            video.playsInline = true;
            video.loading = 'lazy';

            video.oncanplay = () => { placeholder.style.display = 'none'; };
            video.onerror = () => { // 增加错误处理
                console.error(`[Civitai Browser] Failed to load video: ${video.src}`);
                video.remove();
                placeholder.style.display = 'flex';
            };

            card.addEventListener('mouseenter', () => video.play().catch(e => {}));
            card.addEventListener('mouseleave', () => video.pause());

            previewContainer.prepend(video);
        } else {
            // --- 图片处理逻辑 ---
            const img = document.createElement('img');
            img.className = 'browser-preview-img';
            img.src = getOptimizedUrl(coverImage.url, 'image');
            img.alt = model.name;
            img.loading = 'lazy';

            img.onload = () => { placeholder.style.display = 'none'; };
            img.onerror = () => {
                console.error(`[Civitai Browser] Failed to load image: ${img.src}`);
                img.remove();
                placeholder.style.display = 'flex';
            };

            previewContainer.prepend(img);
        }
    } else {
        placeholder.style.display = 'flex';
    }

    card.onclick = () => window.open(`https://civitai.com/models/${model.id}?modelVersionId=${version.id}`, '_blank');

    return card;
}

// --- 数据加载函数 ---
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

        console.log("[Civitai Browser] API Metadata:", data.metadata);

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
                .civitai-browser-filters { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
                #civitai-browser-search { grid-column: 1 / -1; }
                .civitai-browser-filters select, .civitai-browser-filters input { width: 100%; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); box-sizing: border-box; }
                .browser-card-badges { position: absolute; top: 5px; right: 5px; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
                .browser-card-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; color: white; text-transform: capitalize; }
                .browser-card-badge.type { background-color: rgba(0, 0, 0, 0.6); }
                .browser-card-badge.downloaded { background-color: #4CAF50; }
                #civitai-browser-load-more { padding: 10px 0; flex-shrink: 0; }
                #civitai-browser-load-more button { width: 100%; padding: 8px; font-size: 14px; cursor: pointer; }
                #civitai-browser-load-more button:disabled { cursor: not-allowed; opacity: 0.7; }
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
                        <div class="civitai-browser-filters">
                            <input type="search" id="civitai-browser-search" placeholder="Search Civitai...">
                            <select id="civitai-browser-sort">${sortOptions}</select>
                            <select id="civitai-browser-period">${periodOptions}</select>
                            <select id="civitai-browser-types"><option value="">All Types</option>${typeOptions.substring(typeOptions.indexOf('</option>')+9)}</select>
                            <select id="civitai-browser-base-models"><option value="">All Base Models</option>${baseModelOptions.substring(baseModelOptions.indexOf('</option>')+9)}</select>
                        </div>
                        <div id="civitai-browser-list"></div>
                        <div class="loading-spinner" id="civitai-browser-spinner"></div>
                        <div class="empty-message" id="civitai-browser-empty-message">No models found.</div>
                        <div id="civitai-browser-load-more"><button style="display: none;">Load More</button></div>
                    </div>
                `;

                const container = el.querySelector(".civitai-browser-container");

                const resetAndFetch = () => {
                    browserState.nextCursor = null;
                    fetchCivitaiModels(container, false);
                };

                let debounceTimer;
                container.querySelector("#civitai-browser-search").addEventListener("input", (e) => {
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(() => {
                        browserState.filters.query = e.target.value;
                        resetAndFetch();
                    }, 500);
                });

                container.querySelector("#civitai-browser-sort").addEventListener("change", (e) => {
                    browserState.filters.sort = e.target.value; resetAndFetch();
                });
                container.querySelector("#civitai-browser-period").addEventListener("change", (e) => {
                    browserState.filters.period = e.target.value; resetAndFetch();
                });

                // [新增] 刷新按钮的点击事件
                container.querySelector("#civitai-browser-refresh-btn").addEventListener("click", () => {
                    syncFiltersFromUI(); // 点击刷新时，先从UI同步最新的筛选条件
                    resetAndFetch();     // 然后重置并获取数据
                });
                container.querySelector("#civitai-browser-base-models").addEventListener("change", (e) => {
                    browserState.filters.baseModels = e.target.value; resetAndFetch();
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