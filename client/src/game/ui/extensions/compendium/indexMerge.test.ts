import { describe, expect, it } from "vitest";
import {
    mergeIndexNameOverlay,
    mergeIndexPreservePriorSubtree,
    mergeIndexPreservePriorRoots,
    type IndexCollNode,
} from "./indexMerge";

describe("mergeIndexNameOverlay", () => {
    it("applica overlay per slug anche se nidificazione diversa", () => {
        const canon: IndexCollNode[] = [
            {
                slug: "root",
                name: "Root",
                items: [],
                collections: [
                    { slug: "a", name: "A EN", items: [{ slug: "i1", name: "One EN" }], collections: [] },
                ],
            },
        ];
        const overlay: IndexCollNode[] = [
            {
                slug: "root",
                name: "Root IT",
                items: [],
                collections: [{ slug: "a", name: "A IT", items: [{ slug: "i1", name: "Uno IT" }], collections: [] }],
            },
        ];
        const out = mergeIndexNameOverlay(canon, overlay);
        expect(out[0]!.name).toBe("Root IT");
        expect(out[0]!.collections![0]!.name).toBe("A IT");
        expect(out[0]!.collections![0]!.items[0]!.name).toBe("Uno IT");
    });
});

describe("mergeIndexPreservePriorSubtree", () => {
    const chapterCanon: IndexCollNode = {
        slug: "ch",
        name: "Chapter EN",
        items: [],
        collections: [
            {
                slug: "sub-a",
                name: "Sub A EN",
                items: [{ slug: "it1", name: "Item 1 EN" }],
                collections: [],
            },
            {
                slug: "sub-b",
                name: "Sub B EN",
                items: [{ slug: "it2", name: "Item 2 EN" }],
                collections: [],
            },
        ],
    };

    const chapterPrior: IndexCollNode = {
        slug: "ch",
        name: "Capitolo IT",
        items: [],
        collections: [
            {
                slug: "sub-a",
                name: "Sotto A IT",
                items: [{ slug: "it1", name: "Voce 1 IT" }],
                collections: [],
            },
            {
                slug: "sub-b",
                name: "Sub B EN",
                items: [{ slug: "it2", name: "Item 2 EN" }],
                collections: [],
            },
        ],
    };

    it("non azzera un sotto-ramo già tradotto quando il merge AI ripete il canonico su quel ramo", () => {
        const aiParsed: IndexCollNode = {
            slug: "ch",
            name: "Capitolo IT",
            items: [],
            collections: [
                {
                    slug: "sub-a",
                    name: "Sub A EN",
                    items: [{ slug: "it1", name: "Item 1 EN" }],
                    collections: [],
                },
                {
                    slug: "sub-b",
                    name: "Sotto B IT",
                    items: [{ slug: "it2", name: "Voce 2 IT" }],
                    collections: [],
                },
            ],
        };

        const mergedFromAi = mergeIndexNameOverlay([chapterCanon], [aiParsed])[0]!;
        expect(mergedFromAi.collections![0]!.name).toBe("Sub A EN");

        const fixed = mergeIndexPreservePriorSubtree(chapterCanon, mergedFromAi, chapterPrior);
        expect(fixed.collections![0]!.name).toBe("Sotto A IT");
        expect(fixed.collections![0]!.items[0]!.name).toBe("Voce 1 IT");
        expect(fixed.collections![1]!.name).toBe("Sotto B IT");
        expect(fixed.collections![1]!.items[0]!.name).toBe("Voce 2 IT");
    });
});

describe("mergeIndexPreservePriorRoots", () => {
    it("allinea radici multiple", () => {
        const canon: IndexCollNode[] = [
            { slug: "r1", name: "R1 EN", items: [], collections: [] },
            { slug: "r2", name: "R2 EN", items: [], collections: [] },
        ];
        const prior: IndexCollNode[] = [
            { slug: "r1", name: "R1 IT", items: [], collections: [] },
            { slug: "r2", name: "R2 EN", items: [], collections: [] },
        ];
        const aiParsed: IndexCollNode[] = [
            { slug: "r1", name: "R1 EN", items: [], collections: [] },
            { slug: "r2", name: "R2 IT", items: [], collections: [] },
        ];
        const afterAi = mergeIndexNameOverlay(canon, aiParsed);
        const out = mergeIndexPreservePriorRoots(canon, afterAi, prior);
        expect(out[0]!.name).toBe("R1 IT");
        expect(out[1]!.name).toBe("R2 IT");
    });
});
