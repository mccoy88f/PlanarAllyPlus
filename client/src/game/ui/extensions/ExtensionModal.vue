<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { useI18n } from "vue-i18n";

import Modal from "../../../core/components/modals/Modal.vue";
import { baseAdjust } from "../../../core/http";
import { extensionsState } from "../../systems/extensions/state";
import { closeExtensionModal, openDocumentsPdfViewer } from "../../systems/extensions/ui";

const { t } = useI18n();

function handleMessage(event: MessageEvent): void {
    const ext = extensionsState.reactive.extensionModalOpen;
    if (ext?.id !== "documents") return;
    const data = event.data;
    if (data?.type === "planarally-open-document" && data.fileHash && data.name) {
        openDocumentsPdfViewer(data.fileHash, data.name, data.page);
    }
}

onMounted(() => {
    window.addEventListener("message", handleMessage);
});
onUnmounted(() => {
    window.removeEventListener("message", handleMessage);
});

const currentExtension = computed(() => extensionsState.reactive.extensionModalOpen);

const headerStyle = computed(() => {
    const ext = currentExtension.value;
    const color = ext?.titleBarColor;
    if (!color) return {};
    return { backgroundColor: color };
});

const iconProp = computed(() => {
    const icon = currentExtension.value?.icon;
    if (!icon) return undefined;
    if (Array.isArray(icon)) return icon as [string, string];
    if (typeof icon === "string" && icon.includes(" ")) {
        const [prefix, name] = icon.split(" ");
        return [prefix, name?.replace("fa-", "") ?? icon] as [string, string];
    }
    return icon as string;
});

const iframeUrl = computed(() => {
    const ext = currentExtension.value;
    if (!ext?.uiUrl) return "";
    return baseAdjust(ext.uiUrl.startsWith("/") ? ext.uiUrl.slice(1) : ext.uiUrl);
});

function close(): void {
    closeExtensionModal();
}
</script>

<template>
    <Modal
        v-if="currentExtension"
        :visible="!!currentExtension"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="extension-modal"
        @close="close"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                :style="headerStyle"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">
                    <font-awesome-icon
                        v-if="iconProp"
                        :icon="iconProp"
                        class="ext-modal-icon"
                    />
                    {{ currentExtension?.name ?? "" }}
                </h2>
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
                        @click="close"
                    />
                </div>
            </div>
        </template>
        <div class="ext-modal-body">
            <iframe
                v-if="iframeUrl"
                :src="iframeUrl"
                class="ext-modal-iframe"
                :title="currentExtension?.name ?? 'Extension'"
            />
        </div>
    </Modal>
</template>

<style lang="scss">
.extension-modal {
    display: flex;
    flex-direction: column;
    border-radius: 0.5rem;
    resize: both;
    width: min(90vw, 900px);
    height: min(85vh, 700px);
    min-width: 400px;
    min-height: 300px;
    overflow: hidden;
}
</style>

<style lang="scss" scoped>
.ext-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    .ext-modal-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .ext-modal-icon {
        flex-shrink: 0;
    }

    .ext-modal-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .ext-modal-btn,
    .ext-modal-close {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

.ext-modal-body {
    flex: 1;
    min-height: 0;
    overflow: hidden;
}

.ext-modal-iframe {
    width: 100%;
    height: 100%;
    border: none;
}
</style>
