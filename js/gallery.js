import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

// 全局Lightbox，用于双击放大图片
function setupGlobalLightbox() {
    if (document.getElementById('civitai-gallery-lightbox')) return;
    const lightboxHTML = `<div id="civitai-gallery-lightbox" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 10000; justify-content: center; align-items: center;"><span class="lightbox-close" style="position: absolute; top: 20px; right: 30px; font-size: 40px; color: white; cursor: pointer;">&times;</span><img class="lightbox-content" style="max-width: 90%; max-height: 90%; object-fit: contain;"></div>`;
    document.body.insertAdjacentHTML('beforeend', lightboxHTML);
    const lightbox = document.getElementById('civitai-gallery-lightbox');
    lightbox.querySelector('.lightbox-close').addEventListener('click', () => lightbox.style.display = 'none');
    lightbox.addEventListener('click', (e) => { if (e.target.id === 'civitai-gallery-lightbox') lightbox.style.display = 'none'; });
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
                    statusSpan.textContent = 'No recipes found for this model.';
                    return;
                }
                let processedImages = 0;
                let successfulLoads = 0;
                const checkCompletion = () => {
                    if (processedImages === images.length) {
                        rebuildMasonryLayout(grid);
                        statusSpan.textContent = `Displayed ${successfulLoads} of ${images.length} images.`;
                        const firstVisibleItem = grid.querySelector('.civitai-gallery-item:not([style*="display: none"])');
                        if (firstVisibleItem) {
                            firstVisibleItem.click();
                        }
                    }
                };
                images.forEach(imgData => {
                    const item = document.createElement('div');
                    item.className = 'civitai-gallery-item';
                    const img = document.createElement('img');
                    img.src = imgData.url.replace(/\/(width|height)=\d+/g, '/width=300');
                    const onImageProcessed = () => { processedImages++; checkCompletion(); };
                    img.onload = () => { successfulLoads++; onImageProcessed(); };
                    img.onerror = () => {
                        console.error("Civitai Recipe Gallery: Failed to load image:", imgData.url);
                        item.remove();
                        onImageProcessed();
                    };
                    item.appendChild(img);
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
                        lightbox.querySelector('.lightbox-content').src = selectedImageData.url;
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
                    const modelNameWidget = this.widgets.find(w => w.name === "model_name");
                    const sortWidget = this.widgets.find(w => w.name === "sort");
                    const nsfwWidget = this.widgets.find(w => w.name === "nsfw_level");
                    const limitWidget = this.widgets.find(w => w.name === "image_limit");
                    if (!modelNameWidget) { statusSpan.textContent = 'Error: Widget not found.'; return; }
                    statusSpan.textContent = 'Fetching, please wait...';
                    try {
                        const params = new URLSearchParams({ model_name: modelNameWidget.value, sort: sortWidget.value, nsfw_level: nsfwWidget.value, limit: limitWidget.value });
                        const response = await api.fetchApi(`/civitai_recipe_finder/fetch_data?${params}`, { cache: "no-store" });
                        if(!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                        const data = await response.json();
                        if(data.status !== "ok") throw new Error(data.message);
                        statusSpan.textContent = 'Data received. Rendering...';
                        renderGalleryImages(data.images);
                    } catch (e) { statusSpan.textContent = `Error: ${e.message}`; }
                });
                saveBtn.addEventListener('click', async () => {
                    if (!selectedImageData) { alert("Please select an image first."); return; }
                    statusSpan.textContent = 'Saving original image...';
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
                        saveBtn.style.backgroundColor = '#D9534F'; // Red color for error (错误时显示红色)
                        setTimeout(() => { saveBtn.style.backgroundColor = ''; }, 2500);
                    }
                });
                // 事件监听器
                loadWorkflowBtn.addEventListener('click', async () => {
                    if (!selectedImageData) {
                        alert("Please select an image first.");
                        return;
                    }

                    try {
                        const imageId = selectedImageData.id;
                        if (!imageId) throw new Error("Image data is missing a unique ID.");

                        const cacheKey = `civitai-workflow-cache-${imageId}`;
                        let workflowToLoad = null;

                        // 步骤 1: 准备工作流数据 (JSON 或 ImageFile)
                        const cachedWorkflow = localStorage.getItem(cacheKey);

                        let sourceData;
                        let sourceType; // 'json' or 'file'

                        if (cachedWorkflow) {
                            // 情况一：缓存命中
                            console.log(`[Civitai Recipe Gallery] Found workflow for image ${imageId} in cache.`);
                            statusSpan.textContent = 'Found workflow in cache...';
                            sourceData = JSON.parse(cachedWorkflow);
                            sourceType = 'json';
                        } else {
                            // 情况二：缓存未命中
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

                        // 步骤 2: 准备画布并加载数据
                        let newWorkflowCommand = null;
                        if (app.extensionManager && app.extensionManager.command && Array.isArray(app.extensionManager.command.commands)) {
                             newWorkflowCommand = app.extensionManager.command.commands.find(c => c.id === "Comfy.NewBlankWorkflow");
                        }

                        if (newWorkflowCommand && newWorkflowCommand.function) {
                            statusSpan.textContent = 'Creating new tab...';
                            // 先创建新标签页并等待完成
                            await newWorkflowCommand.function();

                            statusSpan.textContent = 'Loading workflow into new tab...';
                            if (sourceType === 'json') {
                                // 如果是缓存的JSON，用 loadGraphData
                                app.loadGraphData(sourceData);
                            } else {
                                // 如果是新下载的文件，用 handleFile
                                await app.handleFile(sourceData);
                                // 加载完后，序列化并存入缓存
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
                            statusSpan.textContent = 'Workflow loaded successfully in new tab!';

                        } else {
                            // 回退方案：无法自动新建标签页
                            if (confirm("Could not create a new tab automatically. REPLACE current workflow instead?")) {
                                statusSpan.textContent = 'Loading workflow...';
                                if (sourceType === 'json') {
                                    app.loadGraphData(sourceData);
                                } else {
                                    await app.handleFile(sourceData);
                                    // 同样存入缓存
                                    const loadedWorkflow = app.graph.serialize();
                                    if (loadedWorkflow && Object.keys(loadedWorkflow.nodes).length > 0) {
                                        localStorage.setItem(cacheKey, JSON.stringify(loadedWorkflow));
                                    }
                                }
                                statusSpan.textContent = 'Workflow loaded successfully!';
                            } else {
                                statusSpan.textContent = 'Load cancelled by user.';
                            }
                        }

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
                        .civitai-gallery-controls .status { font-size: 12px; color: #888; flex-grow: 1; text-align: right; min-width: 150px;}
                        .civitai-gallery-masonry { position: relative; flex-grow: 1; overflow-y: auto; padding: 8px; }
                        .civitai-gallery-item { position: absolute; width: 150px; border-radius: 4px; overflow: hidden; border: 3px solid transparent; transition: border-color 0.2s, top 0.3s, left 0.3s; background-color: #222; }
                        .civitai-gallery-item img { width: 100%; height: auto; display: block; cursor: pointer; }
                        .civitai-gallery-item.selected { border-color: var(--accent-color, #00A9E0); box-shadow: 0 0 10px var(--accent-color, #00A9E0); }
                    </style>
                    <div class="civitai-gallery-controls">
                        <button class="refresh-btn">🔄 Refresh</button>
                        <button class="save-btn" disabled title="Save original image with metadata to ComfyUI's output folder">💾 Save Original</button>
                        <button class="load-workflow-btn" disabled title="Load Workflow (will also save and cache the recipe)">🚀 Load Workflow</button>
                        <span class="status">Select options and click Refresh.</span>
                    </div>
                    <div class="civitai-gallery-masonry"></div>`;
                bindButtonEvents();
            };

            renderUIAndBindEvents();
        };
    }
});