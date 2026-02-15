<script setup lang="ts">
import { onMounted, ref, useTemplateRef, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { http } from "../../../core/http";
import { openDocumentsPdfViewer } from "../../systems/extensions/ui";

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
const deleting = ref(false);
const uploadInput = useTemplateRef<HTMLInputElement>("uploadInput");

async function loadDocuments(): Promise<void> {
    loading.value = true;
    try {
        const response = await http.get("/api/extensions/documents/list");
        if (response.ok) {
            const data = (await response.json()) as { documents: DocumentItem[] };
            documents.value = data.documents ?? [];
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
    const file = uploadInput.value?.files?.[0];
    if (!file || !file.name.toLowerCase().endsWith(".pdf")) return;

    uploading.value = true;
    try {
        const formData = new FormData();
        formData.append("file", file);
        const response = await http.post("/api/extensions/documents/upload", formData);
        if (response.ok) {
            const data = (await response.json()) as DocumentItem;
            documents.value = [...documents.value, data];
            toast.success(t("game.ui.extensions.DocumentsModal.upload_success"));
        } else {
            const text = await response.text();
            toast.error(text || t("game.ui.extensions.DocumentsModal.upload_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.DocumentsModal.upload_error"));
        console.error(e);
    } finally {
        uploading.value = false;
        uploadInput.value!.value = "";
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
                class="modal-header documents-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2>{{ t("game.ui.extensions.DocumentsModal.title") }}</h2>
                <div class="modal-header-actions">
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="header-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="header-btn"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="onClose"
                    />
                </div>
            </div>
        </template>
        <div class="documents-modal-body">
            <div v-if="loading" class="documents-loading">
                {{ t("game.ui.extensions.DocumentsModal.loading") }}
            </div>
            <div v-else-if="documents.length === 0" class="documents-empty">
                {{ t("game.ui.extensions.DocumentsModal.no_documents") }}
            </div>
            <ul v-else class="documents-list">
                <li
                    v-for="doc in documents"
                    :key="doc.id"
                    class="documents-list-item"
                >
                    <div class="documents-list-item-content" @click="openPdf(doc)">
                        <font-awesome-icon icon="file-pdf" class="doc-icon" />
                        <span class="doc-name">{{ doc.name }}</span>
                    </div>
                    <font-awesome-icon
                        class="doc-delete"
                        icon="trash-alt"
                        :title="t('common.remove')"
                        @click.stop="deleteDocument(doc)"
                    />
                </li>
            </ul>
            <div class="documents-upload-bar">
                <input
                    ref="uploadInput"
                    type="file"
                    accept=".pdf,application/pdf"
                    @change="onFileSelected"
                />
                <button :disabled="uploading" @click="triggerUpload">
                    {{ uploading ? t("game.ui.extensions.DocumentsModal.uploading") : t("common.upload") }}
                </button>
            </div>
        </div>
    </Modal>
</template>

<style lang="scss" scoped>
.documents-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    h2 {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
    }

    .modal-header-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .header-btn {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

.documents-modal-body {
    padding: 1rem;
    min-width: 320px;
    max-width: 480px;
    max-height: 60vh;
    overflow-y: auto;
}

.documents-upload-bar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid #eee;

    input[type="file"] {
        display: none;
    }

    button {
        padding: 0.5rem 1rem;
        border-radius: 0.25rem;
        cursor: pointer;
        white-space: nowrap;

        &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    }
}

.documents-loading,
.documents-empty {
    font-style: italic;
    color: #666;
    padding: 1rem 0;
}

.documents-list {
    list-style: none;
    margin: 0;
    padding: 0;

    .documents-list-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
        padding: 0.5rem 0.75rem;
        border-radius: 0.25rem;
        border: 1px solid transparent;

        &:hover {
            background: #f5f5f5;
            border-color: #ddd;
        }

        .documents-list-item-content {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex: 1;
            min-width: 0;
            cursor: pointer;
        }

        .doc-icon {
            color: #c00;
            flex-shrink: 0;
        }

        .doc-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .doc-delete {
            padding: 0.25rem;
            cursor: pointer;
            color: #999;
            flex-shrink: 0;

            &:hover {
                color: #c00;
            }
        }
    }
}
</style>
