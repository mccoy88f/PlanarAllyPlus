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

/**
 * Incrementato all’inizio di ogni caricamento documento (ogni volta che il watch apre un PDF).
 * Così la :key cambia anche: prima apertura, cambio file senza chiudere, riapertura dopo chiusura.
 * (Il vecchio solo-incremento in close() non aggiornava mai pdfViewerSessionId dentro la stessa istanza.)
 */
let pdfViewerOpenGeneration = 0;

/** Log diagnostici: filtra la console con `[PDF Viewer]`. Rimuovere o disattivare quando non serve. */
const PDF_LOG_PREFIX = "[PDF Viewer]";

function pdfDebug(phase: string, data?: Record<string, unknown>): void {
    if (data !== undefined) {
        console.info(PDF_LOG_PREFIX, phase, data);
    } else {
        console.info(PDF_LOG_PREFIX, phase);
    }
}

/** Dimensioni elementi pdf.js nel DOM (0×0 = tipico “pagine che non si disegnano”). */
function logPdfViewerDomSizes(phase: string): void {
    void nextTick(() => {
        const modal = document.querySelector(".documents-pdf-viewer-modal");
        const body = pdfViewerBodyRef.value;
        const shell = document.querySelector(".documents-pdf-app-shell");
        const pdfApp = document.querySelector(".documents-pdf-app-shell .pdf-app");
        const viewerContainer = document.querySelector(".documents-pdf-app-shell #viewerContainer");
        const mainViewer = document.querySelector(".documents-pdf-app-shell .pdfViewer");
        pdfDebug(`DOM sizes · ${phase}`, {
            modal: modal ? { w: modal.clientWidth, h: modal.clientHeight } : null,
            pdfViewerBody: body ? { w: body.clientWidth, h: body.clientHeight } : null,
            shell: shell ? { w: shell.clientWidth, h: shell.clientHeight } : null,
            pdfApp: pdfApp ? { w: pdfApp.clientWidth, h: pdfApp.clientHeight } : null,
            viewerContainer: viewerContainer ? { w: viewerContainer.clientWidth, h: viewerContainer.clientHeight } : null,
            pdfViewer: mainViewer ? { w: mainViewer.clientWidth, h: mainViewer.clientHeight } : null,
        });
    });
}

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

const pdfSrc = ref<string | ArrayBuffer | null>(null);
let lastBlobUrl: string | null = null;
/** Aggiornata a ogni apertura/caricamento documento; usata come :key su VuePdfApp. */
const pdfViewerSessionId = ref(0);
/** Monta VuePdfApp solo dopo layout del modale + precaricamento l10n (evita #of_pages undefined, offsetParent scroll, fake worker instabile). */
const pdfMountReady = ref(false);
const pdfViewerBodyRef = ref<HTMLElement | null>(null);
const pdfLoadFailed = ref(false);
const currentPage = ref(1);
/** Evita doppie registrazioni su eventBus (stessa istanza PDFViewerApplication). */
const pdfViewerEventBusBound = ref(false);
const pdfAppRef = ref<{
    eventBus: { on: (e: string, cb: (e: { pageNumber: number }) => void) => void };
    pdfViewer?: { currentPageNumber: number };
} | null>(null);

let fetchAbortController: AbortController | null = null;
let fetchAbortControllerHash: string | null = null;

const currentDoc = computed(() => extensionsState.reactive.documentsPdfViewer);

/** Allineato a pdf.js 2.4.456 (bundlato in vue3-pdf-app); cartelle l10n su raw GitHub. */
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

/** Locale pdf.js dalla lingua del sito (vue-i18n). */
function getPdfJsLocale(): string {
    const raw = i18n.global.locale.value ?? "en";
    if (LOCALE_MAP[raw]) return LOCALE_MAP[raw];
    const short = raw.split("-")[0] ?? "en";
    return LOCALE_MAP[short] ?? "en-US";
}

/** Allineato a pdf.js 2.4.456 (bundlato in vue3-pdf-app); v3.x ha chiavi l10n diverse e rompe i tooltip. */
const PDF_LOCALE_BASE =
    "https://raw.githubusercontent.com/mozilla/pdf.js/v2.4.456/l10n";
const PDF_LOCALE_LINK_ID = "planarally-pdf-locale-link";

