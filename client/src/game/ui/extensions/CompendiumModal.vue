<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { uuidv4 } from "../../../core/utils";
import Modal from "../../../core/components/modals/Modal.vue";
import { useModal } from "../../../core/plugins/modals/plugin";
import { http } from "../../../core/http";
import {
    getQeNames,
    injectQeLinks,
    invalidateQeNamesCache,
    renderQeMarkdown,
} from "../../systems/extensions/compendium";
import { chatSystem } from "../../systems/chat";
import { focusExtension } from "../../systems/extensions/ui";
import { extensionsState } from "../../systems/extensions/state";
import LoadingBar from "../../../core/components/LoadingBar.vue";
import { playerSystem } from "../../systems/players";

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t, locale } = useI18n();
const toast = useToast();
const modals = useModal();

interface CompendiumMeta {
    id: string;
    name: string;
    slug: string;
    isDefault: boolean;
}

interface CollectionMeta {
    slug: string;
    name: string;
    count: number;
}

interface ItemMeta {
    slug: string;
    name: string;
}

interface ItemFull extends ItemMeta {
    markdown: string;
}

interface SearchResult {
    compendiumId?: string;
    compendiumName?: string;
    collectionSlug: string;
    collectionName: string;
    itemSlug: string;
    itemName: string;
}

const loading = ref(true);
const compendiums = ref<CompendiumMeta[]>([]);
const defaultId = ref<string | null>(null);
const selectedCompendiumId = ref<string | null>(null);
const collectionsByComp = ref<Map<string, CollectionMeta[]>>(new Map());
const itemsByKey = ref<Map<string, ItemMeta[]>>(new Map());
const searchQuery = ref("");
const searchInCompendium = ref<string>("");
const searchResultsAll = ref<SearchResult[]>([]);
const searchCompendiumFilter = ref<string | null>(null);
const searchLoading = ref(false);
const debouncedSearchQuery = ref("");
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
const expandedComps = ref<Set<string>>(new Set());
const expandedColls = ref<Map<string, Set<string>>>(new Map());
const selectedItem = ref<{
    compendium: CompendiumMeta;
    collection: CollectionMeta;
    item: ItemFull;
} | null>(null);
const itemLoading = ref(false);
const showIndex = ref(false);
const currentIndex = ref<{ slug: string; name: string; items: { slug: string; name: string }[] }[]>([]);
const indexLoading = ref(false);
const indexCompendium = ref<CompendiumMeta | null>(null);
const expandedIndexCollections = ref<Set<string>>(new Set());
const aiConfigured = ref(false);
const aiModel = ref("");
const translateLoading = ref(false);
const activeTranslationLang = ref<string | null>(null);
const originalMarkdown = ref<string | null>(null);
const originalIndex = ref<any[] | null>(null);
const showTranslationTools = ref(false);
const translationTagContainer = ref<HTMLElement | null>(null);
const isTranslated = computed(() => !!activeTranslationLang.value);
const currentMarkdown = ref<string>("");

const installDialogOpen = ref(false);
const installName = ref("");
const installFile = ref<File | null>(null);
const installFiles = ref<{ file: File; name: string }[]>([]);
const installLoading = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

const collectionsFor = (compId: string) => collectionsByComp.value.get(compId) ?? [];
const itemsFor = (compId: string, collSlug: string) =>
    itemsByKey.value.get(`${compId}/${collSlug}`) ?? [];
const isExpanded = (compId: string, collSlug?: string) => {
    if (!collSlug) return expandedComps.value.has(compId);
    return expandedColls.value.get(compId)?.has(collSlug) ?? false;
};

const searchResultCompendiums = computed(() => {
    const seen = new Set<string>();
    const list: { id: string; name: string }[] = [];
    for (const r of searchResultsAll.value) {
        const id = r.compendiumId ?? defaultId.value ?? "";
        if (id && !seen.has(id)) {
            seen.add(id);
            list.push({ id, name: r.compendiumName ?? "?" });
        }
    }
    return list;
});

const filteredSearchResults = computed(() => {
    if (!searchCompendiumFilter.value) return searchResultsAll.value;
    return searchResultsAll.value.filter(
        (r) => (r.compendiumId ?? defaultId.value) === searchCompendiumFilter.value,
    );
});

const breadcrumb = computed(() => {
    if (!selectedItem.value) return [];
    const { compendium, collection, item } = selectedItem.value;
    const fallback = (label: string, slug: string) =>
        (label && label.trim()) ? label : (slug || "—");
    return [
        { label: fallback(compendium.name, compendium.slug), slug: compendium.slug },
        { label: fallback(collection.name, collection.slug), slug: collection.slug },
        { label: fallback(item.name, item.slug), slug: item.slug },
    ];
});

const qeNames = ref<{ name: string; compendiumSlug?: string; collectionSlug: string; itemSlug: string }[]>([]);

const selectedMarkdownHtml = computed(() => {
    const raw = currentMarkdown.value || selectedItem.value?.item.markdown || "";
    const withLinks = !qeNames.value.length
        ? raw
        : injectQeLinks(raw, qeNames.value, selectedItem.value ? [selectedItem.value.item.name] : []);
    return renderQeMarkdown(withLinks);
});

const isSearchDebouncing = computed(() => {
    return (
        searchQuery.value.trim().length > 0 &&
        debouncedSearchQuery.value !== searchQuery.value.trim()
    );
});

function formatName(name: string): string {
    return name.charAt(0).toUpperCase() + name.slice(1);
}

function handleMarkdownClick(e: MouseEvent): void {
    const target = (e.target as HTMLElement).closest("a[href^='qe:'], a[data-qe-collection]");
    if (!(target instanceof HTMLAnchorElement)) return;
    let compSlug: string | undefined;
    let collSlug: string;
    let itemSlug: string;
    const dataComp = target.getAttribute("data-qe-compendium");
    const dataColl = target.getAttribute("data-qe-collection");
    const dataSlug = target.getAttribute("data-qe-slug");
    if (dataColl && dataSlug) {
        compSlug = dataComp ?? undefined;
        collSlug = dataColl;
        itemSlug = dataSlug;
    } else {
        const href = target.getAttribute("href") ?? "";
        if (!href.startsWith("qe:")) return;
        const rest = href.slice(3);
        const parts = rest.split("/");
        if (parts.length >= 3) {
            compSlug = parts[0];
            collSlug = parts[1] ?? "";
            itemSlug = parts[2] ?? "";
        } else if (parts.length === 2) {
            collSlug = parts[0] ?? "";
            itemSlug = parts[1] ?? "";
        } else return;
    }
    e.preventDefault();
    const comp = compSlug
        ? compendiums.value.find((c) => c.slug === compSlug)
        : compendiums.value.find((c) => c.isDefault) ?? compendiums.value[0];
    if (!comp) return;
    const coll: CollectionMeta = { slug: collSlug, name: "", count: 0 };
    const item: ItemMeta = { slug: itemSlug, name: "" };
    selectItem(comp, coll, item);
}

