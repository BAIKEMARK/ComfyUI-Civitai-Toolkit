import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

function setupGlobalLightbox() {
    if (document.getElementById('civitai-ultimate-lightbox')) return;
    const lightboxHTML = `<div id="civitai-ultimate-lightbox" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 10000; justify-content: center; align-items: center;"><span class="lightbox-close" style="position: absolute; top: 15px; right: 25px; font-size: 35px; color: white; cursor: pointer;">&times;</span><img class="lightbox-content" style="max-width: 90%; max-height: 90%; object-fit: contain;"></div>`;
    document.body.insertAdjacentHTML('beforeend', lightboxHTML);
    const lightbox = document.getElementById('civitai-ultimate-lightbox');
    lightbox.querySelector('.lightbox-close').addEventListener('click', () => lightbox.style.display = 'none');
    lightbox.addEventListener('click', (e) => { if (e.target.id === 'civitai-ultimate-lightbox') lightbox.style.display = 'none'; });
}
setupGlobalLightbox();

app.registerExtension({
    name: "Comfy.CivitaiRecipeGallery.Ultimate",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "CivitaiRecipeGallery") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                onNodeCreated?.apply(this, arguments);

                const container = document.createElement("div");
                container.className = "civitai-gallery-container";
                this.addDOMWidget("civitai-gallery", "div", container, {});
                this.size[1] = 700;

                const renderUI = () => {
                    container.innerHTML = `<style> .civitai-gallery-container { display: flex; flex-direction: column; height: 100%; } .civitai-gallery-controls { padding: 5px; display: flex; gap: 10px; align-items: center; } .civitai-gallery-controls button { cursor: pointer; padding: 5px 10px; font-size: 14px; border-radius: 5px; background-color: #4a4a4a; color: white; border: none; } .civitai-gallery-controls button:hover { background-color: #5c5c5c; } .civitai-gallery-controls .status { font-size: 12px; color: #888; flex-grow: 1; text-align: right; } .civitai-gallery-masonry { position: relative; flex-grow: 1; overflow-y: auto; padding: 5px; } .civitai-gallery-item { position: absolute; width: 150px; border-radius: 4px; overflow: hidden; border: 3px solid transparent; transition: border-color 0.2s, top 0.3s, left 0.3s; } .civitai-gallery-item img { width: 100%; height: auto; display: block; cursor: pointer; } .civitai-gallery-item.selected { border-color: var(--accent-color, #00A9E0); } </style> <div class="civitai-gallery-controls"> <button class="refresh-btn">🔄 Refresh</button> <span class="status">Select options and click Refresh.</span> </div> <div class="civitai-gallery-masonry"></div>`;
                    const refreshBtn = container.querySelector('.refresh-btn');
                    const statusSpan = container.querySelector('.status');

                    refreshBtn.addEventListener('click', async () => {
                        const modelNameWidget = this.widgets.find(w => w.name === "model_name");
                        const sortWidget = this.widgets.find(w => w.name === "sort");
                        const nsfwWidget = this.widgets.find(w => w.name === "nsfw_level");
                        const limitWidget = this.widgets.find(w => w.name === "image_limit");

                        if (!modelNameWidget || !nsfwWidget) { statusSpan.textContent = 'Error: Widget not found.'; return; }

                        statusSpan.textContent = 'Fetching, please wait...';
                        try {
                            const params = new URLSearchParams({ model_name: modelNameWidget.value, sort: sortWidget.value, nsfw_level: nsfwWidget.value, limit: limitWidget.value });
                            const response = await api.fetchApi(`/civitai_recipe_finder/fetch_data?${params}`);
                            if(!response.ok) throw new Error(`HTTP Error: ${response.status}`);
                            statusSpan.textContent = 'Data received. Rendering...';
                        } catch (e) { statusSpan.textContent = `Error: ${e.message}`; }
                    });
                };

                const rebuildMasonryLayout = (grid) => { if (!grid) return; const gap = 5; const cardWidth = 150; const numColumns = Math.max(1, Math.floor((grid.clientWidth - gap) / (cardWidth + gap))); const columnHeights = Array(numColumns).fill(0); Array.from(grid.children).forEach(card => { const minHeight = Math.min(...columnHeights); const colIndex = columnHeights.indexOf(minHeight); card.style.left = `${colIndex * (cardWidth + gap)}px`; card.style.top = `${minHeight}px`; columnHeights[colIndex] += card.offsetHeight + gap; }); grid.style.height = `${Math.max(...columnHeights)}px`; };

                const renderGalleryImages = (images) => {
                    const grid = container.querySelector('.civitai-gallery-masonry');
                    const statusSpan = container.querySelector('.status');
                    if (!grid) return;
                    grid.innerHTML = "";
                    if (!images || images.length === 0) { statusSpan.textContent = 'No recipes found for this model.'; return; }

                    let loadedImages = 0;
                    images.forEach(imgData => {
                        const item = document.createElement('div');
                        item.className = 'civitai-gallery-item';
                        const img = document.createElement('img');
                        img.src = imgData.url.replace(/\/(width|height)=\d+/, '/width=300');
                        img.onload = () => { loadedImages++; if (loadedImages === images.length) { rebuildMasonryLayout(grid); statusSpan.textContent = `Loaded ${images.length} images.`; }};
                        item.appendChild(img);

                        item.addEventListener('click', () => {
                            grid.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
                            item.classList.add('selected');

                            const meta = imgData.meta || {};

                            // 前端只负责更新核心参数的预览
                            this.setOutputData(0, meta.prompt || "");
                            this.setOutputData(1, meta.negativePrompt || "");
                            this.setOutputData(2, parseInt(meta.seed || -1));
                            this.setOutputData(3, parseInt(meta.steps || 20));
                            this.setOutputData(4, parseFloat(meta.cfgScale || 7.0));
                            this.setOutputData(5, meta.sampler || 'euler');
                            this.setOutputData(6, meta.scheduler || 'normal');
                            this.setOutputData(8, meta.Model || 'unknown');
                            this.setOutputData(9, parseInt(meta.width || 512));
                            this.setOutputData(10, parseInt(meta.height || 512));
                            this.setOutputData(11, parseFloat(meta.denoise || 1.0));

                            const imageOutput = this.outputs.find(o => o.name === 'image');
                            const isConnected = imageOutput && imageOutput.links && imageOutput.links.length > 0;

                            fetch('/civitai_recipe_finder/set_selection', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({ node_id: this.id, item: imgData, download_image: isConnected })
                            });
                        });

                        item.addEventListener('dblclick', () => { const lightbox = document.getElementById('civitai-ultimate-lightbox'); lightbox.querySelector('.lightbox-content').src = imgData.url; lightbox.style.display = 'flex'; });
                        grid.appendChild(item);
                    });
                    new ResizeObserver(() => rebuildMasonryLayout(grid)).observe(grid);

                    if (grid.children.length > 0) {
                        grid.children[0].click();
                    }
                };

                renderUI();

                const handleAsyncMessage = (event) => renderGalleryImages(event.detail.images);
                api.addEventListener("civitai-recipe-gallery-data", handleAsyncMessage);
                this.onRemoved = () => api.removeEventListener("civitai-recipe-gallery-data", handleAsyncMessage);
            };
        }
    }
});