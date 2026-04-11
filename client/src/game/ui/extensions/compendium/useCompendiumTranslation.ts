import type { ComputedRef, Ref } from "vue";
import type { Composer } from "vue-i18n";

import { http } from "../../../../core/http";
import { localeToEnglishPromptName } from "../../../../core/paUiLocales";
import { finalizeIndexOverlayWithItemTitles } from "./indexTranslationDisplay";
import {
    extractItemTranslationDisplayTitle,
    finalizeTranslatedItemBodyForStorage,
    findIndexNodeBySlug,
    mergeIndexNameOverlay,
    mergeIndexPreservePriorRoots,
    mergeIndexPreservePriorSubtree,
    patchItemDisplayNameInIndexTree,
    replaceIndexNodeInTree,
    type IndexCollNode,
} from "./indexTree";
import {
    formatTranslationCaughtError,
    formatTranslationChatErrorResponse,
    formatTranslationHttpErrorResponse,
} from "./translationErrors";

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
    /** Modale compendio aperto: false ferma la traduzione tra un passo e l’altro. */
    compendiumModalVisible: Ref<boolean> | ComputedRef<boolean>;
    /** Segnale collegato all’abort alla chiusura del modale (richieste fetch annullate). */
    getTranslationAbortSignal: () => AbortSignal | undefined;
}

export interface TranslateIndexJsonOnlyOptions {
    /** Se true, non mostrare toast di errore (es. batch: il chiamante gestisce). */
    suppressErrorToast?: boolean;
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

/** Messaggio utente per traduzione voce: impone riga iniziale # Titolo tradotto (nome in indice/sidebar). */
function buildCompendiumItemTranslationUserPrompt(
    rawMarkdown: string,
    indexEntryTitle: string,
    targetCode: string,
): string {
    const targetLangName = localeToEnglishPromptName(targetCode);
    const safeTitle = indexEntryTitle.trim().length > 0 ? indexEntryTitle.trim() : "—";
    return [
        `The sidebar / table-of-contents label for this entry is: "${safeTitle}".`,
        ``,
        `You MUST format your entire reply as follows:`,
        `1) Line 1: exactly one Markdown H1 heading: # followed by the ${targetLangName} translation of that label (short natural title; never a slug, file name, or technical id).`,
        `2) Line 2: blank.`,
        `3) Then the full translation of the document body.`,
        ``,
        `Document body:`,
        ``,
        rawMarkdown,
    ].join("\n");
}

/** Estrae il primo array JSON dall’output LLM (blocco fenced o substring tra [ e ]). */
function parseIndexJsonArrayFromAiResponse(text: string): IndexCollNode[] {
    const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    const candidate = (fenced?.[1] ?? text).trim();
    const start = candidate.indexOf("[");
    const end = candidate.lastIndexOf("]") + 1;
    if (start === -1 || end <= start) throw new Error("no json array");
    return JSON.parse(candidate.slice(start, end)) as IndexCollNode[];
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
    ) => Promise<{ failed: number; cancelled: boolean; lastError?: string }>;
    translateIndexJsonOnly: (
        roots: IndexCollNode[],
        targetCode: string,
        options?: TranslateIndexJsonOnlyOptions,
    ) => Promise<boolean>;
    translateSingleItemMarkdown: (targetCode: string) => Promise<void>;
}

