import type { Ref } from "vue";
import type { Composer } from "vue-i18n";

import { http } from "../../../../core/http";
import { localeToEnglishPromptName } from "../../../../core/paUiLocales";
import {
    findIndexNodeBySlug,
    mergeIndexNameOverlay,
    mergeIndexPreservePriorRoots,
    mergeIndexPreservePriorSubtree,
    replaceIndexNodeInTree,
    type IndexCollNode,
} from "./indexTree";

/** Stato voce selezionata necessario alle API di traduzione. */
export interface CompendiumTranslationSelectedItem {
    compendium: { id: string };
    collection: { slug: string };
    item: { slug: string; markdown: string };
}

export interface CompendiumTranslationMeta {
    id: string;
}

export interface CompendiumTranslationDeps {
    toast: {
        error: (msg: string) => void;
        warning: (msg: string) => void;
    };
    t: Composer["t"];
    getEffectiveTargetLang: () => string;
    compendiumTranslateSource: Ref<string>;
    activeTranslationLang: Ref<string | null>;
    originalMarkdown: Ref<string | null>;
    originalIndex: Ref<unknown[] | null>;
    canonicalIndex: Ref<IndexCollNode[]>;
    /** Merge nomi tradotti da DB/AI; null = nessuna traduzione salvata per l’indice corrente. */
    translatedIndexOverlay: Ref<IndexCollNode[] | null>;
    currentMarkdown: Ref<string>;
    selectedItem: Ref<CompendiumTranslationSelectedItem | null>;
    indexCompendium: Ref<CompendiumTranslationMeta | null>;
    showIndex: Ref<boolean>;
    indexFocusCollectionSlug: Ref<string | null>;
    showTranslationTools: Ref<boolean>;
    translateLoading: Ref<boolean>;
    batchTranslateProgress: Ref<{ current: number; total: number } | null>;
    aiModel: Ref<string>;
    aiMaxTokens: Ref<number>;
}

function buildCompendiumMarkdownSystemPrompt(targetCode: string, compendiumTranslateSource: Ref<string>): string {
    const targetLangName = localeToEnglishPromptName(targetCode);
    const sourceHint =
        compendiumTranslateSource.value === "auto"
            ? "The source text may be in any language; infer the source language from the text."
            : `The source text is written in ${localeToEnglishPromptName(compendiumTranslateSource.value)}.`;
    const dndItHint =
        targetCode === "it"
            ? '\nEnsure terminology consistency with D&D 5e standards in Italian (e.g., "Saving Throw" -> "Tiro Salvezza").'
            : "";
    return `You are a translator specialized in Dungeons & Dragons 5th Edition.
${sourceHint}
Translate the provided content into ${targetLangName}.
Maintain the original Markdown structure and all special tags like {@b ...}, {@i ...}, {@dice ...}, etc.
Do NOT translate these tags or their parameters.${dndItHint}`;
}

export interface CompendiumTranslationApi {
    checkTranslation: (type: "item" | "index") => Promise<void>;
    saveTranslationToDb: (content: string, type: "item" | "index") => Promise<void>;
    revertTranslationUI: () => void;
    clearTranslation: () => Promise<void>;
    fetchCachedItemTranslation: (
        compId: string,
        collectionSlug: string,
        itemSlug: string,
        lang: string,
    ) => Promise<string | null>;
    saveItemTranslationDirect: (
        compId: string,
        collectionSlug: string,
        itemSlug: string,
        content: string,
        lang: string,
    ) => Promise<void>;
    runTranslateIndexRecursiveBatch: (
        leafItems: { collectionSlug: string; itemSlug: string; itemName: string }[],
        targetCode: string,
    ) => Promise<void>;
    translateIndexJsonOnly: (roots: IndexCollNode[], targetCode: string) => Promise<boolean>;
    translateSingleItemMarkdown: (targetCode: string) => Promise<void>;
}

