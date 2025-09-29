// 文件名: civitai_browser.js
// 版本：第三阶段优化完成 (已修复400错误)

import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

// --- 状态管理对象 ---
const browserState = {
    models: [],
    filters: {
        limit: 24,
        page: 1,
        sort: 'Most Downloaded',
        period: 'AllTime',
        query: ''
    },
    network: 'com', // 默认值，会从后端获取并覆盖
    isLoading: false,
    totalPages: 1,
    hasMorePages: true, // 新增：用于跟踪是否还有更多页面
    localHashes: new Set(),
};


// --- 辅助函数：创建在线模型卡片 ---
function createCivitaiCard(model) {
    const card = document.createElement("div");
    card.className = "civitai-browser-card";

    const version = model.modelVersions?.[0];
    if (!version) return null;

    const coverImage = version.images?.find(i => i.url) || version.images?.[0];
    const previewUrl = coverImage ? coverImage.url.replace('/width=dpr', '/width=450') : '';
    const creatorName = model.creator?.username || 'Unknown';

    // 检查模型是否已下载
    const file = version.files?.[0];
    const fileHash = file?.hashes?.SHA256?.toLowerCase();
    const isDownloaded = fileHash && browserState.localHashes.has(fileHash);

    card.innerHTML = `
        <div class="browser-preview-container">
            ${previewUrl ? `<img class="browser-preview-img" src="${previewUrl}" alt="${model.name}" loading="lazy">` : ''}
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

    if (!previewUrl) card.querySelector('.browser-preview-placeholder').style.display = 'flex';

    card.onclick = () => window.open(`https://civitai.com/models/${model.id}?modelVersionId=${version.id}`, '_blank');

    return card;
}

// --- 新增：渲染分页控件 ---
function renderPagination(container) {
    const paginationContainer = container.querySelector("#civitai-browser-pagination");
    const { page } = browserState.filters;
    const { totalPages, hasMorePages } = browserState;

    // 只要当前页不是第一页，或者还有下一页，就应该显示分页控件
    if (page === 1 && !hasMorePages) {
        paginationContainer.style.display = 'none';
        return;
    }

    paginationContainer.style.display = 'flex';

    // 如果API提供了总页数，就显示 "Page X of Y"，否则只显示当前页
    const pageIndicator = totalPages > 1
        ? `Page ${page} of ${totalPages}`
        : `Page ${page}`;

    paginationContainer.innerHTML = `
        <button id="civitai-browser-prev" title="Previous Page" ${page <= 1 ? 'disabled' : ''}>&lt;</button>
        <span class="page-indicator">${pageIndicator}</span>
        <button id="civitai-browser-next" title="Next Page" ${!hasMorePages ? 'disabled' : ''}>&gt;</button>
    `;

    paginationContainer.querySelector("#civitai-browser-prev").onclick = () => {
        if (browserState.filters.page > 1) {
            browserState.filters.page--;
            fetchCivitaiModels(container);
        }
    };
    paginationContainer.querySelector("#civitai-browser-next").onclick = () => {
        if (hasMorePages) {
            browserState.filters.page++;
            fetchCivitaiModels(container);
        }
    };
}


