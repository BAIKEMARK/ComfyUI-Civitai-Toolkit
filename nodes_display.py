from markdown_it import MarkdownIt


class MarkdownPresenter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {"forceInput": True, "multiline": True, "default": ""},
                ),
            },
        }

    RETURN_TYPES = ()
    FUNCTION = "execute"
    OUTPUT_NODE = True
    CATEGORY = "Display"

    def execute(self, text, title=None):
        parts = []
        if title and title.strip():
            parts.append(f"# {title.strip()}")
        if text and text.strip():
            parts.append(text)
        md_text = "\n\n".join(parts)

        md = MarkdownIt("commonmark", {"html": True}).enable("table")

        def link_open_renderer(self, tokens, idx, options, env):
            # 为链接令牌添加 target 和 rel 属性
            tokens[idx].attrSet("target", "_blank")
            tokens[idx].attrSet("rel", "noopener noreferrer")

            return self.renderToken(tokens, idx, options, env)

        md.renderer.rules["link_open"] = link_open_renderer.__get__(md.renderer)

        html = md.render(md_text)

        return {"ui": {"rendered_html": [html]}}


NODE_CLASS_MAPPINGS = {"MarkdownPresenter": MarkdownPresenter}
NODE_DISPLAY_NAME_MAPPINGS = {"MarkdownPresenter": "Markdown Presenter"}
