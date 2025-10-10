import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";


function setupGlobalLightbox() {
    if (document.getElementById('civitai-gallery-lightbox')) return;

    // 同时创建 img 和 video 元素，默认都隐藏
    const lightboxHTML = `
        <div id="civitai-gallery-lightbox" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 10000; justify-content: center; align-items: center;">
            <span class="lightbox-close" style="position: absolute; top: 20px; right: 30px; font-size: 40px; color: white; cursor: pointer;">&times;</span>
            <img class="lightbox-content-img" style="display: none; max-width: 90%; max-height: 90%; object-fit: contain;">
            <video class="lightbox-content-video" controls autoplay loop style="display: none; max-width: 90%; max-height: 90%;"></video>
        </div>`;
    document.body.insertAdjacentHTML('beforeend', lightboxHTML);

    const lightbox = document.getElementById('civitai-gallery-lightbox');
    const videoElement = lightbox.querySelector('.lightbox-content-video');

    const closeLightbox = () => {
        videoElement.pause(); // 关闭时暂停视频，避免在后台播放
        lightbox.style.display = 'none';
    };

    lightbox.querySelector('.lightbox-close').addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', (e) => {
        // 点击背景区域关闭
        if (e.target.id === 'civitai-gallery-lightbox') {
            closeLightbox();
        }
    });
}
setupGlobalLightbox();

