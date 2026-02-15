<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { uuidv4 } from "../../../core/utils";
import Modal from "../../../core/components/modals/Modal.vue";
import { baseAdjust } from "../../../core/http";
import { chatSystem } from "../../systems/chat";
import { extensionsState } from "../../systems/extensions/state";
import { closeDocumentsPdfViewer } from "../../systems/extensions/ui";
import { playerSystem } from "../../systems/players";

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

const pdfViewer = ref<{ container: HTMLDivElement } | null>(null);
const pdfIframe = ref<HTMLIFrameElement | null>(null);
const pdfBlobUrl = ref<string>("");
const pdfLoadFailed = ref(false);

const currentDoc = computed(() => extensionsState.reactive.documentsPdfViewer);

function getCurrentPageFromIframe(): number | undefined {
    const iframe = pdfIframe.value;
    try {
        const hash = iframe?.contentWindow?.location?.hash;
        if (hash) {
            const m = hash.match(/page=(\d+)/i);
            if (m) return parseInt(m[1], 10);
        }
    } catch {
        /* cross-origin o accesso bloccato */
    }
    return undefined;
}

function getShareLink(): string {
    const doc = currentDoc.value;
    if (!doc?.fileHash) return "";
    let page = doc.page;
    const pageFromIframe = getCurrentPageFromIframe();
    if (pageFromIframe !== undefined && pageFromIframe > 0) page = pageFromIframe;
    const base = `doc:${doc.fileHash}`;
    const fragment = page && page > 0 ? `#page=${page}` : "";
    const label = page && page > 0
        ? `${doc.name ?? "Document"} (p. ${page})`
        : doc.name ?? "Document";
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

function triggerFind(): void {
    const iframe = pdfIframe.value;
    try {
        if (iframe?.contentWindow) {
            iframe.contentWindow.focus();
            toast.info(t("game.ui.extensions.DocumentsPdfViewer.search_hint"));
        } else {
            document.execCommand("Find");
        }
    } catch {
        document.execCommand("Find");
    }
}

async function loadPdfUrl(): Promise<void> {
    const doc = currentDoc.value;
    pdfLoadFailed.value = false;
    if (!doc?.fileHash) {
        pdfBlobUrl.value = "";
        return;
    }
    if (pdfBlobUrl.value) {
        URL.revokeObjectURL(pdfBlobUrl.value);
        pdfBlobUrl.value = "";
    }
    const url = baseAdjust(`/api/extensions/documents/serve/${doc.fileHash}`);
    try {
        const response = await fetch(url, { credentials: "include" });
        if (!response.ok) {
            console.error("Documents PDF fetch failed:", response.status, response.statusText);
            pdfLoadFailed.value = true;
            return;
        }
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const params = ["toolbar=1", "navpanes=1", "scrollbar=1"];
        if (doc.page && doc.page > 0) {
            params.unshift(`page=${doc.page}`);
        }
        pdfBlobUrl.value = blobUrl + "#" + params.join("&");
    } catch (err) {
        console.error("Documents PDF load error:", err);
        pdfLoadFailed.value = true;
    }
}

function close(): void {
    closeDocumentsPdfViewer();
    props.onClose();
}

watch(
    () => currentDoc.value,
    (doc) => {
        if (doc) {
            loadPdfUrl();
        } else {
            const prev = pdfBlobUrl.value;
            if (prev && prev.startsWith("blob:")) {
                URL.revokeObjectURL(prev);
            }
            pdfBlobUrl.value = "";
            pdfLoadFailed.value = false;
        }
    },
    { immediate: true },
);

onUnmounted(() => {
    const url = pdfBlobUrl.value;
    if (url && url.startsWith("blob:")) {
        URL.revokeObjectURL(url);
    }
});
</script>

<template>
    <Modal
        v-if="currentDoc"
        ref="pdfViewer"
        :visible="!!currentDoc"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="documents-pdf-viewer-modal"
        @close="close"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="pdf-viewer-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <span class="pdf-viewer-title">{{ currentDoc?.name ?? "" }}</span>
                <div class="pdf-viewer-header-actions">
                    <font-awesome-icon
                        icon="magnifying-glass"
                        :title="t('game.ui.extensions.DocumentsPdfViewer.search')"
                        class="pdf-viewer-btn"
                        @click.stop="triggerFind"
                    />
                    <font-awesome-icon
                        icon="copy"
                        :title="t('game.ui.extensions.DocumentsPdfViewer.copy_link')"
                        class="pdf-viewer-btn"
                        @click.stop="copyShareLink"
                    />
                    <font-awesome-icon
                        :icon="['far', 'share-from-square']"
                        :title="t('game.ui.extensions.DocumentsPdfViewer.share_chat')"
                        class="pdf-viewer-btn"
                        @click.stop="shareToChat"
                    />
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="pdf-viewer-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="pdf-viewer-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="pdf-viewer-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="close"
                    />
                </div>
            </div>
        </template>
        <div class="pdf-viewer-body">
            <iframe
                v-if="pdfBlobUrl"
                ref="pdfIframe"
                :src="pdfBlobUrl"
                class="pdf-iframe"
                title="PDF Viewer"
            />
            <div v-else-if="currentDoc && pdfLoadFailed" class="pdf-viewer-error">
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
    width: 100%;
    height: 100%;
    box-sizing: border-box;
}

.documents-pdf-viewer-modal .pdf-iframe {
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    box-sizing: border-box;
}
</style>

<style lang="scss" scoped>
.pdf-viewer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    .pdf-viewer-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
    }

    .pdf-viewer-header-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .pdf-viewer-btn,
    .pdf-viewer-close {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

.pdf-viewer-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.pdf-viewer-error {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    color: #666;
    font-style: italic;
}

.pdf-iframe {
    flex: 1;
    width: 100%;
    height: 100%;
    min-width: 0;
    min-height: 0;
    border: none;
}
</style>
