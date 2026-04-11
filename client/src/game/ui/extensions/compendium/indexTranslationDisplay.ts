/**
 * Logica unica per l’indice “come mostrato” rispetto alle traduzioni:
 * merge JSON indice + titoli ricavati dalle traduzioni voce (`type=item`).
 * Evita che voci tradotte singolarmente risultino “non tradotte” nell’albero.
 */

import {
    findIndexNodeBySlug,
    indexRootsTranslationState,
    mergeIndexNameOverlay,
    patchItemDisplayNameInIndexTree,
    type IndexCollNode,
} from "./indexTree";

export function compendiumItemTitleKey(collectionSlug: string, itemSlug: string): string {
    return `${collectionSlug}::${itemSlug}`;
}

export function parseCompendiumItemTitleKey(key: string): { collectionSlug: string; itemSlug: string } | null {
    const i = key.lastIndexOf("::");
    if (i <= 0) return null;
    return { collectionSlug: key.slice(0, i), itemSlug: key.slice(i + 2) };
}

/** Applica i titoli voce del manifest API sull’albero già fuso (indice JSON + eventuale prior in memoria). */
export function applySavedItemTitlesToIndexTree(
    mergedTree: IndexCollNode[],
    canonical: IndexCollNode[],
    titles: ReadonlyMap<string, string>,
): IndexCollNode[] {
    let result = mergedTree;
    for (const [key, title] of titles) {
        const p = parseCompendiumItemTitleKey(key);
        if (!p) continue;
        const t = title.trim();
        if (!t) continue;
        const coll = findIndexNodeBySlug(canonical, p.collectionSlug);
        const cit = coll?.items.find((x) => x.slug === p.itemSlug);
        const canonName = cit?.name?.trim() ?? "";
        if (t === canonName) continue;
        result = patchItemDisplayNameInIndexTree(result, p.collectionSlug, p.itemSlug, t);
    }
    return result;
}

/**
 * Overlay da usare per display e per `indexRootsTranslationState` / pallini capitolo:
 * partendo dall’albero già mergiato con la traduzione indice (se presente), applica i titoli voce salvati.
 * `null` se non c’è alcuna differenza rispetto al canonico.
 */
export function finalizeIndexOverlayWithItemTitles(
    canonical: IndexCollNode[],
    baseMergedTree: IndexCollNode[] | null,
    itemTitles: ReadonlyMap<string, string>,
): IndexCollNode[] | null {
    if (canonical.length === 0) return null;
    const mergedStart = baseMergedTree ?? mergeIndexNameOverlay(canonical, null);
    const withItems = applySavedItemTitlesToIndexTree(mergedStart, canonical, itemTitles);
    return indexRootsTranslationState(canonical, withItems) === "none" ? null : withItems;
}
