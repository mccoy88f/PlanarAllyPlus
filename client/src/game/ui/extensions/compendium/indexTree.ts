/**
 * Tipi e funzioni pure per l’albero indice del compendio (merge overlay, ricerca, stato traduzione).
 */

export interface IndexCollNode {
    slug: string;
    name: string;
    items: { slug: string; name: string }[];
    collections?: IndexCollNode[];
}

export function findIndexNodeBySlug(nodes: IndexCollNode[], slug: string): IndexCollNode | null {
    for (const n of nodes) {
        if (n.slug === slug) return n;
        const colls = n.collections;
        if (colls != null && colls.length > 0) {
            const f = findIndexNodeBySlug(colls, slug);
            if (f) return f;
        }
    }
    return null;
}

/** Tutte le voci foglia (slug collezione + slug voce) nell’albero indice mostrato. */
export function collectLeafItemsFromIndexNodes(
    nodes: IndexCollNode[],
): { collectionSlug: string; itemSlug: string; itemName: string }[] {
    const seen = new Set<string>();
    const out: { collectionSlug: string; itemSlug: string; itemName: string }[] = [];
    function walk(nlist: IndexCollNode[]): void {
        for (const n of nlist) {
            for (const it of n.items) {
                const key = `${n.slug}::${it.slug}`;
                if (seen.has(key)) continue;
                seen.add(key);
                out.push({ collectionSlug: n.slug, itemSlug: it.slug, itemName: it.name });
            }
            const colls = n.collections;
            if (colls != null && colls.length > 0) walk(colls);
        }
    }
    walk(nodes);
    return out;
}

export function replaceIndexNodeInTree(roots: IndexCollNode[], focusSlug: string, newNode: IndexCollNode): IndexCollNode[] {
    const clone = JSON.parse(JSON.stringify(roots)) as IndexCollNode[];
    function walk(arr: IndexCollNode[]): boolean {
        for (let i = 0; i < arr.length; i++) {
            const node = arr[i];
            if (!node) continue;
            if (node.slug === focusSlug) {
                arr[i] = newNode;
                return true;
            }
            const subs = node.collections;
            if (subs != null && subs.length > 0 && walk(subs)) return true;
        }
        return false;
    }
    walk(clone);
    return clone;
}

/**
 * Mantiene struttura e slug dell’indice canonico (API) e applica solo i `name`
 * presenti nell’overlay (traduzione salvata, anche parziale o ramo singolo).
 * L’overlay viene indicizzato per slug su tutto l’albero così le traduzioni non
 * si perdono se la nidificazione di `collections` non coincide con il canonico.
 */
export function mergeIndexNameOverlay(
    canonical: IndexCollNode[],
    overlay: IndexCollNode[] | null | undefined,
): IndexCollNode[] {
    if (overlay == null || overlay.length === 0) {
        return JSON.parse(JSON.stringify(canonical)) as IndexCollNode[];
    }
    const overlayBySlug = new Map<string, IndexCollNode>();
    function collectOverlay(nodes: IndexCollNode[]): void {
        for (const n of nodes) {
            overlayBySlug.set(n.slug, n);
            const colls = n.collections;
            if (colls != null && colls.length > 0) collectOverlay(colls);
        }
    }
    collectOverlay(overlay);

    function mergeNode(node: IndexCollNode): IndexCollNode {
        const ov = overlayBySlug.get(node.slug);
        const items = node.items.map((it) => {
            const ovi = ov?.items?.find((x) => x.slug === it.slug);
            return { slug: it.slug, name: ovi ? ovi.name : it.name };
        });
        const out: IndexCollNode = {
            slug: node.slug,
            name: ov?.name ?? node.name,
            items,
        };
        if (node.collections !== undefined) {
            if (node.collections.length === 0) {
                out.collections = [];
            } else {
                out.collections = node.collections.map((child) => mergeNode(child));
            }
        }
        return out;
    }

    return canonical.map((node) => mergeNode(node));
}

function pickTranslatedName(canonName: string, afterAiName: string, priorName: string): string {
    const c = canonName.trim();
    const a = afterAiName.trim();
    const p = priorName.trim();
    if (a !== c) return afterAiName;
    if (p !== c) return priorName;
    return afterAiName;
}