export function useCompendiumTranslation(d: CompendiumTranslationDeps): CompendiumTranslationApi {
    const msg = {
        loadFailed: () => d.t("game.ui.extensions.CompendiumModal.translation_load_failed"),
        saveFailed: () => d.t("game.ui.extensions.CompendiumModal.translation_save_failed"),
        deleteFailed: () => d.t("game.ui.extensions.CompendiumModal.translation_delete_failed"),
        translateError: () => d.t("game.ui.extensions.CompendiumModal.translate_error"),
    };

    async function checkTranslation(type: "item" | "index"): Promise<void> {
        const compId = type === "item" ? d.selectedItem.value?.compendium.id : d.indexCompendium.value?.id;
        if (compId == null || compId.length === 0) return;

        const lang = d.getEffectiveTargetLang();
        let url = `/api/extensions/compendium/translations?compendium=${encodeURIComponent(compId)}&lang=${encodeURIComponent(lang)}&type=${type}`;
        if (type === "item" && d.selectedItem.value) {
            url += `&collection=${encodeURIComponent(d.selectedItem.value.collection.slug)}&slug=${encodeURIComponent(d.selectedItem.value.item.slug)}`;
        }

        try {
            const r = await http.get(url);
            if (!r.ok) {
                d.toast.error(msg.loadFailed());
                return;
            }
            const data = (await r.json()) as { content?: string | null };
            if (typeof data.content === "string" && data.content.length > 0) {
                if (type === "item" && d.selectedItem.value) {
                    if (d.originalMarkdown.value === null) d.originalMarkdown.value = d.selectedItem.value.item.markdown;
                    d.currentMarkdown.value = data.content;
                    d.activeTranslationLang.value = lang;
                } else if (type === "index" && d.canonicalIndex.value.length > 0) {
                    const overlay = JSON.parse(data.content) as IndexCollNode[];
                    const prior = d.translatedIndexOverlay.value;
                    const mergedFromDb = mergeIndexNameOverlay(d.canonicalIndex.value, overlay);
                    const canonRoots = d.canonicalIndex.value;
                    if (prior != null && prior.length === canonRoots.length && prior.length > 0) {
                        d.translatedIndexOverlay.value = mergeIndexPreservePriorRoots(canonRoots, mergedFromDb, prior);
                    } else {
                        d.translatedIndexOverlay.value = mergedFromDb;
                    }
                    d.activeTranslationLang.value = lang;
                }
            } else if (type === "item" && d.selectedItem.value) {
                d.currentMarkdown.value = "";
                d.originalMarkdown.value = null;
                d.activeTranslationLang.value = null;
            }
        } catch (e: unknown) {
            console.error("Error checking translation", e);
            d.toast.error(msg.loadFailed());
        }
    }

    async function saveTranslationToDb(content: string, type: "item" | "index"): Promise<void> {
        const compId = type === "item" ? d.selectedItem.value?.compendium.id : d.indexCompendium.value?.id;
        if (compId == null || compId.length === 0) return;

        const payload: Record<string, unknown> = {
            compendium: compId,
            type,
            lang: d.getEffectiveTargetLang(),
            content,
        };

        if (type === "item" && d.selectedItem.value) {
            payload.collection = d.selectedItem.value.collection.slug;
            payload.slug = d.selectedItem.value.item.slug;
        }

        try {
            const r = await http.postJson("/api/extensions/compendium/translations", payload);
            if (!r.ok) {
                d.toast.error(msg.saveFailed());
            }
        } catch (e: unknown) {
            console.error("Error saving translation", e);
            d.toast.error(msg.saveFailed());
        }
    }

    function revertTranslationUI(): void {
        const isIndex = d.showIndex.value;
        if (isIndex && d.canonicalIndex.value.length > 0) {
            d.translatedIndexOverlay.value = null;
            d.originalIndex.value = null;
        } else if (d.selectedItem.value && d.originalMarkdown.value !== null) {
            d.currentMarkdown.value = d.originalMarkdown.value;
            d.originalMarkdown.value = null;
        }
        d.activeTranslationLang.value = null;
        d.showTranslationTools.value = false;
    }

    async function clearTranslation(): Promise<void> {
        const isIndex = d.showIndex.value;
        const hasIndexTr =
            isIndex && d.canonicalIndex.value.length > 0 && d.translatedIndexOverlay.value != null;
        const hasItemTr =
            !isIndex && d.selectedItem.value != null && d.originalMarkdown.value != null;
        if (!hasIndexTr && !hasItemTr) return;

        const compId = isIndex ? d.indexCompendium.value?.id : d.selectedItem.value?.compendium.id;
        if (compId != null && compId.length > 0) {
            const lang = d.getEffectiveTargetLang();
            const payload: Record<string, unknown> = { compendium: compId, type: isIndex ? "index" : "item", lang };
            if (!isIndex && d.selectedItem.value) {
                payload.collection = d.selectedItem.value.collection.slug;
                payload.slug = d.selectedItem.value.item.slug;
            }
            try {
                const r = await http.deleteJson("/api/extensions/compendium/translations", payload);
                if (!r.ok) {
                    d.toast.error(msg.deleteFailed());
                }
            } catch (e: unknown) {
                console.error("Error deleting translation from db", e);
                d.toast.error(msg.deleteFailed());
            }
        }

        revertTranslationUI();
    }

    async function fetchCachedItemTranslation(
        compId: string,
        collectionSlug: string,
        itemSlug: string,
        lang: string,
    ): Promise<string | null> {
        const url =
            `/api/extensions/compendium/translations?compendium=${encodeURIComponent(compId)}&lang=${encodeURIComponent(lang)}&type=item` +
            `&collection=${encodeURIComponent(collectionSlug)}&slug=${encodeURIComponent(itemSlug)}`;
        try {
            const r = await http.get(url);
            if (!r.ok) return null;
            const data = (await r.json()) as { content?: string | null };
            return typeof data.content === "string" && data.content.length > 0 ? data.content : null;
        } catch {
            return null;
        }
    }

    async function saveItemTranslationDirect(
        compId: string,
        collectionSlug: string,
        itemSlug: string,
        content: string,
        lang: string,
    ): Promise<void> {
        await http.postJson("/api/extensions/compendium/translations", {
            compendium: compId,
            type: "item",
            collection: collectionSlug,
            slug: itemSlug,
            lang,
            content,
        });
    }

    /** Traduzione sequenziale delle voci (evita saturare l’API). */
    async function runTranslateIndexRecursiveBatch(
        leafItems: { collectionSlug: string; itemSlug: string; itemName: string }[],
        targetCode: string,
    ): Promise<void> {
        const compId = d.indexCompendium.value?.id;
        if (compId == null || compId.length === 0) return;
        const systemPrompt = buildCompendiumMarkdownSystemPrompt(targetCode, d.compendiumTranslateSource);
        let failed = 0;
        for (let i = 0; i < leafItems.length; i++) {
            d.batchTranslateProgress.value = { current: i + 1, total: leafItems.length };
            const { collectionSlug, itemSlug } = leafItems[i]!;
            try {
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const cached = await fetchCachedItemTranslation(compId, collectionSlug, itemSlug, targetCode);
                if (cached != null && cached.length > 0) continue;
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const r = await http.get(
                    `/api/extensions/compendium/item?compendium=${encodeURIComponent(compId)}&collection=${encodeURIComponent(collectionSlug)}&slug=${encodeURIComponent(itemSlug)}`,
                );
                if (!r.ok) {
                    failed++;
                    continue;
                }
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const full = (await r.json()) as { markdown?: string };
                const raw = (full.markdown ?? "").trim();
                if (raw.length === 0) continue;
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const tr = await http.postJson("/api/extensions/openrouter/chat", {
                    model: d.aiModel.value,
                    messages: [
                        { role: "system", content: systemPrompt },
                        { role: "user", content: `Translate this content:\n\n${raw}` },
                    ],
                    max_tokens: Math.max(256, Math.min(65536, d.aiMaxTokens.value || 8192)),
                    temperature: 0.7,
                });
                if (!tr.ok) {
                    failed++;
                    continue;
                }
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const data = (await tr.json()) as { choices?: { message?: { content?: string } }[] };
                const translated = data.choices?.[0]?.message?.content;
                if (translated == null || translated.length === 0) {
                    failed++;
                    continue;
                }
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                await saveItemTranslationDirect(compId, collectionSlug, itemSlug, translated, targetCode);
            } catch {
                failed++;
            }
        }
        if (failed > 0) {
            d.toast.warning(d.t("game.ui.extensions.CompendiumModal.translate_batch_partial", { count: failed }));
        }
    }

    async function translateIndexJsonOnly(roots: IndexCollNode[], targetCode: string): Promise<boolean> {
        const targetLangName = localeToEnglishPromptName(targetCode);
        const systemPrompt = buildCompendiumMarkdownSystemPrompt(targetCode, d.compendiumTranslateSource);
        console.log(`[Compendium AI] Index names translation to ${targetLangName} using model ${d.aiModel.value}`);
        const indexJson = JSON.stringify(roots, null, 2);
        const r = await http.postJson("/api/extensions/openrouter/chat", {
            model: d.aiModel.value,
            messages: [
                {
                    role: "system",
                    content:
                        systemPrompt +
                        "\nOnly translate the 'name' values in the provided JSON. Keep everything else identical.",
                },
                { role: "user", content: `Translate this index JSON:\n\n${indexJson}` },
            ],
            max_tokens: Math.max(256, Math.min(65536, d.aiMaxTokens.value || 8192)),
            temperature: 0.7,
        });
        if (!r.ok) {
            d.toast.error(msg.translateError());
            return false;
        }
        const data = (await r.json()) as { choices?: { message?: { content?: string } }[] };
        const translated = data.choices?.[0]?.message?.content;
        if (translated == null || translated.length === 0) {
            d.toast.error(msg.translateError());
            return false;
        }
        try {
            const start = translated.indexOf("[");
            const end = translated.lastIndexOf("]") + 1;
            if (start === -1 || end === 0) throw new Error("no json array");
            const parsed = JSON.parse(translated.substring(start, end)) as IndexCollNode[];
            if (d.originalIndex.value === null) d.originalIndex.value = JSON.parse(JSON.stringify(d.canonicalIndex.value)) as unknown[];
            const canonRoots = d.canonicalIndex.value;
            const baseTree = (): IndexCollNode[] =>
                d.translatedIndexOverlay.value != null
                    ? d.translatedIndexOverlay.value
                    : (JSON.parse(JSON.stringify(canonRoots)) as IndexCollNode[]);
            const focus = d.indexFocusCollectionSlug.value;
            if (focus != null && focus.length > 0) {
                if (parsed.length > 0) {
                    const canonNode = findIndexNodeBySlug(canonRoots, focus);
                    const tree = baseTree();
                    const oldNode = findIndexNodeBySlug(tree, focus);
                    if (canonNode != null && oldNode != null) {
                        const mergedFromAi = mergeIndexNameOverlay([canonNode], [parsed[0]!])[0]!;
                        const mergedNode = mergeIndexPreservePriorSubtree(canonNode, mergedFromAi, oldNode);
                        d.translatedIndexOverlay.value = replaceIndexNodeInTree(tree, focus, mergedNode);
                    } else {
                        const prior = baseTree();
                        const mergedFromAi = mergeIndexNameOverlay(canonRoots, parsed);
                        d.translatedIndexOverlay.value = mergeIndexPreservePriorRoots(canonRoots, mergedFromAi, prior);
                    }
                }
            } else {
                const prior = baseTree();
                const mergedFromAi = mergeIndexNameOverlay(canonRoots, parsed);
                d.translatedIndexOverlay.value = mergeIndexPreservePriorRoots(canonRoots, mergedFromAi, prior);
            }
            d.activeTranslationLang.value = targetCode;
            await saveTranslationToDb(JSON.stringify(d.translatedIndexOverlay.value), "index");
            return true;
        } catch (e: unknown) {
            console.error("Failed to parse translated index", e);
            d.toast.error(msg.translateError());
            return false;
        }
    }

    async function translateSingleItemMarkdown(targetCode: string): Promise<void> {
        const si = d.selectedItem.value;
        if (si == null) return;
        const targetLangName = localeToEnglishPromptName(targetCode);
        const systemPrompt = buildCompendiumMarkdownSystemPrompt(targetCode, d.compendiumTranslateSource);
        console.log(`[Compendium AI] Starting translation to ${targetLangName} using model ${d.aiModel.value}`);
        d.translateLoading.value = true;
        try {
            const raw = si.item.markdown;
            const r = await http.postJson("/api/extensions/openrouter/chat", {
                model: d.aiModel.value,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: `Translate this content:\n\n${raw}` },
                ],
                max_tokens: Math.max(256, Math.min(65536, d.aiMaxTokens.value || 8192)),
                temperature: 0.7,
            });
            if (r.ok) {
                const data = (await r.json()) as { choices?: { message?: { content?: string } }[] };
                const translated = data.choices?.[0]?.message?.content;
                console.log("[Compendium AI] Translation received", { length: translated?.length });
                if (translated != null && translated.length > 0) {
                    if (d.originalMarkdown.value == null) d.originalMarkdown.value = si.item.markdown;
                    d.currentMarkdown.value = translated;
                    d.activeTranslationLang.value = targetCode;
                    await saveTranslationToDb(translated, "item");
                } else {
                    console.error("[Compendium AI] Empty translation response received");
                    d.toast.error(msg.translateError());
                }
            } else {
                d.toast.error(msg.translateError());
            }
        } catch (e: unknown) {
            console.error(e);
            d.toast.error(msg.translateError());
        } finally {
            d.translateLoading.value = false;
        }
    }

    return {
        checkTranslation,
        saveTranslationToDb,
        revertTranslationUI,
        clearTranslation,
        fetchCachedItemTranslation,
        saveItemTranslationDirect,
        runTranslateIndexRecursiveBatch,
        translateIndexJsonOnly,
        translateSingleItemMarkdown,
    };
}