app.registerExtension({
    name: "Comfy.CivitaiRecipeGallery",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "CivitaiRecipeGallery") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);

            const widget = this.addDOMWidget("civitai-gallery", "div", document.createElement("div"), {});
            widget.element.className = "civitai-gallery-container";
            this.size = [480, 700];

            let allModels = []; // 用于存储从API获取的完整模型列表
            const modelTypeWidget = this.widgets.find(w => w.name === "model_type");
            const modelNameWidget = this.widgets.find(w => w.name === "model_name");

            // 1. 定义一个纯前端的筛选和更新函数
            const updateModelNameWidget = (type) => {
                if (!modelNameWidget || allModels.length === 0) return;

                // 从完整的模型列表中筛选出当前类型的文件名
                const filteredNames = allModels
                    .filter(m => m.model_type === type)
                    .map(m => m.filename);

                modelNameWidget.options.values = filteredNames;
                modelNameWidget.value = filteredNames[0] || ""; // 默认选中第一个
            };

            // 2. 将 model_type 的回调指向这个纯前端函数
            if (modelTypeWidget) {
                modelTypeWidget.callback = (value) => {
                    updateModelNameWidget(value);
                };
            }

            // 3. 定义一个只在节点创建时执行一次的异步加载函数
            const initializeNode = async () => {
                try {
                    // 调用和 local_manager 完全相同的 API
                    const response = await api.fetchApi('/civitai_utils/get_local_models');
                    const data = await response.json();
                    if (data.status === 'ok' && data.models) {
                        allModels = data.models; // 缓存完整列表
                        // 首次加载后，立即用默认类型填充 model_name 列表
                        if (modelTypeWidget) {
                            updateModelNameWidget(modelTypeWidget.value);
                        }
                    } else {
                        throw new Error(data.message || "Failed to load models list.");
                    }
                } catch (e) {
                    console.error(`[Civitai Gallery] Failed to initialize model list: ${e.message}`);
                }
            };

            // 4. 执行初始化
            initializeNode();

            let selectedImageData = null;

            const rebuildMasonryLayout = (grid) => {
                if (!grid || grid.clientWidth === 0) return;
                const gap = 8; const cardWidth = 150;
                const numColumns = Math.max(1, Math.floor((grid.clientWidth - gap) / (cardWidth + gap)));
                const columnHeights = Array(numColumns).fill(0);
                Array.from(grid.children).forEach(card => {
                    if (card.style.display === 'none') return;
                    const minHeight = Math.min(...columnHeights);
                    const colIndex = columnHeights.indexOf(minHeight);
                    card.style.left = `${colIndex * (cardWidth + gap)}px`;
                    card.style.top = `${minHeight}px`;
                    columnHeights[colIndex] += card.offsetHeight + gap;
                });
                grid.style.height = `${Math.max(...columnHeights)}px`;
            };

            // [修改] 渲染函数不再需要自己做筛选
            const renderGalleryImages = (images) => {
                const grid = widget.element.querySelector('.civitai-gallery-masonry');
                const statusSpan = widget.element.querySelector('.status');
                const saveBtn = widget.element.querySelector('.save-btn');
                const loadWorkflowBtn = widget.element.querySelector('.load-workflow-btn');
                if (!grid) return;

                grid.innerHTML = "";
                selectedImageData = null;
                saveBtn.disabled = true;
                loadWorkflowBtn.disabled = true;

                if (!images || images.length === 0) {
                    statusSpan.textContent = 'No items found matching your criteria.';
                    rebuildMasonryLayout(grid);
                    return;
                }

                let processedImages = 0;
                let successfulLoads = 0;

                const checkCompletion = () => {
                    if (processedImages === images.length) {

                        requestAnimationFrame(() => {
                            rebuildMasonryLayout(grid);
                        });
                        statusSpan.textContent = `Displayed ${successfulLoads} of ${images.length} items.`;
                        const firstVisibleItem = grid.querySelector('.civitai-gallery-item:not([style*="display: none"])');
                        if (firstVisibleItem) {
                            firstVisibleItem.click();
                        }
                    }
                };

                // 直接遍历后端返回的已筛选数组
                images.forEach(imgData => {
                    const item = document.createElement('div');
                    item.className = 'civitai-gallery-item';

                    let mediaElement;
                    const onMediaProcessed = () => { processedImages++; checkCompletion(); };

                    if (imgData.type === 'video') {
                        mediaElement = document.createElement('video');
                        mediaElement.src = imgData.url.replace(/\/(width|height)=\d+/g, '/width=300');
                        mediaElement.muted = true;
                        mediaElement.loop = true;
                        mediaElement.playsinline = true;
                        mediaElement.onloadedmetadata = () => { successfulLoads++; onMediaProcessed(); };
                        mediaElement.onerror = () => {
                            console.error("Civitai Recipe Gallery: Failed to load video:", imgData.url);
                            item.remove(); onMediaProcessed();
                        };
                        item.addEventListener('mouseenter', () => mediaElement.play());
                        item.addEventListener('mouseleave', () => mediaElement.pause());
                    } else {
                        mediaElement = document.createElement('img');
                        mediaElement.src = imgData.url.replace(/\/(width|height)=\d+/g, '/width=300');
                        mediaElement.onload = () => { successfulLoads++; onMediaProcessed(); };
                        mediaElement.onerror = () => {
                            console.error("Civitai Recipe Gallery: Failed to load image:", imgData.url);
                            item.remove(); onMediaProcessed();
                        };
                    }

                    mediaElement.style.width = '100%';
                    mediaElement.style.height = 'auto';
                    mediaElement.style.display = 'block';
                    item.appendChild(mediaElement);
                    grid.appendChild(item);

                    item.addEventListener('click', () => {
                        grid.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
                        item.classList.add('selected');
                        selectedImageData = imgData;
                        saveBtn.disabled = false;
                        const hasWorkflowInMeta = imgData.meta?.workflow || imgData.meta?.prompt;
                        loadWorkflowBtn.disabled = !hasWorkflowInMeta;
                        loadWorkflowBtn.title = hasWorkflowInMeta ? "Load Workflow (will also save and cache the recipe)" : "No workflow data found.";
                        const imageOutput = this.outputs.find(o => o.name === 'image');
                        const isConnected = imageOutput?.links?.length > 0;
                        api.fetchApi('/civitai_recipe_finder/set_selection', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ node_id: this.id, item: imgData, download_image: isConnected })
                        });
                    });

                    item.addEventListener('dblclick', () => {
                        const lightbox = document.getElementById('civitai-gallery-lightbox');
                        const imgContent = lightbox.querySelector('.lightbox-content-img');
                        const videoContent = lightbox.querySelector('.lightbox-content-video');

                        if (selectedImageData.type === 'video') {
                            imgContent.style.display = 'none';
                            videoContent.style.display = 'block';
                            videoContent.src = selectedImageData.url;
                        } else {
                            videoContent.style.display = 'none';
                            imgContent.style.display = 'block';
                            imgContent.src = selectedImageData.url;
                        }

                        lightbox.style.display = 'flex';
                    });
                });
                new ResizeObserver(() => rebuildMasonryLayout(grid)).observe(grid);
            };

            const bindButtonEvents = () => {
                const refreshBtn = widget.element.querySelector('.refresh-btn');
                const saveBtn = widget.element.querySelector('.save-btn');
                const loadWorkflowBtn = widget.element.querySelector('.load-workflow-btn');
                const statusSpan = widget.element.querySelector('.status');

                refreshBtn.addEventListener('click', async () => {
                    const modelTypeWidget = this.widgets.find(w => w.name === "model_type");
                    const modelNameWidget = this.widgets.find(w => w.name === "model_name");
                    const sortWidget = this.widgets.find(w => w.name === "sort");
                    const nsfwWidget = this.widgets.find(w => w.name === "nsfw_level");
                    const limitWidget = this.widgets.find(w => w.name === "image_limit");
                    const filterTypeWidget = this.widgets.find(w => w.name === "filter_type");

                    if (!modelNameWidget || !modelTypeWidget || !filterTypeWidget) { statusSpan.textContent = 'Error: Widget not found.'; return; }
                    statusSpan.textContent = 'Fetching, please wait...';

                    try {
                        const params = new URLSearchParams({
                            model_type: modelTypeWidget.value,
                            model_filename: modelNameWidget.value,
                            sort: sortWidget.value,
                            nsfw_level: nsfwWidget.value,
                            limit: limitWidget.value,
                            filter_type: filterTypeWidget.value
                        });

                        const response = await api.fetchApi(`/civitai_recipe_finder/fetch_data?${params}`, { cache: "no-store" });
                        if(!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                        const data = await response.json();
                        if(data.status !== "ok") throw new Error(data.message);

                        statusSpan.textContent = 'Data received. Rendering...';
                        renderGalleryImages(data.images);
                    } catch (e) {
                        statusSpan.textContent = `Error: ${e.message}`;
                        renderGalleryImages([]);
                    }
                });

                saveBtn.addEventListener('click', async () => {
                    if (!selectedImageData) { alert("Please select an image first."); return; }
                    statusSpan.textContent = 'Saving original media...';
                    try {
                        const cleanUrl = selectedImageData.url.replace(/\/(width|height|fit|quality|format)=\w+/g, '');
                        const response = await api.fetchApi('/civitai_recipe_finder/save_original_image', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ url: cleanUrl })
                        });
                        if(!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                        const data = await response.json();
                        if(data.status === "ok" || data.status === "exists") {
                             statusSpan.textContent = data.message;
                             saveBtn.style.backgroundColor = '#4CAF50';
                             setTimeout(() => { saveBtn.style.backgroundColor = ''; }, 2500);
                        } else {
                            throw new Error(data.message);
                        }
                    } catch(e) {
                        statusSpan.textContent = `Save Error: ${e.message}`;
                        saveBtn.style.backgroundColor = '#D9534F';
                        setTimeout(() => { saveBtn.style.backgroundColor = ''; }, 2500);
                    }
                });

                loadWorkflowBtn.addEventListener('click', async () => {
                    if (!selectedImageData) { alert("Please select an image first."); return; }
                    if (selectedImageData.type === 'video') { alert("Cannot load workflow from a video."); return; }
                    try {
                        const imageId = selectedImageData.id;
                        if (!imageId) throw new Error("Image data is missing a unique ID.");

                        const cacheKey = `civitai-workflow-cache-${imageId}`;
                        const cachedWorkflow = localStorage.getItem(cacheKey);
                        let sourceData, sourceType;

                        if (cachedWorkflow) {
                            console.log(`[Civitai Recipe Gallery] Found workflow for image ${imageId} in cache.`);
                            statusSpan.textContent = 'Found workflow in cache...';
                            sourceData = JSON.parse(cachedWorkflow);
                            sourceType = 'json';
                        } else {
                            statusSpan.textContent = 'Downloading image...';
                            const cleanUrl = selectedImageData.url.replace(/\/(width|height|fit|quality|format)=\w+/g, '');
                            const response = await api.fetchApi('/civitai_recipe_finder/get_workflow_source', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({ url: cleanUrl })
                            });
                            if (!response.ok) throw new Error(`Failed to download image: ${response.statusText}`);
                            const imageBlob = await response.blob();
                            sourceData = new File([imageBlob], "workflow_image.png", { type: imageBlob.type });
                            sourceType = 'file';
                        }

                        const newWorkflowCommand = app.extensionManager?.command?.commands.find(c => c.id === "Comfy.NewBlankWorkflow");

                        if (newWorkflowCommand?.function) {
                            statusSpan.textContent = 'Creating new tab...';
                            await newWorkflowCommand.function();
                            statusSpan.textContent = 'Loading workflow into new tab...';
                        } else {
                            if (!confirm("Could not create a new tab automatically. REPLACE current workflow instead?")) {
                                statusSpan.textContent = 'Load cancelled by user.';
                                return;
                            }
                            statusSpan.textContent = 'Loading workflow...';
                        }

                        if (sourceType === 'json') {
                            app.loadGraphData(sourceData);
                        } else {
                            await app.handleFile(sourceData);
                            const loadedWorkflow = app.graph.serialize();
                            if (loadedWorkflow && Object.keys(loadedWorkflow.nodes).length > 0) {
                                try {
                                    localStorage.setItem(cacheKey, JSON.stringify(loadedWorkflow));
                                    console.log(`[Civitai Recipe Gallery] Workflow for image ${imageId} has been saved to cache.`);
                                } catch (e) {
                                    console.error("Failed to save workflow to localStorage. It might be full.", e);
                                }
                            }
                        }
                        statusSpan.textContent = 'Workflow loaded successfully!';
                    } catch (e) {
                        statusSpan.textContent = `Load Error: ${e.message}`;
                        alert(`Failed to load workflow: ${e.message}`);
                    }
                });
            };

            const renderUIAndBindEvents = () => {
                widget.element.innerHTML = `
                    <style>
                        .civitai-gallery-container { display: flex; flex-direction: column; height: 100%; font-family: sans-serif; background-color: var(--comfy-input-bg, #333); border-radius: 4px;}
                        .civitai-gallery-controls { padding: 5px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; border-bottom: 1px solid #222; }
                        .civitai-gallery-controls button { cursor: pointer; padding: 5px 10px; font-size: 12px; border-radius: 5px; background-color: var(--comfy-button-bg, #4a4a4a); color: var(--comfy-button-fg, white); border: 1px solid #555; transition: background-color 0.2s; }
                        .civitai-gallery-controls button:hover { background-color: #5c5c5c; }
                        .civitai-gallery-controls button:disabled { background-color: #333; color: #666; cursor: not-allowed; }
                        .civitai-gallery-controls .status { font-size: 12px; color: #888; flex-grow: 1; text-align: right; padding-right: 10px; min-width: 150px;}
                        .civitai-gallery-masonry { position: relative; flex-grow: 1; overflow-y: auto; padding: 8px; }
                        .civitai-gallery-item { position: absolute; width: 150px; border-radius: 4px; overflow: hidden; border: 3px solid transparent; transition: border-color 0.2s, top 0.3s, left 0.3s; background-color: #222; }
                        .civitai-gallery-item img, .civitai-gallery-item video { width: 100%; height: auto; display: block; cursor: pointer; }
                        .civitai-gallery-item.selected { border-color: var(--accent-color, #00A9E0); box-shadow: 0 0 10px var(--accent-color, #00A9E0); }
                    </style>
                    <div class="civitai-gallery-controls">
                        <button class="refresh-btn">🔄 Refresh Gallery</button>
                        <button class="save-btn" disabled title="Save original media with metadata to ComfyUI's output folder">💾 Save Original</button>
                        <button class="load-workflow-btn" disabled title="Load Workflow from selected image">🚀 Load Workflow</button>
                        <span class="status">Select options and click Refresh.</span>
                    </div>
                    <div class="civitai-gallery-masonry"></div>`;
                bindButtonEvents();
            };

            renderUIAndBindEvents();
        };
    }
});