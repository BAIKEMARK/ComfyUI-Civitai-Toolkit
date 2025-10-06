import { app } from "/scripts/app.js";

app.registerExtension({
    name: "Civitai.Toolkit.Notifications",
    async setup() {
        console.log("[Civitai Toolkit] Setting up toast notifications listener.");

        // 使用 app.ui.api.addEventListener 来监听后端通过 WebSocket 发送的自定义事件
        // 这是 ComfyUI 扩展与后端实时通信的标准方式
        app.ui.api.addEventListener("scan_started", (event) => {
            const data = event.detail;
            app.extensionManager.toast.add({
                severity: 'info',
                summary: 'Background Scan Started (Civitai Toolkit)',
                detail: data.message,
                life: 5000
            });
        });

        app.ui.api.addEventListener("scan_complete", (event) => {
            const data = event.detail;
            if (data.success) {
                app.extensionManager.toast.add({
                    severity: 'success',
                    summary: 'Scan Complete! (Civitai Toolkit)',
                    detail: data.message,
                    life: 10000
                });
            } else {
                app.extensionManager.toast.add({
                    severity: 'error',
                    summary: 'Scan Failed (Civitai Toolkit)',
                    detail: data.message,
                    life: 15000
                });
            }
        });
    }
});