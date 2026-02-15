<script setup lang="ts">
import { nextTick, onMounted, ref, useTemplateRef, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { useToast } from "vue-toastification";

import Modal from "../../../core/components/modals/Modal.vue";
import { http } from "../../../core/http";
import { useModal } from "../../../core/plugins/modals/plugin";
import { extensionsState } from "../../systems/extensions/state";
import { closeExtensionsManager } from "../../systems/extensions/ui";
import { modalSystem } from "../../systems/modals";
import type { ModalIndex } from "../../systems/modals/types";

const emit = defineEmits<(e: "close" | "focus") => void>();
defineExpose({ close });
const props = defineProps<{ modalIndex: ModalIndex }>();

const { t } = useI18n();
const toast = useToast();
const modals = useModal();
const route = useRoute();

const uploadInput = useTemplateRef<HTMLInputElement>("uploadInput");
const installUrl = ref("");
const installing = ref(false);

function extensionsUrl(): string {
    let url = "/api/extensions";
    const creator = route.params.creator as string | undefined;
    const room = route.params.room as string | undefined;
    if (creator && room) {
        url += `?room_creator=${encodeURIComponent(creator)}&room_name=${encodeURIComponent(room)}`;
    }
    return url;
}

async function loadExtensions(): Promise<void> {
    try {
        const response = await http.get(extensionsUrl());
        if (response.ok) {
            const data = (await response.json()) as {
                extensions: {
                    id: string;
                    name: string;
                    version: string;
                    description?: string;
                    folder: string;
                    visibleToPlayers?: boolean;
                }[];
            };
            extensionsState.mutableReactive.extensions = data.extensions ?? [];
        }
    } catch {
        extensionsState.mutableReactive.extensions = [];
    }
}

const togglingVisibility = ref(false);

async function toggleVisibility(ext: {
    folder?: string;
    name: string;
    visibleToPlayers?: boolean;
}): Promise<void> {
    if (togglingVisibility.value || !ext.folder) return;
    const newVal = !(ext.visibleToPlayers ?? false);
    const creator = route.params.creator as string | undefined;
    const room = route.params.room as string | undefined;
    if (!creator || !room) {
        toast.error(t("game.ui.extensions.ExtensionsManager.visibility_error"));
        return;
    }
    togglingVisibility.value = true;
    try {
        const response = await http.patchJson("/api/extensions/visibility", {
            folder: ext.folder,
            visibleToPlayers: newVal,
            roomCreator: creator,
            roomName: room,
        });
        if (response.ok) {
            const exts = extensionsState.mutableReactive.extensions;
            const idx = exts.findIndex((e) => e.folder === ext.folder);
            if (idx >= 0) {
                exts[idx] = { ...exts[idx]!, visibleToPlayers: newVal };
            }
            toast.success(
                newVal
                    ? t("game.ui.extensions.ExtensionsManager.visibility_on", { name: ext.name })
                    : t("game.ui.extensions.ExtensionsManager.visibility_off", { name: ext.name }),
            );
        } else {
            toast.error(t("game.ui.extensions.ExtensionsManager.visibility_error"));
        }
    } catch {
        toast.error(t("game.ui.extensions.ExtensionsManager.visibility_error"));
    } finally {
        togglingVisibility.value = false;
    }
}

onMounted(loadExtensions);

watch(
    () => extensionsState.reactive.managerOpen,
    async (open) => {
        if (open) {
            await loadExtensions();
            await nextTick(() => modalSystem.focus(props.modalIndex));
        }
    },
);

function close(): void {
    closeExtensionsManager();
    emit("close");
}

async function installFromZip(): Promise<void> {
    const file = uploadInput.value?.files?.[0];
    if (!file) return;

    installing.value = true;
    try {
        const data = await file.arrayBuffer();
        const response = await http.post("/api/extensions/install/zip", data);
        if (response.ok) {
            toast.success(t("game.ui.extensions.ExtensionsManager.install_success"));
            await loadExtensions();
        } else {
            const text = await response.text();
            toast.error(text || t("game.ui.extensions.ExtensionsManager.install_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.ExtensionsManager.install_error"));
        console.error(e);
    } finally {
        installing.value = false;
        uploadInput.value!.value = "";
    }
}

async function installFromUrl(): Promise<void> {
    const url = installUrl.value.trim();
    if (!url) return;

    installing.value = true;
    try {
        const response = await http.postJson("/api/extensions/install/url", { url });
        if (response.ok) {
            toast.success(t("game.ui.extensions.ExtensionsManager.install_success"));
            installUrl.value = "";
            await loadExtensions();
        } else {
            const text = await response.text();
            toast.error(text || t("game.ui.extensions.ExtensionsManager.install_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.ExtensionsManager.install_error"));
        console.error(e);
    } finally {
        installing.value = false;
    }
}

const uninstalling = ref(false);

async function uninstallExtension(ext: { folder: string; name: string }): Promise<void> {
    if (uninstalling.value) return;
    const confirmed = await modals.confirm(
        t("game.ui.extensions.ExtensionsManager.uninstall_confirm_title"),
        t("game.ui.extensions.ExtensionsManager.uninstall_confirm_text", { name: ext.name }),
    );
    if (confirmed !== true) return;
    uninstalling.value = true;
    try {
        const response = await http.postJson("/api/extensions/uninstall", { folder: ext.folder });
        if (response.ok) {
            toast.success(t("game.ui.extensions.ExtensionsManager.uninstall_success"));
            close();
            window.location.reload();
        } else {
            const text = await response.text();
            toast.error(text || t("game.ui.extensions.ExtensionsManager.uninstall_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.ExtensionsManager.uninstall_error"));
        console.error(e);
    } finally {
        uninstalling.value = false;
    }
}
</script>

<template>
    <Modal
        :visible="extensionsState.reactive.managerOpen"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="extensions-manager-modal"
        @close="close"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="extensions-manager-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="extensions-manager-title">{{ t("game.ui.extensions.ExtensionsManager.title") }}</h2>
                <div class="extensions-manager-actions">
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="extensions-manager-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="extensions-manager-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="extensions-manager-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="close"
                    />
                </div>
            </div>
        </template>
        <div id="extensions-body" @click="$emit('focus')">
                <section class="extensions-list">
                    <div class="section-header">{{ t("game.ui.extensions.ExtensionsManager.installed") }}</div>
                    <div v-if="extensionsState.reactive.extensions.length === 0" class="empty-message">
                        {{ t("game.ui.extensions.ExtensionsManager.no_extensions") }}
                    </div>
                    <div
                        v-for="ext in extensionsState.reactive.extensions"
                        :key="ext.folder ?? ext.id"
                        class="extension-item"
                    >
                        <span class="extension-name">{{ ext.name }}</span>
                        <span class="extension-version">v{{ ext.version }}</span>
                        <span v-if="ext.description" class="extension-desc">{{ ext.description }}</span>
                        <font-awesome-icon
                            v-if="ext.folder"
                            class="extension-visibility"
                            :class="{
                                disabled: togglingVisibility,
                                'visibility-on': ext.visibleToPlayers,
                            }"
                            :icon="ext.visibleToPlayers ? ['fas', 'eye'] : ['far', 'eye-slash']"
                            :title="
                                ext.visibleToPlayers
                                    ? t('game.ui.extensions.ExtensionsManager.visibility_to_players_on')
                                    : t('game.ui.extensions.ExtensionsManager.visibility_to_players_off')
                            "
                            @click="!togglingVisibility && ext.folder && toggleVisibility({ ...ext, folder: ext.folder })"
                        />
                        <font-awesome-icon
                            v-if="ext.folder"
                            class="extension-delete"
                            :class="{ disabled: uninstalling }"
                            icon="trash-alt"
                            :title="t('game.ui.extensions.ExtensionsManager.uninstall')"
                            @click="!uninstalling && ext.folder && uninstallExtension({ folder: ext.folder, name: ext.name })"
                        />
                    </div>
                </section>

                <section class="install-section">
                    <div class="section-header">{{ t("game.ui.extensions.ExtensionsManager.install") }}</div>
                    <div class="install-row">
                        <label>{{ t("game.ui.extensions.ExtensionsManager.upload_zip") }}</label>
                        <div class="install-controls">
                            <input ref="uploadInput" type="file" accept=".zip" />
                            <button :disabled="installing" @click="installFromZip">
                                {{ t("common.upload") }}
                            </button>
                        </div>
                    </div>
                    <div class="install-row">
                        <label>{{ t("game.ui.extensions.ExtensionsManager.install_from_url") }}</label>
                        <div class="install-controls">
                            <input v-model="installUrl" type="url" :placeholder="t('game.ui.extensions.ExtensionsManager.url_placeholder')" />
                            <button :disabled="installing || !installUrl.trim()" @click="installFromUrl">
                                {{ t("game.ui.extensions.ExtensionsManager.install_btn") }}
                            </button>
                        </div>
                    </div>
                </section>
            </div>
    </Modal>
</template>

<style lang="scss">
.extensions-manager-modal {
    display: flex;
    flex-direction: column;
    border-radius: 1rem;
    resize: both;
    width: min(90vw, 700px);
    height: min(85vh, 600px);
    min-width: 400px;
    min-height: 300px;
    overflow: hidden;
}
</style>

<style lang="scss" scoped>
.extensions-manager-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    .extensions-manager-title {
        margin: 0;
        font-size: 1.25rem;
        font-weight: bold;
    }

    .extensions-manager-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .extensions-manager-btn,
    .extensions-manager-close {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

#extensions-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    overflow-y: auto;
    padding: 1rem 1.5rem;
}

.section-header {
    font-weight: bold;
    margin-bottom: 0.5rem;
    font-size: 1.1em;
}

.extensions-list {
    .empty-message {
        font-style: italic;
        color: #666;
        padding: 0.5rem 0;
    }

    .extension-item {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem;
        border: 1px solid #eee;
        border-radius: 0.25rem;
        margin-bottom: 0.25rem;

        .extension-name {
            font-weight: 500;
        }

        .extension-version {
            font-size: 0.9em;
            color: #666;
        }

        .extension-desc {
            width: 100%;
            font-size: 0.9em;
            color: #888;
        }

        .extension-visibility {
            cursor: pointer;
            color: #999;
            margin-left: auto;

            &:hover:not(.disabled) {
                color: #069;
            }

            &.visibility-on {
                color: #069;
            }

            &.disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        }

        .extension-delete {
            cursor: pointer;
            color: #999;

            &:hover:not(.disabled) {
                color: #c00;
            }

            &.disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        }
    }
}

.install-section {
    .install-row {
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        margin-bottom: 1rem;

        label {
            font-weight: 500;
        }

        .install-controls {
            display: flex;
            gap: 0.5rem;
            align-items: center;

            input[type="file"],
            input[type="url"] {
                flex: 1;
                padding: 0.5rem;
                border: 1px solid #ccc;
                border-radius: 0.25rem;
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
    }
}
</style>
