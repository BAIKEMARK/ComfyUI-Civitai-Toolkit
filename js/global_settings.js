import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
    name: "Comfy.CivitaiUtils.Settings",

    async setup() {
        // --- 辅助函数 ---
        const createActionModal = (options) => {
            // 移除任何已存在的模态窗口
            const existingModal = document.querySelector('.civitai-modal');
            if (existingModal) existingModal.remove();

            const modal = document.createElement('div');
            modal.className = 'civitai-modal';

            const modalContent = document.createElement('div');
            modalContent.className = 'civitai-modal-content';
            modal.appendChild(modalContent);

            const updateModal = (title, content, showButtons) => {
                modalContent.innerHTML = `
                    <span class="civitai-modal-close">&times;</span>
                    <h3>${title}</h3>
                    <div class="civitai-modal-body">${content}</div>
                    <div class="civitai-modal-footer" style="display: ${showButtons ? 'flex' : 'none'};">
                        <button class="civitai-button cancel">Cancel</button>
                        <button class="civitai-button confirm">Confirm</button>
                    </div>
                `;
                modalContent.querySelector('.civitai-modal-close').onclick = () => modal.remove();
                modal.onclick = (e) => { if(e.target === modal) modal.remove(); };
            };

            updateModal(options.title, `<p>${options.confirmMessage}</p>`, true);
            document.body.appendChild(modal);
            modal.style.display = 'flex';

            modalContent.querySelector('.cancel').onclick = () => modal.remove();
            modalContent.querySelector('.confirm').onclick = async () => {
                updateModal('🔄 Processing...', '<div class="civitai-loader"></div>', false);
                try {
                    const response = await api.fetchApi(options.endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(options.body)
                    });
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.message || "Unknown error occurred.");

                    updateModal('✅ Success', `<p>${data.message}</p>`, false);
                    if (options.onSuccess) options.onSuccess(data);

                } catch (e) {
                    updateModal('❌ Error', `<p>${e.message}</p>`, false);
                }
            };
        };

        // 创建并显示模型列表模态窗口的函数
        const showModelListModal = async (modelType) => {
            const existingModal = document.querySelector('.civitai-modal');
            if (existingModal) existingModal.remove();

            const modal = document.createElement('div');
            modal.className = 'civitai-modal';
            modal.innerHTML = `
                <div class="civitai-modal-content">
                    <span class="civitai-modal-close">&times;</span>
                    <h3>${modelType.charAt(0).toUpperCase() + modelType.slice(1)} in Database</h3>
                    <div class="civitai-modal-list-container">Loading...</div>
                </div>
            `;
            document.body.appendChild(modal);
            modal.style.display = 'flex';

            modal.querySelector('.civitai-modal-close').onclick = () => modal.remove();
            modal.onclick = (e) => { if(e.target === modal) modal.remove(); };

            try {
                const response = await api.fetchApi(`/civitai_utils/get_scanned_models?model_type=${modelType}`);
                const data = await response.json();
                const listContainer = modal.querySelector('.civitai-modal-list-container');
                if(data.status === 'ok') {
                    if(data.models && data.models.length > 0) {
                        listContainer.innerHTML = `<ul>${data.models.map(m => `<li>${m}</li>`).join('')}</ul>`;
                    } else {
                        listContainer.textContent = 'No models found in the database.';
                    }
                } else { throw new Error(data.message); }
            } catch (e) {
                modal.querySelector('.civitai-modal-list-container').textContent = `Error loading list: ${e.message}`;
            }
        };

        // --- 创建设置项 ---

        // 1. 数据迁移 (只在检测到旧文件时显示)
        try {
            const res = await api.fetchApi('/civitai_utils/check_legacy_cache');
            const data = await res.json();
            if (data.exists) {
                app.ui.settings.addSetting({
                    id: "CivitaiUtils.Migration",
                    name: "🚀 Legacy Data Migration",
                    type: (name, setter, value) => {
                        const container = document.createElement("div");
                        const button = document.createElement("button");
                        button.style.width = '100%';
                        button.innerHTML = `<div class="civitai-button-content">
                            <span class="civitai-button-title">Migrate Hashes from Old Version</span>
                            <span class="civitai-button-desc">One-time import from hash_cache.json to the new database.</span>
                        </div>`;
                        button.onclick = () => createActionModal({
                            title: "Migrate Legacy Data",
                            confirmMessage: "Import hashes from old version (hash_cache.json)? This will merge data into the database and is recommended only once.",
                            endpoint: '/civitai_utils/migrate_hashes',
                            body: {},
                            onSuccess: () => {
                                button.closest('.setting-item').style.display = 'none';
                            }
                        });
                        container.appendChild(button);
                        return container;
                    }
                });
            }
        } catch(e) { console.error("[Civitai Utils] Failed to check for legacy cache:", e); }

        // 2. 数据库状态和管理
        app.ui.settings.addSetting({
            id: "CivitaiUtils.DatabaseManagement",
            name: "🗃️ Database & Models",
            type: (name, setter, value) => {
                const container = document.createElement("div");
                container.className = "civitai-settings-container";
                container.innerHTML = `
                    <div class="civitai-status-panel">
                        <div id="civitai-stats-checkpoints">📈 Checkpoints in DB: Loading... <a href="#" class="view-list-link" data-type="checkpoints">[View List]</a></div>
                        <div id="civitai-stats-loras">📈 LoRAs in DB: Loading... <a href="#" class="view-list-link" data-type="loras">[View List]</a></div>
                    </div>
                    <div class="civitai-settings-grid">
                        <button id="civitai-rescan-checkpoints"><div class="civitai-button-content"><span class="civitai-button-title">🔄 Force Rescan Checkpoints</span><span class="civitai-button-desc">Scan for new or modified files.</span></div></button>
                        <button id="civitai-rehash-checkpoints" class="danger"><div class="civitai-button-content"><span class="civitai-button-title">💥 Re-Hash All Checkpoints</span><span class="civitai-button-desc">Force re-calculation for ALL files. Slow!</span></div></button>
                        <button id="civitai-rescan-loras"><div class="civitai-button-content"><span class="civitai-button-title">🔄 Force Rescan LoRAs</span><span class="civitai-button-desc">Scan for new or modified files.</span></div></button>
                        <button id="civitai-rehash-loras" class="danger"><div class="civitai-button-content"><span class="civitai-button-title">💥 Re-Hash All LoRAs</span><span class="civitai-button-desc">Force re-calculation for ALL files. Slow!</span></div></button>
                    </div>
                    <hr class="civitai-separator">
                    <p class="civitai-settings-widget-desc">Clear specific cached data from the database.</p>
                    <div class="civitai-settings-grid">
                         <button id="civitai-clear-analysis"><div class="civitai-button-content"><span class="civitai-button-title">🧹 Clear Analyzer Cache</span><span class="civitai-button-desc">Removes saved analysis reports.</span></div></button>
                         <button id="civitai-clear-api"><div class="civitai-button-content"><span class="civitai-button-title">☁️ Clear API Response Cache</span><span class="civitai-button-desc">Removes cached model info from Civitai.</span></div></button>
                    </div>
                `;

                const updateStats = async () => {
                    try {
                        const response = await api.fetchApi('/civitai_utils/get_db_stats');
                        const data = await response.json();
                        if (data.status === 'ok') {
                            container.querySelector("#civitai-stats-checkpoints").innerHTML = `📈 Checkpoints in DB: <strong>${data.stats.checkpoints}</strong> <a href="#" class="view-list-link" data-type="checkpoints">[View List]</a>`;
                            container.querySelector("#civitai-stats-loras").innerHTML = `📈 LoRAs in DB: <strong>${data.stats.loras}</strong> <a href="#" class="view-list-link" data-type="loras">[View List]</a>`;
                            container.querySelectorAll('.view-list-link').forEach(link => {
                                link.onclick = (e) => { e.preventDefault(); showModelListModal(e.target.dataset.type); };
                            });
                        }
                    } catch (e) {
                        container.querySelector("#civitai-stats-checkpoints").textContent = `📈 Checkpoints in DB: Error`;
                        container.querySelector("#civitai-stats-loras").textContent = `📈 LoRAs in DB: Error`;
                        console.error("[Civitai Utils] Failed to load DB stats:", e);
                    }
                };
                updateStats();

                container.querySelector("#civitai-rescan-checkpoints").onclick = () => createActionModal({ title: "Force Rescan Checkpoints", confirmMessage: "Force a scan for new/modified checkpoint files?", endpoint: '/civitai_utils/force_rescan', body: { model_type: 'checkpoints' }, onSuccess: updateStats });
                container.querySelector("#civitai-rehash-checkpoints").onclick = () => createActionModal({ title: "Re-Hash All Checkpoints", confirmMessage: "WARNING: This will re-calculate hashes for ALL checkpoint files, which can be very slow. Continue?", endpoint: '/civitai_utils/force_rescan', body: { model_type: 'checkpoints', rehash_all: true }, onSuccess: updateStats });
                container.querySelector("#civitai-rescan-loras").onclick = () => createActionModal({ title: "Force Rescan LoRAs", confirmMessage: "Force a scan for new/modified LoRA files?", endpoint: '/civitai_utils/force_rescan', body: { model_type: 'loras' }, onSuccess: updateStats });
                container.querySelector("#civitai-rehash-loras").onclick = () => createActionModal({ title: "Re-Hash All LoRAs", confirmMessage: "WARNING: This will re-calculate hashes for ALL LoRA files, which can be very slow. Continue?", endpoint: '/civitai_utils/force_rescan', body: { model_type: 'loras', rehash_all: true }, onSuccess: updateStats });
                container.querySelector("#civitai-clear-analysis").onclick = () => createActionModal({ title: "Clear Analyzer Cache", confirmMessage: "Are you sure you want to clear the analyzer cache?", endpoint: '/civitai_utils/clear_cache', body: { cache_type: 'analysis' } });
                container.querySelector("#civitai-clear-api").onclick = () => createActionModal({ title: "Clear API Response Cache", confirmMessage: "Are you sure you want to clear the API response cache?", endpoint: '/civitai_utils/clear_cache', body: { cache_type: 'api_responses' } });

                return container;
            }
        });
        //  3. API Key 管理
        app.ui.settings.addSetting({
            id: "CivitaiUtils.ApiKey",
            name: "🔑 API Key Management",
            type: (name, setter, value) => {
                const container = document.createElement("div");
                container.className = "civitai-settings-container";
                container.innerHTML = `
                    <p class="civitai-settings-widget-desc">
                        Providing an API Key from your Civitai account can increase rate limits and access more content. You can create a key from your
                        <a href="https://civitai.com/user/account" target="_blank">account settings page</a>.
                    </p>
                    <div class="civitai-api-key-input-container">
                        <input type="password" id="civitai-api-key-input" placeholder="Paste your API Key here">
                        <button id="civitai-api-key-save-btn">Save Key</button>
                    </div>
                    <span id="civitai-api-key-status" class="civitai-api-key-status"></span>
                `;

                const input = container.querySelector("#civitai-api-key-input");
                const saveBtn = container.querySelector("#civitai-api-key-save-btn");
                const statusSpan = container.querySelector("#civitai-api-key-status");

                // 从后端加载已保存的key（只用于判断是否存在）
                api.fetchApi('/civitai_utils/get_config').then(async (response) => {
                    const config = await response.json();
                    if (config.api_key_exists) {
                        input.placeholder = 'API Key is set. Enter a new key to overwrite.';
                    }
                });

                saveBtn.onclick = async () => {
                    const apiKey = input.value.trim();
                    saveBtn.textContent = 'Saving...';
                    try {
                        await api.fetchApi('/civitai_utils/set_config', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ api_key: apiKey })
                        });
                        statusSpan.textContent = 'API Key saved successfully!';
                        statusSpan.style.color = '#4CAF50';
                        input.value = ''; // 清空输入框
                        input.placeholder = apiKey ? 'API Key is set. Enter a new key to overwrite.': 'Paste your API Key here';
                    } catch (e) {
                        statusSpan.textContent = `Error saving key: ${e.message}`;
                        statusSpan.style.color = '#D9534F';
                    } finally {
                        saveBtn.textContent = 'Save Key';
                        setTimeout(() => { statusSpan.textContent = ''; }, 4000);
                    }
                };
                return container;
            }
        });
        // 4. 网络设置
        const networkSetting = app.ui.settings.addSetting({
            id: "CivitaiUtils.NetworkChoice",
            name: "🌐 Network Endpoint",
            type: "combo",
            defaultValue: "com",
            options: () => [
                { value: "com", text: "International (civitai.com)" },
                { value: "work", text: "China Mirror (civitai.work)" },
            ],
            async onChange(value) {
                try {
                    await api.fetchApi('/civitai_utils/set_config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ network_choice: value })
                    });
                } catch (e) {
                    console.error("[Civitai Utils] Failed to save network choice:", e);
                }
            },
        });

        // --- 全局样式 ---
        if (!document.getElementById('civitai-settings-styles')) {
            const style = document.createElement('style');
            style.id = 'civitai-settings-styles';
            style.textContent = `
                .civitai-settings-container { display: flex; flex-direction: column; gap: 15px; width: 100%; }
                .civitai-settings-widget-desc { font-size: 12px; color: var(--desc-text-color); opacity: 0.8; margin: 0 0 5px 0; }
                .civitai-settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
                #setting-CivitaiUtils-Migration button, .civitai-settings-grid button { font-family: sans-serif; background-color: var(--comfy-input-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; cursor: pointer; transition: all 0.2s ease; text-align: left; height: 100%; }
                #setting-CivitaiUtils-Migration button:hover, .civitai-settings-grid button:hover { background-color: var(--comfy-input-bg-hover); border-color: var(--desc-text-color); }
                .civitai-button-content { display: flex; flex-direction: column; gap: 4px; }
                .civitai-button-title { font-size: 13px; font-weight: bold; color: var(--fg-color); }
                .civitai-button-desc { font-size: 11px; color: var(--desc-text-color); opacity: 0.8; white-space: normal; }
                .civitai-settings-grid button.success, #setting-CivitaiUtils-Migration button.success, .danger-zone button.success { background-color: rgba(76, 175, 80, 0.3) !important; border-color: #4CAF50 !important; }
                .civitai-settings-grid button.error, #setting-CivitaiUtils-Migration button.error, .danger-zone button.error { background-color: rgba(217, 83, 79, 0.3) !important; border-color: #D9534F !important; }
                .civitai-separator { border: none; border-top: 1px solid var(--border-color); margin: 10px 0; }
                .danger-zone button.danger { border-color: rgba(217, 83, 79, 0.5); }
                .danger-zone button.danger:hover { background-color: #D9534F; border-color: #D9534F; }
                .danger-zone button.danger:hover .civitai-button-title, .danger-zone button.danger:hover .civitai-button-desc { color: white; }
                .civitai-status-panel { display: flex; flex-wrap: wrap; gap: 10px 20px; background-color: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; font-size: 13px; color: var(--desc-text-color); }
                .civitai-status-panel a { color: var(--link-color, #4a90e2); text-decoration: none; font-size: 11px; margin-left: 5px; }
                .civitai-status-panel a:hover { text-decoration: underline; }
                .civitai-modal { display: none; position: fixed; z-index: 10001; left: 0; top: 0; width: 100%; height: 100%; overflow: auto; background-color: rgba(0,0,0,0.7); justify-content: center; align-items: center; }
                .civitai-modal-content { background-color: var(--comfy-menu-bg); margin: auto; padding: 25px; border: 1px solid var(--border-color); border-radius: 8px; width: 80%; max-width: 700px; position: relative; box-shadow: 0 5px 15px rgba(0,0,0,0.5); }
                .civitai-modal-close { color: #aaa; position: absolute; top: 10px; right: 15px; font-size: 28px; font-weight: bold; cursor: pointer; }
                .civitai-modal-close:hover { color: var(--fg-color); }
                .civitai-modal-body p { margin: 10px 0; }
                .civitai-modal-footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
                .civitai-button { font-family: sans-serif; font-size: 13px; padding: 8px 15px; border-radius: 5px; border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s ease; }
                .civitai-button.confirm { background-color: var(--comfy-button-bg); color: var(--comfy-button-fg); }
                .civitai-button.confirm:hover { background-color: #4CAF50; color: white; border-color: #4CAF50;}
                .civitai-button.cancel { background-color: var(--comfy-input-bg); color: var(--input-text-color); }
                .civitai-button.cancel:hover { background-color: #a0a0a0; color: black; }
                .civitai-loader { border: 4px solid #f3f3f3; border-radius: 50%; border-top: 4px solid #3498db; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                .civitai-modal-list-container { max-height: 70vh; overflow-y: auto; background: var(--comfy-input-bg); padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px; }
                .civitai-modal-list-container ul { list-style: none; padding: 0; margin: 0; }
                .civitai-modal-list-container li { padding: 3px 5px; border-bottom: 1px solid var(--border-color); }
                .civitai-modal-list-container li:last-child { border-bottom: none; }
                .civitai-api-key-input-container { display: flex; gap: 10px; }
                #civitai-api-key-input { flex-grow: 1; }
                #civitai-api-key-save-btn { flex-shrink: 0; }
                .civitai-api-key-status { font-size: 12px; margin-top: 5px; }
            `;
            document.head.appendChild(style);
        }

        // 从后端加载网络设置
        try {
            const response = await api.fetchApi('/civitai_utils/get_config');
            const config = await response.json();
            if (config.network_choice && networkSetting) {
                networkSetting.value = config.network_choice;
            }
        } catch (e) {
            console.warn("[Civitai Utils] Could not load saved config, using default.", e);
        }
    }
});