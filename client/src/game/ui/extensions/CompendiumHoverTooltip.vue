<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import { baseAdjust, http } from "../../../core/http";
import {
    compendiumRoomScopeQuerySuffix,
    compendiumSlugFromResolvedId,
    getQeNames,
    loadCompendiumResolverMap,
    parseQePathSegments,
    renderQeMarkdown,
    resolveCompendiumIdForItemQuery,
} from "../../systems/extensions/compendium";
import { extensionsState } from "../../systems/extensions/state";
import { openCompendiumModalForItem } from "../../systems/extensions/ui";

const { t } = useI18n();

/** Stesso contratto della ricerca nel modale compendio. */
interface QeSearchHit {
    compendiumId?: string;
    compendiumName?: string;
    collectionSlug: string;
    collectionName: string;
    itemSlug: string;
    itemName: string;
}

const visible = ref(false);
const x = ref(0);
const y = ref(0);
const title = ref("");
const path = ref("");
const markdown = ref("");
const loading = ref(false);
const collectionSlug = ref("");
const itemSlug = ref("");
const compendiumSlug = ref<string | undefined>(undefined);
const selectedCompendiumIdForOpen = ref<string | undefined>(undefined);

type TooltipPhase = "picker-loading" | "picker" | "preview";
const phase = ref<TooltipPhase>("preview");
const pickerPreferred = ref<QeSearchHit[]>([]);
const pickerOthers = ref<QeSearchHit[]>([]);
const pickerTotalCount = ref(0);
const allowPickerBack = ref(false);

const defaultCompendiumId = computed(() => extensionsState.reactive.compendiumDefaultId);

let loadingTimer: ReturnType<typeof setTimeout> | null = null;

function positionTooltip(screenX: number, screenY: number): void {
    const pad = 8;
    let tx = screenX + pad;
    let ty = screenY + 4;
    const maxW = 360;
    const maxH = 400;
    if (tx + maxW > window.innerWidth) tx = window.innerWidth - maxW - 8;
    if (ty + maxH > window.innerHeight) ty = window.innerHeight - maxH - 8;
    if (tx < 8) tx = 8;
    if (ty < 8) ty = 8;
    x.value = tx;
    y.value = ty;
}

function buildResultPool(results: QeSearchHit[], linkLabel: string): QeSearchHit[] {
    const qn = linkLabel.trim().toLowerCase();
    if (!qn) return [];
    const exact = results.filter((r) => r.itemName.trim().toLowerCase() === qn);
    if (exact.length > 0) return exact;
    const starts = results.filter((r) => r.itemName.trim().toLowerCase().startsWith(qn));
    if (starts.length > 0) return starts.length > 40 ? starts.slice(0, 40) : starts;
    return results.slice(0, 25);
}

function partitionPreferred(pool: QeSearchHit[]): { preferred: QeSearchHit[]; others: QeSearchHit[] } {
    const defId = extensionsState.reactive.compendiumDefaultId;
    const preferred = pool.filter((r) => r.compendiumId === defId);
    const others = pool.filter((r) => r.compendiumId !== defId);
    return { preferred, others };
}

async function fetchItem(
    comp: string | undefined,
    coll: string,
    slug: string,
    compendiumIdHint?: string,
): Promise<void> {
    if (loadingTimer) clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => {
        loading.value = true;
    }, 150);

    try {
        await loadCompendiumResolverMap();
        const params = new URLSearchParams({ collection: coll, slug });
        const compResolved = compendiumIdHint ?? resolveCompendiumIdForItemQuery(comp);
        if (compResolved) params.set("compendium", compResolved);
        const r = await fetch(
            baseAdjust(
                `/api/extensions/compendium/item?${params.toString()}${compendiumRoomScopeQuerySuffix()}`,
            ),
            { credentials: "include" },
        );
        if (r.ok) {
            const data = (await r.json()) as {
                name: string;
                markdown: string;
                collectionName?: string;
                compendiumName?: string;
            };
            title.value = data.name;
            const parts: string[] = [];
            if (data.compendiumName) parts.push(data.compendiumName);
            parts.push(data.collectionName || coll, data.name);
            path.value = parts.join(" › ");
            markdown.value = stripLeadingTitle(data.markdown, data.name);
        } else {
            visible.value = false;
        }
    } catch {
        visible.value = false;
    } finally {
        if (loadingTimer) {
            clearTimeout(loadingTimer);
            loadingTimer = null;
        }
        loading.value = false;
    }
}