/**
 * Dopo mergeIndexNameOverlay(canonical, aiParsed), ripristina i nomi già tradotti in `prior`
 * quando il merge AI coincide col canonico, così una seconda passata non azzera i fratelli.
 */
export function mergeIndexPreservePriorSubtree(
    canon: IndexCollNode,
    afterAi: IndexCollNode,
    prior: IndexCollNode,
): IndexCollNode {
    const name = pickTranslatedName(canon.name, afterAi.name, prior.name);
    const items = canon.items.map((cit) => {
        const ait = afterAi.items.find((x) => x.slug === cit.slug);
        const pit = prior.items.find((x) => x.slug === cit.slug);
        const aName = ait?.name ?? cit.name;
        const pName = pit?.name ?? cit.name;
        return { slug: cit.slug, name: pickTranslatedName(cit.name, aName, pName) };
    });
    const out: IndexCollNode = { slug: canon.slug, name, items };

    const cc = canon.collections;
    if (cc === undefined) return out;

    if (cc.length === 0) {
        out.collections = [];
        return out;
    }

    out.collections = cc.map((child) => {
        const aChild = afterAi.collections?.find((x) => x.slug === child.slug) ?? child;
        const pChild = prior.collections?.find((x) => x.slug === child.slug) ?? child;
        return mergeIndexPreservePriorSubtree(child, aChild, pChild);
    });
    return out;
}

/**
 * Come mergeIndexPreservePriorSubtree sulle radici, ma abbina per `slug` invece che per indice:
 * l’ordine delle radici in `afterAi` / `prior` può differire da `canon` (es. risposta AI incompleta).
 */
export function mergeIndexPreservePriorRoots(
    canon: IndexCollNode[],
    afterAi: IndexCollNode[],
    prior: IndexCollNode[],
): IndexCollNode[] {
    const afterBySlug = new Map(afterAi.map((n) => [n.slug, n] as const));
    const priorBySlug = new Map(prior.map((n) => [n.slug, n] as const));
    return canon.map((c) => {
        const a = afterBySlug.get(c.slug) ?? c;
        const p = priorBySlug.get(c.slug) ?? c;
        return mergeIndexPreservePriorSubtree(c, a, p);
    });
}

/** Aggiorna il `name` di una voce nell’albero (clone profondo). */
export function patchItemDisplayNameInIndexTree(
    roots: IndexCollNode[],
    collectionSlug: string,
    itemSlug: string,
    displayName: string,
): IndexCollNode[] {
    const clone = JSON.parse(JSON.stringify(roots)) as IndexCollNode[];
    const coll = findIndexNodeBySlug(clone, collectionSlug);
    if (!coll) return clone;
    const idx = coll.items.findIndex((x) => x.slug === itemSlug);
    if (idx === -1) return clone;
    coll.items[idx] = { slug: itemSlug, name: displayName };
    return clone;
}

