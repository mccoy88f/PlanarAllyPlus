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