async function toggleCompendium(compId: string): Promise<void> {
    const next = new Set(expandedComps.value);
    if (next.has(compId)) {
        next.delete(compId);
        expandedComps.value = next;
        return;
    }
    next.add(compId);
    expandedComps.value = next;
    if (collectionsByComp.value.has(compId)) return;
    try {
        const r = await http.get(
            `/api/extensions/compendium/collections?compendium=${encodeURIComponent(compId)}`,
        );
        if (r.ok) {
            const data = (await r.json()) as { collections: CollectionMeta[] };
            collectionsByComp.value = new Map(collectionsByComp.value).set(compId, data.collections);
        }
    } catch {
        /* ignore */
    }
}

/** Espande compendium e carica collezioni se necessario (senza chiudere se già aperto). */
async function ensureCompendiumExpanded(compId: string): Promise<void> {
    if (!expandedComps.value.has(compId)) {
        expandedComps.value = new Set([...expandedComps.value, compId]);
    }
    if (collectionsByComp.value.has(compId)) return;
    try {
        const r = await http.get(
            `/api/extensions/compendium/collections?compendium=${encodeURIComponent(compId)}`,
        );
        if (r.ok) {
            const data = (await r.json()) as { collections: CollectionMeta[] };
            collectionsByComp.value = new Map(collectionsByComp.value).set(compId, data.collections);
        }
    } catch {
        /* ignore */
    }
}

/** Espande collezione e carica items se necessario (senza chiudere se già aperta). */
async function ensureCollectionExpanded(compId: string, collSlug: string): Promise<void> {
    const set = expandedColls.value.get(compId);
    if (!set?.has(collSlug)) {
        const next = new Map(expandedColls.value);
        next.set(compId, new Set([...(next.get(compId) ?? []), collSlug]));
        expandedColls.value = next;
    }
    const key = `${compId}/${collSlug}`;
    if (itemsByKey.value.has(key)) return;
    try {
        const r = await http.get(
            `/api/extensions/compendium/collections/${encodeURIComponent(collSlug)}/items?compendium=${encodeURIComponent(compId)}`,
        );
        if (r.ok) {
            const data = (await r.json()) as { items: ItemMeta[] };
            itemsByKey.value = new Map(itemsByKey.value).set(key, data.items);
        }
    } catch {
        /* ignore */
    }
}

async function toggleCollection(compId: string, collSlug: string): Promise<void> {
    const next = new Map(expandedColls.value);
    const set = new Set(next.get(compId) ?? []);
    if (set.has(collSlug)) {
        set.delete(collSlug);
    } else {
        set.add(collSlug);
        const key = `${compId}/${collSlug}`;
        if (!itemsByKey.value.has(key)) {
            try {
                const r = await http.get(
                    `/api/extensions/compendium/collections/${encodeURIComponent(collSlug)}/items?compendium=${encodeURIComponent(compId)}`,
                );
                if (r.ok) {
                    const data = (await r.json()) as { items: ItemMeta[] };
                    itemsByKey.value = new Map(itemsByKey.value).set(key, data.items);
                }
            } catch {
                /* ignore */
            }
        }
    }
    next.set(compId, set);
    expandedColls.value = next;
}

async function selectItem(
    compendium: CompendiumMeta,
    collection: CollectionMeta,
    item: ItemMeta,
): Promise<void> {
    showIndex.value = false;
    itemLoading.value = true;
    try {
        const r = await http.get(
            `/api/extensions/compendium/item?compendium=${encodeURIComponent(compendium.id)}&collection=${encodeURIComponent(collection.slug)}&slug=${encodeURIComponent(item.slug)}`,
        );
        if (r.ok) {
            const full = (await r.json()) as ItemFull;
            originalMarkdown.value = null;
            activeTranslationLang.value = null;
            currentMarkdown.value = "";
            selectedItem.value = { compendium, collection, item: full };
            await checkTranslation("item");
        }
    } catch {
        /* ignore */
    } finally {
        itemLoading.value = false;
    }
}

async function selectFromSearch(result: SearchResult): Promise<void> {
    showIndex.value = false;
    const compId = result.compendiumId ?? defaultId.value;
    if (!compId) return;
    const comp = compendiums.value.find((c) => c.id === compId);
    if (!comp) return;
    expandedComps.value = new Set([...expandedComps.value, compId]);
    await toggleCompendium(compId);
    expandedColls.value = new Map(expandedColls.value).set(
        compId,
        new Set([...(expandedColls.value.get(compId) ?? []), result.collectionSlug]),
    );
    const key = `${compId}/${result.collectionSlug}`;
    if (!itemsByKey.value.has(key)) {
        try {
            const r = await http.get(
                `/api/extensions/compendium/collections/${encodeURIComponent(result.collectionSlug)}/items?compendium=${encodeURIComponent(compId)}`,
            );
            if (r.ok) {
                const data = (await r.json()) as { items: ItemMeta[] };
                itemsByKey.value = new Map(itemsByKey.value).set(key, data.items);
            }
        } catch {
            /* ignore */
        }
    }
    const coll: CollectionMeta = {
        slug: result.collectionSlug,
        name: result.collectionName,
        count: 0,
    };
    const itemMeta: ItemMeta = { slug: result.itemSlug, name: result.itemName };
    await selectItem(comp, coll, itemMeta);
    searchQuery.value = "";
    debouncedSearchQuery.value = "";
}

async function showCompendiumIndex(comp: CompendiumMeta): Promise<void> {
    selectedItem.value = null;
    showIndex.value = true;
    indexLoading.value = true;
    indexCompendium.value = comp;
    currentIndex.value = [];
    expandedIndexCollections.value.clear();
    try {
        const r = await http.get(
            `/api/extensions/compendium/index?compendium=${encodeURIComponent(comp.id)}`,
        );
        if (r.ok) {
            const data = (await r.json()) as { index: any[] };
            originalIndex.value = null;
            activeTranslationLang.value = null;
            currentMarkdown.value = "";
            currentIndex.value = data.index;
            await checkTranslation("index");
        }
    } catch {
        /* ignore */
    } finally {
        indexLoading.value = false;
    }
}

async function selectItemBySlug(collSlug: string, itemSlug: string): Promise<void> {
    if (!indexCompendium.value) return;
    const coll: CollectionMeta = { slug: collSlug, name: "", count: 0 };
    const item: ItemMeta = { slug: itemSlug, name: "" };
    await selectItem(indexCompendium.value, coll, item);
}

function toggleIndexCollection(collSlug: string): void {
    if (expandedIndexCollections.value.has(collSlug)) {
        expandedIndexCollections.value.delete(collSlug);
    } else {
        expandedIndexCollections.value.add(collSlug);
    }
}