function cleanMarkdownHeadingContent(raw: string): string {
    let line = raw.trim();
    line = line.replace(/\s*\{#[^}]+\}\s*$/, "").trim();
    line = line.replace(/^\*\*|\*\*$/g, "").trim();
    return line;
}

/**
 * Titolo da usare come nome voce: preferisce un titolo di **livello 1** (`# Titolo`, non `##`).
 * Se manca, usa il primo `##` … `######`. Utile quando l’indice non ha ancora il nome tradotto.
 */
export function extractFirstMarkdownHeading(markdown: string): string | null {
    // Ignora BOM / righe vuote in testa (modelli a volte restituiscono paragrafi prima del #)
    const body = markdown.replace(/^\uFEFF/, "").replace(/^\s*\n+/, "");
    const h1 = body.match(/^#\s+(.+)$/m);
    if (h1?.[1]) {
        const t = cleanMarkdownHeadingContent(h1[1]);
        if (t.length > 0) return t;
    }
    const sub = body.match(/^#{2,6}\s+(.+)$/m);
    if (sub?.[1]) {
        const t = cleanMarkdownHeadingContent(sub[1]);
        if (t.length > 0) return t;
    }
    return null;
}

/** Prima riga non vuota del documento è un H1 (`# …`, non `##`). */
export function markdownDocumentStartsWithH1Line(markdown: string): boolean {
    const norm = markdown.replace(/^\uFEFF/, "").replace(/^\s*\n+/, "");
    const line = (norm.split(/\r?\n/, 1)[0] ?? "").trimEnd();
    if (line.length === 0) return false;
    return line.startsWith("# ") || (line === "#" ? false : /^#\s+\S/.test(line));
}

/** Rimuove la prima riga `# …` e le righe vuote subito dopo (titolo sintetico aggiunto per l’indice). */
export function stripFirstMarkdownH1AndFollowingBlankLines(markdown: string): string {
    const norm = markdown.replace(/^\uFEFF/, "").replace(/^\s*\n+/, "");
    return norm.replace(/^#\s+[^\r\n]*\r?\n(?:\s*\r?\n)*/, "").trimStart();
}

const PA_TITLE_COMMENT = /^\s*<!--\s*pa-compendium-title:([\s\S]*?)\s*-->\s*\n*/i;

/** Metadato invisibile in rendering: titolo tradotto per indice quando il corpo non ha H1 iniziale. */
export function parsePaCompendiumTitleComment(markdown: string): { metaTitle: string | null; rest: string } {
    const norm = markdown.replace(/^\uFEFF/, "");
    const m = norm.match(PA_TITLE_COMMENT);
    if (!m || m.index === undefined) {
        return { metaTitle: null, rest: markdown };
    }
    const metaTitle = m[1].trim().replace(/\s+/g, " ");
    const rest = norm.slice(m.index + m[0].length);
    return { metaTitle: metaTitle.length > 0 ? metaTitle : null, rest };
}

export function prependPaCompendiumTitleComment(title: string, body: string): string {
    const safe = title.trim().replace(/\s+/g, " ").replace(/--/g, "—");
    const b = body.replace(/^\uFEFF/, "").trimStart();
    return `<!-- pa-compendium-title:${safe} -->\n\n${b}`;
}

/** Titolo voce da markdown tradotto: commento persistito o primo heading. */
export function extractItemTranslationDisplayTitle(markdown: string): string | null {
    const { metaTitle } = parsePaCompendiumTitleComment(markdown);
    if (metaTitle != null && metaTitle.length > 0) {
        return metaTitle;
    }
    return extractFirstMarkdownHeading(markdown);
}

/** Rimuove il commento titolo prima del render (non deve apparire nel corpo). */
export function stripPaCompendiumTitleCommentForRender(markdown: string): string {
    const norm = markdown.replace(/^\uFEFF/, "");
    const m = norm.match(PA_TITLE_COMMENT);
    if (!m || m.index === undefined) {
        return markdown;
    }
    return norm.slice(m.index + m[0].length);
}

/**
 * Se il sorgente non aveva H1 iniziale, toglie l’H1 imposto dal modello e salva il titolo nel commento.
 * Se il sorgente aveva già H1, lascia il testo del modello com’è.
 */
export function finalizeTranslatedItemBodyForStorage(originalMarkdown: string, fullAiMarkdown: string): string {
    if (markdownDocumentStartsWithH1Line(originalMarkdown)) {
        return fullAiMarkdown;
    }
    const h1Title = extractFirstMarkdownHeading(fullAiMarkdown);
    const body = stripFirstMarkdownH1AndFollowingBlankLines(fullAiMarkdown);
    if (h1Title != null && h1Title.length > 0) {
        return prependPaCompendiumTitleComment(h1Title, body);
    }
    return body.trimStart();
}

/**
 * True se questo ramo (slug) ha traduzione visibile sul titolo o sulle voci dirette (items) rispetto al canonico.
 * Non risale dalle sotto-collezioni annidate: un padre non tradotto non eredita la spunta dal figlio.
 */
export function isBranchDirectlyTranslated(
    canonicalRoots: IndexCollNode[],
    currentRoots: IndexCollNode[],
    slug: string,
): boolean {
    const canon = findIndexNodeBySlug(canonicalRoots, slug);
    const cur = findIndexNodeBySlug(currentRoots, slug);
    if (!canon || !cur) return false;
    if (canon.name.trim() !== cur.name.trim()) return true;
    for (const cIt of canon.items) {
        const uIt = cur.items.find((x) => x.slug === cIt.slug);
        if (uIt && cIt.name.trim() !== uIt.name.trim()) return true;
    }
    return false;
}

/** Tutti i titoli e le voci nel sotto-albero differiscono dal canonico (traduzione completa del ramo). */
export function indexSubtreeFullyTranslated(canon: IndexCollNode, cur: IndexCollNode): boolean {
    if (canon.name.trim() === cur.name.trim()) return false;
    for (const cIt of canon.items) {
        const uIt = cur.items.find((x) => x.slug === cIt.slug);
        if (!uIt || cIt.name.trim() === uIt.name.trim()) return false;
    }
    const cc = canon.collections ?? [];
    const uc = cur.collections ?? [];
    for (const child of cc) {
        const uChild = uc.find((x) => x.slug === child.slug);
        if (!uChild || !indexSubtreeFullyTranslated(child, uChild)) return false;
    }
    return true;
}

export function isSubtreeFullyTranslatedForSlug(
    canonicalRoots: IndexCollNode[],
    currentRoots: IndexCollNode[],
    slug: string,
): boolean {
    const canon = findIndexNodeBySlug(canonicalRoots, slug);
    const cur = findIndexNodeBySlug(currentRoots, slug);
    if (!canon || !cur) return false;
    return indexSubtreeFullyTranslated(canon, cur);
}

/** Indice globale: ogni radice ha sotto-albero completamente tradotto. */
export function isGlobalIndexFullyTranslatedRoots(
    canonicalRoots: IndexCollNode[],
    currentRoots: IndexCollNode[],
): boolean {
    if (canonicalRoots.length === 0 || currentRoots.length === 0) return false;
    for (const c of canonicalRoots) {
        const u = currentRoots.find((x) => x.slug === c.slug);
        if (!u || !indexSubtreeFullyTranslated(c, u)) return false;
    }
    return true;
}

/** Almeno un nome (titolo, voce o sotto-ramo) differisce dal canonico. */
export function indexSubtreeHasAnyTranslation(canon: IndexCollNode, cur: IndexCollNode): boolean {
    if (canon.name.trim() !== cur.name.trim()) return true;
    for (const cIt of canon.items) {
        const uIt = cur.items.find((x) => x.slug === cIt.slug);
        if (uIt && cIt.name.trim() !== uIt.name.trim()) return true;
    }
    const cc = canon.collections ?? [];
    const uc = cur.collections ?? [];
    for (const child of cc) {
        const uChild = uc.find((x) => x.slug === child.slug);
        if (uChild && indexSubtreeHasAnyTranslation(child, uChild)) return true;
    }
    return false;
}

export type IndexSubtreeTranslationState = "none" | "partial" | "full";

export function indexSubtreeTranslationState(canon: IndexCollNode, cur: IndexCollNode): IndexSubtreeTranslationState {
    if (indexSubtreeFullyTranslated(canon, cur)) return "full";
    if (indexSubtreeHasAnyTranslation(canon, cur)) return "partial";
    return "none";
}

/** Stato dell’indice mostrato (una o più radici): nessuna / parziale / tutto tradotto. */
export function indexRootsTranslationState(
    canonicalRoots: IndexCollNode[],
    currentRoots: IndexCollNode[],
): IndexSubtreeTranslationState {
    if (canonicalRoots.length === 0) return "none";
    if (isGlobalIndexFullyTranslatedRoots(canonicalRoots, currentRoots)) return "full";
    for (const c of canonicalRoots) {
        const u = currentRoots.find((x) => x.slug === c.slug);
        if (!u) continue;
        if (indexSubtreeTranslationState(c, u) !== "none") return "partial";
    }
    return "none";
}

export function findItemNameInIndexTree(
    roots: IndexCollNode[],
    collectionSlug: string,
    itemSlug: string,
): string | null {
    const coll = findIndexNodeBySlug(roots, collectionSlug);
    if (!coll) return null;
    const it = coll.items.find((x) => x.slug === itemSlug);
    return it?.name ?? null;
}

/** L’indice JSON può avere voci/sotto-rami anche se l’API collections non li espone come figli. */
export function indexNodeHasVisibleBranchContent(roots: IndexCollNode[], slug: string): boolean {
    const node = findIndexNodeBySlug(roots, slug);
    if (!node) return false;
    return (node.items?.length ?? 0) > 0 || (node.collections?.length ?? 0) > 0;
}
