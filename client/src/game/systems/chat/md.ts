import MarkdownIt from "markdown-it";

import { parseQePathSegments, preprocessQeLinksToHtml } from "../extensions/compendium";

export const chatMarkDown = new MarkdownIt({ linkify: true, html: true });

chatMarkDown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
    const href = tokens[idx]?.attrGet("href") ?? "";
    if (href.startsWith("qe:")) {
        const rest = href.slice(3);
        const { compSlug, collectionSlug, itemSlug } = parseQePathSegments(rest);

        tokens[idx]?.attrSet("href", "#");
        if (compSlug) tokens[idx]?.attrSet("data-qe-compendium", compSlug);
        tokens[idx]?.attrSet("data-qe-collection", collectionSlug);
        tokens[idx]?.attrSet("data-qe-slug", itemSlug);
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
