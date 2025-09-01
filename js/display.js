import { app } from "/scripts/app.js";

function injectGlobalStyles() {
    const STYLE_ID = "markdown-presenter-styles";
    if (document.getElementById(STYLE_ID)) return;

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
.markdown-presenter-wrapper {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    padding: 10px;
    box-sizing: border-box;
    background: #282828;
    border-radius: 5px;
    color: #ccc;
    font-family: sans-serif;
    line-height: 1.6;
}
.markdown-presenter-wrapper h1, .markdown-presenter-wrapper h2, .markdown-presenter-wrapper h3 { color: #e0e0e0; border-bottom: 1px solid #444; padding-bottom: 5px; margin-top: 1em; margin-bottom: 0.5em; }
.markdown-presenter-wrapper code { background: #1e1e1e; padding: 2px 5px; border-radius: 3px; font-family: monospace; color: #ffb871; }
.markdown-presenter-wrapper pre { background: #1e1e1e; padding: 10px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }
.markdown-presenter-wrapper pre code { padding: 0; background: none; }
.markdown-presenter-wrapper a { color: #68a2ff; text-decoration: none; }
.markdown-presenter-wrapper a:hover { text-decoration: underline; }
.markdown-presenter-wrapper ul, .markdown-presenter-wrapper ol { padding-left: 20px; }
.markdown-presenter-wrapper table { border-collapse: collapse; width: 100%; margin: 1em 0; }
.markdown-presenter-wrapper th, .markdown-presenter-wrapper td { border: 1px solid #444; padding: 8px; text-align: left; }
.markdown-presenter-wrapper th { background-color: #333; }
    `;
    document.head.appendChild(style);
}

app.registerExtension({
    name: "Comfy.MarkdownPresenter",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "MarkdownPresenter") return;

        injectGlobalStyles();

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            originalOnNodeCreated?.apply(this, arguments);

            const container = document.createElement("div");
            container.className = "markdown-presenter-wrapper";

            const contentDiv = document.createElement("div");
            container.appendChild(contentDiv);

            const updateContent = (html) => {
                contentDiv.innerHTML = html || "<em>(empty)</em>";
            };

            updateContent("<em>Waiting for input...</em>");

            this.addDOMWidget("markdown-presenter", "div", container, {});

            const originalOnExecuted = this.onExecuted;
            this.onExecuted = function (output) {
                originalOnExecuted?.apply(this, arguments);

                const html = output?.ui?.rendered_html?.[0] || output?.rendered_html?.[0];

                if (html) {
                    updateContent(html);
                }
            };

            this.size = [400, 250];
            this.resizable = true;

            const originalOnResize = this.onResize;
            this.onResize = function(size) {
                originalOnResize?.apply(this, arguments);
                const contentHeight = size[1] - 32;
                if (contentHeight > 0) {
                    container.style.height = `${contentHeight}px`;
                }
            };
        };
    },
});