const toolbarConfig = {
    sidebar: {
        /* Thumbnails: molti warning l10n (#thumb_page_title) se le stringhe non sono ancora pronte. */
        viewThumbnail: false,
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
    const locale = getPdfJsLocale();
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
    const locale = getPdfJsLocale();
    const url = `${PDF_LOCALE_BASE}/${locale}/viewer.properties`;
    setPdfLocale();
    try {
        const r = await fetch(url, { cache: "force-cache" });
        pdfDebug("l10n viewer.properties", { locale, ok: r.ok, status: r.status });
    } catch (e) {
        pdfDebug("l10n viewer.properties fetch error", { locale, err: String(e) });
    }
    await nextTick();
    await new Promise<void>((r) => setTimeout(r, 0));
}

/** Attende che il body del modale abbia dimensioni (transition Modal + extension layer) prima di montare pdf.js. */
async function waitForPdfContainerLayout(): Promise<void> {
    const t0 = Date.now();
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
            pdfDebug("waitForPdfContainerLayout ok", {
                w: el.offsetWidth,
                h: el.offsetHeight,
                waitedMs: Date.now() - t0,
            });
            return;
        }
        await new Promise((r) => setTimeout(r, 20));
    }
    const el = pdfViewerBodyRef.value;
    pdfDebug("waitForPdfContainerLayout TIMEOUT (body ancora 0×0?)", {
        body: el ? { w: el.offsetWidth, h: el.offsetHeight } : null,
    });
}

type PdfViewerAppForSync = {
    eventBus: { on: (e: string, cb: (e: unknown) => void) => void };
    page?: number;
    pdfViewer?: { currentPageNumber: number };
};

