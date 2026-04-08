<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { uuidv4 } from "../../../core/utils";
import Modal from "../../../core/components/modals/Modal.vue";
import { useModal } from "../../../core/plugins/modals/plugin";
import { http } from "../../../core/http";
import { normalizeToPaLocale } from "../../../core/paUiLocales";
import {
    applyCompendiumResolverMap,
    ensureQeLinksCompendiumContext,
    getQeNames,
    injectQeLinks,
    invalidateQeNamesCache,
    parseQePathSegments,
    renderQeMarkdown,
} from "../../systems/extensions/compendium";
import { chatSystem } from "../../systems/chat";
import { focusExtension } from "../../systems/extensions/ui";
import { extensionsState } from "../../systems/extensions/state";
import LoadingBar from "../../../core/components/LoadingBar.vue";
import GroupedAutocomplete from "./components/GroupedAutocomplete.vue";
import { playerSystem } from "../../systems/players";
import type { ApiNote, ApiNoteRoom } from "../../../apiTypes";
import { coreStore } from "../../../store/core";
import { gameState } from "../../systems/game/state";
import { noteSystem } from "../../systems/notes";
import { openNoteManager } from "../../systems/notes/ui";
import type { NoteId } from "../../systems/notes/types";
import { NoteManagerMode } from "../../systems/notes/types";
import { assetSystem } from "../../../assets";
import { getFolderByPath } from "../../../assets/emits";
import { assetState } from "../../../assets/state";
import { socket } from "../../../assets/socket";
import type { DropAssetInfo } from "../../dropAsset";
import type { IndexCollNode } from "./compendium/indexTree";
import {
    collectLeafItemsFromIndexNodes,
    findIndexNodeBySlug,
    findItemNameInIndexTree,
    indexNodeHasVisibleBranchContent as indexBranchHasVisibleContent,
    isBranchDirectlyTranslated,
    isGlobalIndexFullyTranslatedRoots,
    isSubtreeFullyTranslatedForSlug,
} from "./compendium/indexTree";
import { useCompendiumTranslation } from "./compendium/useCompendiumTranslation";

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
    parentSlug: string | null;
    count: number;
}

interface ItemMeta {
    slug: string;
    name: string;
}