export function useCompendiumTranslation(d: CompendiumTranslationDeps): CompendiumTranslationApi {
    const msg = {
        loadFailed: () => d.t("game.ui.extensions.CompendiumModal.translation_load_failed"),
        saveFailed: () => d.t("game.ui.extensions.CompendiumModal.translation_save_failed"),
        deleteFailed: () => d.t("game.ui.extensions.CompendiumModal.translation_delete_failed"),
        translateError: () => d.t("game.ui.extensions.CompendiumModal.translate_error"),
        indexJsonInvalid: () => d.t("game.ui.extensions.CompendiumModal.translation_index_load_invalid"),
        emptyModel: () => d.t("game.ui.extensions.CompendiumModal.translate_error_empty_model"),
    };

    async function toastTranslateFailure(r?: Response, extra?: string): Promise<void> {
        const base = msg.translateError();
        if (r != null) {
            const detail = await formatTranslationChatErrorResponse(r);
            d.toast.error(`${base}: ${detail}`);
            return;
        }
        if (extra != null && extra.length > 0) {
            d.toast.error(`${base}: ${extra}`);
            return;
        }
        d.toast.error(base);
    }

    function trAbort(): AbortSignal | undefined {
        return d.getTranslationAbortSignal();
    }
    function trClosed(): boolean {
        return !d.compendiumModalVisible.value;
    }
    function isAbortError(e: unknown): boolean {
        return e instanceof DOMException && e.name === "AbortError";
    }

    async function fetchItemTranslationTitlesManifest(compId: string, lang: string): Promise<Map<string, string>> {
        const url =
            `/api/extensions/compendium/translations?compendium=${encodeURIComponent(compId)}` +
            `&lang=${encodeURIComponent(lang)}&manifest=item_titles`;
        try {
            const r = await http.get(url, { signal: trAbort() });
            if (!r.ok) return new Map();
            const data = (await r.json()) as { titles?: Record<string, string> };
            const rec = data.titles;
            if (rec == null || typeof rec !== "object") return new Map();
            return new Map(Object.entries(rec));
        } catch (e: unknown) {
            if (isAbortError(e)) throw e;
            return new Map();
        }
    }

    let itemTranslationFetchSeq = 0;
    let indexTranslationFetchSeq = 0;

    /** Nome voce in indice dopo traduzione: heading nel markdown, altrimenti nome canonico (mai lo slug tecnico). */
    function itemDisplayNameAfterItemTranslation(
        collectionSlug: string,
        itemSlug: string,
        translatedMarkdown: string,
    ): string {
        const fromMd = extractItemTranslationDisplayTitle(translatedMarkdown);
        if (fromMd != null && fromMd.length > 0) {
            return fromMd;
        }
        const coll = findIndexNodeBySlug(d.canonicalIndex.value, collectionSlug);
        const canonItem = coll?.items.find((x) => x.slug === itemSlug);
        const fromIndex = canonItem?.name?.trim();
        if (fromIndex != null && fromIndex.length > 0) {
            return fromIndex;
        }
        const si = d.selectedItem.value;
        if (
            si != null &&
            si.collection.slug === collectionSlug &&
            si.item.slug === itemSlug &&
            si.item.name.trim().length > 0
        ) {
            return si.item.name.trim();
        }
        return itemSlug;
    }

    function applyPatchAfterItemSave(
        collectionSlug: string,
        itemSlug: string,
        translatedMarkdown: string,
        targetCode: string,
    ): void {
        const title = itemDisplayNameAfterItemTranslation(collectionSlug, itemSlug, translatedMarkdown);
        const canon = d.canonicalIndex.value;
        if (canon.length === 0) return;
        let next = d.translatedIndexOverlay.value;
        if (next == null) {
            next = mergeIndexNameOverlay(canon, null);
        }
        d.translatedIndexOverlay.value = patchItemDisplayNameInIndexTree(next, collectionSlug, itemSlug, title);
        d.activeTranslationLang.value = targetCode;
    }

    async function checkTranslation(type: "item" | "index"): Promise<void> {
        const compId = type === "item" ? d.selectedItem.value?.compendium.id : d.indexCompendium.value?.id;
        if (compId == null || compId.length === 0) return;

        const lang = d.getEffectiveTargetLang();
        let url = `/api/extensions/compendium/translations?compendium=${encodeURIComponent(compId)}&lang=${encodeURIComponent(lang)}&type=${type}`;
        if (type === "item" && d.selectedItem.value) {
            url += `&collection=${encodeURIComponent(d.selectedItem.value.collection.slug)}&slug=${encodeURIComponent(d.selectedItem.value.item.slug)}`;
        }

        const itemKey =
            type === "item" && d.selectedItem.value
                ? `${d.selectedItem.value.collection.slug}::${d.selectedItem.value.item.slug}`
                : "";

        try {
            if (type === "item") {
                itemTranslationFetchSeq += 1;
                const mySeq = itemTranslationFetchSeq;
                const r = await http.get(url);
                if (mySeq !== itemTranslationFetchSeq) return;
                if (
                    !d.selectedItem.value ||
                    `${d.selectedItem.value.collection.slug}::${d.selectedItem.value.item.slug}` !== itemKey
                ) {
                    return;
                }
                if (!r.ok) {
                    const detail = await formatTranslationHttpErrorResponse(r);
                    d.toast.error(`${msg.loadFailed()}: ${detail}`);
                    return;
                }
                const data = (await r.json()) as { content?: string | null };
                if (typeof data.content === "string" && data.content.length > 0) {
                    if (d.originalMarkdown.value === null) d.originalMarkdown.value = d.selectedItem.value.item.markdown;
                    d.currentMarkdown.value = data.content;
                    d.activeTranslationLang.value = lang;
                    const si = d.selectedItem.value;
                    applyPatchAfterItemSave(si.collection.slug, si.item.slug, data.content, lang);
                } else {
                    d.currentMarkdown.value = "";
                    d.originalMarkdown.value = null;
                    d.activeTranslationLang.value = null;
                }
                return;
            }

            // index
            indexTranslationFetchSeq += 1;
            const mySeq = indexTranslationFetchSeq;
            const r = await http.get(url);
            if (mySeq !== indexTranslationFetchSeq) return;
            if (d.indexCompendium.value?.id !== compId) return;
            if (!r.ok) {
                const detail = await formatTranslationHttpErrorResponse(r);
                d.toast.error(`${msg.loadFailed()}: ${detail}`);
                return;
            }
            const data = (await r.json()) as { content?: string | null };
            const canonRoots = d.canonicalIndex.value;
            if (canonRoots.length === 0) {
                return;
            }

            let baseMerged: IndexCollNode[] | null = null;
            if (typeof data.content === "string" && data.content.length > 0) {
                try {
                    const overlay = JSON.parse(data.content) as IndexCollNode[];
                    const prior = d.translatedIndexOverlay.value;
                    const mergedFromDb = mergeIndexNameOverlay(canonRoots, overlay);
                    if (prior != null && prior.length === canonRoots.length && prior.length > 0) {
                        baseMerged = mergeIndexPreservePriorRoots(canonRoots, mergedFromDb, prior);
                    } else {
                        baseMerged = mergedFromDb;
                    }
                } catch (e: unknown) {
                    console.error("Invalid index translation JSON from DB", e);
                    d.toast.error(msg.indexJsonInvalid());
                }
            }

            let titles = new Map<string, string>();
            try {
                titles = await fetchItemTranslationTitlesManifest(compId, lang);
            } catch (e: unknown) {
                if (isAbortError(e)) {
                    return;
                }
                console.error("Item translation titles manifest failed", e);
            }
            if (mySeq !== indexTranslationFetchSeq) return;
            if (d.indexCompendium.value?.id !== compId) return;

            const finalOverlay = finalizeIndexOverlayWithItemTitles(canonRoots, baseMerged, titles);
            d.translatedIndexOverlay.value = finalOverlay;
            d.activeTranslationLang.value = finalOverlay != null ? lang : null;
        } catch (e: unknown) {
            console.error("Error checking translation", e);
            const detail = formatTranslationCaughtError(e);
            if (detail.length > 0) {
                d.toast.error(`${msg.loadFailed()}: ${detail}`);
            } else {
                d.toast.error(msg.loadFailed());
            }
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
                const detail = await formatTranslationHttpErrorResponse(r);
                d.toast.error(`${msg.saveFailed()}: ${detail}`);
            }
        } catch (e: unknown) {
            console.error("Error saving translation", e);
            const detail = formatTranslationCaughtError(e);
            if (detail.length > 0) {
                d.toast.error(`${msg.saveFailed()}: ${detail}`);
            } else {
                d.toast.error(msg.saveFailed());
            }
        }
    }

    function revertTranslationUI(): void {
        const isIndex = d.showIndex.value;
        if (isIndex && d.canonicalIndex.value.length > 0) {
            d.translatedIndexOverlay.value = null;
            d.originalIndex.value = null;
        } else if (d.selectedItem.value && d.originalMarkdown.value !== null) {
            const si = d.selectedItem.value;
            d.currentMarkdown.value = d.originalMarkdown.value;
            d.originalMarkdown.value = null;
            /** `applyPatchAfterItemSave` aggiorna il nome voce nell’overlay; senza questo il titolo resta tradotto. */
            if (d.translatedIndexOverlay.value != null && d.canonicalIndex.value.length > 0) {
                const coll = findIndexNodeBySlug(d.canonicalIndex.value, si.collection.slug);
                const canonItem = coll?.items.find((x) => x.slug === si.item.slug);
                const restoredName =
                    canonItem?.name?.trim() || si.item.name?.trim() || si.item.slug;
                d.translatedIndexOverlay.value = patchItemDisplayNameInIndexTree(
                    d.translatedIndexOverlay.value,
                    si.collection.slug,
                    si.item.slug,
                    restoredName,
                );
            }
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
                    const detail = await formatTranslationHttpErrorResponse(r);
                    d.toast.error(`${msg.deleteFailed()}: ${detail}`);
                }
            } catch (e: unknown) {
                console.error("Error deleting translation from db", e);
                const detail = formatTranslationCaughtError(e);
                if (detail.length > 0) {
                    d.toast.error(`${msg.deleteFailed()}: ${detail}`);
                } else {
                    d.toast.error(msg.deleteFailed());
                }
            }
        }

        revertTranslationUI();
        if (isIndex && d.indexCompendium.value != null && d.canonicalIndex.value.length > 0) {
            await checkTranslation("index");
        }
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
            const r = await http.get(url, { signal: trAbort() });
            if (!r.ok) return null;
            const data = (await r.json()) as { content?: string | null };
            return typeof data.content === "string" && data.content.length > 0 ? data.content : null;
        } catch (e: unknown) {
            if (isAbortError(e)) throw e;
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
        if (trClosed()) return;
        await http.postJson(
            "/api/extensions/compendium/translations",
            {
                compendium: compId,
                type: "item",
                collection: collectionSlug,
                slug: itemSlug,
                lang,
                content,
            },
            { signal: trAbort() },
        );
    }

    /** Traduzione sequenziale delle voci (evita saturare l’API). Aggiorna l’overlay indice dopo ogni salvataggio. */
    async function runTranslateIndexRecursiveBatch(
        leafItems: { collectionSlug: string; itemSlug: string; itemName: string }[],
        targetCode: string,
    ): Promise<{ failed: number; cancelled: boolean; lastError?: string }> {
        const compId = d.indexCompendium.value?.id;
        if (compId == null || compId.length === 0) return { failed: 0, cancelled: false, lastError: undefined };
        const systemPrompt = buildCompendiumMarkdownSystemPrompt(targetCode, d.compendiumTranslateSource);
        let failed = 0;
        let lastError: string | undefined;
        for (let i = 0; i < leafItems.length; i++) {
            if (trClosed()) {
                return { failed, cancelled: true, lastError };
            }
            d.batchTranslateProgress.value = { current: i + 1, total: leafItems.length };
            const { collectionSlug, itemSlug, itemName } = leafItems[i]!;
            try {
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const cached = await fetchCachedItemTranslation(compId, collectionSlug, itemSlug, targetCode);
                if (trClosed()) {
                    return { failed, cancelled: true, lastError };
                }
                if (cached != null && cached.length > 0) {
                    applyPatchAfterItemSave(
                        collectionSlug,
                        itemSlug,
                        cached,
                        targetCode,
                    );
                    continue;
                }
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const r = await http.get(
                    `/api/extensions/compendium/item?compendium=${encodeURIComponent(compId)}&collection=${encodeURIComponent(collectionSlug)}&slug=${encodeURIComponent(itemSlug)}`,
                    { signal: trAbort() },
                );
                if (!r.ok) {
                    failed++;
                    continue;
                }
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const full = (await r.json()) as { markdown?: string };
                const raw = (full.markdown ?? "").trim();
                if (trClosed()) {
                    return { failed, cancelled: true, lastError };
                }
                if (raw.length === 0) continue;
                const userPrompt = buildCompendiumItemTranslationUserPrompt(raw, itemName, targetCode);
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const tr = await http.postJson(
                    "/api/extensions/openrouter/chat",
                    {
                        model: d.aiModel.value,
                        messages: [
                            { role: "system", content: systemPrompt },
                            { role: "user", content: userPrompt },
                        ],
                        max_tokens: Math.max(256, Math.min(65536, d.aiMaxTokens.value || 8192)),
                        temperature: 0.7,
                    },
                    { signal: trAbort() },
                );
                if (trClosed()) {
                    return { failed, cancelled: true, lastError };
                }
                if (!tr.ok) {
                    // oxlint-disable-next-line no-await-in-loop -- errore da mostrare all’utente
                    lastError = await formatTranslationChatErrorResponse(tr);
                    failed++;
                    continue;
                }
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                const data = (await tr.json()) as { choices?: { message?: { content?: string } }[] };
                const translated = data.choices?.[0]?.message?.content;
                if (translated == null || translated.length === 0) {
                    lastError = msg.emptyModel();
                    failed++;
                    continue;
                }
                if (trClosed()) {
                    return { failed, cancelled: true, lastError };
                }
                const toSave = finalizeTranslatedItemBodyForStorage(raw, translated);
                // oxlint-disable-next-line no-await-in-loop -- batch sequenziale
                await saveItemTranslationDirect(compId, collectionSlug, itemSlug, toSave, targetCode);
                applyPatchAfterItemSave(collectionSlug, itemSlug, toSave, targetCode);
            } catch (e: unknown) {
                if (isAbortError(e) || trClosed()) {
                    return { failed, cancelled: true, lastError };
                }
                lastError = formatTranslationCaughtError(e);
                failed++;
            }
        }
        return { failed, cancelled: false, lastError };
    }

    async function translateIndexJsonOnly(
        roots: IndexCollNode[],
        targetCode: string,
        options?: TranslateIndexJsonOnlyOptions,
    ): Promise<boolean> {
        const suppress = options?.suppressErrorToast === true;
        const reportErr = async (r?: Response, extra?: string): Promise<void> => {
            if (suppress) return;
            await toastTranslateFailure(r, extra);
        };

        if (trClosed()) {
            return false;
        }
        const targetLangName = localeToEnglishPromptName(targetCode);
        const systemPrompt = buildCompendiumMarkdownSystemPrompt(targetCode, d.compendiumTranslateSource);
        console.log(`[Compendium AI] Index names translation to ${targetLangName} using model ${d.aiModel.value}`);
        const indexJson = JSON.stringify(roots, null, 2);
        let r: Response;
        try {
            r = await http.postJson(
                "/api/extensions/openrouter/chat",
                {
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
                },
                { signal: trAbort() },
            );
        } catch (e: unknown) {
            if (isAbortError(e) || trClosed()) {
                return false;
            }
            throw e;
        }
        if (trClosed()) {
            return false;
        }
        if (!r.ok) {
            await reportErr(r);
            return false;
        }
        const data = (await r.json()) as { choices?: { message?: { content?: string } }[] };
        const translated = data.choices?.[0]?.message?.content;
        if (translated == null || translated.length === 0) {
            await reportErr(undefined, msg.emptyModel());
            return false;
        }
        if (trClosed()) {
            return false;
        }
        try {
            const parsed = parseIndexJsonArrayFromAiResponse(translated);
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
            if (trClosed()) {
                return false;
            }
            await saveTranslationToDb(JSON.stringify(d.translatedIndexOverlay.value), "index");
            return true;
        } catch (e: unknown) {
            console.error("Failed to parse translated index", e);
            const detail = formatTranslationCaughtError(e);
            await reportErr(undefined, detail.length > 0 ? detail : msg.indexJsonInvalid());
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
            if (trClosed()) {
                return;
            }
            const raw = si.item.markdown;
            const userPrompt = buildCompendiumItemTranslationUserPrompt(raw, si.item.name, targetCode);
            let r: Response;
            try {
                r = await http.postJson(
                    "/api/extensions/openrouter/chat",
                    {
                        model: d.aiModel.value,
                        messages: [
                            { role: "system", content: systemPrompt },
                            { role: "user", content: userPrompt },
                        ],
                        max_tokens: Math.max(256, Math.min(65536, d.aiMaxTokens.value || 8192)),
                        temperature: 0.7,
                    },
                    { signal: trAbort() },
                );
            } catch (e: unknown) {
                if (isAbortError(e) || trClosed()) {
                    return;
                }
                throw e;
            }
            if (trClosed()) {
                return;
            }
            if (r.ok) {
                const data = (await r.json()) as { choices?: { message?: { content?: string } }[] };
                const translated = data.choices?.[0]?.message?.content;
                console.log("[Compendium AI] Translation received", { length: translated?.length });
                if (trClosed()) {
                    return;
                }
                if (translated != null && translated.length > 0) {
                    if (d.originalMarkdown.value == null) d.originalMarkdown.value = si.item.markdown;
                    const toSave = finalizeTranslatedItemBodyForStorage(si.item.markdown, translated);
                    d.currentMarkdown.value = toSave;
                    d.activeTranslationLang.value = targetCode;
                    await saveTranslationToDb(toSave, "item");
                    const coll = si.collection.slug;
                    const slug = si.item.slug;
                    applyPatchAfterItemSave(coll, slug, toSave, targetCode);
                } else {
                    console.error("[Compendium AI] Empty translation response received");
                    await toastTranslateFailure(undefined, msg.emptyModel());
                }
            } else {
                await toastTranslateFailure(r);
            }
        } catch (e: unknown) {
            if (isAbortError(e) || trClosed()) {
                return;
            }
            console.error(e);
            const detail = formatTranslationCaughtError(e);
            await toastTranslateFailure(undefined, detail.length > 0 ? detail : undefined);
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
