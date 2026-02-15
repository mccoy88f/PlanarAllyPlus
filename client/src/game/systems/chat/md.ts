import MarkdownIt from "markdown-it";

export const chatMarkDown = new MarkdownIt({ linkify: true });

chatMarkDown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const href = tokens[idx]?.attrGet("href") ?? "";
    if (href.startsWith("qe:")) {
        tokens[idx]?.attrSet("class", "qe-chat-link");
    } else if (href.startsWith("doc:")) {
        tokens[idx]?.attrSet("class", "doc-chat-link");
    } else {
        tokens[idx]?.attrSet("target", "_blank");
    }
    return self.renderToken(tokens, idx, options);
};