interface ItemFull extends ItemMeta {
    markdown: string;
    tags?: Record<string, { id: number; name: string }[]>;
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
/** Barra superiore (standard estensioni) durante fetch sidebar: collezioni / voci numerose. */
const treeLoadingDepth = ref(0);
const treeLoading = computed(() => treeLoadingDepth.value > 0);

async function withTreeLoad<T>(fn: () => Promise<T>): Promise<T> {
    treeLoadingDepth.value++;
    try {
        return await fn();
    } finally {
        treeLoadingDepth.value--;
    }
}

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
const nextItem = ref<{
    itemSlug: string;
    itemName: string;
    collectionSlug: string;
    collectionName: string;
} | null>(null);
const prevItem = ref<{
    itemSlug: string;
    itemName: string;
    collectionSlug: string;
    collectionName: string;
} | null>(null);
const itemLoading = ref(false);
const showIndex = ref(false);
/** Merge traduzione indice (DB/AI); null = nessuna traduzione salvata per questo compendio. */
const translatedIndexOverlay = ref<IndexCollNode[] | null>(null);
const SHOW_TRANSLATED_STORAGE_KEY = "pa-compendium-show-translated";
/** Preferenza utente: mostrare nomi/testi tradotti ove presenti (non si disattiva da sola). */
const showTranslatedContent = ref(true);
/** Se valorizzato, l’indice mostra solo il ramo di questa collezione (sotto-albero). */
const indexFocusCollectionSlug = ref<string | null>(null);

function indexOverlayForStatus(): IndexCollNode[] {
    return translatedIndexOverlay.value ?? (canonicalIndex.value as IndexCollNode[]);
}

const indexTreeForDisplay = computed((): IndexCollNode[] => {
    const canon = canonicalIndex.value as IndexCollNode[];
    if (showTranslatedContent.value && translatedIndexOverlay.value != null) {
        return translatedIndexOverlay.value;
    }
    return canon;
});

function isIndexBranchTranslated(slug: string): boolean {
    return isBranchDirectlyTranslated(canonicalIndex.value, indexOverlayForStatus(), slug);
}

function isIndexBranchFullyTranslated(slug: string): boolean {
    return isSubtreeFullyTranslatedForSlug(canonicalIndex.value, indexOverlayForStatus(), slug);
}

function isGlobalIndexFullyTranslated(): boolean {
    return isGlobalIndexFullyTranslatedRoots(canonicalIndex.value, indexOverlayForStatus());
}

function findItemNameInIndex(collectionSlug: string, itemSlug: string): string | null {
    return findItemNameInIndexTree(indexTreeForDisplay.value, collectionSlug, itemSlug);
}

/** Nome collezione come nell’indice mostrato (canonico o tradotto secondo il toggle). */
function collectionLabelFromIndexTree(slug: string, apiName: string): string {
    const node = findIndexNodeBySlug(indexTreeForDisplay.value, slug);
    if (node?.name?.trim()) return formatName(node.name);
    const a = apiName?.trim();
    return a ? a : slug || "—";
}

function displayAdjacentItemName(entry: {
    itemSlug: string;
    collectionSlug: string;
    itemName: string;
} | null): string {
    if (!entry) return "";
    if (!showTranslatedContent.value) return entry.itemName;
    const fromIndex = findItemNameInIndex(entry.collectionSlug, entry.itemSlug);
    return fromIndex ?? entry.itemName;
}

/** Stesso flusso di executeIndexTranslationBatch: prima voci foglia (n/tot, salta cache), poi nomi indice. */
async function completeIndexTranslation(): Promise<void> {
    if (translateLoading.value || !aiConfigured.value || !indexCompendium.value) return;
    showTranslationTools.value = false;
    const targetCode = effectiveCompendiumTargetLang();
    await checkTranslation("index");
    const roots = displayedIndex.value as IndexCollNode[];
    if (roots.length === 0) return;
    const leafItems = collectLeafItemsFromIndexNodes(roots);
    await executeIndexTranslationBatch({ leafItems, targetCode, roots });
}

/** L’indice JSON può avere voci/sotto-rami anche se l’API collections non li espone come figli. */
function indexNodeHasVisibleBranchContent(slug: string): boolean {
    return indexBranchHasVisibleContent(canonicalIndex.value as IndexCollNode[], slug);
}

async function openSubcollIndexFromIndex(subColl: IndexCollNode): Promise<void> {
    const comp = indexCompendium.value;
    if (!comp) return;
    const real = collectionsFor(comp.id).find((c: CollectionMeta) => c.slug === subColl.slug);
    const itemCount = subColl.items?.length ?? 0;
    const subColCount = subColl.collections?.length ?? 0;
    const fromIndex = itemCount + subColCount;
    const coll: CollectionMeta = real
        ? { ...real, count: Math.max(real.count ?? 0, fromIndex) }
        : {
              slug: subColl.slug,
              name: subColl.name,
              parentSlug: null,
              count: fromIndex,
          };
    await showCollectionIndex(comp, coll);
}

const displayedIndex = computed(() => {
    const full = indexTreeForDisplay.value;
    if (!indexFocusCollectionSlug.value) return full;
    const node = findIndexNodeBySlug(full, indexFocusCollectionSlug.value);
    return node ? [node] : full;
});

const indexLoading = ref(false);
const indexCompendium = ref<CompendiumMeta | null>(null);
const indexMetadata = ref<Record<string, string>>({});
const expandedIndexCollections = ref<Set<string>>(new Set());
const aiConfigured = ref(false);
const aiModel = ref("");
/** Max output tokens (from AI Generator settings) for translation requests. */
const aiMaxTokens = ref(8192);
const translateLoading = ref(false);
/** Progress during recursive index translation: current/total entries. */
const batchTranslateProgress = ref<{ current: number; total: number } | null>(null);
const activeTranslationLang = ref<string | null>(null);
const originalMarkdown = ref<string | null>(null);
const sidebarCollapsed = ref(false);
const originalIndex = ref<any[] | null>(null);
/** Indice completo dall’API (senza traduzione); base per merge con traduzione e per ripristino. */
const canonicalIndex = ref<IndexCollNode[]>([]);
const showTranslationTools = ref(false);
const translationTagContainer = ref<HTMLElement | null>(null);
/** AI Generator: compendium translation source (`auto` = detect) and optional target (`null` = same as UI). */
const compendiumTranslateSource = ref<"auto" | string>("auto");
const compendiumTranslateTarget = ref<string | null>(null);

function effectiveCompendiumTargetLang(): string {
    return compendiumTranslateTarget.value ?? normalizeToPaLocale(locale.value);
}

const translationTargetLabel = computed(() => {
    const code = effectiveCompendiumTargetLang();
    return t(`game.ui.extensions.OpenRouterModal.locale_${code}`);
});

// Global tag filter state
interface GlobalTag { id: number; name: string; compendiumId: string; }
interface GlobalTagCategory { name: string; tags: GlobalTag[]; }
const allTagCategories = ref<GlobalTagCategory[]>([]);
const selectedTagIds = ref<Set<number>>(new Set());
const showTagDropdown = ref(false);

const selectedTagIdsArray = computed({
    get: () => Array.from(selectedTagIds.value),
    set: (newList: (string | number)[]) => {
        selectedTagIds.value = new Set(newList.map(Number));
        void refetchAllCollections();
        void refetchAllVisibleItems();
    }
});

const flatTags = computed(() => {
    return allTagCategories.value.flatMap(cat => 
        cat.tags.map(tag => ({
            id: tag.id,
            title: tag.name,
            category: cat.name
        }))
    );
});

const hasActiveTagFilters = computed(() => selectedTagIds.value.size > 0);


function clearTagFilters(): void {
    selectedTagIds.value = new Set();
    showTagDropdown.value = false; // Chiudi il vassoio
    void refetchAllCollections();
    void refetchAllVisibleItems();
}


function toggleTagInFilter(tagId: number): void {
    const next = new Set(selectedTagIds.value);
    if (next.has(tagId)) next.delete(tagId);
    else next.add(tagId);
    selectedTagIds.value = next;
    void refetchAllCollections();
    void refetchAllVisibleItems();
    if (debouncedSearchQuery.value.trim()) {
        void runSearch(debouncedSearchQuery.value.trim(), searchInCompendium.value || undefined);
    }
}

/** Traduzione salvata in DB per la vista corrente (indice o voce). */
const hasSavedTranslation = computed(() => {
    if (showIndex.value && canonicalIndex.value.length > 0) {
        return translatedIndexOverlay.value != null;
    }
    if (selectedItem.value) {
        return currentMarkdown.value.trim().length > 0;
    }
    return false;
});

/** Titolo sotto il breadcrumb: con modalità tradotta attiva usa il nome dall’indice se presente, altrimenti il nome API. */
const displayedItemTitle = computed(() => {
    const si = selectedItem.value;
    if (!si) return "";
    const { collection, item } = si;
    if (!showTranslatedContent.value) {
        return item.name?.trim() || item.slug || "—";
    }
    const fromIdx = findItemNameInIndex(collection.slug, item.slug);
    return fromIdx?.trim() || item.name?.trim() || item.slug || "—";
});

const currentMarkdown = ref<string>("");

const {
    checkTranslation,
    clearTranslation,
    runTranslateIndexRecursiveBatch,
    translateIndexJsonOnly,
    translateSingleItemMarkdown,
} = useCompendiumTranslation({
    toast,
    t,
    getEffectiveTargetLang: effectiveCompendiumTargetLang,
    compendiumTranslateSource,
    activeTranslationLang,
    originalMarkdown,
    originalIndex,
    canonicalIndex,
    translatedIndexOverlay,
    currentMarkdown,
    selectedItem,
    indexCompendium,
    showIndex,
    indexFocusCollectionSlug,
    showTranslationTools,
    translateLoading,
    batchTranslateProgress,
    aiModel,
    aiMaxTokens,
});






const installDialogOpen = ref(false);
const installName = ref("");
const installFile = ref<File | null>(null);
const installFiles = ref<{ file: File; name: string }[]>([]);
const installAssets = ref(false);
const assetZipFile = ref<File | null>(null);
const installLoading = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const assetZipInputRef = ref<HTMLInputElement | null>(null);

const sidebarWidth = ref(260);
let isResizing = false;
let resizeStartX = 0;
let resizeStartWidth = 0;

function startResize(e: MouseEvent): void {
    isResizing = true;
    resizeStartX = e.clientX;
    resizeStartWidth = sidebarWidth.value;
    document.addEventListener("mousemove", onResize);
    document.addEventListener("mouseup", stopResize);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
}

function onResize(e: MouseEvent): void {
    if (!isResizing) return;
    const delta = e.clientX - resizeStartX;
    sidebarWidth.value = Math.min(500, Math.max(150, resizeStartWidth + delta));
}

function stopResize(): void {
    isResizing = false;
    document.removeEventListener("mousemove", onResize);
    document.removeEventListener("mouseup", stopResize);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
}

const collectionsFor = (compId: string) => collectionsByComp.value.get(compId) ?? [];
const rootCollectionsFor = (compId: string) => collectionsFor(compId).filter((c: CollectionMeta) => !c.parentSlug);
const subCollectionsFor = (compId: string, parentSlug: string) => collectionsFor(compId).filter((c: CollectionMeta) => c.parentSlug === parentSlug);

const itemsFor = (compId: string, collSlug: string) =>
    itemsByKey.value.get(`${compId}/${collSlug}`) ?? [];

const interleavedChildrenFor = (compId: string, collSlug: string) => {
    const subs = subCollectionsFor(compId, collSlug).map((c: CollectionMeta) => ({ ...c, type: "collection" as const }));
    const items = itemsFor(compId, collSlug).map((i: ItemMeta) => ({ ...i, type: "item" as const }));
    return [...subs, ...items].sort((a, b: any) => ((a as any).order ?? 0) - ((b as any).order ?? 0));
};
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
    list.sort((a, b) => {
        const def = defaultId.value;
        if (def) {
            if (a.id === def && b.id !== def) return -1;
            if (b.id === def && a.id !== def) return 1;
        }
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
    return list;
});

const filteredSearchResults = computed(() => {
    if (!searchCompendiumFilter.value) return searchResultsAll.value;
    return searchResultsAll.value.filter(
        (r: SearchResult) => (r.compendiumId ?? defaultId.value) === searchCompendiumFilter.value,
    );
});

const breadcrumb = computed(() => {
    if (!selectedItem.value) return [];
    const { compendium, collection, item } = selectedItem.value;
    const fallback = (label: string, slug: string) =>
        (label && label.trim()) ? label : (slug || "—");

    const crumbs: { label: string; slug: string; type: "compendium" | "collection" | "item" }[] = [
        { label: fallback(compendium.name, compendium.slug), slug: compendium.slug, type: "compendium" },
    ];

    const ancestorChain: CollectionMeta[] = [];
    let p: string | null | undefined = collection.parentSlug;
    while (p) {
        const col = collectionsFor(compendium.id).find((c: CollectionMeta) => c.slug === p);
        if (!col) break;
        ancestorChain.unshift(col);
        p = col.parentSlug;
    }
    for (const col of ancestorChain) {
        crumbs.push({
            label: collectionLabelFromIndexTree(col.slug, col.name),
            slug: col.slug,
            type: "collection",
        });
    }

    crumbs.push({
        label: collectionLabelFromIndexTree(collection.slug, collection.name),
        slug: collection.slug,
        type: "collection",
    });
    const itemNameFromIndex = findItemNameInIndex(collection.slug, item.slug);
    crumbs.push({
        label: itemNameFromIndex?.trim() ? itemNameFromIndex : fallback(item.name, item.slug),
        slug: item.slug,
        type: "item",
    });
    return crumbs;
});

/** Menu contestuale su immagine: salva in Assets sotto extensions/compendium/… (ultima cartella = slug voce) */
const imgContextMenu = ref<{ x: number; y: number; img: HTMLImageElement } | null>(null);
const addToAssetsLoading = ref(false);
const markdownContentRef = ref<HTMLElement | null>(null);

/** Dopo "Aggiungi ad asset" o lookup server, consente il drag con lo stesso payload della libreria asset. */
const compendiumDragCache = ref<Record<string, DropAssetInfo>>({});
/** Evita richieste duplicate mentre Folder.GetByPath è in corso. */
const compendiumDragResolvePending = new Set<string>();

function normalizeCompendiumImgSrc(src: string): string {
    try {
        const u = new URL(src, window.location.href);
        return u.pathname + u.search;
    } catch {
        return src;
    }
}

/** Stesso criterio di `assetSystem.upload` / server: nome voce = nome file senza ultima estensione. */
function entryNameFromUploadFilename(uploadName: string): string {
    const parts = uploadName.split(".");
    if (parts.length > 1) {
        return parts.slice(0, -1).join(".");
    }
    return uploadName;
}

function setCompendiumDropInfo(src: string, info: DropAssetInfo): void {
    const key = normalizeCompendiumImgSrc(src);
    compendiumDragCache.value = { ...compendiumDragCache.value, [key]: info };
}

function getDropInfoForCompendiumImg(img: HTMLImageElement): DropAssetInfo | null {
    const key = normalizeCompendiumImgSrc(img.src);
    return compendiumDragCache.value[key] ?? null;
}

/**
 * Cerca in libreria il file con lo stesso percorso e nome dell'upload dal compendio
 * (`extensions/compendium/…` + nome da URL). Se `Folder.GetByPath` non risolve tutto il path,
 * il server può restituire la root: in quel caso `path.length` non coincide e si ignora.
 */
async function resolveCompendiumImageInAssetLibrary(img: HTMLImageElement): Promise<void> {
    const key = normalizeCompendiumImgSrc(img.src);
    if (compendiumDragCache.value[key] || compendiumDragResolvePending.has(key)) return;
    if (!selectedItem.value) return;
    compendiumDragResolvePending.add(key);
    try {
        if (socket.disconnected) socket.connect();
        if (assetState.raw.root === undefined) {
            await assetSystem.rootCallback.wait();
        }
        const dirs = buildCompendiumAssetDirectories();
        if (dirs.length === 0) return;
        const pathStr = dirs.join("/");
        let filename: string;
        try {
            filename = filenameFromImageSrc(img.src);
        } catch {
            return;
        }
        const baseName = entryNameFromUploadFilename(filename);
        const data = await getFolderByPath(pathStr);
        if (!data.path || data.path.length !== dirs.length) {
            return;
        }
        const children = data.folder.children ?? [];
        const child = children.find(
            (c) =>
                c.fileHash &&
                c.assetId != null &&
                (c.name === baseName || c.name === filename),
        );
        if (!child?.fileHash || child.assetId == null) return;
        setCompendiumDropInfo(img.src, {
            assetHash: child.fileHash,
            entryId: child.id,
            assetId: child.assetId,
        });
    } catch {
        /* cartella assente o socket */
    } finally {
        compendiumDragResolvePending.delete(key);
    }
}

function handleCompendiumImageDragStart(e: DragEvent): void {
    const raw = e.target;
    const img =
        raw instanceof HTMLImageElement ? raw : (raw as HTMLElement | null)?.closest?.("img");
    if (!(img instanceof HTMLImageElement) || e.dataTransfer === null) return;
    const info = getDropInfoForCompendiumImg(img);
    if (!info) {
        e.preventDefault();
        toast.info(t("game.ui.extensions.CompendiumModal.drag_to_map_requires_assets"));
        return;
    }
    e.dataTransfer.setData("text/plain", JSON.stringify(info));
    e.dataTransfer.effectAllowed = "copy";
    e.dataTransfer.setDragImage(img, 0, 0);
}

const imgContextMenuAlreadyInAssets = computed(() => {
    const img = imgContextMenu.value?.img;
    if (!img) return false;
    return getDropInfoForCompendiumImg(img) !== null;
});

watch(
    () => imgContextMenu.value?.img,
    async (img) => {
        if (img instanceof HTMLImageElement) {
            await resolveCompendiumImageInAssetLibrary(img);
        }
    },
);

function sanitizeAssetFolderName(name: string): string {
    const s = name.trim().replace(/[\\/:*?"<>|]/g, "-").replace(/\s+/g, " ").trim();
    return s || "_";
}

/**
 * Percorso upload/lookup in libreria. L’ultima cartella è lo slug della voce (univoco),
 * non il nome visualizzato: così due elementi omonimi non collidono sulla stessa cartella.
 */
function buildCompendiumAssetDirectories(): string[] {
    const crumbs = breadcrumb.value;
    if (crumbs.length === 0) return ["extensions", "compendium"];
    const head = crumbs.slice(0, -1).map((c) => sanitizeAssetFolderName(c.label));
    const last = crumbs[crumbs.length - 1];
    const itemFolder = sanitizeAssetFolderName(last.slug || last.label);
    return ["extensions", "compendium", ...head, itemFolder];
}

function filenameFromImageSrc(src: string): string {
    try {
        if (src.startsWith("data:")) {
            return "compendium-image.png";
        }
        const u = new URL(src, window.location.href);
        const seg = u.pathname.split("/").filter(Boolean).pop() || "image";
        const decoded = decodeURIComponent(seg);
        return decoded || "image.png";
    } catch {
        return "compendium-image.png";
    }
}

async function blobFromImageSrc(src: string): Promise<{ blob: Blob; filename: string }> {
    let filename = filenameFromImageSrc(src);
    if (src.startsWith("data:")) {
        const comma = src.indexOf(",");
        if (comma < 0) throw new Error("invalid data uri");
        const head = src.slice(5, comma);
        const mime = head.split(";")[0].trim() || "image/png";
        const b64 = src.slice(comma + 1);
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], { type: mime });
        if (!/\.\w{2,5}$/i.test(filename)) {
            const ext =
                mime.includes("jpeg") || mime.includes("jpg")
                    ? ".jpg"
                    : mime.includes("webp")
                      ? ".webp"
                      : mime.includes("gif")
                        ? ".gif"
                        : mime.includes("svg")
                          ? ".svg"
                          : ".png";
            filename = filename.replace(/\.png$/i, "") + ext;
        }
        return { blob, filename };
    }
    const res = await fetch(src, { credentials: "include" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const ct = res.headers.get("content-type");
    if (!/\.\w{2,5}$/i.test(filename) && ct?.startsWith("image/")) {
        const ext =
            ct.includes("jpeg") || ct.includes("jpg")
                ? ".jpg"
                : ct.includes("png")
                  ? ".png"
                  : ct.includes("webp")
                    ? ".webp"
                    : ct.includes("gif")
                      ? ".gif"
                      : ct.includes("svg")
                        ? ".svg"
                        : ".png";
        filename = filename.replace(/\.[^.]+$/, "") + ext;
    }
    return { blob, filename };
}

function handleMarkdownContextMenu(e: MouseEvent): void {
    const t = e.target;
    const img =
        t instanceof HTMLImageElement ? t : (t as HTMLElement | null)?.closest?.("img");
    if (!(img instanceof HTMLImageElement)) {
        imgContextMenu.value = null;
        return;
    }
    if (!selectedItem.value) return;
    e.preventDefault();
    imgContextMenu.value = { x: e.clientX, y: e.clientY, img };
}

function closeImgContextMenu(): void {
    imgContextMenu.value = null;
}

async function addCompendiumImageToAssets(): Promise<void> {
    if (!imgContextMenu.value?.img || !selectedItem.value || addToAssetsLoading.value) return;
    const { img } = imgContextMenu.value;
    if (getDropInfoForCompendiumImg(img)) return;
    closeImgContextMenu();
    addToAssetsLoading.value = true;
    try {
        const { blob, filename } = await blobFromImageSrc(img.src);
        const file = new File([blob], filename, { type: blob.type || "image/png" });
        const dirs = buildCompendiumAssetDirectories();
        if (socket.disconnected) socket.connect();
        if (assetState.raw.root === undefined) {
            await assetSystem.rootCallback.wait();
        }
        const target = assetState.raw.root;
        if (target === undefined) {
            toast.error(t("game.ui.extensions.CompendiumModal.asset_upload_no_root"));
            return;
        }
        const dt = new DataTransfer();
        dt.items.add(file);
        const uploadedFiles = await assetSystem.upload(dt.files, {
            target: () => target,
            newDirectories: dirs,
        });
        const up = uploadedFiles[0];
        if (up?.fileHash && up.assetId != null) {
            setCompendiumDropInfo(img.src, {
                assetHash: up.fileHash,
                entryId: up.id,
                assetId: up.assetId,
            });
        }
        toast.success(t("game.ui.extensions.CompendiumModal.asset_upload_success"));
    } catch (err) {
        console.error(err);
        toast.error(t("game.ui.extensions.CompendiumModal.asset_upload_error"));
    } finally {
        addToAssetsLoading.value = false;
    }
}

async function navigateBreadcrumb(index: number): Promise<void> {
    if (!selectedItem.value) return;
    const { compendium } = selectedItem.value;
    const crumbs = breadcrumb.value;
    const crumb = crumbs[index];
    if (!crumb || crumb.type === "item") return;

    if (crumb.type === "compendium") {
        await showCompendiumIndex(compendium);
        return;
    }

    const coll = collectionsFor(compendium.id).find((c: CollectionMeta) => c.slug === crumb.slug);
    if (coll) {
        await showCollectionIndex(compendium, coll);
    }
}

const qeNames = ref<{ name: string; compendiumSlug?: string; collectionSlug: string; itemSlug: string }[]>([]);

const selectedMarkdownHtml = computed(() => {
    const orig = selectedItem.value?.item.markdown ?? "";
    const raw =
        showTranslatedContent.value && currentMarkdown.value.trim().length > 0 ? currentMarkdown.value : orig;
    const withLinks = !qeNames.value.length
        ? raw
        : injectQeLinks(raw, qeNames.value, selectedItem.value ? [selectedItem.value.item.name] : []);
    const rendered = renderQeMarkdown(withLinks);
    return ensureQeLinksCompendiumContext(rendered, selectedItem.value?.compendium.slug);
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

const indexViewTitle = computed(() => {
    const metaTitle = indexMetadata.value?.title;
    if (!indexFocusCollectionSlug.value) {
        return metaTitle || indexCompendium.value?.name || "";
    }
    const node = findIndexNodeBySlug(indexTreeForDisplay.value, indexFocusCollectionSlug.value);
    if (node?.name) return formatName(node.name);
    return metaTitle || indexCompendium.value?.name || "";
});

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
        const parsed = parseQePathSegments(href.slice(3));
        if (!parsed.collectionSlug || !parsed.itemSlug) return;
        compSlug = parsed.compSlug;
        collSlug = parsed.collectionSlug;
        itemSlug = parsed.itemSlug;
    }
    e.preventDefault();
    const comp = compSlug
        ? compendiums.value.find((c) => c.slug === compSlug)
        : (selectedItem.value?.compendium ??
              compendiums.value.find((c) => c.isDefault) ??
              compendiums.value[0]);
    if (!comp) return;
    const coll: CollectionMeta = { slug: collSlug, name: "", parentSlug: null, count: 0 };
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
    await withTreeLoad(async () => {
        try {
            const tagsParam = Array.from(selectedTagIds.value).join(",");
            const url = `/api/extensions/compendium/collections?compendium=${encodeURIComponent(compId)}` + (tagsParam ? `&tags=${tagsParam}` : "");
            const r = await http.get(url);
            if (r.ok) {
                const data = (await r.json()) as { collections: CollectionMeta[] };
                collectionsByComp.value = new Map(collectionsByComp.value).set(compId, data.collections);
            }
        } catch {
            /* ignore */
        }
    });
}


/** Espande compendium e carica collezioni se necessario (senza chiudere se già aperto). */
async function ensureCompendiumExpanded(compId: string): Promise<void> {
    if (!expandedComps.value.has(compId)) {
        expandedComps.value = new Set([...expandedComps.value, compId]);
    }
    if (collectionsByComp.value.has(compId)) return;
    await withTreeLoad(async () => {
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
    });
}

/** Espande collezione e carica items se necessario (senza chiudere se già aperta). */
async function ensureCollectionExpanded(compId: string, collSlug: string): Promise<void> {
    const set = expandedColls.value.get(compId);
    if (!set?.has(collSlug)) {
        const next = new Map<string, Set<string>>(expandedColls.value);
        next.set(compId, new Set<string>([...(next.get(compId) ?? []), collSlug]));
        expandedColls.value = next;
    }
    const key = `${compId}/${collSlug}`;
    if (itemsByKey.value.has(key)) return;
    await withTreeLoad(async () => {
        try {
            const tagsParam = Array.from(selectedTagIds.value).join(",");

            const r = await http.get(
                `/api/extensions/compendium/collections/${encodeURIComponent(collSlug)}/items?compendium=${encodeURIComponent(compId)}&tags=${tagsParam}`,
            );
            if (r.ok) {
                const data = (await r.json()) as { items: ItemMeta[] };
                itemsByKey.value = new Map(itemsByKey.value).set(key, data.items);
            }
        } catch {
            /* ignore */
        }
    });
}

async function toggleCollection(compId: string, collSlug: string): Promise<void> {
    const next = new Map<string, Set<string>>(expandedColls.value);
    const set = new Set<string>(next.get(compId) ?? []);
    if (set.has(collSlug)) {
        set.delete(collSlug);
    } else {
        set.add(collSlug);
        const key = `${compId}/${collSlug}`;
        if (!itemsByKey.value.has(key)) {
            await withTreeLoad(async () => {
                try {
                    const tagsParam = Array.from(selectedTagIds.value).join(",");

                    const r = await http.get(
                        `/api/extensions/compendium/collections/${encodeURIComponent(collSlug)}/items?compendium=${encodeURIComponent(compId)}&tags=${tagsParam}`,
                    );
                    if (r.ok) {
                        const data = (await r.json()) as { items: ItemMeta[] };
                        itemsByKey.value = new Map(itemsByKey.value).set(key, data.items);
                    }
                } catch {
                    /* ignore */
                }
            });
        }
    }
    next.set(compId, set);
    expandedColls.value = next;
}

function collectionHasChildren(compId: string, coll: CollectionMeta): boolean {
    if (subCollectionsFor(compId, coll.slug).length > 0) return true;
    if ((coll.count ?? 0) > 0) return true;
    return false;
}

async function expandAncestorsForCollection(compId: string, coll: CollectionMeta): Promise<void> {
    const chain: CollectionMeta[] = [];
    let p: string | null | undefined = coll.parentSlug;
    while (p) {
        const parent = collectionsFor(compId).find((c: CollectionMeta) => c.slug === p);
        if (!parent) break;
        chain.unshift(parent);
        p = parent.parentSlug;
    }
    for (const c of chain) {
        await ensureCollectionExpanded(compId, c.slug);
    }
}

async function selectItem(
    compendium: CompendiumMeta,
    collection: CollectionMeta,
    item: ItemMeta,
): Promise<void> {
    showIndex.value = false;
    indexFocusCollectionSlug.value = null;
    itemLoading.value = true;
    try {
        const r = await http.get(
            `/api/extensions/compendium/item?compendium=${encodeURIComponent(compendium.id)}&collection=${encodeURIComponent(collection.slug)}&slug=${encodeURIComponent(item.slug)}`,
        );
        if (r.ok) {
            const full = (await r.json()) as ItemFull;
            originalMarkdown.value = null;
            currentMarkdown.value = "";
            selectedItem.value = { compendium, collection, item: full };
            await checkTranslation("item");
            await fetchNextItem(compendium.id, collection.slug, item.slug);
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
    const comp = compendiums.value.find((c: CompendiumMeta) => c.id === compId);
    if (!comp) return;
    expandedComps.value = new Set([...expandedComps.value, compId]);
    await toggleCompendium(compId);
    expandedColls.value = new Map<string, Set<string>>(expandedColls.value).set(
        compId,
        new Set<string>([...(expandedColls.value.get(compId) ?? []), result.collectionSlug]),
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
        parentSlug: null,
        count: 0,
    };
    const itemMeta: ItemMeta = { slug: result.itemSlug, name: result.itemName };
    await selectItem(comp, coll, itemMeta);
    searchQuery.value = "";
    debouncedSearchQuery.value = "";
}

async function fetchNextItem(compId: string, collSlug: string, itemSlug: string): Promise<void> {
    nextItem.value = null;
    prevItem.value = null;
    try {
        const r = await http.get(
            `/api/extensions/compendium/next?compendium=${encodeURIComponent(compId)}&collection=${encodeURIComponent(collSlug)}&slug=${encodeURIComponent(itemSlug)}`,
        );
        if (r.ok) {
            const data = (await r.json()) as {
                next: { itemSlug: string; itemName: string; collectionSlug: string; collectionName: string } | null;
                prev: { itemSlug: string; itemName: string; collectionSlug: string; collectionName: string } | null;
            };
            nextItem.value = data.next;
            prevItem.value = data.prev;
        }
    } catch {
        /* ignore */
    }
}

async function navigateToNextItem(): Promise<void> {
    if (!nextItem.value || !selectedItem.value) return;
    const comp = selectedItem.value.compendium;
    const { collectionSlug, collectionName, itemSlug, itemName } = nextItem.value;

    await ensureCollectionExpanded(comp.id, collectionSlug);

    const coll: CollectionMeta = {
        slug: collectionSlug,
        name: collectionName,
        parentSlug: null,
        count: 0,
    };
    const displayName = displayAdjacentItemName(nextItem.value);
    const itemMeta: ItemMeta = { slug: itemSlug, name: displayName || itemName };
    await selectItem(comp, coll, itemMeta);
}

async function navigateToPrevItem(): Promise<void> {
    if (!prevItem.value || !selectedItem.value) return;
    const comp = selectedItem.value.compendium;
    const { collectionSlug, collectionName, itemSlug, itemName } = prevItem.value;

    await ensureCollectionExpanded(comp.id, collectionSlug);

    const coll: CollectionMeta = {
        slug: collectionSlug,
        name: collectionName,
        parentSlug: null,
        count: 0,
    };
    const displayName = displayAdjacentItemName(prevItem.value);
    const itemMeta: ItemMeta = { slug: itemSlug, name: displayName || itemName };
    await selectItem(comp, coll, itemMeta);
}

async function showCompendiumIndex(comp: CompendiumMeta): Promise<void> {
    selectedItem.value = null;
    showIndex.value = true;

    /** Stesso compendio con indice già caricato (es. si torna dall’indice di un sotto-ramo): non rifare GET /index così non si perde il merge traduzione in memoria se checkTranslation fallisce o è lenta. */
    const sameCompIndexInMemory =
        indexCompendium.value?.id === comp.id && canonicalIndex.value.length > 0;

    indexCompendium.value = comp;
    selectedCompendiumId.value = comp.id;
    indexFocusCollectionSlug.value = null;

    if (sameCompIndexInMemory) {
        indexLoading.value = false;
        await ensureCompendiumExpanded(comp.id);
        return;
    }

    indexLoading.value = true;
    translatedIndexOverlay.value = null;
    canonicalIndex.value = [];
    expandedIndexCollections.value.clear();

    try {
        const r = await http.get(
            `/api/extensions/compendium/index?compendium=${encodeURIComponent(comp.id)}`,
        );
        if (r.ok) {
            const data = (await r.json()) as { index: any[], metadata?: Record<string, string> };
            originalIndex.value = null;
            activeTranslationLang.value = null;
            currentMarkdown.value = "";
            canonicalIndex.value = JSON.parse(JSON.stringify(data.index)) as IndexCollNode[];
            indexMetadata.value = data.metadata || {};
            await checkTranslation("index");
        }
    } catch {
        /* ignore */
    } finally {
        indexLoading.value = false;
    }
    await ensureCompendiumExpanded(comp.id);
}

async function showCollectionIndex(comp: CompendiumMeta, coll: CollectionMeta): Promise<void> {
    const hasApiChildren = collectionHasChildren(comp.id, coll);
    const indexLoadedForComp =
        indexCompendium.value?.id === comp.id && canonicalIndex.value.length > 0;
    const hasContentInIndexTree = indexLoadedForComp && indexNodeHasVisibleBranchContent(coll.slug);
    /** Se il nodo è nell’indice JSON (anche ramo “vuoto” per items/collections), apri la vista ramo come dal titolo in griglia. */
    const nodeExistsInIndexTree =
        indexLoadedForComp &&
        findIndexNodeBySlug(canonicalIndex.value as IndexCollNode[], coll.slug) !== null;

    if (!hasApiChildren && !hasContentInIndexTree && !nodeExistsInIndexTree) {
        await ensureCompendiumExpanded(comp.id);
        await expandAncestorsForCollection(comp.id, coll);
        await ensureCollectionExpanded(comp.id, coll.slug);
        return;
    }
    selectedItem.value = null;
    showIndex.value = true;
    const indexAlreadyLoaded =
        canonicalIndex.value.length > 0 && indexCompendium.value?.id === comp.id;
    indexCompendium.value = comp;
    selectedCompendiumId.value = comp.id;
    indexFocusCollectionSlug.value = coll.slug;

    if (!indexAlreadyLoaded) {
        indexLoading.value = true;
        translatedIndexOverlay.value = null;
        canonicalIndex.value = [];
        expandedIndexCollections.value.clear();
        try {
            const r = await http.get(
                `/api/extensions/compendium/index?compendium=${encodeURIComponent(comp.id)}`,
            );
            if (r.ok) {
                const data = (await r.json()) as { index: any[], metadata?: Record<string, string> };
                originalIndex.value = null;
                activeTranslationLang.value = null;
                currentMarkdown.value = "";
                canonicalIndex.value = JSON.parse(JSON.stringify(data.index)) as IndexCollNode[];
                indexMetadata.value = data.metadata || {};
                await checkTranslation("index");
            }
        } catch {
            /* ignore */
        } finally {
            indexLoading.value = false;
        }
    }

    await ensureCompendiumExpanded(comp.id);
    await expandAncestorsForCollection(comp.id, coll);
    await ensureCollectionExpanded(comp.id, coll.slug);
}

async function onCollectionLabelClick(comp: CompendiumMeta, coll: CollectionMeta): Promise<void> {
    if (!collectionHasChildren(comp.id, coll)) {
        await toggleCollection(comp.id, coll.slug);
        return;
    }
    await showCollectionIndex(comp, coll);
}

async function selectItemBySlug(collSlug: string, itemSlug: string): Promise<void> {
    if (!indexCompendium.value) return;
    const coll: CollectionMeta = { slug: collSlug, name: "", parentSlug: null, count: 0 };
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

async function renameCompendium(comp: CompendiumMeta): Promise<void> {
    const newName = await modals.prompt(
        t("game.ui.extensions.CompendiumModal.rename"),
        t("game.ui.extensions.CompendiumModal.rename_prompt")
    );
    if (!newName || !newName.trim() || newName.trim() === comp.name) return;
    
    try {
        const r = await http.patchJson(
            `/api/extensions/compendium/compendiums/${encodeURIComponent(comp.id)}/rename`,
            { name: newName.trim() }
        );
        if (r.ok) {
            comp.name = newName.trim();
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
            const file = files[0]!;
            installFile.value = file;
            installFiles.value = [];
            
            const reader = new FileReader();
            reader.onload = (ev) => {
                try {
                    const content = ev.target?.result as string;
                    const json = JSON.parse(content);
                    installName.value = json.name || json.title || file.name.replace(/\.json$/i, "") || "Compendium";
                } catch (err) {
                    if (!installName.value) installName.value = file.name.replace(/\.json$/i, "") || "Compendium";
                }
            };
            reader.readAsText(file);
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

function onAssetZipFileChange(e: Event): void {
    const input = e.target as HTMLInputElement;
    const files = input.files;
    if (files && files.length > 0) {
        assetZipFile.value = files[0]!;
    }
    input.value = "";
}

async function checkAiConfig(): Promise<void> {
    try {
        const r = await http.get("/api/extensions/openrouter/settings");
        if (r.ok) {
            const data = (await r.json()) as {
                hasApiKey?: boolean;
                hasGoogleKey?: boolean;
                model?: string;
                compendiumTranslateSource?: string;
                compendiumTranslateTarget?: string | null;
                maxTokens?: number;
            };
            aiConfigured.value = !!(data.hasApiKey || data.hasGoogleKey);
            aiModel.value = data.model || "google/gemini-2.0-flash-001";
            aiMaxTokens.value = data.maxTokens ?? 8192;
            const src = (data.compendiumTranslateSource ?? "auto").toLowerCase();
            compendiumTranslateSource.value = src === "auto" ? "auto" : src;
            compendiumTranslateTarget.value = data.compendiumTranslateTarget ?? null;
        }
    } catch {
        aiConfigured.value = false;
    }
}

async function rerunTranslation(): Promise<void> {
    await clearTranslation();
    await runTranslateCurrentView();
}

function toggleShowTranslatedContent(): void {
    showTranslatedContent.value = !showTranslatedContent.value;
    try {
        localStorage.setItem(SHOW_TRANSLATED_STORAGE_KEY, showTranslatedContent.value ? "1" : "0");
    } catch {
        /* ignore */
    }
}

/** Avvia traduzione AI per la vista corrente (voce o indice); non modifica la preferenza mostra traduzioni. */
async function runTranslateCurrentView(): Promise<void> {
    if (translateLoading.value) return;

    const targetCode = effectiveCompendiumTargetLang();

    await checkTranslation(selectedItem.value ? "item" : "index");
    if (activeTranslationLang.value === targetCode) return;

    if (selectedItem.value) {
        await translateSingleItemMarkdown(targetCode);
        return;
    }

    if (showIndex.value && canonicalIndex.value.length > 0) {
        /** Stesso ramo mostrato dalla pagina indice (root o nodo cliccato); la traduzione nomi usa solo questo JSON, poi merge nell’albero completo. */
        const roots = displayedIndex.value as IndexCollNode[];
        const leafItems = collectLeafItemsFromIndexNodes(roots);
        if (leafItems.length > 0) {
            openTranslateBatchConfirm(leafItems, targetCode, roots);
            return;
        }
        translateLoading.value = true;
        batchTranslateProgress.value = null;
        try {
            await translateIndexJsonOnly(roots, targetCode);
        } catch (e: unknown) {
            console.error(e);
            toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
        } finally {
            translateLoading.value = false;
        }
    }
}

function handleOutsideClick(event: MouseEvent): void {
    if (showTranslationTools.value && translationTagContainer.value && !translationTagContainer.value.contains(event.target as Node)) {
        showTranslationTools.value = false;
    }
}

onMounted(async () => {
    try {
        const s = localStorage.getItem(SHOW_TRANSLATED_STORAGE_KEY);
        if (s === "0") showTranslatedContent.value = false;
        if (s === "1") showTranslatedContent.value = true;
    } catch {
        /* ignore */
    }
    await loadCompendiums();
    await checkAiConfig();
    window.addEventListener("mousedown", handleOutsideClick);
});

onUnmounted(() => {
    window.removeEventListener("mousedown", handleOutsideClick);
    stopResize();
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
        if (installAssets.value && assetZipFile.value) {
            form.append("installAssets", "true");
            form.append("zipFile", assetZipFile.value);
        }
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
            applyCompendiumResolverMap(data.compendiums, data.defaultId);
            qeNames.value = await getQeNames();
            const openItem = extensionsState.raw.compendiumOpenItem;
            if (openItem && compendiums.value.length > 0) {
                sidebarCollapsed.value = true;
                const comp = openItem.compendiumSlug
                    ? compendiums.value.find((c: CompendiumMeta) => c.slug === openItem.compendiumSlug)
                    : compendiums.value.find((c: CompendiumMeta) => c.isDefault) ?? compendiums.value[0];
                if (comp) {
                    selectedCompendiumId.value = comp.id;
                    expandedComps.value = new Set([comp.id]);
                    await toggleCompendium(comp.id);
                    const colls = collectionsByComp.value.get(comp.id) ?? [];
                    const targetColl = colls.find((c: CollectionMeta) => c.slug === openItem.collectionSlug);
                    if (targetColl) {
                        expandedColls.value = new Map(expandedColls.value).set(
                            comp.id,
                            new Set([...(expandedColls.value.get(comp.id) ?? []), targetColl.slug]),
                        );
                        await toggleCollection(comp.id, targetColl.slug);
                        const items = itemsByKey.value.get(`${comp.id}/${targetColl.slug}`) ?? [];
                        const itemMeta =
                            items.find((i: ItemMeta) => i.slug === openItem.itemSlug) ??
                            ({ slug: openItem.itemSlug, name: openItem.itemSlug } as ItemMeta);
                        await selectItem(comp, targetColl, itemMeta);
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
    // Load tags after compendiums are loaded so the endpoint returns results
    void loadAllGlobalTags();
}


async function runSearch(q: string, compendiumId?: string | null): Promise<void> {
    searchLoading.value = true;
    searchCompendiumFilter.value = null;
    try {
        const params = new URLSearchParams({ q });
        if (compendiumId) params.set("compendium", compendiumId);
        const tagsParam = Array.from(selectedTagIds.value).join(",");

        if (tagsParam) params.set("tags", tagsParam);
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

const shareModalOpen = ref(false);

/** Conferma traduzione indice ricorsiva (stesso pattern overlay del modale Condividi). */
const translateBatchConfirmOpen = ref(false);
const pendingTranslateBatch = ref<{
    leafItems: { collectionSlug: string; itemSlug: string; itemName: string }[];
    targetCode: string;
    roots: IndexCollNode[];
} | null>(null);

const translateBatchPendingCount = computed(() => pendingTranslateBatch.value?.leafItems.length ?? 0);

function openTranslateBatchConfirm(
    leafItems: { collectionSlug: string; itemSlug: string; itemName: string }[],
    targetCode: string,
    roots: IndexCollNode[],
): void {
    pendingTranslateBatch.value = { leafItems, targetCode, roots };
    translateBatchConfirmOpen.value = true;
}

function closeTranslateBatchConfirm(): void {
    translateBatchConfirmOpen.value = false;
    pendingTranslateBatch.value = null;
}

async function executeIndexTranslationBatch(p: {
    leafItems: { collectionSlug: string; itemSlug: string; itemName: string }[];
    targetCode: string;
    roots: IndexCollNode[];
}): Promise<void> {
    const { leafItems, targetCode, roots } = p;
    translateLoading.value = true;
    batchTranslateProgress.value = leafItems.length > 0 ? { current: 0, total: leafItems.length } : null;
    try {
        if (leafItems.length > 0) {
            await runTranslateIndexRecursiveBatch(leafItems, targetCode);
        }
        const indexOk = await translateIndexJsonOnly(roots, targetCode);
        if (leafItems.length > 0 && indexOk) {
            toast.success(t("game.ui.extensions.CompendiumModal.translate_batch_done"));
        }
    } catch (e: unknown) {
        console.error(e);
        toast.error(t("game.ui.extensions.CompendiumModal.translate_error"));
    } finally {
        translateLoading.value = false;
        batchTranslateProgress.value = null;
    }
}

async function confirmTranslateBatch(): Promise<void> {
    const p = pendingTranslateBatch.value;
    if (!p) return;
    translateBatchConfirmOpen.value = false;
    pendingTranslateBatch.value = null;
    await executeIndexTranslationBatch(p);
}

function openShareModal(): void {
    if (!selectedItem.value) return;
    shareModalOpen.value = true;
}

function closeShareModal(): void {
    shareModalOpen.value = false;
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

function shareToChatAndClose(): void {
    shareToChat();
    closeShareModal();
}

async function addCompendiumToNote(): Promise<void> {
    if (!selectedItem.value) return;
    const { item } = selectedItem.value;
    const text = (
        showTranslatedContent.value && currentMarkdown.value.trim().length > 0 ? currentMarkdown.value : item.markdown
    ).trim();
    const title = (item.name || "").trim() || t("game.ui.extensions.CompendiumModal.note_title_fallback");

    const fullRoom = gameState.fullRoomName.value || "";
    const slash = fullRoom.indexOf("/");
    const rooms: ApiNoteRoom[] = [];
    if (slash > 0) {
        const roomCreator = fullRoom.slice(0, slash);
        const roomName = fullRoom.slice(slash + 1);
        if (roomCreator && roomName) {
            rooms.push({
                roomCreator,
                roomName,
                locationId: null,
                locationName: null,
            });
        }
    }

    const id = uuidv4() as unknown as NoteId;
    const note: ApiNote = {
        uuid: id,
        creator: coreStore.state.username,
        title,
        text,
        showOnHover: false,
        showIconOnShape: false,
        rooms,
        tags: [],
        access: [],
        shapes: [],
    };

    try {
        await noteSystem.newNote(note, true);
        closeShareModal();
        openNoteManager(NoteManagerMode.Edit, id);
        toast.success(t("game.ui.extensions.CompendiumModal.note_created_open"));
    } catch (e) {
        console.error(e);
        toast.error(t("game.ui.extensions.CompendiumModal.note_create_error"));
    }
}

async function loadAllGlobalTags(): Promise<void> {
    try {
        const r = await http.get("/api/extensions/compendium/all-tags");
        if (r.ok) {
            const data = (await r.json()) as { categories: GlobalTagCategory[] };
            allTagCategories.value = data.categories || [];
        }
    } catch { /* ignore */ }
}

async function refetchAllCollections(): Promise<void> {
    const tagsParam = Array.from(selectedTagIds.value).join(",");
    const promises: Promise<void>[] = [];
    for (const compId of expandedComps.value) {
        promises.push((async () => {
            try {
                const url = `/api/extensions/compendium/collections?compendium=${encodeURIComponent(compId)}` + (tagsParam ? `&tags=${tagsParam}` : "");
                const r = await http.get(url);
                if (r.ok) {
                    const data = (await r.json()) as { collections: CollectionMeta[] };
                    collectionsByComp.value = new Map(collectionsByComp.value).set(compId, data.collections);
                }
            } catch {}
        })());
    }
    await withTreeLoad(async () => {
        await Promise.all(promises);
    });
}



async function refetchAllVisibleItems(): Promise<void> {
    const tagsParam = Array.from(selectedTagIds.value).join(",");
    const promises: Promise<void>[] = [];
    for (const key of itemsByKey.value.keys()) {
         const parts = key.split("/");
         const compId = parts[0]!;
         const collSlug = parts[1]!;
         promises.push((async () => {
             try {
                 const r = await http.get(`/api/extensions/compendium/collections/${encodeURIComponent(collSlug)}/items?compendium=${encodeURIComponent(compId)}&tags=${tagsParam}`);
                 if (r.ok) {
                     const data = (await r.json()) as { items: ItemMeta[] };
                     itemsByKey.value.set(key, data.items);
                 }
             } catch {}
         })());
    }
    await withTreeLoad(async () => {
        await Promise.all(promises);
    });
}

async function selectItemTag(tagId: number): Promise<void> {
    toggleTagInFilter(tagId);
}

watch(
    () => props.visible,

    (visible: boolean) => {
        if (visible) {
            loadCompendiums();
            loadAllGlobalTags();
        }
    },
);

/** Anteprima link qe: nel modale: contesto con id UUID + slug per risolvere le richieste con ?compendium=id (evita 404 su slug). */
watch(
    () => [props.visible, selectedItem.value?.compendium, indexCompendium.value] as const,
    ([visible, itemComp, idxComp]) => {
        if (!visible) {
            extensionsState.mutableReactive.compendiumPreviewContext = undefined;
            return;
        }
        const comp = itemComp ?? idxComp;
        if (comp?.id) {
            extensionsState.mutableReactive.compendiumPreviewContext = {
                compendiumId: comp.id,
                compendiumSlug: comp.slug,
            };
        } else {
            extensionsState.mutableReactive.compendiumPreviewContext = undefined;
        }
    },
    { immediate: true },
);

watch(
    /* reactive (non raw): altrimenti il watch non si riattiva quando il compendio è già aperto */
    () => [extensionsState.reactive.compendiumOpenItem, compendiums.value.length] as const,
    async ([openItem]) => {
        if (!openItem || !props.visible || !compendiums.value.length) return;
        sidebarCollapsed.value = true;
        const comp = openItem.compendiumSlug
            ? compendiums.value.find((c: CompendiumMeta) => c.slug === openItem.compendiumSlug)
            : compendiums.value.find((c: CompendiumMeta) => c.isDefault) ?? compendiums.value[0];
        if (!comp) return;
        await ensureCompendiumExpanded(comp.id);
        const colls = collectionsByComp.value.get(comp.id) ?? [];
        const targetColl = colls.find((c: CollectionMeta) => c.slug === openItem.collectionSlug);
        if (targetColl) {
            await ensureCollectionExpanded(comp.id, targetColl.slug);
            const items = itemsByKey.value.get(`${comp.id}/${targetColl.slug}`) ?? [];
            const itemMeta =
                items.find((i: ItemMeta) => i.slug === openItem.itemSlug) ??
                ({ slug: openItem.itemSlug, name: openItem.itemSlug } as ItemMeta);
            await selectItem(comp, targetColl, itemMeta);
        }
        extensionsState.mutableReactive.compendiumOpenItem = undefined;
    },
    { immediate: true },
);

watch(
    () => [selectedMarkdownHtml.value, itemLoading.value] as const,
    async ([, loading]) => {
        if (loading) return;
        await nextTick();
        await nextTick();
        const root = markdownContentRef.value;
        if (!root) return;
        root.querySelectorAll("img").forEach((el) => {
            if (el instanceof HTMLImageElement) {
                void resolveCompendiumImageInAssetLibrary(el);
            }
        });
    },
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
        <template #header="{ dragStart, dragEnd, toggleMinimize, minimized, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">{{ t("game.ui.extensions.CompendiumModal.title") }}</h2>
                <div class="ext-modal-actions">
                    <font-awesome-icon
                        :icon="minimized ? ['far', 'window-restore'] : 'minus'"
                        :title="minimized ? t('common.restore') : t('common.minimize')"
                        class="ext-modal-btn"
                        @click.stop="toggleMinimize?.()"
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
            <div v-if="installLoading || translateLoading || treeLoading" class="ext-progress-top-container">
                <LoadingBar :progress="100" indeterminate height="6px" />
                <div v-if="batchTranslateProgress" class="qe-batch-translate-hint">
                    {{
                        t("game.ui.extensions.CompendiumModal.translate_batch_progress", {
                            current: batchTranslateProgress.current,
                            total: batchTranslateProgress.total,
                        })
                    }}
                </div>
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

                <!-- Tags filter toggle button -->
                <button
                    type="button"
                    class="ext-search-add-btn filter-btn"
                    :class="{ 'has-filters': hasActiveTagFilters, 'is-active': showTagDropdown }"
                    title="Filtra per Tag"
                    @click="showTagDropdown = !showTagDropdown"
                >
                    <font-awesome-icon icon="filter" />
                    <span v-if="selectedTagIds.size > 0" class="qe-tag-filter-badge">{{ selectedTagIds.size }}</span>
                </button>


                <!-- Clear filters button -->
                <button
                    v-if="hasActiveTagFilters"
                    type="button"
                    class="ext-search-add-btn qe-clear-tags-btn"
                    title="Rimuovi tutti i filtri Tag"
                    @click="clearTagFilters"
                >
                    <font-awesome-icon icon="circle-xmark" />

                </button>

                <button
                    type="button"
                    class="ext-search-add-btn"
                    :title="t('game.ui.extensions.CompendiumModal.install_compendium')"
                    @click="openInstallDialog"
                >
                    <font-awesome-icon icon="plus" />
                </button>
                <button
                    v-if="selectedItem || (showIndex && canonicalIndex.length > 0)"
                    type="button"
                    class="ext-search-add-btn translate-btn"
                    :class="{ 'is-active': showTranslatedContent }"
                    :title="t('game.ui.extensions.CompendiumModal.toggle_translated_display_tooltip')"
                    @click="toggleShowTranslatedContent"
                >
                    <font-awesome-icon icon="language" />
                </button>
            </div>

            <!-- Expandable Grouped Filters Shelf -->
            <div v-if="showTagDropdown" class="ext-toolbar-bar ext-search-bar qe-tag-filter-shelf">
                <div class="ga-spacer"></div>

                <div v-if="compendiums.length > 1" class="ga-spacer"></div>
                <GroupedAutocomplete
                    :options="flatTags"
                    v-model="selectedTagIdsArray"
                    :placeholder="t('game.ui.extensions.CompendiumModal.filter_tags_placeholder')"
                    :group-by="(o) => o.category"
                />

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
                            <font-awesome-icon
                                v-if="defaultId === comp.id"
                                icon="star"
                                class="qe-search-filter-default-star"
                                :title="t('game.ui.extensions.CompendiumModal.default_compendium')"
                            />
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
                            <span class="ext-ui-list-item-name qe-search-result-title">
                                <font-awesome-icon
                                    v-if="defaultId && result.compendiumId === defaultId"
                                    icon="star"
                                    class="qe-search-result-default-star"
                                    :title="t('game.ui.extensions.CompendiumModal.default_compendium')"
                                />
                                {{ result.itemName }}
                            </span>
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
                <nav class="qe-tree" :class="{ collapsed: sidebarCollapsed }" :style="{ width: sidebarWidth + 'px' }">
                    <div class="qe-tree-content">
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
                                    class="ext-action-btn"
                                    :title="t('game.ui.extensions.CompendiumModal.rename')"
                                    @click.stop="renameCompendium(comp)"
                                >
                                    <font-awesome-icon icon="edit" />
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
                                    v-for="coll in rootCollectionsFor(comp.id)"
                                    :key="coll.slug"
                                    class="qe-tree-collection"
                                >
                                    <div class="qe-tree-collection-row">
                                        <button
                                            type="button"
                                            class="qe-tree-toggle coll"
                                            :class="{ expanded: isExpanded(comp.id, coll.slug) }"
                                            @click="toggleCollection(comp.id, coll.slug)"
                                        >
                                            <font-awesome-icon
                                                :icon="
                                                    isExpanded(comp.id, coll.slug) ? 'chevron-down' : 'chevron-right'
                                                "
                                            />
                                        </button>
                                        <span
                                            class="qe-tree-coll-name"
                                            :class="{ 'has-children': collectionHasChildren(comp.id, coll) }"
                                            @click.stop="onCollectionLabelClick(comp, coll)"
                                        >{{ formatName(coll.name) }}</span>
                                        <span class="qe-tree-count">({{ coll.count }})</span>
                                    </div>
                                    <div
                                        v-show="isExpanded(comp.id, coll.slug)"
                                        class="qe-tree-items"
                                    >
                                        <template v-for="child in interleavedChildrenFor(comp.id, coll.slug)" :key="child.slug">
                                            <!-- COLLECTION CHILD -->
                                            <div
                                                v-if="child.type === 'collection'"
                                                class="qe-tree-collection qe-tree-subcollection"
                                            >
                                                <div class="qe-tree-collection-row">
                                                    <button
                                                        type="button"
                                                        class="qe-tree-toggle coll"
                                                        :class="{ expanded: isExpanded(comp.id, child.slug) }"
                                                        @click="toggleCollection(comp.id, child.slug)"
                                                    >
                                                        <font-awesome-icon
                                                            :icon="isExpanded(comp.id, child.slug) ? 'chevron-down' : 'chevron-right'"
                                                        />
                                                    </button>
                                                    <span
                                                        class="qe-tree-coll-name"
                                                        :class="{ 'has-children': collectionHasChildren(comp.id, child) }"
                                                        @click.stop="onCollectionLabelClick(comp, child)"
                                                    >{{ formatName(child.name) }}</span>
                                                    <span class="qe-tree-count">({{ child.count }})</span>
                                                </div>
                                                <div
                                                    v-show="isExpanded(comp.id, child.slug)"
                                                    class="qe-tree-items"
                                                >
                                                    <button
                                                        v-for="subItem in itemsFor(comp.id, child.slug)"
                                                        :key="subItem.slug"
                                                        class="qe-tree-item"
                                                        :class="{
                                                            active:
                                                                selectedItem?.compendium.id === comp.id &&
                                                                selectedItem?.collection.slug === child.slug &&
                                                                selectedItem?.item.slug === subItem.slug,
                                                        }"
                                                        @click="selectItem(comp, child, subItem)"
                                                    >
                                                        {{ subItem.name }}
                                                    </button>
                                                </div>
                                            </div>
    
                                            <!-- ITEM CHILD -->
                                            <button
                                                v-else
                                                class="qe-tree-item"
                                                :class="{
                                                    active:
                                                        selectedItem?.compendium.id === comp.id &&
                                                        selectedItem?.collection.slug === coll.slug &&
                                                        selectedItem?.item.slug === child.slug,
                                                }"
                                                @click="selectItem(comp, coll, child)"
                                            >
                                                {{ child.name }}
                                            </button>
                                        </template>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <button
                        class="qe-sidebar-toggle"
                        :title="sidebarCollapsed ? t('game.ui.extensions.CompendiumModal.expand_sidebar') : t('game.ui.extensions.CompendiumModal.collapse_sidebar')"
                        @click="sidebarCollapsed = !sidebarCollapsed"
                    >
                        <font-awesome-icon :icon="sidebarCollapsed ? 'chevron-right' : 'chevron-left'" />
                    </button>
                </nav>
                <div v-if="!sidebarCollapsed" class="qe-sidebar-resizer" @mousedown.prevent="startResize" />
                <div class="qe-content-area">
                    <div v-if="selectedItem" class="qe-breadcrumb">
                        <div class="qe-breadcrumb-path">
                            <template v-for="(crumb, i) in breadcrumb" :key="'crumb-' + i">
                                <span v-if="Number(i) > 0" class="qe-breadcrumb-sep"> › </span>
                                <button
                                    v-if="crumb.type !== 'item'"
                                    class="qe-breadcrumb-link"
                                    @click="navigateBreadcrumb(i)"
                                >{{ crumb.label }}</button>
                                <span v-else class="qe-breadcrumb-item">{{ crumb.label }}</span>
                            </template>
                        </div>
                        <template v-if="showTranslatedContent">
                            <div v-if="hasSavedTranslation" class="translation-tag-container" ref="translationTagContainer">
                                <div class="translation-tag" @click.stop="showTranslationTools = !showTranslationTools">
                                    <font-awesome-icon icon="check-circle" class="me-1" />
                                    {{
                                        t("game.ui.extensions.CompendiumModal.translated_to", {
                                            lang: translationTargetLabel,
                                        })
                                    }}
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
                                v-else-if="aiConfigured"
                                type="button"
                                class="qe-translate-inline-btn"
                                :title="t('game.ui.extensions.CompendiumModal.translate_with_ai_tooltip')"
                                :disabled="translateLoading"
                                @click.stop="runTranslateCurrentView"
                            >
                                <font-awesome-icon icon="circle" />
                            </button>
                        </template>
                        <button
                            type="button"
                            class="qe-share-btn"
                            :title="t('game.ui.extensions.CompendiumModal.share_menu_hint')"
                            @click="openShareModal"
                        >
                            <font-awesome-icon icon="share-alt" />
                            {{ t("game.ui.extensions.CompendiumModal.share") }}
                        </button>
                    </div>
                    <h2 v-if="selectedItem" class="qe-item-view-heading">{{ displayedItemTitle }}</h2>
                    <div v-if="showIndex" class="qe-index-view">
                        <div v-if="indexLoading" class="qe-loading-inline">
                            {{ t("game.ui.extensions.CompendiumModal.loading") }}
                        </div>
                        <div v-else class="qe-index-container">
                            <div class="qe-index-header">
                                <h1 class="qe-index-title">{{ indexViewTitle }}</h1>
                                <template v-if="showTranslatedContent">
                                    <div
                                        v-if="hasSavedTranslation"
                                        class="translation-tag-container"
                                        ref="translationTagContainer"
                                    >
                                        <div
                                            class="translation-tag translation-tag--index-icon-only"
                                            :class="{
                                                'translation-tag--index-partial': !isGlobalIndexFullyTranslated(),
                                                'translation-tag--index-complete': isGlobalIndexFullyTranslated(),
                                            }"
                                            :title="
                                                t('game.ui.extensions.CompendiumModal.translated_to', {
                                                    lang: translationTargetLabel,
                                                })
                                            "
                                            @click.stop="showTranslationTools = !showTranslationTools"
                                        >
                                            <font-awesome-icon icon="check-circle" />
                                        </div>
                                        <div v-if="showTranslationTools" class="translation-tools-popover">
                                            <button class="popover-btn" @click.stop="clearTranslation">
                                                <font-awesome-icon icon="undo" /> {{ t("game.ui.extensions.CompendiumModal.clear_translation") }}
                                            </button>
                                            <button class="popover-btn" @click.stop="rerunTranslation">
                                                <font-awesome-icon icon="sync" /> {{ t("game.ui.extensions.CompendiumModal.rerun_translation") }}
                                            </button>
                                            <button
                                                v-if="aiConfigured"
                                                class="popover-btn"
                                                type="button"
                                                :disabled="translateLoading"
                                                :title="t('game.ui.extensions.CompendiumModal.complete_translation_hint')"
                                                @click.stop="completeIndexTranslation"
                                            >
                                                <font-awesome-icon icon="wand-magic-sparkles" />
                                                {{ t("game.ui.extensions.CompendiumModal.complete_translation") }}
                                            </button>
                                        </div>
                                    </div>
                                    <button
                                        v-else-if="aiConfigured"
                                        type="button"
                                        class="qe-translate-inline-btn qe-translate-inline-btn--index-header"
                                        :title="t('game.ui.extensions.CompendiumModal.translate_with_ai_tooltip')"
                                        :disabled="translateLoading"
                                        @click.stop="runTranslateCurrentView"
                                    >
                                        <font-awesome-icon icon="circle" />
                                    </button>
                                </template>
                            </div>
                            <!-- Tag Filters moved to search bar -->

                            <div class="qe-index-grid">

                                <div v-for="coll in displayedIndex" :key="coll.slug" class="qe-index-coll">
                                    <h2 class="qe-index-coll-title">
                                        <font-awesome-icon
                                            v-if="showTranslatedContent && isIndexBranchTranslated(coll.slug)"
                                            icon="check-circle"
                                            :class="[
                                                'qe-index-branch-translated-icon',
                                                isIndexBranchFullyTranslated(coll.slug)
                                                    ? 'qe-index-branch-translated-icon--complete'
                                                    : 'qe-index-branch-translated-icon--partial',
                                            ]"
                                            :title="
                                                t('game.ui.extensions.CompendiumModal.translated_to', {
                                                    lang: translationTargetLabel,
                                                })
                                            "
                                        />
                                        <button
                                            type="button"
                                            class="qe-index-coll-title-link"
                                            @click.stop="openSubcollIndexFromIndex(coll)"
                                        >
                                            {{ formatName(coll.name) }}
                                        </button>
                                    </h2>
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
                                    <div v-if="coll.collections && coll.collections.length > 0" class="qe-index-subcolls">
                                        <div v-for="subColl in coll.collections" :key="subColl.slug" class="qe-index-subcoll">
                                            <h3 class="qe-index-subcoll-title">
                                                <font-awesome-icon
                                                    v-if="showTranslatedContent && isIndexBranchTranslated(subColl.slug)"
                                                    icon="check-circle"
                                                    :class="[
                                                        'qe-index-branch-translated-icon',
                                                        isIndexBranchFullyTranslated(subColl.slug)
                                                            ? 'qe-index-branch-translated-icon--complete'
                                                            : 'qe-index-branch-translated-icon--partial',
                                                    ]"
                                                    :title="
                                                        t('game.ui.extensions.CompendiumModal.translated_to', {
                                                            lang: translationTargetLabel,
                                                        })
                                                    "
                                                />
                                                <button
                                                    type="button"
                                                    class="qe-index-coll-title-link"
                                                    @click.stop="openSubcollIndexFromIndex(subColl)"
                                                >
                                                    {{ formatName(subColl.name) }}
                                                </button>
                                            </h3>
                                            <div class="qe-index-item-list">
                                                <button
                                                    v-for="item in (expandedIndexCollections.has(subColl.slug) ? subColl.items : subColl.items.slice(0, 10))"
                                                    :key="item.slug"
                                                    class="qe-index-item-link"
                                                    @click="selectItemBySlug(subColl.slug, item.slug)"
                                                >
                                                    {{ item.name }}
                                                </button>
                                                <button
                                                    v-if="subColl.items.length > 10 && !expandedIndexCollections.has(subColl.slug)"
                                                    class="qe-index-load-more"
                                                    @click="toggleIndexCollection(subColl.slug)"
                                                >
                                                    ... {{ t("game.ui.extensions.CompendiumModal.load_all") }}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div v-if="Object.keys(indexMetadata).length > 0 && (indexMetadata.author || indexMetadata.date || indexMetadata.website || indexMetadata.license)" class="qe-index-metadata">
                                <div v-if="indexMetadata.author" class="qe-metadata-row"><strong>{{ t('game.ui.extensions.CompendiumModal.author') }}:</strong> {{ indexMetadata.author }}</div>
                                <div v-if="indexMetadata.date" class="qe-metadata-row"><strong>{{ t('game.ui.extensions.CompendiumModal.date') }}:</strong> {{ indexMetadata.date }}</div>
                                <div v-if="indexMetadata.website" class="qe-metadata-row"><strong>{{ t('game.ui.extensions.CompendiumModal.website') }}:</strong> <a :href="indexMetadata.website" target="_blank">{{ indexMetadata.website }}</a></div>
                                <div v-if="indexMetadata.license" class="qe-metadata-row"><strong>{{ t('game.ui.extensions.CompendiumModal.license') }}:</strong> {{ indexMetadata.license }}</div>
                            </div>
                        </div>
                    </div>
                    <div
                        v-else-if="selectedItem"
                        class="qe-markdown"
                        @click="handleMarkdownClick"
                        @contextmenu="handleMarkdownContextMenu"
                        @dragstart.capture="handleCompendiumImageDragStart"
                    >
                        <div
                            v-if="itemLoading"
                            class="qe-loading-inline"
                        >
                            {{ t("game.ui.extensions.CompendiumModal.loading") }}
                        </div>
                        <div v-else>
                            <div
                                ref="markdownContentRef"
                                class="qe-markdown-content"
                                v-html="selectedMarkdownHtml"
                            />
                                          <div v-if="selectedItem?.item.tags && Object.keys(selectedItem.item.tags).length > 0" class="qe-item-tags">
                                 <div v-for="(tags, catName) in selectedItem.item.tags" :key="catName" class="qe-item-tag-group">
                                     <span class="qe-item-tag-category">{{ catName }}:</span>
                                     <span v-for="tag in tags" :key="tag.id" class="qe-item-tag" @click="selectItemTag(tag.id)">{{ tag.name }}</span>

                                 </div>
                             </div>
                <div v-if="nextItem || prevItem" class="qe-continue-reading">
                                <div class="qe-nav-adjacent">
                                    <div class="qe-nav-col qe-nav-col--left">
                                        <button
                                            v-if="prevItem"
                                            type="button"
                                            class="qe-nav-link qe-nav-link--prev"
                                            @click="navigateToPrevItem"
                                        >
                                            {{
                                                t("game.ui.extensions.CompendiumModal.back_to", {
                                                    name: displayAdjacentItemName(prevItem),
                                                })
                                            }}
                                        </button>
                                    </div>
                                    <div class="qe-nav-col qe-nav-col--right">
                                        <button
                                            v-if="nextItem"
                                            type="button"
                                            class="qe-nav-link qe-nav-link--next"
                                            @click="navigateToNextItem"
                                        >
                                            {{
                                                t("game.ui.extensions.CompendiumModal.proceed_to", {
                                                    name: displayAdjacentItemName(nextItem),
                                                })
                                            }}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
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
        <div
            v-if="shareModalOpen"
            class="ext-ui-overlay open qe-share-overlay"
            role="dialog"
            aria-modal="true"
            @click.self="closeShareModal"
        >
            <div class="ext-ui-overlay-panel ext-ui-overlay-panel--sm ext-ui-overlay-panel--padded qe-share-modal-panel" @click.stop>
                <h3 class="qe-share-modal-title">{{ t("game.ui.extensions.CompendiumModal.share_dialog_title") }}</h3>
                <p class="qe-share-modal-hint">{{ t("game.ui.extensions.CompendiumModal.share_dialog_hint") }}</p>
                <div class="qe-share-modal-actions">
                    <button type="button" class="ext-ui-btn ext-ui-btn-primary" @click="shareToChatAndClose">
                        {{ t("game.ui.extensions.CompendiumModal.share_to_chat_action") }}
                    </button>
                    <button type="button" class="ext-ui-btn ext-ui-btn-success" @click="addCompendiumToNote">
                        {{ t("game.ui.extensions.CompendiumModal.add_as_note") }}
                    </button>
                </div>
            </div>
        </div>
    </Teleport>

    <Teleport to="body">
        <div
            v-if="translateBatchConfirmOpen"
            class="ext-ui-overlay open qe-share-overlay"
            role="dialog"
            aria-modal="true"
            :aria-label="t('game.ui.extensions.CompendiumModal.translate_batch_title')"
            @click.self="closeTranslateBatchConfirm"
        >
            <div
                class="ext-ui-overlay-panel ext-ui-overlay-panel--sm ext-ui-overlay-panel--padded qe-share-modal-panel"
                @click.stop
            >
                <h3 class="qe-share-modal-title">{{ t("game.ui.extensions.CompendiumModal.translate_batch_title") }}</h3>
                <p class="qe-share-modal-hint">
                    {{ t("game.ui.extensions.CompendiumModal.translate_batch_body", { count: translateBatchPendingCount }) }}
                </p>
                <div class="qe-translate-batch-actions">
                    <button type="button" class="ext-ui-btn" @click="closeTranslateBatchConfirm">
                        {{ t("game.ui.extensions.CompendiumModal.translate_batch_confirm_cancel") }}
                    </button>
                    <button type="button" class="ext-ui-btn ext-ui-btn-primary" @click="confirmTranslateBatch">
                        {{ t("game.ui.extensions.CompendiumModal.translate_batch_confirm_start") }}
                    </button>
                </div>
            </div>
        </div>
    </Teleport>

    <Teleport to="body">
        <div
            v-if="imgContextMenu"
            class="qe-img-ctx-backdrop"
            @mousedown="closeImgContextMenu"
        >
            <div
                class="qe-img-ctx-menu"
                :style="{ left: imgContextMenu.x + 'px', top: imgContextMenu.y + 'px' }"
                @mousedown.stop
            >
                <div
                    v-if="imgContextMenuAlreadyInAssets"
                    class="qe-img-ctx-item qe-img-ctx-item--disabled"
                    role="status"
                >
                    {{ t("game.ui.extensions.CompendiumModal.image_already_in_assets") }}
                </div>
                <button
                    v-else
                    type="button"
                    class="qe-img-ctx-item"
                    :disabled="addToAssetsLoading"
                    @click="addCompendiumImageToAssets"
                >
                    {{ t("game.ui.extensions.CompendiumModal.add_to_assets") }}
                </button>
            </div>
        </div>
    </Teleport>

    <Teleport to="body">
        <div v-if="installDialogOpen" class="qe-install-overlay" @click.self="installDialogOpen = false">
            <div class="qe-install-dialog">
                <h3>{{ t("game.ui.extensions.CompendiumModal.install_compendium") }}</h3>
                <p class="qe-install-hint">{{ t("game.ui.extensions.CompendiumModal.install_prompt") }}</p>
                <input
                    ref="fileInputRef"
                    type="file"
                    accept=".json"
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
                    <div class="qe-install-field checkbox-field">
                        <label class="ext-ui-checkbox">
                            <input v-model="installAssets" type="checkbox" />
                            <span>{{ t("game.ui.extensions.CompendiumModal.install_assets") }}</span>
                        </label>
                    </div>
                    <div v-if="installAssets" class="qe-install-field">
                        <label>{{ t("game.ui.extensions.CompendiumModal.assets_zip_file") }}</label>
                        <input
                            ref="assetZipInputRef"
                            type="file"
                            accept=".zip"
                            style="display: none"
                            @change="onAssetZipFileChange"
                        />
                        <button
                            type="button"
                            class="qe-install-file-btn"
                            :class="{ 'file-selected': !!assetZipFile }"
                            @click="assetZipInputRef?.click()"
                        >
                            {{ assetZipFile?.name ?? t("game.ui.extensions.CompendiumModal.assets_zip_file") }}
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

.qe-batch-translate-hint {
    padding: 0.35rem 0.75rem 0.25rem;
    font-size: 0.8rem;
    color: #555;
    text-align: center;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
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
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.25rem 0.6rem;
        font-size: 0.8rem;

        &.active {
            background: #e0e8f0;
            border-color: #888;
            color: #333;
        }
    }

    .qe-search-filter-default-star {
        color: #f9a825;
        flex-shrink: 0;
    }

    .qe-search-result-title {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
    }

    .qe-search-result-default-star {
        color: #f9a825;
        flex-shrink: 0;
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
    border-top: 1px solid #eee;
}

.qe-tree {
    flex-shrink: 0;
    border-right: none;
    overflow: visible;
    min-height: 0;
    background: #fafafa;
    position: relative;
    transition: width 0.3s ease;

    &.collapsed {
        width: 0 !important;
        border: none;
        overflow: visible;
        
        .qe-tree-content {
            display: none;
        }
    }
}

.qe-tree-content {
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 0.5rem 0.5rem 0.5rem 0;
}

.qe-sidebar-toggle {
    position: absolute;
    right: -24px;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 32px;
    background: #f0f0f0;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    z-index: 10;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);

    &:hover {
        background: #e0e0e0;
        color: #333;
    }
}

.qe-sidebar-resizer {
    flex-shrink: 0;
    width: 3px;
    cursor: col-resize;
    background: #eee;
    transition: background 0.15s;

    &:hover {
        background: #c0d0e0;
    }
}

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

    .qe-tree-collection-row {
        display: flex;
        align-items: center;
        gap: 0.25rem;
        min-width: 0;
        flex-wrap: nowrap;
    }

    .qe-tree-collection-row .qe-tree-toggle.coll {
        flex: 0 0 auto;
    }

    .qe-tree-collection-row .qe-tree-count {
        flex-shrink: 0;
        margin-left: auto;
        padding-left: 0.25rem;
        font-size: 0.8rem;
        color: #888;
    }

    .qe-tree-coll-name {
        flex: 1;
        min-width: 0;
        font-size: 0.85rem;
        cursor: pointer;
        color: #333;
        text-align: left;
    }

    .qe-tree-coll-name.has-children:hover {
        text-decoration: underline;
        color: #1565c0;
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
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 1.1rem;
    font-weight: 700;
    color: #2d3748;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #e2e8f0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.qe-index-subcolls {
    margin-top: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.qe-index-subcoll-title {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: #4a5568;
    margin-bottom: 0.5rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px dashed #e2e8f0;
}

.qe-index-branch-translated-icon {
    flex-shrink: 0;
    font-size: 0.95em;
}

.qe-index-branch-translated-icon--complete {
    color: #1976d2;
}

.qe-index-branch-translated-icon--partial {
    color: #e65100;
}

.qe-index-coll-title-link {
    flex: 1;
    min-width: 0;
    border: none;
    background: transparent;
    padding: 0;
    margin: 0;
    font: inherit;
    font-weight: inherit;
    color: inherit;
    text-align: left;
    cursor: pointer;
    text-decoration: none;

    &:hover {
        color: #2b6cb0;
        text-decoration: underline;
    }
}

.qe-index-metadata {
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid #e2e8f0;
    font-size: 0.9rem;
    color: #718096;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
}

.qe-metadata-row strong {
    color: #4a5568;
    margin-right: 0.4rem;
}

.qe-metadata-row a {
    color: #4299e1;
    text-decoration: none;
    transition: color 0.2s;
}

.qe-metadata-row a:hover {
    color: #2b6cb0;
    text-decoration: underline;
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

.qe-continue-reading {
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid #e2e8f0;
}

.qe-nav-adjacent {
    display: flex;
    flex-direction: row;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    width: 100%;
}

.qe-nav-col {
    flex: 1;
    min-width: 0;

    &--left {
        text-align: left;
    }

    &--right {
        text-align: right;
    }
}

.qe-nav-link {
    background: transparent;
    border: none;
    color: #3182ce;
    font-weight: 600;
    cursor: pointer;
    font-size: 0.98rem;
    line-height: 1.35;
    padding: 0.15rem 0;
    transition: color 0.2s;

    &:hover {
        color: #2b6cb0;
        text-decoration: underline;
    }

    &--prev {
        text-align: left;
    }

    &--next {
        text-align: right;
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

    .qe-breadcrumb-link {
        background: none;
        border: none;
        padding: 0;
        margin: 0;
        cursor: pointer;
        color: #5b8ef0;
        font-size: inherit;
        font-family: inherit;
        text-transform: capitalize;
        text-decoration: none;

        &:hover {
            text-decoration: underline;
            color: #3a6fd8;
        }
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

.qe-item-view-heading {
    flex-shrink: 0;
    margin: 0;
    padding: 0.75rem 1.5rem 0.65rem;
    font-size: 1.35rem;
    font-weight: 600;
    line-height: 1.3;
    color: #1a1a1a;
    border-bottom: 1px solid #eee;
    background: #fafafa;
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

    :deep(blockquote) {
        text-align: center;
        margin: 0.75rem auto;
        padding: 0.5rem 1rem;
        max-width: 95%;
    }

    :deep(blockquote p) {
        text-align: center;
    }

    :deep(ul),
    :deep(ol) {
        margin: 0.4rem 0;
        padding-left: 1.5rem;
    }

    :deep(img) {
        max-width: 34%;
        height: auto;
        display: block;
        margin: 0.5rem auto;
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

/* Modale condividi (sopra il modale Compendium; stile base da static/extensions/ui.css .ext-ui-overlay) */
.qe-share-overlay {
    z-index: 10052;
}

.qe-share-modal-title {
    margin: 0 0 0.5rem;
    font-size: 1.1rem;
    font-weight: 600;
}

.qe-share-modal-hint {
    margin: 0 0 1rem;
    font-size: 0.9rem;
    color: #666;
    line-height: 1.35;
}

.qe-share-modal-actions {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.qe-translate-batch-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: flex-end;
    margin-top: 0.25rem;
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
    border-color: #e65100 !important;
    color: #e65100 !important;
    background: #fff !important;

    &.is-active {
        background: #e65100 !important;
        color: #fff !important;
    }
}

.qe-translate-inline-btn {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2rem;
    height: 2rem;
    padding: 0;
    border: 1px solid #e65100;
    border-radius: 50%;
    background: #fff8e1;
    color: #e65100;
    cursor: pointer;

    &:hover:not(:disabled) {
        background: #ffecb3;
    }

    &:disabled {
        opacity: 0.55;
        cursor: not-allowed;
    }
}

.qe-translate-inline-btn--index-header {
    width: 2.25rem;
    height: 2.25rem;
}

.translate-btn:hover:not(:disabled) {
    background: #fff3e0 !important;
    &.is-active {
        background: #e65100 !important;
        color: #fff !important;
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

    &.translation-tag--index-icon-only {
        padding: 0.2rem;
        margin: 0;
        font-size: 1rem;
        line-height: 1;
        border-radius: 50%;

        &.translation-tag--index-complete {
            background: #e3f2fd;
            color: #1976d2;
            border-color: #bbdefb;

            &:hover {
                background: #bbdefb;
            }
        }

        &.translation-tag--index-partial {
            background: #fff3e0;
            color: #e65100;
            border-color: #ffcc80;

            &:hover {
                background: #ffe0b2;
            }
        }
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

.qe-markdown-content :deep(img) {
    max-width: 50%;
    display: block;
    margin: 0.5rem auto;
    cursor: grab;
}

.qe-markdown-content :deep(img:active) {
    cursor: grabbing;
}

.qe-img-ctx-backdrop {
    position: fixed;
    inset: 0;
    z-index: 10050;
    background: transparent;
}

.qe-img-ctx-menu {
    position: fixed;
    z-index: 10051;
    min-width: 12rem;
    padding: 0.25rem 0;
    background: var(--modal-bg, #fff);
    border: 1px solid var(--border-color, #ddd);
    border-radius: 6px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.qe-img-ctx-item--disabled {
    padding: 0.5rem 0.75rem;
    font-size: 0.85rem;
    color: #9a9a9a;
    opacity: 0.92;
    cursor: default;
    user-select: none;
}

.qe-img-ctx-item {
    display: block;
    width: 100%;
    padding: 0.5rem 0.85rem;
    border: none;
    background: transparent;
    text-align: left;
    font-size: 0.9rem;
    cursor: pointer;
    color: inherit;

    &:hover:not(:disabled) {
        background: rgba(0, 0, 0, 0.06);
    }

    &:disabled {
        opacity: 0.6;
        cursor: wait;
    }
}

.filter-btn {
    position: relative;
    &.has-filters {
        border-color: #4caf50 !important;
        color: #4caf50 !important;
    }
    &.is-active {
        background: #e8f5e9 !important;
        color: #2e7d32 !important;
        border-color: #4caf50 !important;
    }
}

/* Stessa estetica di ui.css .ext-toolbar-bar / .ext-toolbar-bar.ext-search-bar (#fafafa, padding 0.625rem 1.5rem) */
.ext-search-bar {
    display: grid !important;
    grid-template-columns: auto auto 1fr auto auto auto auto;
    align-items: center;
    gap: 0.5rem;
    background: #fafafa !important;
    padding: 0.625rem 1.5rem;
    border-radius: 0;
    border-bottom: 1px solid #eee;

    &.qe-tag-filter-shelf {
        border-top: none;
        border-bottom: none;
        margin-top: -1px;
        padding-top: 0;
        background: #fafafa !important;

        .ga-spacer {
            pointer-events: none;
            visibility: hidden;
        }
    }
}

.qe-tag-filter-shelf {
    background: #fafafa;
    border: none !important;
    border-radius: 0;
    padding: 0;
    margin: 0 0 0.4rem 0;
    box-shadow: none !important;
    display: flex;
    flex-direction: column;
}



// Keep badge style for funnel button
.qe-tag-filter-badge {
    position: absolute;
    top: -5px;
    right: -5px;
    background: #e53935;
    color: #fff;
    border-radius: 50%;
    font-size: 0.65rem;
    width: 17px;
    height: 17px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    pointer-events: none;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}


.qe-clear-tags-btn {
    border-color: #e53935 !important;
    color: #e53935 !important;
    background: #fff !important;

    &:hover {
        background: #ffebee !important;
    }
}


.qe-item-tags {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid #eee;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    font-size: 0.9rem;

    .qe-item-tag-group {
        display: flex;
        align-items: center;
        gap: 0.5rem;

        .qe-item-tag-category {
            font-weight: 600;
            color: #666;
        }

        .qe-item-tag {
            background: #e3f2fd;
            color: #1565c0;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s;

            &:hover {
                background: #bbdefb;
            }
        }

    }
}
</style>
