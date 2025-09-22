import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
    name: "Comfy.CivitaiUtils.Settings",

    async setup() {
        // 辅助函数: 处理缓存清除逻辑
        const handleClearCache = async (cacheType, buttonElement) => {
            const originalContent = buttonElement.innerHTML;
            const confirmMessage = cacheType === 'all'
                ? "Are you sure you want to clear ALL caches? This includes analysis results, API responses, and trigger words. This action cannot be undone."
                : `Are you sure you want to clear the '${cacheType}' cache? This action cannot be undone.`;

            if (!confirm(confirmMessage)) return;

            buttonElement.disabled = true;
            buttonElement.innerHTML = `<div class="civitai-button-content"><span class="civitai-button-title">🗑️ Clearing...</span></div>`;

            try {
                const response = await api.fetchApi('/civitai_utils/clear_cache', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 'cache_type': cacheType })
                });
                const data = await response.json();
                if (response.ok) {
                    buttonElement.classList.add('success');
                } else {
                    throw new Error(data.message || "Unknown error occurred.");
                }
            } catch (e) {
                console.error(`[Civitai Utils] Failed to clear ${cacheType} cache:`, e);
                alert(`Error clearing cache: ${e.message}`);
                buttonElement.classList.add('error');
            } finally {
                setTimeout(() => {
                    buttonElement.innerHTML = originalContent;
                    buttonElement.disabled = false;
                    buttonElement.classList.remove('success', 'error');
                }, 2000);
            }
        };

        // 1. 网络设置 - 使用原生布局
        const networkSetting = app.ui.settings.addSetting({
            id: "CivitaiUtils.NetworkChoice",
            name: "🌐 Network Endpoint", // 左侧标签
            type: "combo", // 右侧控件
            defaultValue: "com",
            options: () => [
                { value: "com", text: "International (civitai.com)" },
                { value: "work", text: "China Mirror (civitai.work)" },
            ],
            async onChange(value) {
                try {
                    await api.fetchApi('/civitai_recipe_finder/set_config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ network_choice: value })
                    });
                } catch (e) {
                    console.error("[Civitai Utils] Failed to save network choice:", e);
                }
            },
        });

        // 2. 数据库管理 - 使用原生布局
        app.ui.settings.addSetting({
            id: "CivitaiUtils.DatabaseManagement",
            name: "🗃️ Database Actions", // 左侧标签
            type: (name, setter, value) => {
                // 右侧控件
                const container = document.createElement("div");
                container.className = "civitai-settings-btn-container";

                container.innerHTML = `
                    <p class="civitai-settings-widget-desc">Clear cached data to resolve issues or re-fetch information.</p>
                    <div class="civitai-settings-grid">
                        <button id="civitai-clear-analysis">
                            <div class="civitai-button-content">
                                <span class="civitai-button-title">📈 Clear Analyzer Cache</span>
                                <span class="civitai-button-desc">Removes saved analysis reports.</span>
                            </div>
                        </button>
                        <button id="civitai-clear-api">
                            <div class="civitai-button-content">
                                <span class="civitai-button-title">☁️ Clear API Cache</span>
                                <span class="civitai-button-desc">Removes cached model info.</span>
                            </div>
                        </button>
                        <button id="civitai-clear-triggers">
                            <div class="civitai-button-content">
                                <span class="civitai-button-title">🏷️ Clear Triggers Cache</span>
                                <span class="civitai-button-desc">Removes cached LoRA trigger words.</span>
                            </div>
                        </button>
                    </div>
                    <hr class="civitai-separator">
                    <div class="civitai-danger-zone">
                        <button id="civitai-clear-all" class="danger">
                            <div class="civitai-button-content">
                                <span class="civitai-button-title">💥 Clear All Caches</span>
                                <span class="civitai-button-desc">Reset everything.</span>
                            </div>
                        </button>
                    </div>
                `;

                // 绑定事件
                container.querySelector("#civitai-clear-analysis").onclick = (e) => handleClearCache('analysis', e.currentTarget);
                container.querySelector("#civitai-clear-api").onclick = (e) => handleClearCache('api_responses', e.currentTarget);
                container.querySelector("#civitai-clear-triggers").onclick = (e) => handleClearCache('triggers', e.currentTarget);
                container.querySelector("#civitai-clear-all").onclick = (e) => handleClearCache('all', e.currentTarget);

                return container;
            }
        });

        // --- 全局样式注入 (只美化控件，不改变布局) ---
        if (!document.getElementById('civitai-settings-styles')) {
            const style = document.createElement('style');
            style.id = 'civitai-settings-styles';
            style.textContent = `
                .civitai-settings-btn-container {
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    width: 100%;
                }
                .civitai-settings-widget-desc {
                    font-size: 12px;
                    color: var(--desc-text-color);
                    opacity: 0.8;
                    margin: 0;
                }
                .civitai-settings-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 10px;
                }
                .civitai-settings-grid button {
                    font-family: sans-serif;
                    background-color: var(--comfy-input-bg);
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    padding: 10px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    text-align: left;
                    height: 100%;
                }
                .civitai-settings-grid button:hover {
                    background-color: var(--comfy-input-bg-hover);
                    border-color: var(--desc-text-color);
                }
                .civitai-button-content { display: flex; flex-direction: column; gap: 4px; }
                .civitai-button-title {
                    font-size: 13px;
                    font-weight: bold;
                    color: var(--fg-color);
                }
                .civitai-button-desc {
                    font-size: 11px;
                    color: var(--desc-text-color);
                    opacity: 0.8;
                    white-space: normal;
                }
                .civitai-settings-grid button.success,
                .danger-zone button.success { background-color: rgba(76, 175, 80, 0.3) !important; border-color: #4CAF50 !important; }
                .civitai-settings-grid button.error,
                .danger-zone button.error { background-color: rgba(217, 83, 79, 0.3) !important; border-color: #D9534F !important; }
                
                .civitai-separator { border: none; border-top: 1px solid var(--border-color); margin: 10px 0; }
                .danger-zone button.danger {
                    border-color: rgba(217, 83, 79, 0.5);
                    width: 100%;
                }
                .danger-zone button.danger:hover { background-color: #D9534F; border-color: #D9534F; }
                .danger-zone button.danger:hover .civitai-button-title,
                .danger-zone button.danger:hover .civitai-button-desc { color: white; }
            `;
            document.head.appendChild(style);
        }

        // 从后端加载已保存的设置
        try {
            const response = await api.fetchApi('/civitai_recipe_finder/get_config');
            const config = await response.json();
            if (config.network_choice && networkSetting) {
                networkSetting.value = config.network_choice;
            }
        } catch (e) {
            console.warn("[Civitai Utils] Could not load saved config, using default.", e);
        }
    }
});