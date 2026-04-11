import { describe, expect, it } from "vitest";

import {
    applySavedItemTitlesToIndexTree,
    compendiumItemTitleKey,
    finalizeIndexOverlayWithItemTitles,
} from "../../../../../src/game/ui/extensions/compendium/indexTranslationDisplay";
import type { IndexCollNode } from "../../../../../src/game/ui/extensions/compendium/indexTree";

const canon: IndexCollNode[] = [
    {
        slug: "chap",
        name: "Chapter",
        items: [{ slug: "a", name: "Spell A" }],
 },
];

describe("indexTranslationDisplay", () => {
    it("compendiumItemTitleKey round-trips", () => {
        const k = compendiumItemTitleKey("c", "s");
        expect(k).toBe("c::s");
    });

    it("finalizeIndexOverlayWithItemTitles detects item-only translation", () => {
        const titles = new Map([[compendiumItemTitleKey("chap", "a"), "Incantesimo A"]]);
        const out = finalizeIndexOverlayWithItemTitles(canon, null, titles);
        expect(out).not.toBeNull();
        expect(out?.[0]?.items[0]?.name).toBe("Incantesimo A");
    });

    it("finalizeIndexOverlayWithItemTitles returns null when nothing differs", () => {
        const titles = new Map([[compendiumItemTitleKey("chap", "a"), "Spell A"]]);
        const out = finalizeIndexOverlayWithItemTitles(canon, null, titles);
        expect(out).toBeNull();
    });

    it("applySavedItemTitlesToIndexTree patches merged tree", () => {
        const merged = structuredClone(canon) as IndexCollNode[];
        const titles = new Map([[compendiumItemTitleKey("chap", "a"), "X"]]);
        const patched = applySavedItemTitlesToIndexTree(merged, canon, titles);
        expect(patched[0]?.items[0]?.name).toBe("X");
    });
});
