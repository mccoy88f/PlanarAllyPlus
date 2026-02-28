<script setup lang="ts">
import { onMounted, ref, useTemplateRef, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { http } from "../../../core/http";
import LoadingBar from "../../../core/components/LoadingBar.vue";
import { openDocumentsPdfViewer } from "../../systems/extensions/ui";
import { gameState } from "../../systems/game/state";

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

interface DocumentItem {
    id: number;
    name: string;
    fileHash: string;
}

const documents = ref<DocumentItem[]>([]);
const loading = ref(false);
const uploading = ref(false);
const uploadProgress = ref(0);
const uploadingFilename = ref("");
const deleting = ref(false);
const uploadInput = useTemplateRef<HTMLInputElement>("uploadInput");

async function loadDocuments(): Promise<void> {
    loading.value = true;
    try {
        let url = "/api/extensions/documents/list";
        const creator = gameState.reactive.roomCreator;
        const room = gameState.reactive.roomName;
        if (creator && room) {
            url += `?room_creator=${encodeURIComponent(creator)}&room_name=${encodeURIComponent(room)}`;
        }
        const response = await http.get(url);
        if (response.ok) {
            const data = (await response.json()) as { documents: DocumentItem[] };
            const all = data.documents ?? [];
            documents.value = all.filter((d) => "fileHash" in d && d.fileHash) as DocumentItem[];
        } else {
            documents.value = [];
        }
    } catch {
        documents.value = [];
    } finally {
        loading.value = false;
    }
}

async function onFileSelected(): Promise<void> {
    const files = uploadInput.value?.files;
    if (!files || files.length === 0) return;

    const pdfs = Array.from(files).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) return;

    uploading.value = true;
    let okCount = 0;
    let errCount = 0;
    
    try {
        for (const file of pdfs) {
            uploadingFilename.value = file.name;
            uploadProgress.value = 0;
            
            await new Promise<void>((resolve, reject) => {
                const formData = new FormData();
                formData.append("file", file);
                
                const xhr = new XMLHttpRequest();
                xhr.open("POST", "/api/extensions/documents/upload");
                
                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        uploadProgress.value = (event.loaded / event.total) * 100;
                    }
                };
                
                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            const data = JSON.parse(xhr.responseText) as DocumentItem;
                            documents.value = [...documents.value, data];
                            okCount++;
                            resolve();
                        } catch {
                            errCount++;
                            resolve();
                        }
                    } else {
                        errCount++;
                        resolve();
                    }
                };
                
                xhr.onerror = () => {
                    errCount++;
                    resolve();
                };
                
                xhr.send(formData);
            });
        }
        
        if (okCount > 0) {
            toast.success(
                okCount === 1
                    ? t("game.ui.extensions.DocumentsModal.upload_success")
                    : t("game.ui.extensions.DocumentsModal.upload_multi_success", { count: okCount }),
            );
        }
        if (errCount > 0) {
            toast.error(
                errCount === pdfs.length
                    ? t("game.ui.extensions.DocumentsModal.upload_error")
                    : t("game.ui.extensions.DocumentsModal.upload_partial", { ok: okCount, err: errCount }),
            );
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.DocumentsModal.upload_error"));
        console.error(e);
    } finally {
        uploading.value = false;
        uploadProgress.value = 0;
        uploadingFilename.value = "";
        if (uploadInput.value) {
            uploadInput.value.value = "";
        }
    }
}

function openPdf(doc: DocumentItem): void {
    openDocumentsPdfViewer(doc.fileHash, doc.name);
}

async function deleteDocument(doc: DocumentItem): Promise<void> {
    if (deleting.value) return;
    deleting.value = true;
    try {
        const response = await http.postJson("/api/extensions/documents/delete", { id: doc.id });
        if (response.ok) {
            documents.value = documents.value.filter((d) => d.id !== doc.id);
            toast.success(t("game.ui.extensions.DocumentsModal.delete_success"));
        } else {
            const text = await response.text();
            toast.error(text || t("game.ui.extensions.DocumentsModal.delete_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.DocumentsModal.delete_error"));
        console.error(e);
    } finally {
        deleting.value = false;
    }
}

function triggerUpload(): void {
    uploadInput.value?.click();
}

watch(
    () => props.visible,
    (visible) => {
        if (visible) loadDocuments();
    },
);

onMounted(() => {
    if (props.visible) loadDocuments();
});
</script>

<template>
    <Modal v-if="visible" :visible="visible" :mask="false" @close="onClose">
        <template #header="{ dragStart, dragEnd, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">{{ t("game.ui.extensions.DocumentsModal.title") }}</h2>
                <div class="ext-modal-actions">
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
        <div class="ext-toolbar-bar">
            <input
                ref="uploadInput"
                type="file"
                accept=".pdf,application/pdf"
                multiple
                class="ext-ui-file-input"
                @change="onFileSelected"
            />
            <button
                type="button"
                class="ext-ui-btn ext-ui-btn-primary"
                :disabled="uploading"
                @click="triggerUpload"
            >
                <font-awesome-icon icon="upload" />
                {{ t("common.upload") }}
            </button>
        </div>
        <div class="ext-modal-body-wrapper">
            <div v-if="uploading" class="ext-progress-top-container">
                <LoadingBar
                    :progress="uploadProgress"
                    :label="`${t('game.ui.extensions.DocumentsModal.uploading')} ${uploadingFilename}...`"
                    height="6px"
                />
            </div>
            <div class="documents-modal-body ext-body">
                <div v-if="loading" class="ext-ui-loading">
                    {{ t("game.ui.extensions.DocumentsModal.loading") }}
                </div>
                <div v-else-if="documents.length === 0" class="ext-ui-empty">
                    {{ t("game.ui.extensions.DocumentsModal.no_documents") }}
                </div>
                <ul v-else class="ext-ui-list documents-list">
                    <li
                        v-for="doc in documents"
                        :key="doc.id"
                        class="ext-ui-list-item documents-list-item"
                    >
                        <div class="ext-ui-list-item-content" @click="openPdf(doc)">
                            <font-awesome-icon icon="file-pdf" class="doc-icon" />
                            <span class="ext-ui-list-item-name">{{ doc.name }}</span>
                        </div>
                        <div class="ext-item-actions">
                            <font-awesome-icon
                                class="ext-action-btn delete"
                                icon="trash-alt"
                                :title="t('common.remove')"
                                @click.stop="deleteDocument(doc)"
                            />
                        </div>
                    </li>
                </ul>
            </div>
        </div>
    </Modal>
</template>

<style lang="scss" scoped>
.ext-modal-body-wrapper {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
}

.documents-modal-body {
    min-width: 380px;
    max-width: 500px;
    max-height: 60vh;
}

.ext-bottom-section {
    flex-shrink: 0;
    border-top: 1px solid #eee;
    background: #fafafa;
}

.upload-progress-container {
    padding: 0.75rem 1.5rem 0.25rem;
}

.documents-list .ext-ui-list-item-content {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.doc-icon {
    color: #c00;
    flex-shrink: 0;
}
</style>
