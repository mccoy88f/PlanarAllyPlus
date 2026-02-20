import MarkdownIt from "markdown-it";

import { preprocessQeLinksToHtml } from "../extensions/compendium";

export const chatMarkDown = new MarkdownIt({ linkify: true, html: true });

chatMarkDown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const href = tokens[idx]?.attrGet("href") ?? "";
    if (href.startsWith("qe:")) {
        const rest = href.slice(3);
        const slashIdx = rest.indexOf("/");
        const collection = slashIdx > 0 ? rest.slice(0, slashIdx) : rest;
        const slug = slashIdx > 0 ? rest.slice(slashIdx + 1) : "";
        tokens[idx]?.attrSet("href", "#");
        tokens[idx]?.attrSet("data-qe-collection", collection);
        tokens[idx]?.attrSet("data-qe-slug", slug);
        tokens[idx]?.attrSet("class", "qe-chat-link qe-internal-link");
    } else if (href.startsWith("doc:")) {
        tokens[idx]?.attrSet("class", "doc-chat-link");
    } else {
        tokens[idx]?.attrSet("target", "_blank");
    }
    return self.renderToken(tokens, idx, options);
};

/** Render con preprocess per convertire [text](qe:path) in HTML (markdown-it può non riconoscerli). */
export function renderChatMarkdown(source: string): string {
    return chatMarkDown.render(preprocessQeLinksToHtml(source));
}