// --- 数据加载函数 (已修改) ---
async function fetchCivitaiModels(container) {
    if (browserState.isLoading) return;

    browserState.isLoading = true;
    const spinner = container.querySelector("#civitai-browser-spinner");
    const emptyMsg = container.querySelector('#civitai-browser-empty-message');
    const listContainer = container.querySelector("#civitai-browser-list");
    const paginationContainer = container.querySelector("#civitai-browser-pagination");

    spinner.style.display = 'block';
    emptyMsg.style.display = 'none';
    listContainer.innerHTML = ''; // 每次翻页都清空当前内容
    paginationContainer.style.display = 'none'; // 加载时隐藏分页

    try {
        const filters = { ...browserState.filters };

        if (!filters.query) {
            delete filters.query;
        }

        const params = new URLSearchParams(filters);
        const baseUrl = `https://civitai.${browserState.network}/api/v1/models`;

        const response = await fetch(`${baseUrl}?${params.toString()}`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();

        console.log("[Civitai Browser] API Metadata:", data.metadata); // 调试日志

        browserState.models = data.items;
        // 同时更新 totalPages 和 hasMorePages，增加健壮性
        browserState.totalPages = data.metadata.totalPages || browserState.filters.page;
        browserState.hasMorePages = !!data.metadata.nextPage;

        for (const model of data.items) {
            const card = createCivitaiCard(model);
            if(card) listContainer.appendChild(card);
        }

        if (browserState.models.length === 0) {
            emptyMsg.style.display = 'block';
        }

    } catch (e) {
        console.error("Failed to fetch from Civitai:", e);
        emptyMsg.textContent = `Error: ${e.message}. Check console.`;
        emptyMsg.style.display = 'block';
    } finally {
        browserState.isLoading = false;
        spinner.style.display = 'none';
        renderPagination(container); // 渲染分页控件
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
                .browser-preview-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; }
                .browser-preview-placeholder { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: none; justify-content: center; align-items: center; font-size: 2em; color: #555; }
                .browser-model-info { padding: 8px; }
                .browser-model-name { font-weight: bold; color: var(--fg-color); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; min-height: 2.4em; }
                .browser-model-creator { font-size: 0.8em; color: var(--desc-text-color); }
                .browser-model-stats { display: flex; justify-content: space-between; font-size: 0.8em; color: var(--desc-text-color); margin-top: 5px; }
                .civitai-browser-filters { display: flex; gap: 10px; margin-bottom: 10px; }
                .civitai-browser-filters select, .civitai-browser-filters input { flex-grow: 1; padding: 5px; border-radius: 4px; border: 1px solid var(--border-color); background: var(--comfy-input-bg); color: var(--input-text-color); }
                .browser-card-badges { position: absolute; top: 5px; right: 5px; display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
                .browser-card-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; color: white; text-transform: capitalize; }
                .browser-card-badge.type { background-color: rgba(0, 0, 0, 0.6); }
                .browser-card-badge.downloaded { background-color: #4CAF50; }
                #civitai-browser-pagination { display: flex; justify-content: center; align-items: center; padding: 10px 0; gap: 10px; flex-shrink: 0; }
                #civitai-browser-pagination button { padding: 5px 10px; cursor: pointer; }
                #civitai-browser-pagination button:disabled { cursor: not-allowed; opacity: 0.5; }
                #civitai-browser-pagination .page-indicator { color: var(--desc-text-color); font-size: 14px; }
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

                el.innerHTML = `
                    <div class="civitai-browser-container">
                        <div class="civitai-browser-filters">
                            <input type="search" id="civitai-browser-search" placeholder="Search Civitai...">
                            <select id="civitai-browser-sort">${sortOptions}</select>
                            <select id="civitai-browser-period">${periodOptions}</select>
                        </div>
                        <div id="civitai-browser-list"></div>
                        <div class="loading-spinner" id="civitai-browser-spinner"></div>
                        <div class="empty-message" id="civitai-browser-empty-message">No models found.</div>
                        <div id="civitai-browser-pagination"></div>
                    </div>
                `;

                const container = el.querySelector(".civitai-browser-container");
                const listContainer = container.querySelector("#civitai-browser-list");

                const resetAndFetch = () => {
                    browserState.filters.page = 1; // 任何筛选或搜索都重置到第一页
                    fetchCivitaiModels(container);
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
                    browserState.filters.sort = e.target.value;
                    resetAndFetch();
                });
                container.querySelector("#civitai-browser-period").addEventListener("change", (e) => {
                    browserState.filters.period = e.target.value;
                    resetAndFetch();
                });


                // ---- 初始化 ----
                try {
                    // 1. 获取网络配置
                    const configRes = await api.fetchApi('/civitai_recipe_finder/get_config');
                    const config = await configRes.json();
                    browserState.network = config.network_choice || 'com';

                    // 2. 获取本地哈希列表
                    const hashesRes = await api.fetchApi('/civitai_utils/get_local_hashes');
                    const hashesData = await hashesRes.json();
                    if(hashesData.status === 'ok' && Array.isArray(hashesData.hashes)){
                        browserState.localHashes = new Set(hashesData.hashes);
                    }

                } catch (e) {
                    console.error("[Civitai Browser] Failed to initialize settings:", e);
                } finally {
                     // 3. 开始第一次数据加载
                    fetchCivitaiModels(container);
                }
            }
        });
    }
});