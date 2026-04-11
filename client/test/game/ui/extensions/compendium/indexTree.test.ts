import { describe, expect, it } from "vitest";

import {
    extractFirstMarkdownHeading,
    extractItemTranslationDisplayTitle,
    finalizeTranslatedItemBodyForStorage,
    findIndexNodeBySlug,
    markdownDocumentStartsWithH1Line,
    indexRootsTranslationState,
    indexSubtreeFullyTranslated,
    indexSubtreeHasAnyTranslation,
    isBranchDirectlyTranslated,
    isGlobalIndexFullyTranslatedRoots,
    mergeIndexNameOverlay,
    mergeIndexPreservePriorRoots,
    patchItemDisplayNameInIndexTree,
    replaceIndexNodeInTree,
    stripPaCompendiumTitleCommentForRender,
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

    it("mergeIndexPreservePriorRoots abbina per slug se l’ordine delle radici differisce", () => {
        const canon = sample;
        const afterAi = [
            {
                slug: "a",
                name: "A-ai",
                items: [{ slug: "i1", name: "Item-ai" }],
                collections: [{ slug: "b", name: "B-ai", items: [] }],
            },
        ];
        const prior = mergeIndexNameOverlay(sample, null);
        const reordered = [afterAi[0]!];
        const merged = mergeIndexPreservePriorRoots(canon, reordered, prior);
        expect(merged[0]?.name).toBe("A-ai");
        expect(merged[0]?.items[0]?.name).toBe("Item-ai");
    });

    it("patchItemDisplayNameInIndexTree aggiorna il nome voce", () => {
        const tree = mergeIndexNameOverlay(sample, null);
        const next = patchItemDisplayNameInIndexTree(tree, "a", "i1", "Patched");
        expect(findIndexNodeBySlug(next, "a")?.items.find((x) => x.slug === "i1")?.name).toBe("Patched");
    });

    it("extractFirstMarkdownHeading preferisce # livello 1; altrimenti primo ##", () => {
        expect(extractFirstMarkdownHeading("# Fireball\n\n## Sotto\n")).toBe("Fireball");
        expect(extractFirstMarkdownHeading("## Solo secondo\n")).toBe("Solo secondo");
        expect(extractFirstMarkdownHeading("## In cima\n\n# Dopo\n")).toBe("Dopo");
        expect(extractFirstMarkdownHeading("no heading")).toBeNull();
    });

    it("markdownDocumentStartsWithH1Line rileva solo # iniziale", () => {
        expect(markdownDocumentStartsWithH1Line("# Intro\n\np")).toBe(true);
        expect(markdownDocumentStartsWithH1Line("\n\n# T\n")).toBe(true);
        expect(markdownDocumentStartsWithH1Line("Testo senza H1")).toBe(false);
        expect(markdownDocumentStartsWithH1Line("## Due\n")).toBe(false);
    });

    it("finalizeTranslatedItemBodyForStorage toglie H1 sintetico se l’originale non aveva H1", () => {
        const orig = "The town of…";
        const ai = "# Introduzione\n\nLa città di…";
        const out = finalizeTranslatedItemBodyForStorage(orig, ai);
        expect(out.startsWith("<!-- pa-compendium-title:Introduzione -->")).toBe(true);
        expect(out).not.toContain("# Introduzione");
        expect(out).toContain("La città");
        expect(extractItemTranslationDisplayTitle(out)).toBe("Introduzione");
        expect(stripPaCompendiumTitleCommentForRender(out).trimStart()).toMatch(/^La città/);
    });

    it("finalizeTranslatedItemBodyForStorage mantiene output se l’originale ha già H1", () => {
        const orig = "# Introduction\n\nBody";
        const ai = "# Introduzione\n\nCorpo";
        expect(finalizeTranslatedItemBodyForStorage(orig, ai)).toBe(ai);
    });
});
