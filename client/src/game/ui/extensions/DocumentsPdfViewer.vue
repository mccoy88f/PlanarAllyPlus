<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";
import VuePdfApp from "vue3-pdf-app";
import "vue3-pdf-app/dist/icons/main.css";

import { uuidv4 } from "../../../core/utils";
import Modal from "../../../core/components/modals/Modal.vue";
import { baseAdjust } from "../../../core/http";
import { chatSystem } from "../../systems/chat";
import { extensionsState } from "../../systems/extensions/state";
import { closeDocumentsPdfViewer, focusExtension } from "../../systems/extensions/ui";
import { playerSystem } from "../../systems/players";
import { i18n } from "../../../i18n";

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

const pdfSrc = ref<string | ArrayBuffer | null>(null);
let lastBlobUrl: string | null = null;
/** Incrementata a ogni caricamento PDF: forza il remount di vue3-pdf-app e evita "0 pagine" riaprendo lo stesso file. */
const pdfViewerInstanceKey = ref(0);
/** Monta VuePdfApp solo dopo layout del modale + precaricamento l10n (evita #of_pages undefined, offsetParent scroll, fake worker instabile). */
const pdfMountReady = ref(false);
const pdfViewerBodyRef = ref<HTMLElement | null>(null);
const pdfLoadFailed = ref(false);
const currentPage = ref(1);
const pdfAppRef = ref<{
    eventBus: { on: (e: string, cb: (e: { pageNumber: number }) => void) => void };
    pdfViewer?: { currentPageNumber: number };
} | null>(null);

let fetchAbortController: AbortController | null = null;
let fetchAbortControllerHash: string | null = null;

const currentDoc = computed(() => extensionsState.reactive.documentsPdfViewer);

const LOCALE_MAP: Record<string, string> = {
    en: "en-US",
    it: "it",
    de: "de",
    es: "es-ES",
    fr: "fr",
    ru: "ru",
    zh: "zh-CN",
    tw: "zh-TW",
    dk: "da",
};

/** Allineato a pdf.js 2.4.456 (bundlato in vue3-pdf-app); v3.x ha chiavi l10n diverse e rompe i tooltip. */
const PDF_LOCALE_BASE =
    "https://raw.githubusercontent.com/mozilla/pdf.js/v2.4.456/l10n";
const PDF_LOCALE_LINK_ID = "planarally-pdf-locale-link";

const toolbarConfig = {
    sidebar: {
        viewThumbnail: true,
        viewOutline: true,
        viewAttachments: false,
    },
    toolbar: {
        toolbarViewerLeft: {
            findbar: true,
            previous: true,
            next: true,
            pageNumber: true,
        },
        toolbarViewerRight: {
            presentationMode: true,
            openFile: false,
            print: true,
            download: true,
            viewBookmark: true,
        },
        toolbarViewerMiddle: {
            zoomOut: true,
            zoomIn: true,
            scaleSelectContainer: true,
        },
    },
    errorWrapper: true,
};

function getEffectivePage(): number {
    const pageInput = document.getElementById("pageNumber") as HTMLInputElement | null;
    if (pageInput?.value) {
        const p = parseInt(pageInput.value, 10);
        if (!Number.isNaN(p) && p > 0) return p;
    }
    const app = pdfAppRef.value as { page?: number; pdfViewer?: { currentPageNumber: number } } | null;
    const fromViewer = app?.pdfViewer?.currentPageNumber;
    if (fromViewer != null && fromViewer > 0) return fromViewer;
    const fromAppPage = app?.page;
    if (fromAppPage != null && fromAppPage > 0) return fromAppPage;
    if (currentPage.value > 0) return currentPage.value;
    const fromDoc = currentDoc.value?.page;
    if (fromDoc != null && fromDoc > 0) return fromDoc;
    return 1;
}

function getShareLink(): string {
    const doc = currentDoc.value;
    if (!doc?.fileHash) return "";
    const page = getEffectivePage();
    const base = `doc:${doc.fileHash}`;
    const fragment = `#page=${page}`;
    const fallback = t("game.ui.extensions.DocumentsPdfViewer.document_fallback");
    const name = doc.name ?? fallback;
    const label = `${name} (p. ${page})`;
    return `[${label}](${base}${fragment})`;
}

async function copyShareLink(): Promise<void> {
    const link = getShareLink();
    if (!link) return;
    try {
        await navigator.clipboard.writeText(link);
        toast.success(t("game.ui.extensions.DocumentsPdfViewer.copy_success"));
    } catch {
        const ta = document.createElement("textarea");
        ta.value = link;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        toast.success(t("game.ui.extensions.DocumentsPdfViewer.copy_success"));
    }
}

function shareToChat(): void {
    const link = getShareLink();
    if (!link) return;
    chatSystem.addMessage(
        uuidv4(),
        playerSystem.getCurrentPlayer()?.name ?? "?",
        [link],
        true,
    );
    toast.success(t("game.ui.extensions.DocumentsPdfViewer.share_success"));
}

