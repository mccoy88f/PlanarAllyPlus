<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

import { http } from "../../../core/http";
import { getQeNames, renderQeMarkdown } from "../../systems/extensions/compendium";
import { openCompendiumModalForItem } from "../../systems/extensions/ui";

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
const isMouseOverTooltip = ref(false);
let hideTimer: ReturnType<typeof setTimeout> | null = null;
let loadingTimer: ReturnType<typeof setTimeout> | null = null;

async function fetchItem(comp: string | undefined, coll: string, slug: string): Promise<void> {
    if (loadingTimer) clearTimeout(loadingTimer);
    loadingTimer = setTimeout(() => {
        loading.value = true;
    }, 150);

    try {
        const params = new URLSearchParams({ collection: coll, slug });
        if (comp) params.set("compendium", comp);
        const r = await http.get(
            `/api/extensions/compendium/item?${params.toString()}`,
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
    if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
    }
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
    if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
    }
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

function scheduleHide(): void {
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
        visible.value = false;
        hideTimer = null;
    }, 400);
}

function cancelHide(): void {
    if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
    }
}

function handleMouseOver(e: MouseEvent): void {
    const target = (e.target as HTMLElement).closest("a[href^='qe:'], a[data-qe-collection]");
    if (!(target instanceof HTMLAnchorElement)) return;
    cancelHide();
    const dataComp = target.getAttribute("data-qe-compendium");
    const dataColl = target.getAttribute("data-qe-collection");
    const dataSlug = target.getAttribute("data-qe-slug");
    const href = target.getAttribute("href");
    let qeHref: string;
    if (dataColl && dataSlug) {
        qeHref = dataComp
            ? `qe:${dataComp}/${dataColl}/${dataSlug}`
            : `qe:${dataColl}/${dataSlug}`;
    } else if (href?.startsWith("qe:")) {
        qeHref = href;
    } else {
        return;
    }
    show(e, qeHref);
}

function handleMouseOut(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    const related = e.relatedTarget as HTMLElement | null;
    const fromLink = target.closest("a[href^='qe:'], a[data-qe-collection]");
    const fromTooltip = target.closest(".qe-hover-tooltip");
    const toLink = related?.closest("a[href^='qe:'], a[data-qe-collection]");
    const toTooltip = related?.closest(".qe-hover-tooltip");
    if (fromLink && !toTooltip && !toLink) scheduleHide();
    if (fromTooltip && !toLink && !toTooltip) scheduleHide();
}

function handleMouseEnterTooltip(): void {
    isMouseOverTooltip.value = true;
    cancelHide();
}

function handleMouseLeaveTooltip(): void {
    isMouseOverTooltip.value = false;
    scheduleHide();
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
    } else if (d.type === "planarally-qe-hover-end") {
        if (isMouseOverTooltip.value) return;
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            if (isMouseOverTooltip.value) return;
            visible.value = false;
            hideTimer = null;
        }, 600);
    }
}

function handleDocumentClick(e: MouseEvent): void {
    const target = (e.target as HTMLElement).closest("a[data-qe-collection], a[href^='qe:']");
    if (!(target instanceof HTMLAnchorElement)) return;
    if (target.closest(".compendium-modal")) return;
    const dataComp = target.getAttribute("data-qe-compendium");
    const dataColl = target.getAttribute("data-qe-collection");
    const dataSlug = target.getAttribute("data-qe-slug");
    if (dataColl && dataSlug) {
        e.preventDefault();
        openCompendiumModalForItem(dataColl, dataSlug, dataComp ?? undefined);
        return;
    }
    const href = target.getAttribute("href");
    if (href?.startsWith("qe:")) {
        e.preventDefault();
        const parsed = parseQeHref(href);
        if (parsed) {
            openCompendiumModalForItem(
                parsed.coll,
                parsed.slug,
                parsed.comp,
            );
        }
    }
}

onMounted(() => {
    getQeNames(); // preload per autolink
    document.addEventListener("mouseover", handleMouseOver);
    document.addEventListener("mouseout", handleMouseOut);
    document.addEventListener("click", handleDocumentClick, true);
    window.addEventListener("message", handleMessage);
});

onUnmounted(() => {
    document.removeEventListener("mouseover", handleMouseOver);
    document.removeEventListener("mouseout", handleMouseOut);
    document.removeEventListener("click", handleDocumentClick, true);
    window.removeEventListener("message", handleMessage);
    if (hideTimer) clearTimeout(hideTimer);
});
</script>

<template>
    <Teleport to="body">
        <div
            v-if="visible"
            class="qe-hover-tooltip"
            :style="{ left: `${x}px`, top: `${y}px` }"
            @mouseenter="handleMouseEnterTooltip"
            @mouseleave="handleMouseLeaveTooltip"
            @click.stop
        >
            <div class="qe-tooltip-header">
                <span class="qe-tooltip-title">{{ loading ? '...' : title }}</span>
            </div>
            <div v-if="path" class="qe-tooltip-path-bar">{{ path }}</div>
            <div v-if="loading" class="qe-tooltip-loading">...</div>
            <div v-else class="qe-tooltip-body">
                <!-- eslint-disable-next-line vue/no-v-html -->
                <div v-html="renderQeMarkdown(markdown.substring(0, 600) + (markdown.length > 600 ? '...' : ''))" />
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
.qe-tooltip-body :deep(h1), .qe-tooltip-body :deep(h2), .qe-tooltip-body :deep(h3) {
    margin: 0.5rem 0 0.2rem;
    font-size: 1em;
}
</style>
