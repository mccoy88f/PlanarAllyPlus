<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import { baseAdjust } from "../../../core/http";
import { getQeNames, renderQeMarkdown } from "../../systems/extensions/compendium";
import { extensionsState } from "../../systems/extensions/state";
import { openCompendiumModalForItem } from "../../systems/extensions/ui";

const { t } = useI18n();

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
let loadingTimer: ReturnType<typeof setTimeout> | null = null;

async function fetchItem(comp: string | undefined, coll: string, slug: string): Promise<void> {
    if (loadingTimer) clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => {
        loading.value = true;
    }, 150);

    try {
        const params = new URLSearchParams({ collection: coll, slug });
        const ctxId = extensionsState.reactive.compendiumPreviewContext?.compendiumId;
        const compResolved = (comp?.trim() || ctxId || "").trim() || undefined;
        if (compResolved) params.set("compendium", compResolved);
        const r = await fetch(
            baseAdjust(`/api/extensions/compendium/item?${params.toString()}`),
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
    const parts = rest.split("/");
    if (parts.length >= 3) {
        return { comp: parts[0], coll: parts[1] ?? "", slug: parts[2] ?? "" };
    }
    if (parts.length === 2) {
        return { coll: parts[0] ?? "", slug: parts[1] ?? "" };
    }
    return null;
}

function showAtCoords(coll: string, slug: string, comp: string | undefined, screenX: number, screenY: number): void {
    compendiumSlug.value = comp;
    collectionSlug.value = coll;
    itemSlug.value = slug;
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
    visible.value = true;
    fetchItem(comp, coll, slug);
}

function show(e: MouseEvent, href: string): void {
    const parsed = parseQeHref(href);
    if (!parsed || !parsed.coll || !parsed.slug) return;

    compendiumSlug.value = parsed.comp;
    collectionSlug.value = parsed.coll;
    itemSlug.value = parsed.slug;
    const pad = 8;
    let tx = e.clientX + pad;
    let ty = e.clientY + 4;
    const maxW = 360;
    const maxH = 400;
    if (tx + maxW > window.innerWidth) tx = window.innerWidth - maxW - 8;
    if (ty + maxH > window.innerHeight) ty = window.innerHeight - maxH - 8;
    if (tx < 8) tx = 8;
    if (ty < 8) ty = 8;
    x.value = tx;
    y.value = ty;

    visible.value = true;
    fetchItem(parsed.comp, parsed.coll, parsed.slug);
}

function stripLeadingTitle(md: string, itemTitle: string): string {
    if (!md || !itemTitle) return md;
    const t = itemTitle.trim();
    const re = new RegExp(`^#+\\s*${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\n+`, "i");
    return md.replace(re, "");
}

function closeTooltip(): void {
    visible.value = false;
}

function openFullCompendiumAndClose(): void {
    openCompendiumModalForItem(
        collectionSlug.value,
        itemSlug.value,
        compendiumSlug.value,
    );
    closeTooltip();
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
        showAtCoords(coll, slug, comp, screenX, screenY);
    }
}

function handleDocumentClick(e: MouseEvent): void {
    const target = (e.target as HTMLElement).closest("a[data-qe-collection], a[href^='qe:']");
    /* Anche dentro CompendiumModal: stesso comportamento dell’anteprima (non navigare con selectItem). */
    if (target instanceof HTMLAnchorElement) {
        const qeHref = getQeHrefFromAnchor(target);
        if (qeHref) {
            e.preventDefault();
            e.stopPropagation();
            show(e, qeHref);
        }
        return;
    }
    if (visible.value && !(e.target as HTMLElement).closest(".qe-hover-tooltip")) {
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
            :style="{ left: `${x}px`, top: `${y}px` }"
            @click.stop
        >
            <div class="qe-tooltip-header">
                <span class="qe-tooltip-title">{{ loading ? '...' : title }}</span>
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
            <div v-if="loading" class="qe-tooltip-loading">...</div>
            <div v-else class="qe-tooltip-body">
                <!-- eslint-disable-next-line vue/no-v-html -->
                <div v-html="renderQeMarkdown(markdown.substring(0, 600) + (markdown.length > 600 ? '...' : ''))" />
            </div>
            <div class="qe-tooltip-footer">
                <button type="button" class="qe-tooltip-continue" @click="openFullCompendiumAndClose">
                    {{ t("game.ui.extensions.CompendiumModal.continue_in_compendium") }}
                </button>
            </div>
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

.qe-tooltip-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
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
