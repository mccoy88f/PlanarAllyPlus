/**
 * Merge dell’indice compendio: overlay traduzioni e preservazione tra passate AI.
 */

export interface IndexCollNode {
    slug: string;
    name: string;
    items: { slug: string; name: string }[];
    collections?: IndexCollNode[];
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
    if (!overlay?.length) {
        return JSON.parse(JSON.stringify(canonical)) as IndexCollNode[];
    }
    const overlayBySlug = new Map<string, IndexCollNode>();
    function collectOverlay(nodes: IndexCollNode[]): void {
        for (const n of nodes) {
            overlayBySlug.set(n.slug, n);
            if (n.collections?.length) collectOverlay(n.collections);
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

function pickName(canonName: string, afterAiName: string, priorName: string): string {
    const c = canonName.trim();
    const a = afterAiName.trim();
    const p = priorName.trim();
    if (a !== c) return afterAiName;
    if (p !== c) return priorName;
    return afterAiName;
}

/**
 * Dopo mergeIndexNameOverlay(canonical, aiParsed), ripristina i nomi già tradotti
 * in `prior` quando il merge AI coincide col canonico (modello che ristampa l’inglese
 * o ramo assente dall’overlay), così una seconda traduzione su un sotto-ramo non
 * azzera i fratelli già tradotti.
 */
export function mergeIndexPreservePriorSubtree(
    canon: IndexCollNode,
    afterAi: IndexCollNode,
    prior: IndexCollNode,
): IndexCollNode {
    const name = pickName(canon.name, afterAi.name, prior.name);
    const items = canon.items.map((cit) => {
        const ait = afterAi.items.find((x) => x.slug === cit.slug);
        const pit = prior.items.find((x) => x.slug === cit.slug);
        const aName = ait?.name ?? cit.name;
        const pName = pit?.name ?? cit.name;
        return { slug: cit.slug, name: pickName(cit.name, aName, pName) };
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

export function mergeIndexPreservePriorRoots(
    canon: IndexCollNode[],
    afterAi: IndexCollNode[],
    prior: IndexCollNode[],
): IndexCollNode[] {
    return canon.map((c, i) => mergeIndexPreservePriorSubtree(c, afterAi[i]!, prior[i]!));
}