function wirePdfViewerPageSync(pdfApp: PdfViewerAppForSync): void {
    if (pdfViewerEventBusBound.value) return;
    pdfViewerEventBusBound.value = true;

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

function onAfterCreated(pdfApp: unknown): void {
    pdfDebug("event after-created (PDFViewerApplication creato)");
    const app = pdfApp as {
        appOptions?: { set: (k: string, v: string) => void };
        l10n?: { setLanguage?: (l: string) => void };
    };
    const locale = getPdfJsLocale();
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

    /*
     * vue3-pdf-app: il primo caricamento usa open() in onMounted, che NON emette mai "open"
     * (solo openDocument dal file input emette "open"). Qui agganciamo ref + eventBus sempre.
     */
    pdfLoadFailed.value = false;
    pdfAppRef.value = pdfApp as typeof pdfAppRef.value;
    wirePdfViewerPageSync(pdfApp as PdfViewerAppForSync);
}

/** Senza altezza sul container pdf.js non disegna le pagine (0 pagine visibili); download e metadati funzionano comunque. */
function forcePdfViewerLayout(pdfApp: { pdfViewer?: { update?: () => void; currentScaleValue?: string } }): void {
    const run = (label: string): void => {
        try {
            window.dispatchEvent(new Event("resize"));
            pdfApp.pdfViewer?.update?.();
            pdfDebug(`forcePdfViewerLayout ${label}`, {
                currentScaleValue: pdfApp.pdfViewer?.currentScaleValue ?? null,
            });
        } catch (e) {
            pdfDebug(`forcePdfViewerLayout ${label} error`, { err: String(e) });
        }
    };
    void nextTick(() => {
        requestAnimationFrame(() => {
            run("raf");
            setTimeout(() => run("t50"), 50);
            setTimeout(() => run("t200"), 200);
        });
    });
}

function onPagesRendered(pdfApp: {
    pdfViewer?: {
        currentPageNumber: number;
        currentScaleValue?: string;
        update?: () => void;
        scrollPageIntoView?: (n: { pageNumber: number }) => void;
    };
}): void {
    const pv = pdfApp.pdfViewer;
    pdfDebug("event pages-rendered", {
        currentPage: pv?.currentPageNumber,
        currentScaleValue: pv?.currentScaleValue ?? null,
    });
    logPdfViewerDomSizes("onPagesRendered");

    pdfLoadFailed.value = false;
    if (!pdfAppRef.value) {
        pdfAppRef.value = pdfApp as typeof pdfAppRef.value;
        wirePdfViewerPageSync(pdfApp as PdfViewerAppForSync);
    }
    try {
        if (pv && !pv.currentScaleValue) {
            pv.currentScaleValue = "page-fit";
        }
    } catch {
        /* ignore */
    }
    forcePdfViewerLayout(pdfApp);

    /* README: dopo il primo render impostare la scala se il viewer era 0×0. */
    setTimeout(() => {
        try {
            if (pv) {
                pv.currentScaleValue = "page-fit";
                pv.update?.();
                pdfDebug("pages-rendered setTimeout scale", {
                    currentScaleValue: pv.currentScaleValue,
                });
            }
        } catch (e) {
            pdfDebug("pages-rendered setTimeout error", { err: String(e) });
        }
    }, 0);

    const page = currentDoc.value?.page;
    if (page == null || page < 1 || !pv) return;
    pv.currentPageNumber = page;
    setTimeout(() => {
        pv.currentPageNumber = page;
        pv.scrollPageIntoView?.({ pageNumber: page });
    }, 50);
}

function close(): void {
    pdfDebug("close()");
    pdfMountReady.value = false;
    pdfViewerEventBusBound.value = false;
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
            pdfViewerEventBusBound.value = false;
            pdfAppRef.value = null;
            pdfSrc.value = null;
            pdfLoadFailed.value = false;
            return;
        }

        const fileHash = doc.fileHash.trim();
        if (fileHash.length < 40) {
            pdfDebug("watch: hash troppo corto", { len: fileHash.length });
            pdfLoadFailed.value = true;
            return;
        }

        pdfViewerOpenGeneration += 1;
        pdfViewerSessionId.value = pdfViewerOpenGeneration;

        pdfDebug("watch: start load", {
            name: doc.name,
            fileHashPrefix: `${fileHash.slice(0, 12)}…`,
            sessionId: pdfViewerSessionId.value,
            page: doc.page ?? null,
        });

        if (fetchAbortController && fetchAbortControllerHash !== fileHash) {
            fetchAbortController.abort();
        }
        const controller = new AbortController();
        fetchAbortController = controller;
        fetchAbortControllerHash = fileHash;

        pdfMountReady.value = false;
        pdfViewerEventBusBound.value = false;
        pdfAppRef.value = null;
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
                pdfDebug("fetch serve_document NON ok", { status: response.status, statusText: response.statusText });
                pdfLoadFailed.value = true;
                return;
            }
            const ct = response.headers.get("Content-Type") ?? "";
            if (!ct.toLowerCase().includes("application/pdf")) {
                pdfDebug("fetch Content-Type inatteso", { contentType: ct });
                pdfLoadFailed.value = true;
                return;
            }
            const arrayBuffer = await response.arrayBuffer();
            if (arrayBuffer.byteLength < 100) {
                pdfDebug("fetch arrayBuffer troppo piccolo", { byteLength: arrayBuffer.byteLength });
                pdfLoadFailed.value = true;
                return;
            }
            const blob = new Blob([arrayBuffer], { type: "application/pdf" });
            lastBlobUrl = URL.createObjectURL(blob);
            pdfSrc.value = lastBlobUrl;
            pdfDebug("fetch OK, blob creato", {
                byteLength: arrayBuffer.byteLength,
                blobUrlPrefix: lastBlobUrl.slice(0, 32) + "…",
            });

            await ensurePdfLocaleReady();
            const stillOpen = extensionsState.raw.documentsPdfViewer?.fileHash?.trim() === fileHash;
            if (!stillOpen) {
                pdfDebug("watch: abort dopo fetch (documento chiuso / hash cambiato)");
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
                pdfDebug("watch: abort dopo waitForLayout (hash cambiato)");
                if (lastBlobUrl) {
                    URL.revokeObjectURL(lastBlobUrl);
                    lastBlobUrl = null;
                }
                pdfSrc.value = null;
                pdfMountReady.value = false;
                return;
            }
            pdfMountReady.value = true;
            pdfDebug("pdfMountReady=true (VuePdfApp può montare)", {
                sessionId: pdfViewerSessionId.value,
            });
            logPdfViewerDomSizes("after pdfMountReady");
        } catch (e) {
            if ((e as Error).name === "AbortError") {
                pdfDebug("watch: AbortError", { message: (e as Error).message });
                return;
            }
            pdfDebug("watch: catch", { err: String(e), name: (e as Error).name });
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
            <!-- vue3-pdf-app: senza altezza esplicita sul root non renderizza le pagine (README). -->
            <div v-if="pdfSrc && pdfMountReady" class="documents-pdf-app-shell">
                <VuePdfApp
                    :key="pdfViewerSessionId"
                    :pdf="pdfSrc"
                    page-scale="page-fit"
                    :page-number="currentDoc?.page ?? 1"
                    :config="toolbarConfig"
                    :file-name="(currentDoc?.name ?? 'document').replace(/\.pdf$/i, '') + '.pdf'"
                    class="documents-pdf-app"
                    style="height: 100%; width: 100%; min-height: 0"
                    @after-created="onAfterCreated"
                    @pages-rendered="onPagesRendered"
                />
            </div>
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

/* Shell: altrimenti .pdf-app (root vue3-pdf-app) può avere altezza 0 e non disegnare le pagine. */
.documents-pdf-app-shell {
    flex: 1;
    min-height: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.documents-pdf-viewer-modal .documents-pdf-app-shell :deep(.pdf-app) {
    flex: 1;
    min-height: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
}

/* offsetParent null / scrollViewer: il viewer deve avere contenitore posizionato e altezza nel flex. */
.documents-pdf-viewer-modal .documents-pdf-app-shell :deep(#mainContainer),
.documents-pdf-viewer-modal .documents-pdf-app-shell :deep(#viewerContainer) {
    position: relative;
    flex: 1;
    min-height: 0;
}

.documents-pdf-viewer-modal .documents-pdf-app-shell :deep(.scrollViewer) {
    position: relative;
    min-height: 0;
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
