import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";


const settingId = "CivitaiUtils.NetworkChoice";

const settingName = "Civitai Helper Network";

app.registerExtension({
    name: "Comfy.CivitaiUtils.Settings",

    async setup() {

        const setting = app.ui.settings.addSetting({
            id: settingId,
            name: settingName,
            type: "combo",
            defaultValue: "com",
            // 下拉菜单的选项
            options: (value) => [
                { value: "com", text: "International (civitai.com)" },
                { value: "work", text: "China Mirror (civitai.work)" },
            ],
            // 当用户更改选项时，此函数会被调用
            async onChange(value) {
                try {
                    console.log(`[Civitai Utils] Saving network choice: ${value}`);
                    // (调用后端 API 来保存新设置)
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

        // 当 App 启动时，从后端加载已保存的设置
        try {
            const response = await api.fetchApi('/civitai_recipe_finder/get_config');
            const config = await response.json();
            if (config.network_choice) {
                setting.value = config.network_choice;
            }
        } catch (e) {
            console.warn("[Civitai Utils] Could not load saved config, using default.", e);
        }
    }
});