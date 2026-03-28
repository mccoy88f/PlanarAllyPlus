import MarkdownIt from "markdown-it";

import { preprocessQeLinksToHtml } from "../extensions/compendium";

export const chatMarkDown = new MarkdownIt({ linkify: true, html: true });

chatMarkDown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const href = tokens[idx]?.attrGet("href") ?? "";
    if (href.startsWith("qe:")) {
        const rest = href.slice(3);
        const parts = rest.split("/");

        let compendium = "";
        let collection = "";
        let slug = "";

        if (parts.length >= 3) {
            compendium = parts[0] ?? "";
            collection = parts[1] ?? "";
            slug = parts[2] ?? "";
        } else {
            collection = parts[0] ?? "";
            slug = parts[1] ?? "";
        }

        tokens[idx]?.attrSet("href", "#");
        if (compendium) tokens[idx]?.attrSet("data-qe-compendium", compendium);
        tokens[idx]?.attrSet("data-qe-collection", collection);
        tokens[idx]?.attrSet("data-qe-slug", slug);
        tokens[idx]?.attrSet("class", "qe-chat-link qe-internal-link");
    } else if (href.startsWith("doc:")) {
        /* href="#": lo schema doc: non è standard; alcuni browser svuotano o alterano href="doc:…". */
        const rest = href.slice(4).trim();
        const hashIdx = rest.indexOf("#");
        const hashPart = (hashIdx >= 0 ? rest.slice(0, hashIdx) : rest).trim();
        if (hashIdx >= 0) {
            const fragment = rest.slice(hashIdx + 1);
            const pageMatch = /page=(\d+)/i.exec(fragment);
            if (pageMatch) tokens[idx]?.attrSet("data-doc-page", pageMatch[1]!);
        }
        tokens[idx]?.attrSet("href", "#");
        tokens[idx]?.attrSet("data-doc-hash", hashPart);
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