function parseQeHref(href: string): { comp?: string; coll: string; slug: string } | null {
    const rest = href.slice(3);
    const { compSlug, collectionSlug, itemSlug } = parseQePathSegments(rest);
    if (!collectionSlug || !itemSlug) return null;
    return { comp: compSlug, coll: collectionSlug, slug: itemSlug };
}

async function openDisambiguationFlow(
    linkLabel: string | undefined,
    fallback: { comp?: string; coll: string; slug: string },
    screenX: number,
    screenY: number,
): Promise<void> {
    positionTooltip(screenX, screenY);
    visible.value = true;
    allowPickerBack.value = false;
    pickerPreferred.value = [];
    pickerOthers.value = [];
    pickerTotalCount.value = 0;
    title.value = "";
    path.value = "";
    markdown.value = "";

    const label = linkLabel?.trim() ?? "";
    if (label.length < 2) {
        phase.value = "preview";
        compendiumSlug.value = fallback.comp;
        collectionSlug.value = fallback.coll;
        itemSlug.value = fallback.slug;
        selectedCompendiumIdForOpen.value = undefined;
        await fetchItem(fallback.comp, fallback.coll, fallback.slug);
        return;
    }

    phase.value = "picker-loading";
    try {
        await loadCompendiumResolverMap();
        const params = new URLSearchParams({ q: label });
        const r = await http.get(
            `/api/extensions/compendium/search?${params.toString()}${compendiumRoomScopeQuerySuffix()}`,
        );
        if (!r.ok) throw new Error("search failed");
        const data = (await r.json()) as { results: QeSearchHit[] };
        const pool = buildResultPool(data.results ?? [], label);
        pickerTotalCount.value = pool.length;

        if (pool.length === 0) {
            phase.value = "preview";
            compendiumSlug.value = fallback.comp;
            collectionSlug.value = fallback.coll;
            itemSlug.value = fallback.slug;
            selectedCompendiumIdForOpen.value = undefined;
            await fetchItem(fallback.comp, fallback.coll, fallback.slug);
            return;
        }

        if (pool.length === 1) {
            const h = pool[0]!;
            phase.value = "preview";
            compendiumSlug.value = compendiumSlugFromResolvedId(h.compendiumId);
            collectionSlug.value = h.collectionSlug;
            itemSlug.value = h.itemSlug;
            selectedCompendiumIdForOpen.value = h.compendiumId;
            allowPickerBack.value = false;
            await fetchItem(compendiumSlug.value, h.collectionSlug, h.itemSlug, h.compendiumId);
            return;
        }

        const { preferred, others } = partitionPreferred(pool);
        pickerPreferred.value = preferred;
        pickerOthers.value = others;
        phase.value = "picker";
    } catch {
        phase.value = "preview";
        compendiumSlug.value = fallback.comp;
        collectionSlug.value = fallback.coll;
        itemSlug.value = fallback.slug;
        selectedCompendiumIdForOpen.value = undefined;
        await fetchItem(fallback.comp, fallback.coll, fallback.slug);
    }
}

function showAtCoords(
    coll: string,
    slug: string,
    comp: string | undefined,
    screenX: number,
    screenY: number,
    linkLabel?: string,
): void {
    void openDisambiguationFlow(linkLabel?.trim() || undefined, { comp, coll, slug }, screenX, screenY);
}

function show(e: MouseEvent, href: string, anchor: HTMLAnchorElement): void {
    const parsed = parseQeHref(href);
    if (!parsed || !parsed.coll || !parsed.slug) return;
    const linkLabel = (anchor.textContent ?? "").trim();
    void openDisambiguationFlow(linkLabel || undefined, { comp: parsed.comp, coll: parsed.coll, slug: parsed.slug }, e.clientX, e.clientY);
}

function stripLeadingTitle(md: string, itemTitle: string): string {
    if (!md || !itemTitle) return md;
    const t = itemTitle.trim();
    const re = new RegExp(`^#+\\s*${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n+`, "i");
    return md.replace(re, "");
}

function closeTooltip(): void {
    visible.value = false;
    phase.value = "preview";
    pickerPreferred.value = [];
    pickerOthers.value = [];
    allowPickerBack.value = false;
    pickerTotalCount.value = 0;
    selectedCompendiumIdForOpen.value = undefined;
    title.value = "";
    path.value = "";
    markdown.value = "";
}

