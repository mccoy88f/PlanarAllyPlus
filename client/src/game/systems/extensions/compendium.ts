import MarkdownIt from "markdown-it";
import { ref } from "vue";

import { http } from "../../../core/http";

import { extensionsState } from "./state";

/** Segmenti path dopo `qe:`: lo slug voce può contenere `/` (es. `5.5e/creatura`). */
export interface QePathParts {
    compSlug: string | undefined;
    collectionSlug: string;
    itemSlug: string;
}

/** True se il primo segmento è un compendio noto (mappa API) o id compendio (UUID / id corto). */
function isCompendiumFirstSegment(seg: string): boolean {
    const map = extensionsState.raw.compendiumSlugToId;
    const k = seg.toLowerCase();
    if (map[k] || map[seg]) return true;
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(seg)) return true;
    if (/^[0-9a-f]{8}$/i.test(seg)) return true;
    return false;
}

/**
 * Spezza `rest` (path dopo `qe:`) in comp / collezione / slug voce.
 * - 4+ segmenti: sempre `comp/coll/voce/con/slash/...`.
 * - 3 segmenti: se il primo è un compendio noto → `comp/coll/voce`; altrimenti `coll/voce` con voce = seg2/seg3.
 * - 2 segmenti: `coll/voce` (legacy senza compendio nello slug).
 */
export function parseQePathSegments(rest: string): QePathParts {
    const parts = rest.split("/").filter((p) => p.length > 0);
    if (parts.length === 0) {
        return { compSlug: undefined, collectionSlug: "", itemSlug: "" };
    }
    if (parts.length === 1) {
        return { compSlug: undefined, collectionSlug: "", itemSlug: parts[0]! };
    }
    if (parts.length === 2) {
        return { compSlug: undefined, collectionSlug: parts[0]!, itemSlug: parts[1]! };
    }
    if (parts.length >= 4) {
        return {
            compSlug: parts[0]!,
            collectionSlug: parts[1]!,
            itemSlug: parts.slice(2).join("/"),
        };
    }
    /* 3 segmenti */
    if (isCompendiumFirstSegment(parts[0]!)) {
        return {
            compSlug: parts[0]!,
            collectionSlug: parts[1]!,
            itemSlug: parts[2]!,
        };
    }
    return {
        compSlug: undefined,
        collectionSlug: parts[0]!,
        itemSlug: parts.slice(1).join("/"),
    };
}

/** Plugin markdown-it: link qe: → href="#" con data attributes (nasconde qe: in barra stato). */
export function qeLinkPlugin(md: MarkdownIt): void {
    const defaultRender =
        md.renderer.rules.link_open ??
        ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
    md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
        const href = tokens[idx]?.attrGet("href") ?? "";
        if (href.startsWith("qe:")) {
            const rest = href.slice(3);
            const { compSlug, collectionSlug, itemSlug } = parseQePathSegments(rest);
            tokens[idx]?.attrSet("href", "#");
            if (compSlug) tokens[idx]?.attrSet("data-qe-compendium", compSlug);
            tokens[idx]?.attrSet("data-qe-collection", collectionSlug);
            tokens[idx]?.attrSet("data-qe-slug", itemSlug);
            tokens[idx]?.attrSet("class", "qe-internal-link");
        }
        return defaultRender(tokens, idx, options, env, self);
    };
}

export interface QeNameEntry {
    name: string;
    compendiumSlug?: string;
    collectionSlug: string;
    itemSlug: string;
}

const namesCache = ref<QeNameEntry[] | null>(null);

export async function getQeNames(compendiumId?: string): Promise<QeNameEntry[]> {
    const cacheKey = compendiumId ?? "default";
    if (namesCache.value && namesCache.value.length > 0 && !compendiumId) return namesCache.value;
    try {
        const url = compendiumId
            ? `/api/extensions/compendium/names?compendium=${encodeURIComponent(compendiumId)}`
            : "/api/extensions/compendium/names";
        const r = await http.get(url);
        if (r.ok) {
            const data = (await r.json()) as { names: QeNameEntry[] };
            if (!compendiumId) namesCache.value = data.names;
            return data.names;
        }
    } catch {
        /* ignore */
    }
    return [];
}

/** Invalida la cache dei nomi (es. dopo install/disinstall compendio). */
export function invalidateQeNamesCache(): void {
    namesCache.value = null;
    extensionsState.mutableReactive.compendiumSlugToId = {};
    extensionsState.mutableReactive.compendiumDefaultId = undefined;
}

let resolverMapLoadPromise: Promise<void> | null = null;

/** Aggiorna slug→UUID dalla risposta GET compendiums (evita doppia richiesta se già caricato dal modale). */
export function applyCompendiumResolverMap(
    compendiums: { id: string; slug: string }[],
    defaultId: string | null | undefined,
): void {
    const map: Record<string, string> = {};
    for (const c of compendiums) {
        if (c.id && c.slug) {
            map[c.slug.toLowerCase()] = c.id;
            map[c.id] = c.id;
        }
    }
    extensionsState.mutableReactive.compendiumSlugToId = map;
    extensionsState.mutableReactive.compendiumDefaultId = defaultId ?? undefined;
}