async function setDefault(compId: string): Promise<void> {
    try {
        const r = await http.put(
            `/api/extensions/compendium/compendiums/${encodeURIComponent(compId)}/default`,
        );
        if (r.ok) {
            defaultId.value = compId;
            for (const c of compendiums.value) {
                (c as { isDefault: boolean }).isDefault = c.id === compId;
            }
            invalidateQeNamesCache();
            qeNames.value = await getQeNames();
        }
    } catch {
        /* ignore */
    }
}

async function uninstallCompendium(comp: CompendiumMeta): Promise<void> {
    const ok = await modals.confirm(
        t("game.ui.extensions.CompendiumModal.uninstall_confirm_title"),
        t("game.ui.extensions.CompendiumModal.uninstall_confirm", { name: comp.name }),
    );
    if (!ok) return;
    try {
        const r = await http.delete(
            `/api/extensions/compendium/compendiums/${encodeURIComponent(comp.id)}`,
        );
        if (r.ok) {
            toast.success(t("game.ui.extensions.CompendiumModal.uninstall_success"));
            if (selectedItem.value?.compendium.id === comp.id) selectedItem.value = null;
            await loadCompendiums();
        }
    } catch {
        toast.error(t("game.ui.extensions.CompendiumModal.install_error"));
    }
}

function openInstallDialog(): void {
    installName.value = "";
    installFile.value = null;
    installFiles.value = [];
    installDialogOpen.value = true;
    setTimeout(() => fileInputRef.value?.click(), 100);
}

function onInstallFileChange(e: Event): void {
    const input = e.target as HTMLInputElement;
    const files = input.files;
    if (files && files.length > 0) {
        if (files.length === 1) {
            installFile.value = files[0]!;
            installFiles.value = [];
            if (!installName.value) installName.value = files[0]!.name.replace(/\.json$/i, "") || "Compendium";
        } else {
            installFile.value = null;
            installName.value = "";
            installFiles.value = Array.from(files)
                .filter((f) => f.name.toLowerCase().endsWith(".json"))
                .map((f) => ({ file: f, name: f.name.replace(/\.json$/i, "") || "Compendium" }));
        }
    }
    input.value = "";
}

async function checkAiConfig(): Promise<void> {
    try {
        const r = await http.get("/api/extensions/openrouter/settings");
        if (r.ok) {
            const data = await r.json();
            aiConfigured.value = data.hasApiKey || data.hasGoogleKey;
            aiModel.value = data.model || "google/gemini-2.0-flash-001";
        }
    } catch {
        aiConfigured.value = false;
    }
}

async function checkTranslation(type: "item" | "index"): Promise<void> {
    const compId = type === "item" ? selectedItem.value?.compendium.id : indexCompendium.value?.id;
    if (!compId) return;
    
    const lang = locale.value;
    let url = `/api/extensions/compendium/translations?compendium=${encodeURIComponent(compId)}&lang=${encodeURIComponent(lang)}&type=${type}`;
    if (type === "item" && selectedItem.value) {
        url += `&collection=${encodeURIComponent(selectedItem.value.collection.slug)}&slug=${encodeURIComponent(selectedItem.value.item.slug)}`;
    }
    
    try {
        const r = await http.get(url);
        if (r.ok) {
            const data = await r.json();
            if (data.content) {
                if (type === "item" && selectedItem.value) {
                    if (originalMarkdown.value === null) originalMarkdown.value = selectedItem.value.item.markdown;
                    currentMarkdown.value = data.content;
                    activeTranslationLang.value = lang;
                } else if (type === "index" && currentIndex.value.length > 0) {
                    if (originalIndex.value === null) originalIndex.value = JSON.parse(JSON.stringify(currentIndex.value));
                    currentIndex.value = JSON.parse(data.content);
                    activeTranslationLang.value = lang;
                }
            }
        }
    } catch (e) {
        console.error("Error checking translation", e);
    }
}

async function saveTranslationToDb(content: string, type: "item" | "index"): Promise<void> {
    const compId = type === "item" ? selectedItem.value?.compendium.id : indexCompendium.value?.id;
    if (!compId) return;

    const payload: any = {
        compendium: compId,
        type,
        lang: locale.value,
        content: content
    };

    if (type === "item" && selectedItem.value) {
        payload.collection = selectedItem.value.collection.slug;
        payload.slug = selectedItem.value.item.slug;
    }

    try {
        await http.postJson("/api/extensions/compendium/translations", payload);
    } catch (e) {
        console.error("Error saving translation", e);
    }
}

function revertTranslationUI(): void {
    if (!activeTranslationLang.value) return;

    const isIndex = showIndex.value;
    if (isIndex && originalIndex.value) {
        currentIndex.value = JSON.parse(JSON.stringify(originalIndex.value));
        originalIndex.value = null;
    } else if (selectedItem.value && originalMarkdown.value !== null) {
        currentMarkdown.value = originalMarkdown.value;
        originalMarkdown.value = null;
    }
    activeTranslationLang.value = null;
    showTranslationTools.value = false;
}

async function clearTranslation(): Promise<void> {
    if (!activeTranslationLang.value) return;

    // Delete from DB — only called from the tag menu "Cancella Traduzione"
    const isIndex = showIndex.value;
    const compId = isIndex ? indexCompendium.value?.id : selectedItem.value?.compendium.id;
    if (compId) {
        const lang = activeTranslationLang.value;
        const payload: any = { compendium: compId, type: isIndex ? "index" : "item", lang };
        if (!isIndex && selectedItem.value) {
            payload.collection = selectedItem.value.collection.slug;
            payload.slug = selectedItem.value.item.slug;
        }
        try {
            await http.deleteJson("/api/extensions/compendium/translations", payload);
        } catch (e) {
            console.error("Error deleting translation from db", e);
        }
    }

    revertTranslationUI();
}

async function rerunTranslation(): Promise<void> {
    await clearTranslation();
    await translateCurrentView();
}