function openFullCompendiumAndClose(): void {
    openCompendiumModalForItem(
        collectionSlug.value,
        itemSlug.value,
        compendiumSlug.value,
        selectedCompendiumIdForOpen.value,
    );
    closeTooltip();
}

function selectPickerResult(hit: QeSearchHit): void {
    allowPickerBack.value = pickerTotalCount.value > 1;
    compendiumSlug.value = compendiumSlugFromResolvedId(hit.compendiumId);
    selectedCompendiumIdForOpen.value = hit.compendiumId;
    collectionSlug.value = hit.collectionSlug;
    itemSlug.value = hit.itemSlug;
    phase.value = "preview";
    void fetchItem(compendiumSlug.value, hit.collectionSlug, hit.itemSlug, hit.compendiumId);
}

function backToPicker(): void {
    phase.value = "picker";
    title.value = "";
    path.value = "";
    markdown.value = "";
}

function pickerSubtitle(hit: QeSearchHit): string {
    if (hit.compendiumName?.trim()) {
        return `${hit.compendiumName} › ${hit.collectionName}`;
    }
    return hit.collectionName;
}

function getQeHrefFromAnchor(target: HTMLAnchorElement): string | null {
    const dataComp = target.getAttribute("data-qe-compendium");
    const dataColl = target.getAttribute("data-qe-collection");
    const dataSlug = target.getAttribute("data-qe-slug");
    if (dataColl && dataSlug) {
        return dataComp ? `qe:${dataComp}/${dataColl}/${dataSlug}` : `qe:${dataColl}/${dataSlug}`;
    }
    const href = target.getAttribute("href");
    if (href?.startsWith("qe:")) return href;
    return null;
}

function findIframeForSource(source: MessageEventSource | null): HTMLIFrameElement | null {
    if (!source || typeof (source as Window).document === "undefined") return null;
    const iframes = document.querySelectorAll("iframe");
    for (let i = 0; i < iframes.length; i++) {
        try {
            if (iframes[i]!.contentWindow === source) return iframes[i]!;
        } catch {
            /* cross-origin */
        }
    }
    return null;
}

function handleMessage(e: MessageEvent): void {
    const data = e.data as unknown;
    if (!data || typeof data !== "object") return;
    const d = data as Record<string, unknown>;
    if (d.type === "planarally-qe-hover") {
        const coll = d.collection as string | undefined;
        const slug = d.slug as string | undefined;
        const comp = d.compendium as string | undefined;
        const linkLabel = typeof d.linkLabel === "string" ? d.linkLabel : undefined;
        const clientX = typeof d.clientX === "number" ? d.clientX : 0;
        const clientY = typeof d.clientY === "number" ? d.clientY : 0;
        if (!coll || !slug) return;
        const iframe = findIframeForSource(e.source) ?? document.querySelector(".ext-modal-iframe");
        let screenX = clientX;
        let screenY = clientY;
        if (iframe instanceof HTMLIFrameElement) {
            const rect = iframe.getBoundingClientRect();
            screenX = rect.left + clientX;
            screenY = rect.top + clientY;
        }
        showAtCoords(coll, slug, comp, screenX, screenY, linkLabel);
    }
}

/** Click su testo dentro `<a>` espone spesso un Text node: senza questo `.closest` fallisce. */
function eventTargetElement(e: MouseEvent): Element | null {
    const t = e.target;
    if (t instanceof Element) return t;
    if (t instanceof Text) return t.parentElement;
    return null;
}

function handleDocumentClick(e: MouseEvent): void {
    const fromEl = eventTargetElement(e);
    const target = fromEl?.closest("a[data-qe-collection], a[href^='qe:']");
    /* Anche dentro CompendiumModal: anteprima; link nell’anteprima con compendio aperto → apri la voce nel modale. */
    if (target instanceof HTMLAnchorElement) {
        const qeHref = getQeHrefFromAnchor(target);
        if (qeHref) {
            e.preventDefault();
            e.stopPropagation();
            const insideTooltip = target.closest(".qe-hover-tooltip");
            if (insideTooltip && extensionsState.raw.compendiumModalOpen) {
                const parsed = parseQeHref(qeHref);
                if (parsed?.coll && parsed.slug) {
                    openCompendiumModalForItem(parsed.coll, parsed.slug, parsed.comp);
                    closeTooltip();
                }
            } else {
                show(e, qeHref, target);
            }
        }
        return;
    }
    if (visible.value && !fromEl?.closest(".qe-hover-tooltip")) {
        closeTooltip();
    }
}

