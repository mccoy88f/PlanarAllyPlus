import { describe, expect, it } from "vitest";

import {
    findIndexNodeBySlug,
    indexRootsTranslationState,
    indexSubtreeFullyTranslated,
    indexSubtreeHasAnyTranslation,
    isBranchDirectlyTranslated,
    isGlobalIndexFullyTranslatedRoots,
    mergeIndexNameOverlay,
    replaceIndexNodeInTree,
} from "../../../../../src/game/ui/extensions/compendium/indexTree";

describe("indexTree", () => {
    const sample: Parameters<typeof mergeIndexNameOverlay>[0] = [
        {
            slug: "a",
            name: "A",
            items: [{ slug: "i1", name: "Item" }],
            collections: [{ slug: "b", name: "B", items: [] }],
        },
    ];

    it("findIndexNodeBySlug trova radice e figlio", () => {
        expect(findIndexNodeBySlug(sample, "x")).toBeNull();
        expect(findIndexNodeBySlug(sample, "a")?.name).toBe("A");
        expect(findIndexNodeBySlug(sample, "b")?.name).toBe("B");
    });

    it("mergeIndexNameOverlay mantiene slug e applica solo name", () => {
        const merged = mergeIndexNameOverlay(sample, [
            { slug: "a", name: "A'", items: [{ slug: "i1", name: "Item'" }] },
        ]);
        expect(merged[0].name).toBe("A'");
        expect(merged[0].items[0].name).toBe("Item'");
        expect(merged[0].collections?.[0].name).toBe("B");
    });

    it("replaceIndexNodeInTree sostituisce un nodo per slug", () => {
        const next = replaceIndexNodeInTree(sample, "b", {
            slug: "b",
            name: "B2",
            items: [{ slug: "x", name: "y" }],
        });
        expect(findIndexNodeBySlug(next, "b")?.name).toBe("B2");
    });

    it("isBranchDirectlyTranslated: titolo o item diretto diverso", () => {
        const cur = mergeIndexNameOverlay(sample, [
            { slug: "a", name: "A'", items: [{ slug: "i1", name: "Item" }] },
        ]);
        expect(isBranchDirectlyTranslated(sample, cur, "a")).toBe(true);
        expect(isBranchDirectlyTranslated(sample, cur, "b")).toBe(false);
    });

    it("indexSubtreeFullyTranslated richiede tutto il sotto-albero", () => {
        const full = sample[0];
        const partial = mergeIndexNameOverlay(sample, [
            { slug: "a", name: "A'", items: [{ slug: "i1", name: "Item'" }] },
        ])[0];
        expect(indexSubtreeFullyTranslated(full, partial)).toBe(false);
    });

    it("isGlobalIndexFullyTranslatedRoots su radici singola", () => {
        const canon = sample;
        const cur = mergeIndexNameOverlay(sample, [
            {
                slug: "a",
                name: "A'",
                items: [{ slug: "i1", name: "Item'" }],
                collections: [{ slug: "b", name: "B'", items: [] }],
            },
        ]);
        expect(isGlobalIndexFullyTranslatedRoots(canon, cur)).toBe(true);
    });

    it("indexSubtreeHasAnyTranslation e indexRootsTranslationState", () => {
        const canon = sample[0]!;
        const curPartial = mergeIndexNameOverlay(sample, [
            { slug: "a", name: "A'", items: [{ slug: "i1", name: "Item" }] },
        ])[0]!;
        expect(indexSubtreeHasAnyTranslation(canon, curPartial)).toBe(true);
        expect(indexRootsTranslationState(sample, [curPartial])).toBe("partial");

        const curFull = mergeIndexNameOverlay(sample, [
            {
                slug: "a",
                name: "A'",
                items: [{ slug: "i1", name: "Item'" }],
                collections: [{ slug: "b", name: "B'", items: [] }],
            },
        ]);
        expect(indexRootsTranslationState(sample, curFull)).toBe("full");

        expect(indexRootsTranslationState(sample, sample)).toBe("none");
    });
});