async function translateCurrentView(): Promise<void> {
    if (translateLoading.value) return;

    if (activeTranslationLang.value === locale.value) {
        revertTranslationUI();
        return;
    }

    // Check if we have a cached translation first
    await checkTranslation(selectedItem.value ? "item" : "index");
    if (activeTranslationLang.value === locale.value) return;

    const targetLang = locale.value.startsWith("it") ? "Italian" : "English";
    console.log(`[Compendium AI] Starting translation to ${targetLang} using model ${aiModel.value}`);
    
    if (activeTranslationLang.value === locale.value) {
        toast.info("Content already translated to " + targetLang);
        return;
    }

    const systemPrompt = `You are a translator specialized in Dungeons & Dragons 5th Edition.
Translate the provided content into ${targetLang}. 
Maintain the original Markdown structure and all special tags like {@b ...}, {@i ...}, {@dice ...}, etc. 
Do NOT translate these tags or their parameters. 
Ensure terminology consistency with D&D 5e standards (e.g., "Saving Throw" -> "Tiro Salvezza" in Italian).`;

    translateLoading.value = true;
    try {
        if (selectedItem.value) {
            const raw = selectedItem.value.item.markdown;
            const r = await http.postJson("/api/extensions/openrouter/chat", {
                model: aiModel.value,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: `Translate this content:\n\n${raw}` }
                ]
            });
            if (r.ok) {
                const data = await r.json();
                const translated = data.choices?.[0]?.message?.content;
                console.log("[Compendium AI] Translation received", { length: translated?.length });
                if (translated) {
                    if (!originalMarkdown.value) originalMarkdown.value = selectedItem.value.item.markdown;
                    currentMarkdown.value = translated;
                    activeTranslationLang.value = locale.value;
                    await saveTranslationToDb(translated, "item");
                } else {
                    console.error("[Compendium AI] Empty translation response received");
                    toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
                }
            } else {
                toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
            }
        } else if (showIndex.value && currentIndex.value.length > 0) {
            const indexJson = JSON.stringify(currentIndex.value, null, 2);
            const r = await http.postJson("/api/extensions/openrouter/chat", {
                model: aiModel.value,
                messages: [
                    { role: "system", content: systemPrompt + "\nOnly translate the 'name' values in the provided JSON. Keep everything else identical." },
                    { role: "user", content: `Translate this index JSON:\n\n${indexJson}` }
                ]
            });
            if (r.ok) {
                const data = await r.json();
                const translated = data.choices?.[0]?.message?.content;
                if (translated) {
                    try {
                        const start = translated.indexOf("[");
                        const end = translated.lastIndexOf("]") + 1;
                        if (start !== -1 && end !== 0) {
                            currentIndex.value = JSON.parse(translated.substring(start, end));
                        }
                    } catch (e) {
                        console.error("Failed to parse translated index", e);
                        toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
                    }
                }
            } else {
                toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
            }
        }
    } catch (e) {
        console.error(e);
        toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
    } finally {
        translateLoading.value = false;
    }
}

function handleOutsideClick(event: MouseEvent): void {
    if (showTranslationTools.value && translationTagContainer.value && !translationTagContainer.value.contains(event.target as Node)) {
        showTranslationTools.value = false;
    }
}

onMounted(async () => {
    await loadCompendiums();
    await checkAiConfig();
    window.addEventListener("mousedown", handleOutsideClick);
});

onUnmounted(() => {
    window.removeEventListener("mousedown", handleOutsideClick);
});

async function doInstall(): Promise<void> {
    if (installFiles.value.length > 0) {
        installLoading.value = true;
        let okCount = 0;
        let errCount = 0;
        try {
            for (const { file, name } of installFiles.value) {
                const form = new FormData();
                form.append("name", name.trim() || "Compendium");
                form.append("file", file);
                const r = await http.post(
                    "/api/extensions/compendium/compendiums",
                    form,
                );
                if (r.ok) okCount++;
                else errCount++;
            }
            if (errCount === 0) {
                toast.success(
                    okCount === 1
                        ? t("game.ui.extensions.CompendiumModal.install_success")
                        : t("game.ui.extensions.CompendiumModal.install_multi_success", { count: okCount }),
                );
                installDialogOpen.value = false;
                invalidateQeNamesCache();
                await loadCompendiums();
            } else {
                toast.error(
                    errCount === installFiles.value.length
                        ? t("game.ui.extensions.CompendiumModal.install_error")
                        : t("game.ui.extensions.CompendiumModal.install_partial", { ok: okCount, err: errCount }),
                );
                if (okCount > 0) {
                    invalidateQeNamesCache();
                    await loadCompendiums();
                }
            }
        } catch {
            toast.error(t("game.ui.extensions.CompendiumModal.install_error"));
        } finally {
            installLoading.value = false;
        }
        return;
    }
    if (!installFile.value || !installName.value.trim()) return;
    installLoading.value = true;
    try {
        const form = new FormData();
        form.append("name", installName.value.trim());
        form.append("file", installFile.value);
        const r = await http.post(
            "/api/extensions/compendium/compendiums",
            form,
        );
        if (r.ok) {
            toast.success(t("game.ui.extensions.CompendiumModal.install_success"));
            installDialogOpen.value = false;
            invalidateQeNamesCache();
            await loadCompendiums();
        } else {
            const err = (await r.json()) as { error?: string };
            toast.error(err.error ?? t("game.ui.extensions.CompendiumModal.install_error"));
        }
    } catch {
        toast.error(t("game.ui.extensions.CompendiumModal.install_error"));
    } finally {
        installLoading.value = false;
    }
}

async function loadCompendiums(): Promise<void> {
    loading.value = true;
    try {
        const rComp = await http.get("/api/extensions/compendium/compendiums");
        if (rComp.ok) {
            const data = (await rComp.json()) as {
                compendiums: CompendiumMeta[];
                defaultId: string | null;
            };
            compendiums.value = data.compendiums;
            defaultId.value = data.defaultId;
            qeNames.value = await getQeNames();
            const openItem = extensionsState.raw.compendiumOpenItem;
            if (openItem && compendiums.value.length > 0) {
                const comp = openItem.compendiumSlug
                    ? compendiums.value.find((c) => c.slug === openItem.compendiumSlug)
                    : compendiums.value.find((c) => c.isDefault) ?? compendiums.value[0];
                if (comp) {
                    selectedCompendiumId.value = comp.id;
                    expandedComps.value = new Set([comp.id]);
                    await toggleCompendium(comp.id);
                    const colls = collectionsByComp.value.get(comp.id) ?? [];
                    const targetColl = colls.find((c) => c.slug === openItem.collectionSlug);
                    if (targetColl) {
                        expandedColls.value = new Map(expandedColls.value).set(
                            comp.id,
                            new Set([...(expandedColls.value.get(comp.id) ?? []), targetColl.slug]),
                        );
                        await toggleCollection(comp.id, targetColl.slug);
                        const items = itemsByKey.value.get(`${comp.id}/${targetColl.slug}`) ?? [];
                        const itemMeta = items.find((i) => i.slug === openItem.itemSlug);
                        if (itemMeta) await selectItem(comp, targetColl, itemMeta);
                    }
                }
                extensionsState.mutableReactive.compendiumOpenItem = undefined;
            } else if (compendiums.value.length > 0) {
                const first = compendiums.value[0]!;
                selectedCompendiumId.value = first.id;
                expandedComps.value = new Set([first.id]);
                await toggleCompendium(first.id);
            }
        }
    } catch {
        compendiums.value = [];
    } finally {
        loading.value = false;
    }
}

async function runSearch(q: string, compendiumId?: string | null): Promise<void> {
    searchLoading.value = true;
    searchCompendiumFilter.value = null;
    try {
        const params = new URLSearchParams({ q });
        if (compendiumId) params.set("compendium", compendiumId);
        const r = await http.get(
            `/api/extensions/compendium/search?${params.toString()}`,
        );
        if (r.ok) {
            const data = (await r.json()) as { results: SearchResult[] };
            searchResultsAll.value = data.results;
        } else {
            searchResultsAll.value = [];
        }
    } catch {
        searchResultsAll.value = [];
    } finally {
        searchLoading.value = false;
    }
}