function setPdfLocale(): void {
    const locale = LOCALE_MAP[i18n.global.locale.value] ?? i18n.global.locale.value;

    /* Inietta link per caricare il locale da raw GitHub (cache del browser al primo fetch) */
    let link = document.getElementById(PDF_LOCALE_LINK_ID) as HTMLLinkElement | null;
    if (!link) {
        link = document.createElement("link");
        link.id = PDF_LOCALE_LINK_ID;
        link.setAttribute("type", "application/l10n");
        document.head.appendChild(link);
    }
    link.href = `${PDF_LOCALE_BASE}/${locale}/viewer.properties`;

    try {
        (window as unknown as { PDFViewerApplicationOptions?: { set: (k: string, v: string) => void } })
            .PDFViewerApplicationOptions?.set?.("locale", locale);
    } catch {
        /* vue3-pdf-app potrebbe non esporre le options */
    }
}

/** Precarica viewer.properties e attende un tick così pdf.js non inizializza con l10n vuota (errori #of_pages, print_progress_percent, ecc.). */
async function ensurePdfLocaleReady(): Promise<void> {
    const locale = LOCALE_MAP[i18n.global.locale.value] ?? i18n.global.locale.value;
    const url = `${PDF_LOCALE_BASE}/${locale}/viewer.properties`;
    setPdfLocale();
    try {
        await fetch(url, { cache: "force-cache" });
    } catch {
        /* offline: il viewer userà fallback / stringhe mancanti */
    }
    await nextTick();
    await new Promise<void>((r) => setTimeout(r, 0));
}

/** Attende che il body del modale abbia dimensioni (transition Modal + extension layer) prima di montare pdf.js. */
async function waitForPdfContainerLayout(): Promise<void> {
    await nextTick();
    await new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
            requestAnimationFrame(() => resolve());
        });
    });
    const deadline = Date.now() + 600;
    while (Date.now() < deadline) {
        const el = pdfViewerBodyRef.value;
        /* Non usare offsetParent: con antenati fixed/transform può essere null anche con layout valido. */
        if (el && el.offsetWidth > 0 && el.offsetHeight > 0) {
            return;
        }
        await new Promise((r) => setTimeout(r, 20));
    }
}

function onAfterCreated(pdfApp: unknown): void {
    const app = pdfApp as {
        appOptions?: { set: (k: string, v: string) => void };
        l10n?: { setLanguage?: (l: string) => void };
    };
    const locale = LOCALE_MAP[i18n.global.locale.value] ?? i18n.global.locale.value;
    try {
        app?.appOptions?.set?.("locale", locale);
    } catch {
        setPdfLocale();
    }
    try {
        app?.l10n?.setLanguage?.(locale);
    } catch {
        /* fallback già provato sopra */
    }
}

function onOpen(pdfApp: {
    eventBus: { on: (e: string, cb: (e: unknown) => void) => void };
    page?: number;
    pdfViewer?: { currentPageNumber: number };
}): void {
    pdfLoadFailed.value = false;
    pdfAppRef.value = pdfApp;
    const syncFromApp = (): void => {
        const p = (pdfApp as { page?: number }).page ?? pdfApp?.pdfViewer?.currentPageNumber;
        if (typeof p === "number" && p > 0) currentPage.value = p;
    };
    syncFromApp();
    if (pdfApp?.eventBus) {
        const syncPage = (e: unknown): void => {
            const ev = e as { pageNumber?: number; page?: number };
            const p = ev?.pageNumber ?? ev?.page;
            if (typeof p === "number" && p > 0) currentPage.value = p;
        };
        pdfApp.eventBus.on("pagechanging", syncPage);
        pdfApp.eventBus.on("pagenumberchanged", syncPage);
    }
}

function onPagesRendered(pdfApp: { pdfViewer?: { currentPageNumber: number; scrollPageIntoView?: (n: { pageNumber: number }) => void } }): void {
    const page = currentDoc.value?.page;
    if (page == null || page < 1 || !pdfApp?.pdfViewer) return;
    const pv = pdfApp.pdfViewer;
    pv.currentPageNumber = page;
    setTimeout(() => {
        pv.currentPageNumber = page;
        pv.scrollPageIntoView?.({ pageNumber: page });
    }, 50);
}

function close(): void {
    pdfMountReady.value = false;
    fetchAbortController?.abort();
    fetchAbortController = null;
    fetchAbortControllerHash = null;
    pdfAppRef.value = null;
    if (lastBlobUrl) {
        URL.revokeObjectURL(lastBlobUrl);
        lastBlobUrl = null;
    }
    pdfSrc.value = null;
    closeDocumentsPdfViewer();
    props.onClose();
}

onBeforeUnmount(() => {
    fetchAbortController?.abort();
    if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
    /* Non rimuovere il link l10n: la prossima apertura riusa la cache e evita race con pdf.js. */
});