/** Carica mappa slug→id per anteprima tooltip (chat, link qe: con slug server). */
export async function loadCompendiumResolverMap(): Promise<void> {
    if (Object.keys(extensionsState.raw.compendiumSlugToId).length > 0) return;
    if (resolverMapLoadPromise) return resolverMapLoadPromise;
    resolverMapLoadPromise = (async () => {
        try {
            const r = await http.get("/api/extensions/compendium/compendiums");
            if (!r.ok) return;
            const data = (await r.json()) as {
                compendiums: { id: string; slug: string }[];
                defaultId: string | null;
            };
            applyCompendiumResolverMap(data.compendiums ?? [], data.defaultId);
        } finally {
            resolverMapLoadPromise = null;
        }
    })();
    return resolverMapLoadPromise;
}

/** Parametro `compendium` per GET /api/extensions/compendium/item (preferisce UUID da slug→id). */
export function resolveCompendiumIdForItemQuery(compFromLink: string | undefined): string | undefined {
    const ctx = extensionsState.reactive.compendiumPreviewContext;
    const link = compFromLink?.trim();
    const map = extensionsState.reactive.compendiumSlugToId;
    const defaultId = extensionsState.reactive.compendiumDefaultId;

    if (ctx?.compendiumId) {
        if (!link || link === ctx.compendiumSlug || link === ctx.compendiumId) {
            return ctx.compendiumId;
        }
    }
    if (link) {
        const m = map[link] ?? map[link.toLowerCase()];
        if (m) return m;
        if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(link)) return link;
        return undefined;
    }
    return ctx?.compendiumId ?? defaultId;
}

const MARKDOWN_LINK = /\[([^\]]*)\]\(([^)]*)\)/g;
const QE_LINK = /\[([^\]]*)\]\(\s*qe:([^)]+)\s*\)/gi;
/** Solo path "puliti" (slug validi): niente [, ], ( - evita di matchare link annidati/malformati */
const QE_LINK_CLEAN = /\[([^\]]*)\]\(\s*qe:([a-zA-Z0-9_\-\/.]+)\s*\)/gi;


const qeMarkdownRenderer = (() => {
    const md = new MarkdownIt({ html: true });
    md.use(qeLinkPlugin);
    return md;
})();

/**
 * Ripara heading spezzati nell'export quintaedizione (es. "Incantesimi del Circolo della" + "Terra"
 * invece di "Incantesimi del Circolo della Terra"). Il bug dell'export spezza titoli con " della ".
 */