function setSearchCompendiumFilter(id: string | null): void {
    searchCompendiumFilter.value = searchCompendiumFilter.value === id ? null : id;
}

function shareToChat(): void {
    if (!selectedItem.value) return;
    const { compendium, collection, item } = selectedItem.value;
    const label = `${item.name} (${formatName(collection.name)})`;
    const link = compendiums.value.length > 1
        ? `[📖 ${label}](qe:${compendium.slug}/${collection.slug}/${item.slug})`
        : `[📖 ${label}](qe:${collection.slug}/${item.slug})`;
    chatSystem.addMessage(
        uuidv4(),
        playerSystem.getCurrentPlayer()?.name ?? "?",
        [link],
        true,
    );
    toast.success(t("game.ui.extensions.CompendiumModal.share_success"));
}

watch(
    () => props.visible,
    (visible) => {
        if (visible) loadCompendiums();
    },
);

watch(
    () => [extensionsState.raw.compendiumOpenItem, compendiums.value.length] as const,
    async ([openItem]) => {
        if (!openItem || !props.visible || !compendiums.value.length) return;
        const comp = openItem.compendiumSlug
            ? compendiums.value.find((c) => c.slug === openItem.compendiumSlug)
            : compendiums.value.find((c) => c.isDefault) ?? compendiums.value[0];
        if (!comp) return;
        await ensureCompendiumExpanded(comp.id);
        const colls = collectionsByComp.value.get(comp.id) ?? [];
        const targetColl = colls.find((c) => c.slug === openItem.collectionSlug);
        if (targetColl) {
            await ensureCollectionExpanded(comp.id, targetColl.slug);
            const items = itemsByKey.value.get(`${comp.id}/${targetColl.slug}`) ?? [];
            const itemMeta = items.find((i) => i.slug === openItem.itemSlug);
            if (itemMeta) await selectItem(comp, targetColl, itemMeta);
        }
        extensionsState.mutableReactive.compendiumOpenItem = undefined;
    },
    { immediate: true },
);

watch(searchQuery, (newVal) => {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    const trimmed = newVal.trim();
    if (trimmed === "") {
        debouncedSearchQuery.value = "";
        searchResultsAll.value = [];
        searchCompendiumFilter.value = null;
        return;
    }
    searchDebounceTimer = setTimeout(() => {
        debouncedSearchQuery.value = trimmed;
        searchDebounceTimer = null;
        runSearch(trimmed, searchInCompendium.value || undefined);
    }, 300);
});

onMounted(() => {
    if (props.visible) loadCompendiums();
});
</script>

