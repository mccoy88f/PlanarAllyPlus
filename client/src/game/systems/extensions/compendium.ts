import MarkdownIt from "markdown-it";
import { ref } from "vue";

import { http } from "../../../core/http";

/** Plugin markdown-it: link qe: → href="#" con data attributes (nasconde qe: in barra stato). */
export function qeLinkPlugin(md: MarkdownIt): void {
    const defaultRender =
        md.renderer.rules.link_open ??
        ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options));
    md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
        const href = tokens[idx]?.attrGet("href") ?? "";
        if (href.startsWith("qe:")) {
            const rest = href.slice(3);
            const parts = rest.split("/");
            const compSlug = parts.length >= 3 ? parts[0] : "";
            const collSlug = parts.length >= 3 ? parts[1] : parts[0] ?? "";
            const itemSlug = parts.length >= 3 ? parts[2] ?? "" : parts[1] ?? "";
            tokens[idx]?.attrSet("href", "#");
            tokens[idx]?.attrSet("data-qe-compendium", compSlug);
            tokens[idx]?.attrSet("data-qe-collection", collSlug);
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
            const parts = path.split("/");
            const comp = parts.length >= 3 ? esc(parts[0]!) : "";
            const coll = parts.length >= 3 ? esc(parts[1]!) : esc(parts[0] ?? "");
            const slug = parts.length >= 3 ? esc(parts[2]!) : esc(parts[1] ?? "");
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