function repairSplitHeadings(md: string): string {
    if (!md) return md;
    /* Pattern: ### X della (Livello N) seguito da ### Y (Livello 0) → unisci in ### X della Y (Livello N) */
    return md.replace(
        /(### ([^\n#]+) della) \((Livello \d+)\)\s*\n+\s*### ([^\n#]+) \(Livello 0\)/g,
        (_, prefix, _x, level, y) => `${prefix} ${y} (${level})`,
    );
}

/** Render markdown con link qe: convertiti in HTML cliccabili. Usa preprocess + markdown-it invece di VueMarkdown per evitare rendering grezzo. */
export function renderQeMarkdown(source: string): string {
    if (!source) return "";
    const repaired = repairSplitHeadings(source);
    return qeMarkdownRenderer.render(preprocessQeLinksToHtml(repaired));
}

/**
 * Imposta `data-qe-compendium` sugli anchor `qe-internal-link` che non hanno un compendio (link legacy `qe:coll/slug`).
 * L'API anteprima usa il default server se manca; in multi-compendio aprendo una voce non-default si ottiene 404 e il tooltip sparisce subito.
 */
export function ensureQeLinksCompendiumContext(html: string, compendiumSlug: string | undefined): string {
    const slug = compendiumSlug?.trim();
    if (!html || !slug) return html;
    if (typeof DOMParser === "undefined") return html;
    try {
        const doc = new DOMParser().parseFromString(`<div id="__qe_ctx">${html}</div>`, "text/html");
        const root = doc.getElementById("__qe_ctx");
        if (!root) return html;
        root.querySelectorAll("a.qe-internal-link").forEach((a) => {
            const cur = a.getAttribute("data-qe-compendium");
            if (!cur?.trim()) {
                a.setAttribute("data-qe-compendium", slug);
            }
        });
        return root.innerHTML;
    } catch {
        return html;
    }
}

/** Converte link markdown [text](qe:path) in HTML prima del rendering. Evita che markdown-it non li riconosca.
 * Processa iterativamente solo link con path "puliti" (slug validi), così i link annidati vengono gestiti
 * dall'interno verso l'esterno. Path malformati (con [, ], () vengono poi sostituiti con il solo testo del link. */
export function preprocessQeLinksToHtml(text: string): string {
    if (!text) return text;
    const esc = (s: string) =>
        String(s ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/"/g, "&quot;");
    const replaceOne = (str: string) =>
        str.replace(QE_LINK_CLEAN, (_, linkText, path) => {
            const { compSlug, collectionSlug, itemSlug } = parseQePathSegments(path);
            const comp = compSlug ? esc(compSlug) : "";
            const coll = esc(collectionSlug);
            const slug = esc(itemSlug);
            let attrs = `href="#" data-qe-collection="${coll}" data-qe-slug="${slug}" class="qe-internal-link"`;
            if (comp) attrs = `data-qe-compendium="${comp}" ${attrs}`;
            return `<a ${attrs}>${esc(linkText)}</a>`;
        });
    let result = text;
    let prev: string;
    do {
        prev = result;
        result = replaceOne(result);
    } while (prev !== result);
    /* Link con path malformato (es. path contiene markup annidato): non crearli, mostra solo il testo */
    result = result.replace(QE_LINK, (_, linkText) => linkText);
    return result;
}

function buildQeLink(entry: QeNameEntry): string {
    if (entry.compendiumSlug) {
        return `[${entry.name}](qe:${entry.compendiumSlug}/${entry.collectionSlug}/${entry.itemSlug})`;
    }
    return `[${entry.name}](qe:${entry.collectionSlug}/${entry.itemSlug})`;
}

/**
 * Inietta link qe: nel testo dove appaiono nomi dal DB.
 * Formato link: qe:compendiumSlug/collectionSlug/itemSlug (se multi-compendium) o qe:collectionSlug/itemSlug (legacy).
 * @param excludeNames - nomi da non linkare (es. titolo della scheda corrente)
 */
export function injectQeLinks(
    text: string,
    names: QeNameEntry[],
    excludeNames?: string[],
): string {
    if (!names.length) return text;
    /* Ordina per lunghezza decrescente: frasi più lunghe prima, così "Tiro Salvezza"
     * viene linkata prima di "Tiro" e non viene spezzata/corrupta. */
    const sorted = [...names].sort((a, b) => (b.name?.length ?? 0) - (a.name?.length ?? 0));
    const exclude = new Set((excludeNames ?? []).map((n) => n.toLowerCase().trim()).filter(Boolean));

    /* ── Step 1: salva i link markdown già presenti nel testo ────────────── */
    const existingLinks: string[] = [];
    const withoutLinks = text.replace(MARKDOWN_LINK, (_, linkText, url) => {
        existingLinks.push(`[${linkText}](${url})`);
        return `\x00QEL\x00`;
    });

    let result = withoutLinks;

    /* ── Step 2: inietta link tra virgolette e parentesi ─────────────────── */
    for (const entry of sorted) {
        if (exclude.has(entry.name.toLowerCase().trim())) continue;
        const escaped = entry.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const link = buildQeLink(entry);
        result = result.replace(new RegExp(`"(${escaped})"`, "gi"), () => `"${link}"`);
        result = result.replace(new RegExp(`\\((${escaped})\\)`, "gi"), () => `(${link})`);
    }

    /* ── Step 3: proteggi tutti i link qe: già esistenti (step 2 + originali)
     *  come placeholder indicizzati, così il loop successivo non li tocca ── */
    const protectedLinks: string[] = [];
    const LINK_PLACEHOLDER = (i: number) => `\x02QELINK${i}\x03`;
    result = result.replace(QE_LINK, (m) => {
        const idx = protectedLinks.length;
        protectedLinks.push(m);
        return LINK_PLACEHOLDER(idx);
    });

    /* ── Step 4: inietta link nel testo libero (word-boundary), dal più lungo ──
     *  Dopo ogni sostituzione, protegge subito i nuovi link così le iterazioni
     *  successive con termini più corti non entrano dentro link già creati. ── */
    for (const entry of sorted) {
        if (exclude.has(entry.name.toLowerCase().trim())) continue;
        const escaped = entry.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const re = new RegExp(`\\b(${escaped})\\b`, "gi");
        const link = buildQeLink(entry);

        let replaced = false;
        result = result.replace(re, (_match) => {
            replaced = true;
            return link;
        });

        /* Se abbiamo creato nuovi link, proteggili subito come placeholder */
        if (replaced) {
            result = result.replace(QE_LINK, (m) => {
                const i = protectedLinks.length;
                protectedLinks.push(m);
                return LINK_PLACEHOLDER(i);
            });
        }
    }

    /* ── Step 5: ripristina tutti i link protetti ────────────────────────── */
    result = result.replace(/\x02QELINK(\d+)\x03/g, (_, i) => protectedLinks[Number(i)] ?? "");

    /* ── Step 6: ripristina i link originali del testo ───────────────────── */
    let idx = 0;
    return result.replace(/\x00QEL\x00/g, () => existingLinks[idx++] ?? "");
}