<template>
    <Modal
        v-if="visible"
        ref="modalRef"
        :visible="visible"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="compendium-modal"
        @close="onClose"
        @focus="focusExtension('compendium')"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">{{ t("game.ui.extensions.CompendiumModal.title") }}</h2>
                <div class="ext-modal-actions">
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="ext-modal-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="ext-modal-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="ext-modal-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="onClose"
                    />
                </div>
            </div>
        </template>
        <div class="ext-modal-body-wrapper">
            <div v-if="installLoading || translateLoading" class="ext-progress-top-container">
                <LoadingBar :progress="100" indeterminate height="6px" />
            </div>
            <div class="qe-body">
            <div class="ext-toolbar-bar ext-search-bar">
                <font-awesome-icon icon="search" class="ext-search-icon" />
                <select
                    v-if="compendiums.length > 1"
                    v-model="searchInCompendium"
                    class="ext-ui-select"
                >
                    <option value="">{{ t("game.ui.extensions.CompendiumModal.filter_all") }}</option>
                    <option
                        v-for="comp in compendiums"
                        :key="comp.id"
                        :value="comp.id"
                    >
                        {{ comp.name }}
                    </option>
                </select>
                <input
                    v-model="searchQuery"
                    type="text"
                    class="ext-search-input"
                    :placeholder="t('game.ui.extensions.CompendiumModal.search_placeholder')"
                />
                <button
                    type="button"
                    class="ext-search-add-btn"
                    :title="t('game.ui.extensions.CompendiumModal.install_compendium')"
                    @click="openInstallDialog"
                >
                    <font-awesome-icon icon="plus" />
                </button>
                <button
                    v-if="aiConfigured && (selectedItem || (showIndex && currentIndex.length > 0))"
                    type="button"
                    class="ext-search-add-btn translate-btn"
                    :class="{ 'is-active': isTranslated }"
                    :title="t('game.ui.extensions.CompendiumModal.translate')"
                    :disabled="translateLoading"
                    @click="translateCurrentView"
                >
                    <font-awesome-icon icon="language" />
                </button>
            </div>

            <div v-if="loading" class="ext-ui-loading qe-loading">
                {{ t("game.ui.extensions.CompendiumModal.loading") }}
            </div>

            <div v-else-if="searchQuery.trim()" class="qe-search-results">
                <div
                    v-if="isSearchDebouncing || searchLoading"
                    class="ext-ui-empty qe-search-empty"
                >
                    {{ t("game.ui.extensions.CompendiumModal.searching") }}
                </div>
                <template v-else>
                    <div
                        v-if="searchResultCompendiums.length > 1"
                        class="qe-search-filters"
                    >
                        <button
                            type="button"
                            class="ext-ui-btn qe-filter-tag"
                            :class="{ active: !searchCompendiumFilter }"
                            @click="setSearchCompendiumFilter(null)"
                        >
                            {{ t("game.ui.extensions.CompendiumModal.filter_all") }}
                        </button>
                        <button
                            v-for="comp in searchResultCompendiums"
                            :key="comp.id"
                            type="button"
                            class="ext-ui-btn qe-filter-tag"
                            :class="{ active: searchCompendiumFilter === comp.id }"
                            @click="setSearchCompendiumFilter(comp.id)"
                        >
                            {{ comp.name }}
                        </button>
                    </div>
                    <div
                        v-for="(result, idx) in filteredSearchResults"
                        :key="`${result.compendiumId ?? ''}-${result.collectionSlug}-${result.itemSlug}-${idx}`"
                        class="ext-ui-list-item qe-search-result-item"
                        @click="selectFromSearch(result)"
                    >
                        <div class="ext-ui-list-item-content ext-ui-stacked">
                            <span class="ext-ui-list-item-subtitle">
                                {{ compendiums.length > 1 && result.compendiumName
                                    ? `${result.compendiumName} › ${formatName(result.collectionName)}`
                                    : formatName(result.collectionName) }}
                            </span>
                            <span class="ext-ui-list-item-name">{{ result.itemName }}</span>
                        </div>
                    </div>
                    <div v-if="filteredSearchResults.length === 0" class="ext-ui-empty qe-search-empty">
                        {{ t("game.ui.extensions.CompendiumModal.no_results") }}
                    </div>
                </template>
            </div>

            <div v-else-if="!loading && compendiums.length === 0" class="qe-empty-state">
                {{ t("game.ui.extensions.CompendiumModal.no_compendiums") }}
                <button
                    type="button"
                    class="ext-ui-btn ext-ui-btn-success"
                    @click="openInstallDialog"
                >
                    {{ t("game.ui.extensions.CompendiumModal.install_compendium") }}
                </button>
            </div>

            <div v-else-if="!loading" class="qe-main">
                <nav class="qe-tree">
                    <div
                        v-for="comp in compendiums"
                        :key="comp.id"
                        class="qe-tree-compendium"
                    >
                        <div class="qe-tree-comp-header">
                            <button
                                class="qe-tree-toggle"
                                :class="{ expanded: isExpanded(comp.id) }"
                                @click="toggleCompendium(comp.id)"
                            >
                                <font-awesome-icon
                                    :icon="isExpanded(comp.id) ? 'chevron-down' : 'chevron-right'"
                                />
                                <span class="qe-tree-comp-name" @click.stop="showCompendiumIndex(comp)">{{ comp.name }}</span>
                            </button>
                            <button
                                v-if="!comp.isDefault"
                                type="button"
                                class="ext-action-btn star"
                                :title="t('game.ui.extensions.CompendiumModal.default_compendium')"
                                @click.stop="setDefault(comp.id)"
                            >
                                <font-awesome-icon :icon="['far', 'star']" />
                            </button>
                            <button
                                v-else
                                type="button"
                                class="ext-action-btn star active"
                                :title="t('game.ui.extensions.CompendiumModal.default_compendium')"
                                @click.stop="() => {}"
                            >
                                <font-awesome-icon icon="star" />
                            </button>
                            <button
                                type="button"
                                class="ext-action-btn delete"
                                :title="t('game.ui.extensions.CompendiumModal.uninstall')"
                                @click.stop="uninstallCompendium(comp)"
                            >
                                <font-awesome-icon icon="trash-alt" />
                            </button>
                        </div>
                        <div v-show="isExpanded(comp.id)" class="qe-tree-collections">
                            <div
                                v-for="coll in collectionsFor(comp.id)"
                                :key="coll.slug"
                                class="qe-tree-collection"
                            >
                                <button
                                    class="qe-tree-toggle coll"
                                    :class="{ expanded: isExpanded(comp.id, coll.slug) }"
                                    @click="toggleCollection(comp.id, coll.slug)"
                                >
                                    <font-awesome-icon
                                        :icon="
                                            isExpanded(comp.id, coll.slug) ? 'chevron-down' : 'chevron-right'
                                        "
                                    />
                                    {{ formatName(coll.name) }}
                                    <span class="qe-tree-count">({{ coll.count }})</span>
                                </button>
                                <div
                                    v-show="isExpanded(comp.id, coll.slug)"
                                    class="qe-tree-items"
                                >
                                    <button
                                        v-for="item in itemsFor(comp.id, coll.slug)"
                                        :key="item.slug"
                                        class="qe-tree-item"
                                        :class="{
                                            active:
                                                selectedItem?.compendium.id === comp.id &&
                                                selectedItem?.collection.slug === coll.slug &&
                                                selectedItem?.item.slug === item.slug,
                                        }"
                                        @click="selectItem(comp, coll, item)"
                                    >
                                        {{ item.name }}
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </nav>
                <div class="qe-content-area">
                    <div v-if="selectedItem" class="qe-breadcrumb">
                        <div class="qe-breadcrumb-path">
                            <template v-for="(crumb, i) in breadcrumb" :key="'crumb-' + i">
                                <span v-if="i > 0" class="qe-breadcrumb-sep"> › </span>
                                <span class="qe-breadcrumb-item">{{ crumb.label }}</span>
                            </template>
                        </div>
                        <div v-if="isTranslated" class="translation-tag-container" ref="translationTagContainer">
                            <div class="translation-tag" @click.stop="showTranslationTools = !showTranslationTools">
                                <font-awesome-icon icon="check-circle" class="me-1" />
                                {{ t("game.ui.extensions.CompendiumModal.translated_to", { lang: activeTranslationLang === 'it' ? 'Italiano' : 'English' }) }}
                                <font-awesome-icon icon="chevron-down" class="ms-1" />
                            </div>
                            
                            <div v-if="showTranslationTools" class="translation-tools-popover">
                                <button class="popover-btn" @click.stop="clearTranslation">
                                    <font-awesome-icon icon="undo" /> {{ t("game.ui.extensions.CompendiumModal.clear_translation") }}
                                </button>
                                <button class="popover-btn" @click.stop="rerunTranslation">
                                    <font-awesome-icon icon="sync" /> {{ t("game.ui.extensions.CompendiumModal.rerun_translation") }}
                                </button>
                            </div>
                        </div>
                        <button
                            class="qe-share-btn"
                            :title="t('game.ui.extensions.CompendiumModal.share_to_chat')"
                            @click="shareToChat"
                        >
                            <font-awesome-icon icon="share-alt" />
                            {{ t("game.ui.extensions.CompendiumModal.share") }}
                        </button>
                    </div>
                    <div v-if="showIndex" class="qe-index-view">
                        <div v-if="indexLoading" class="qe-loading-inline">
                            {{ t("game.ui.extensions.CompendiumModal.loading") }}
                        </div>
                        <div v-else class="qe-index-container">
                            <div class="qe-index-header">
                                <h1 class="qe-index-title">{{ indexCompendium?.name }}</h1>
                                <div v-if="isTranslated" class="translation-tag-container" ref="translationTagContainer">
                                    <div class="translation-tag" @click.stop="showTranslationTools = !showTranslationTools">
                                        <font-awesome-icon icon="check-circle" class="me-1" />
                                        {{ t("game.ui.extensions.CompendiumModal.translated_to", { lang: activeTranslationLang === 'it' ? 'Italiano' : 'English' }) }}
                                        <font-awesome-icon icon="chevron-down" class="ms-1" />
                                    </div>
                                    
                                    <div v-if="showTranslationTools" class="translation-tools-popover">
                                        <button class="popover-btn" @click.stop="clearTranslation">
                                            <font-awesome-icon icon="undo" /> {{ t("game.ui.extensions.CompendiumModal.clear_translation") }}
                                        </button>
                                        <button class="popover-btn" @click.stop="rerunTranslation">
                                            <font-awesome-icon icon="sync" /> {{ t("game.ui.extensions.CompendiumModal.rerun_translation") }}
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <div class="qe-index-grid">
                                <div v-for="coll in currentIndex" :key="coll.slug" class="qe-index-coll">
                                    <h2 class="qe-index-coll-title">{{ formatName(coll.name) }}</h2>
                                    <div class="qe-index-item-list">
                                        <button 
                                            v-for="item in (expandedIndexCollections.has(coll.slug) ? coll.items : coll.items.slice(0, 10))" 
                                            :key="item.slug" 
                                            class="qe-index-item-link"
                                            @click="selectItemBySlug(coll.slug, item.slug)"
                                        >
                                            {{ item.name }}
                                        </button>
                                        <button 
                                            v-if="coll.items.length > 10 && !expandedIndexCollections.has(coll.slug)"
                                            class="qe-index-load-more"
                                            @click="toggleIndexCollection(coll.slug)"
                                        >
                                            ... {{ t("game.ui.extensions.CompendiumModal.load_all") }}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div
                        v-else-if="selectedItem"
                        class="qe-markdown"
                        @click="handleMarkdownClick"
                    >
                        <div
                            v-if="itemLoading"
                            class="qe-loading-inline"
                        >
                            {{ t("game.ui.extensions.CompendiumModal.loading") }}
                        </div>
                        <!-- eslint-disable-next-line vue/no-v-html -->
                        <div
                            v-else
                            class="qe-markdown-content"
                            v-html="selectedMarkdownHtml"
                        />
                    </div>
                    <div v-else class="qe-empty">
                        {{ t("game.ui.extensions.CompendiumModal.select_item") }}
                    </div>
                </div>
            </div>
        </div>
    </div>