function handleEscape(e: KeyboardEvent): void {
    if (e.key === "Escape" && visible.value) {
        e.stopPropagation();
        closeTooltip();
    }
}

onMounted(() => {
    void loadCompendiumResolverMap();
    getQeNames(); // preload per autolink
    document.addEventListener("click", handleDocumentClick, true);
    window.addEventListener("message", handleMessage);
    window.addEventListener("keydown", handleEscape, true);
});

onUnmounted(() => {
    document.removeEventListener("click", handleDocumentClick, true);
    window.removeEventListener("message", handleMessage);
    window.removeEventListener("keydown", handleEscape, true);
});
</script>

<template>
    <Teleport to="body">
        <div
            v-if="visible"
            class="qe-hover-tooltip"
            :class="{ 'qe-hover-tooltip--picker': phase === 'picker' || phase === 'picker-loading' }"
            :style="{ left: `${x}px`, top: `${y}px` }"
            @click.stop
        >
            <!-- Elenco disambiguazione -->
            <template v-if="phase === 'picker-loading'">
                <div class="qe-tooltip-header">
                    <span class="qe-tooltip-title">{{ t("game.ui.extensions.CompendiumModal.searching") }}</span>
                    <button
                        type="button"
                        class="qe-tooltip-close"
                        :aria-label="t('game.ui.extensions.CompendiumModal.preview_close')"
                        @click="closeTooltip"
                    >
                        ×
                    </button>
                </div>
                <div class="qe-tooltip-loading qe-picker-loading-msg">…</div>
            </template>

            <template v-else-if="phase === 'picker'">
                <div class="qe-tooltip-header">
                    <span class="qe-tooltip-title">{{ t("game.ui.extensions.CompendiumModal.hover_pick_title") }}</span>
                    <button
                        type="button"
                        class="qe-tooltip-close"
                        :aria-label="t('game.ui.extensions.CompendiumModal.preview_close')"
                        @click="closeTooltip"
                    >
                        ×
                    </button>
                </div>
                <div class="qe-picker-body">
                    <template v-if="pickerPreferred.length > 0">
                        <div class="qe-picker-section-label">
                            {{ t("game.ui.extensions.CompendiumModal.hover_section_preferred") }}
                        </div>
                        <button
                            v-for="hit in pickerPreferred"
                            :key="`p-${hit.compendiumId ?? ''}-${hit.collectionSlug}-${hit.itemSlug}`"
                            type="button"
                            class="qe-picker-row"
                            @click="selectPickerResult(hit)"
                        >
                            <span class="qe-picker-row-sub">{{ pickerSubtitle(hit) }}</span>
                            <span class="qe-picker-row-title">
                                <span
                                    v-if="defaultCompendiumId && hit.compendiumId === defaultCompendiumId"
                                    class="qe-picker-star"
                                    :title="t('game.ui.extensions.CompendiumModal.default_compendium')"
                                >★</span>
                                {{ hit.itemName }}
                            </span>
                        </button>
                    </template>
                    <template v-if="pickerOthers.length > 0">
                        <div class="qe-picker-section-label qe-picker-section-label--spaced">
                            {{ t("game.ui.extensions.CompendiumModal.hover_section_other") }}
                        </div>
                        <button
                            v-for="hit in pickerOthers"
                            :key="`o-${hit.compendiumId ?? ''}-${hit.collectionSlug}-${hit.itemSlug}`"
                            type="button"
                            class="qe-picker-row"
                            @click="selectPickerResult(hit)"
                        >
                            <span class="qe-picker-row-sub">{{ pickerSubtitle(hit) }}</span>
                            <span class="qe-picker-row-title">{{ hit.itemName }}</span>
                        </button>
                    </template>
                </div>
            </template>

            <!-- Anteprima voce (come prima) -->
            <template v-else>
                <div class="qe-tooltip-header">
                    <button
                        v-if="allowPickerBack"
                        type="button"
                        class="qe-tooltip-back"
                        :title="t('game.ui.extensions.CompendiumModal.hover_back_list')"
                        @click="backToPicker"
                    >
                        ←
                    </button>
                    <span class="qe-tooltip-title">{{ loading ? "…" : title }}</span>
                    <button
                        type="button"
                        class="qe-tooltip-close"
                        :aria-label="t('game.ui.extensions.CompendiumModal.preview_close')"
                        @click="closeTooltip"
                    >
                        ×
                    </button>
                </div>
                <div v-if="path" class="qe-tooltip-path-bar">{{ path }}</div>
                <div v-if="loading" class="qe-tooltip-loading">…</div>
                <div v-else class="qe-tooltip-body">
                    <!-- eslint-disable-next-line vue/no-v-html -->
                    <div v-html="renderQeMarkdown(markdown.substring(0, 600) + (markdown.length > 600 ? '...' : ''))" />
                </div>
                <div class="qe-tooltip-footer">
                    <button type="button" class="qe-tooltip-continue" @click="openFullCompendiumAndClose">
                        {{ t("game.ui.extensions.CompendiumModal.continue_in_compendium") }}
                    </button>
                </div>
            </template>
        </div>
    </Teleport>