watch(
    () => currentDoc.value,
    async (doc) => {
        if (!doc?.fileHash) {
            pdfMountReady.value = false;
            pdfSrc.value = null;
            pdfLoadFailed.value = false;
            return;
        }

        const fileHash = doc.fileHash.trim();
        if (fileHash.length < 40) {
            pdfLoadFailed.value = true;
            return;
        }

        if (fetchAbortController && fetchAbortControllerHash !== fileHash) {
            fetchAbortController.abort();
        }
        const controller = new AbortController();
        fetchAbortController = controller;
        fetchAbortControllerHash = fileHash;

        pdfMountReady.value = false;
        pdfLoadFailed.value = false;
        pdfSrc.value = null;
        if (lastBlobUrl) {
            URL.revokeObjectURL(lastBlobUrl);
            lastBlobUrl = null;
        }
        currentPage.value = doc.page ?? 1;

        await nextTick();

        try {
            const url = baseAdjust(`/api/extensions/documents/serve/${fileHash}`);
            const response = await fetch(url, {
                credentials: "include",
                signal: controller.signal,
            });
            if (!response.ok) {
                pdfLoadFailed.value = true;
                return;
            }
            const ct = response.headers.get("Content-Type") ?? "";
            if (!ct.toLowerCase().includes("application/pdf")) {
                pdfLoadFailed.value = true;
                return;
            }
            const arrayBuffer = await response.arrayBuffer();
            if (arrayBuffer.byteLength < 100) {
                pdfLoadFailed.value = true;
                return;
            }
            const blob = new Blob([arrayBuffer], { type: "application/pdf" });
            lastBlobUrl = URL.createObjectURL(blob);
            pdfSrc.value = lastBlobUrl;
            pdfViewerInstanceKey.value += 1;

            await ensurePdfLocaleReady();
            const stillOpen = extensionsState.raw.documentsPdfViewer?.fileHash?.trim() === fileHash;
            if (!stillOpen) {
                if (lastBlobUrl) {
                    URL.revokeObjectURL(lastBlobUrl);
                    lastBlobUrl = null;
                }
                pdfSrc.value = null;
                pdfMountReady.value = false;
                return;
            }
            await waitForPdfContainerLayout();
            if (extensionsState.raw.documentsPdfViewer?.fileHash?.trim() !== fileHash) {
                if (lastBlobUrl) {
                    URL.revokeObjectURL(lastBlobUrl);
                    lastBlobUrl = null;
                }
                pdfSrc.value = null;
                pdfMountReady.value = false;
                return;
            }
            pdfMountReady.value = true;
        } catch (e) {
            if ((e as Error).name === "AbortError") return;
            pdfLoadFailed.value = true;
        } finally {
            if (fetchAbortController === controller) {
                fetchAbortController = null;
                fetchAbortControllerHash = null;
            }
        }
    },
    { immediate: true },
);
</script>

<template>
    <Modal
        v-if="currentDoc"
        :visible="!!currentDoc"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="documents-pdf-viewer-modal"
        @close="close"
        @focus="focusExtension('documents-pdf')"
    >
        <template #header="{ dragStart, dragEnd, toggleMinimize, minimized, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <span class="ext-modal-title pdf-viewer-title">{{ currentDoc?.name ?? "" }}</span>
                <div class="ext-modal-actions">
                    <font-awesome-icon
                        icon="copy"
                        :title="t('game.ui.extensions.DocumentsPdfViewer.copy_link')"
                        class="ext-modal-btn"
                        @click.stop="copyShareLink"
                    />
                    <font-awesome-icon
                        icon="share-alt"
                        :title="t('game.ui.extensions.DocumentsPdfViewer.share_chat')"
                        class="ext-modal-btn"
                        @click.stop="shareToChat"
                    />
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
                        @click.stop="close"
                    />
                </div>
            </div>
        </template>
        <div ref="pdfViewerBodyRef" class="pdf-viewer-body">
            <VuePdfApp
                v-if="pdfSrc && pdfMountReady"
                :key="pdfViewerInstanceKey"
                :pdf="pdfSrc"
                :page-number="currentDoc?.page ?? 1"
                :config="toolbarConfig"
                :file-name="(currentDoc?.name ?? 'document').replace(/\.pdf$/i, '') + '.pdf'"
                class="documents-pdf-app"
                @after-created="onAfterCreated"
                @open="onOpen"
                @pages-rendered="onPagesRendered"
            />
            <div v-else-if="currentDoc && !pdfLoadFailed" class="ext-ui-loading pdf-viewer-loading">
                {{ t("game.ui.extensions.DocumentsModal.loading") }}
            </div>
            <div v-else-if="currentDoc && pdfLoadFailed" class="ext-ui-empty pdf-viewer-error">
                {{ t("game.ui.extensions.DocumentsPdfViewer.load_error") }}
            </div>
        </div>
    </Modal>
</template>

<style lang="scss">
.documents-pdf-viewer-modal {
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    resize: both;
    min-width: 400px;
    min-height: 300px;
    overflow: hidden;
    width: min(90vw, 900px);
    height: min(85vh, 700px);
    box-sizing: border-box;
}

.documents-pdf-viewer-modal .pdf-viewer-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.documents-pdf-app {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
}

.documents-pdf-app.pdf-app {
    min-height: 100%;
}
</style>

<style lang="scss" scoped>
.pdf-viewer-title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.pdf-viewer-loading,
.pdf-viewer-error {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
}
</style>