</Modal>

    <Teleport to="body">
        <div v-if="installDialogOpen" class="qe-install-overlay" @click.self="installDialogOpen = false">
            <div class="qe-install-dialog">
                <h3>{{ t("game.ui.extensions.CompendiumModal.install_compendium") }}</h3>
                <p class="qe-install-hint">{{ t("game.ui.extensions.CompendiumModal.install_prompt") }}</p>
                <input
                    ref="fileInputRef"
                    type="file"
                    accept=".json,application/json"
                    multiple
                    style="display: none"
                    @change="onInstallFileChange"
                />
                <template v-if="installFiles.length > 0">
                    <div class="qe-install-field">
                        <label>{{ t("game.ui.extensions.CompendiumModal.install_multi_files", { count: installFiles.length }) }}</label>
                        <ul class="qe-install-file-list">
                            <li v-for="(item, i) in installFiles" :key="i">{{ item.file.name }} → {{ item.name }}</li>
                        </ul>
                        <button
                            type="button"
                            class="qe-install-file-btn qe-install-change-btn"
                            @click="fileInputRef?.click()"
                        >
                            {{ t("game.ui.extensions.CompendiumModal.install_change_files") }}
                        </button>
                    </div>
                    <div class="qe-install-actions">
                        <button
                            type="button"
                            class="qe-install-cancel"
                            @click="installDialogOpen = false"
                        >
                            {{ t("game.ui.extensions.CompendiumModal.install_cancel") }}
                        </button>
                        <button
                            type="button"
                            class="qe-install-submit"
                            :disabled="installLoading"
                            @click="doInstall"
                        >
                            {{ installLoading ? "..." : t("game.ui.extensions.CompendiumModal.install_submit") }}
                        </button>
                    </div>
                </template>
                <template v-else>
                    <div class="qe-install-field">
                        <label>{{ t("game.ui.extensions.CompendiumModal.compendium_name") }}</label>
                        <input v-model="installName" type="text" class="qe-install-input" />
                    </div>
                    <div class="qe-install-field">
                        <label>File JSON</label>
                        <button
                            type="button"
                            class="qe-install-file-btn"
                            @click="fileInputRef?.click()"
                        >
                            {{ installFile?.name ?? t("game.ui.extensions.CompendiumModal.install_prompt") }}
                        </button>
                    </div>
                    <div class="qe-install-actions">
                        <button
                            type="button"
                            class="qe-install-cancel"
                            @click="installDialogOpen = false"
                        >
                            {{ t("game.ui.extensions.CompendiumModal.install_cancel") }}
                        </button>
                        <button
                            type="button"
                            class="qe-install-submit"
                            :disabled="!installName.trim() || !installFile || installLoading"
                            @click="doInstall"
                        >
                            {{ installLoading ? "..." : t("game.ui.extensions.CompendiumModal.install_submit") }}
                        </button>
                    </div>
                </template>
            </div>
        </div>
    </Teleport>
</template>

<style lang="scss">
.compendium-modal {
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    resize: both;
    width: 800px;
    height: 600px;
    min-width: 500px;
    min-height: 400px;
    max-width: min(100vw, 1200px);
    max-height: min(100vh, 900px);
    overflow: hidden;
}
</style>

<style lang="scss" scoped>
.qe-body {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.qe-loading {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    font-style: italic;
}

.qe-empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    color: #666;
    text-align: center;
    padding: 2rem;

}

.qe-search-results {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem 1.5rem;

    .qe-search-filters {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin-bottom: 0.75rem;
    }

    .qe-filter-tag {
        padding: 0.25rem 0.6rem;
        font-size: 0.8rem;

        &.active {
            background: #e0e8f0;
            border-color: #888;
            color: #333;
        }
    }

    /* Search results use ext-ui-stacked (standard variant in ui.css) */

    .qe-search-empty {
        padding: 1rem;
        color: #666;
        font-style: italic;
    }
}

.qe-main {
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.qe-tree {
    width: 260px;
    flex-shrink: 0;
    border-right: 1px solid #eee;
    overflow-y: auto;
    overflow-x: hidden;
    min-height: 0;
    padding: 0.5rem 0;

    .qe-tree-compendium {
        margin-bottom: 0.5rem;
    }

    .qe-tree-comp-header {
        display: flex;
        align-items: center;
        gap: 0.25rem;
    }

    .qe-tree-toggle {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        flex: 1;
        min-width: 0;
        padding: 0.4rem 0.5rem;
        border: none;
        background: transparent;
        cursor: pointer;
        text-align: left;
        font-size: 0.95rem;
        font-weight: 600;

        &:hover {
            background: #f0f0f0;
        }

        &.coll {
            font-weight: 400;
            font-size: 0.9rem;

            .qe-tree-count {
                font-size: 0.8rem;
                color: #888;
                margin-left: auto;
            }
        }
    }

    .qe-tree-comp-header .ext-action-btn {
        flex-shrink: 0;
    }

    .qe-tree-collections {
        padding-left: 0.5rem;
        border-left: 2px solid #e0e0e0;
        margin-left: 0.75rem;
    }

    .qe-tree-collection {
        margin-bottom: 0.15rem;
    }

    .qe-tree-items {
        padding-left: 1.25rem;
    }

    .qe-tree-item {
        display: block;
        width: 100%;
        padding: 0.35rem 0.75rem;
        border: none;
        background: transparent;
        cursor: pointer;
        text-align: left;
        font-size: 0.85rem;
        border-radius: 0.2rem;

        &:hover {
            background: #f0f0f0;
        }

        &.active {
            background: #e0e8f0;
            font-weight: 500;
        }
    }
}

.qe-content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    background: #fff;
}