</template>

<style scoped>
.qe-hover-tooltip {
    position: fixed;
    z-index: 20000;
    max-width: 360px;
    max-height: 400px;
    padding: 0.5rem;
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 0.5rem;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    pointer-events: auto;
}

.qe-hover-tooltip--picker {
    max-height: min(400px, 85vh);
}

.qe-tooltip-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
}

.qe-tooltip-back {
    flex-shrink: 0;
    width: 1.75rem;
    height: 1.75rem;
    margin: 0;
    padding: 0;
    border: none;
    border-radius: 0.25rem;
    background: transparent;
    color: #1a5fb4;
    font-size: 1.1rem;
    line-height: 1;
    cursor: pointer;
}

.qe-tooltip-back:hover {
    background: #eef4fc;
}

.qe-tooltip-title {
    font-weight: 600;
    font-size: 0.95rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
}

.qe-tooltip-close {
    flex-shrink: 0;
    width: 1.75rem;
    height: 1.75rem;
    margin: 0;
    padding: 0;
    border: none;
    border-radius: 0.25rem;
    background: transparent;
    color: #555;
    font-size: 1.35rem;
    line-height: 1;
    cursor: pointer;
}

.qe-tooltip-close:hover {
    background: #eee;
    color: #111;
}

.qe-tooltip-path-bar {
    flex-shrink: 0;
    padding: 0.3rem 0;
    background: #f0f0f0;
    font-size: 0.8rem;
    color: #555;
    border-radius: 0.25rem;
    margin-bottom: 0.4rem;
    padding-left: 0.5rem;
    padding-right: 0.5rem;
}

.qe-tooltip-loading {
    padding: 0.5rem;
    color: #666;
    font-style: italic;
}

.qe-picker-loading-msg {
    flex: 1;
    min-height: 2rem;
}

.qe-picker-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    margin-top: 0.35rem;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.qe-picker-section-label {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #666;
    margin-top: 0.25rem;
    margin-bottom: 0.2rem;
}

.qe-picker-section-label--spaced {
    margin-top: 0.65rem;
}

.qe-picker-row {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0.15rem;
    width: 100%;
    margin: 0;
    padding: 0.45rem 0.5rem;
    border: 1px solid #e8e8e8;
    border-radius: 0.35rem;
    background: #fafafa;
    cursor: pointer;
    text-align: left;
    transition: background 0.12s ease, border-color 0.12s ease;
}

.qe-picker-row:hover {
    background: #f0f4fc;
    border-color: #c5d7f0;
}

.qe-picker-row-sub {
    font-size: 0.75rem;
    color: #666;
    line-height: 1.25;
}

.qe-picker-row-title {
    font-size: 0.88rem;
    font-weight: 600;
    color: #222;
    line-height: 1.3;
}

.qe-picker-star {
    color: #e8b00c;
    margin-right: 0.2rem;
    font-size: 0.85em;
}

.qe-tooltip-body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    font-size: 0.85rem;
    line-height: 1.4;
    padding-top: 0.4rem;
}

.qe-tooltip-body :deep(p) { margin: 0.3rem 0; }
.qe-tooltip-body :deep(img) {
    max-width: 50%;
    display: block;
    margin: 0.5rem auto;
}

.qe-tooltip-footer {
    flex-shrink: 0;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid #eee;
}

.qe-tooltip-continue {
    width: 100%;
    margin: 0;
    padding: 0.45rem 0.5rem;
    border: none;
    border-radius: 0.35rem;
    background: #f0f0f0;
    color: #1a5fb4;
    font-size: 0.88rem;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
}

.qe-tooltip-continue:hover {
    background: #e4e4e4;
}
</style>