.qe-index-view {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 2rem;
    background: linear-gradient(135deg, #ffffff 0%, #f9fbff 100%);
}

.qe-index-container {
    max-width: 900px;
    margin: 0 auto;
}

.qe-index-title {
    font-size: 2.2rem;
    font-weight: 800;
    color: #1a2a3a;
    margin-bottom: 2rem;
    border-bottom: 3px solid #3498db;
    padding-bottom: 0.5rem;
    background: linear-gradient(to right, #1a2a3a, #3498db);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.qe-index-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 2rem;
}

.qe-index-coll {
    background: #fff;
    border-radius: 0.75rem;
    padding: 1.25rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    border: 1px solid #edf2f7;
    transition: transform 0.2s, box-shadow 0.2s;

    &:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
    }
}

.qe-index-coll-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #2d3748;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #e2e8f0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.qe-index-item-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.qe-index-item-link {
    display: block;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    padding: 0.4rem 0.6rem;
    font-size: 0.9rem;
    color: #4a5568;
    cursor: pointer;
    border-radius: 0.35rem;
    transition: background 0.2s, color 0.2s;

    &:hover {
        background: #ebf8ff;
        color: #2b6cb0;
        text-decoration: underline;
    }
}

.qe-index-load-more {
    display: block;
    width: 100%;
    text-align: left;
    background: transparent;
    border: none;
    padding: 0.4rem 0.6rem;
    font-size: 0.85rem;
    color: #3498db;
    cursor: pointer;
    font-weight: 600;
    font-style: italic;

    &:hover {
        color: #2980b9;
        text-decoration: underline;
    }
}

.qe-breadcrumb {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.5rem 1.5rem;
    background: #fafafa;
    border-bottom: 1px solid #eee;
    font-size: 0.85rem;
    color: #555;

    .qe-breadcrumb-path {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .qe-breadcrumb-sep {
        color: #999;
    }

    .qe-breadcrumb-item {
        text-transform: capitalize;
    }

    .qe-share-btn {
        display: flex;
        align-items: center;
        gap: 0.35rem;
        flex-shrink: 0;
        padding: 0.35rem 0.6rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        background: #fff;
        cursor: pointer;
        font-size: 0.8rem;

        &:hover {
            background: #f0f0f0;
            border-color: #999;
        }
    }
}

.qe-markdown {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 1rem 1.5rem;
    font-size: 0.9rem;
    line-height: 1.5;

    :deep(h1) {
        font-size: 1.4rem;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }

    :deep(h2) {
        font-size: 1.2rem;
        margin-top: 0.9rem;
        margin-bottom: 0.4rem;
    }

    :deep(h3) {
        font-size: 1.05rem;
        margin-top: 0.7rem;
        margin-bottom: 0.3rem;
    }

    :deep(table) {
        border-collapse: collapse;
        width: 100%;
        margin: 0.5rem 0;

        th,
        td {
            border: 1px solid #ddd;
            padding: 0.35rem 0.6rem;
            text-align: left;
        }

        th {
            background: #f5f5f5;
            font-weight: 600;
        }
    }

    :deep(p) {
        margin: 0.4rem 0;
    }

    :deep(ul),
    :deep(ol) {
        margin: 0.4rem 0;
        padding-left: 1.5rem;
    }

    :deep(a[href^="qe:"], a.qe-internal-link) {
        color: #333;
        text-decoration: underline;
        cursor: pointer;
    }

    :deep(a[href^="qe:"]:hover, a.qe-internal-link:hover) {
        color: #111;
    }
}

.qe-empty {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #888;
    font-style: italic;
}

.qe-loading-inline {
    color: #666;
    font-style: italic;
    padding: 1rem;
}

.qe-install-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10001;
}

.qe-install-dialog {
    background: #fff;
    border-radius: 0.5rem;
    padding: 1.5rem;
    min-width: 360px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);

    h3 {
        margin: 0 0 0.5rem;
        font-size: 1.1rem;
    }

    .qe-install-hint {
        margin: 0 0 1rem;
        font-size: 0.9rem;
        color: #666;
    }

    .qe-install-field {
        margin-bottom: 1rem;

        label {
            display: block;
            margin-bottom: 0.35rem;
            font-size: 0.9rem;
        }

        .qe-install-input {
            width: 100%;
            padding: 0.5rem;
            border: 1px solid #ddd;
            border-radius: 0.25rem;
        }

        .qe-install-file-list {
            margin: 0;
            padding-left: 1.25rem;
            max-height: 8rem;
            overflow-y: auto;
            font-size: 0.9rem;
            color: #555;
        }

        .qe-install-file-btn {
            width: 100%;
            padding: 0.5rem;
            border: 1px dashed #ccc;
            border-radius: 0.25rem;
            background: #fafafa;
            cursor: pointer;
            font-size: 0.9rem;
            color: #666;

            &:hover {
                background: #f0f0f0;
            }

            &.qe-install-change-btn {
                margin-top: 0.5rem;
                width: auto;
            }
        }
    }

    .qe-install-actions {
        display: flex;
        justify-content: flex-end;
        gap: 0.5rem;
        margin-top: 1rem;
    }

    .qe-install-cancel {
        padding: 0.4rem 0.8rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        background: #fff;
        cursor: pointer;
    }

    .qe-install-submit {
        padding: 0.4rem 0.8rem;
        border: 1px solid #2e7d32;
        border-radius: 0.25rem;
        background: #2e7d32;
        color: #fff;
        cursor: pointer;

        &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    }
}

.translate-btn {
    border-color: #2196f3 !important;
    color: #2196f3 !important;
    background: #fff !important;

    &.is-active {
        background: #2196f3 !important;
        color: #fff !important;
    }
}

.translate-btn:hover:not(:disabled) {
    background: #e3f2fd !important;
    &.is-active {
        background: #1976d2 !important;
    }
}

.translate-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.translation-tag-container {
    position: relative;
    display: flex;
    align-items: center;
}

.translation-tag {
    background: #e3f2fd;
    color: #1976d2;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    border: 1px solid #bbdefb;
    margin: 0 0.5rem;

    &:hover {
        background: #bbdefb;
    }
}

.translation-tools-popover {
    position: absolute;
    top: 100%;
    left: 0.5rem;
    background: white;
    border: 1px solid #ccc;
    border-radius: 4px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    z-index: 100;
    margin-top: 0.25rem;
    display: flex;
    flex-direction: column;
    padding: 4px;
    min-width: 150px;
}

.popover-btn {
    border: none;
    background: transparent;
    padding: 0.5rem;
    text-align: left;
    cursor: pointer;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 2px;

    &:hover {
        background: #f5f5f5;
    }

    svg {
        width: 14px;
    }
}

.ms-1 { margin-left: 0.25rem !important; }
.me-1 { margin-right: 0.25rem !important; }

.qe-index-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
}
</style>
