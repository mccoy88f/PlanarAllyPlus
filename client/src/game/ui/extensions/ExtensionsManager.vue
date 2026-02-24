<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from "vue";
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

const { t, locale: locale_ } = useI18n();
const toast = useToast();
const modals = useModal();
const route = useRoute();

const uploadInput = useTemplateRef<HTMLInputElement>("uploadInput");
const installUrl = ref("");
const installing = ref(false);
const searchQuery = ref("");

const filteredExtensions = computed(() => {
    const q = searchQuery.value.trim().toLowerCase();
    const exts = extensionsState.reactive.extensions;
    if (!q) return exts;
    return exts.filter(
        (e) =>
            e.name.toLowerCase().includes(q) ||
            (e.description?.toLowerCase().includes(q) ?? false) ||
            (e.folder?.toLowerCase().includes(q) ?? false),
    );
});

function extensionsUrl(): string {
    let url = "/api/extensions";
    const creator = route.params.creator as string | undefined;
    const room = route.params.room as string | undefined;
    const params = new URLSearchParams();
    if (creator && room) {
        params.set("room_creator", creator);
        params.set("room_name", room);
    }
    // Pass current UI locale so the server returns the localised description
    const locale = (String(locale_.value ?? "en")).startsWith("it") ? "it" : "en";
    params.set("locale", locale);
    url += `?${params.toString()}`;
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
                    author?: string;
                    folder: string;
                    visibleToPlayers?: boolean;
                }[];
            };
            const exts = data.extensions ?? [];
            exts.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
            extensionsState.mutableReactive.extensions = exts;
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

async function onAddClick(): Promise<void> {
    if (installing.value) return;
    const uploadZipLabel = t("game.ui.extensions.ExtensionsManager.upload_zip");
    const fromUrlLabel = t("game.ui.extensions.ExtensionsManager.install_from_url");
    const choices = await modals.selectionBox(
        t("game.ui.extensions.ExtensionsManager.install_how"),
        [uploadZipLabel, fromUrlLabel],
    );
    if (choices === undefined || choices.length === 0) return;
    const choice = choices[0];
    if (choice === uploadZipLabel) {
        uploadInput.value?.click();
    } else if (choice === fromUrlLabel) {
        const url = await modals.prompt(
            t("game.ui.extensions.ExtensionsManager.url_prompt"),
            t("game.ui.extensions.ExtensionsManager.install_from_url"),
            undefined,
            "https://",
        );
        if (url?.trim()) {
            installUrl.value = url.trim();
            await installFromUrl();
        }
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
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">{{ t("game.ui.extensions.ExtensionsManager.title") }}</h2>
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
        <div class="ext-toolbar-bar ext-search-bar">
            <font-awesome-icon icon="search" class="ext-search-icon" />
            <input
                v-model="searchQuery"
                type="text"
                class="ext-search-input"
                :placeholder="t('game.ui.extensions.ExtensionsManager.search_placeholder')"
            />
            <button
                type="button"
                class="ext-search-add-btn"
                :disabled="installing"
                :title="t('game.ui.extensions.ExtensionsManager.add_extension')"
                @click="onAddClick"
            >
                <font-awesome-icon icon="plus" />
            </button>
        </div>
        <div id="extensions-body" class="ext-body" @click="$emit('focus')">
                <section class="extensions-list">
                    <div class="section-header">{{ t("game.ui.extensions.ExtensionsManager.installed") }}</div>
                    <div v-if="filteredExtensions.length === 0" class="empty-message">
                        {{
                            extensionsState.reactive.extensions.length === 0
                                ? t("game.ui.extensions.ExtensionsManager.no_extensions")
                                : t("game.ui.extensions.ExtensionsManager.no_search_results")
                        }}
                    </div>
                    <div
                        v-for="ext in filteredExtensions"
                        :key="ext.folder ?? ext.id"
                        class="ext-ui-list-item extension-item"
                    >
                        <div class="ext-ui-list-item-content">
                            <div class="ext-name-version">
                                <span class="ext-ui-list-item-name extension-name">{{ ext.name }}</span>
                                <span class="extension-version">v{{ ext.version }}</span>
                            </div>
                            <div v-if="ext.description" class="extension-desc ext-ui-muted">{{ ext.description }}</div>
                            <div v-if="ext.author" class="extension-author ext-ui-muted">{{ ext.author }}</div>
                        </div>
                        <div class="ext-item-actions extension-item-actions">
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
                    </div>
                </section>
            </div>
        <input
            ref="uploadInput"
            type="file"
            accept=".zip"
            style="display: none"
            @change="installFromZip"
        />
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
.extensions-manager-modal .ext-modal-title {
    font-size: 1.25rem;
    font-weight: bold;
}

#extensions-body {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
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
        .ext-ui-list-item-content {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.35rem;
        }

        .ext-name-version {
            display: flex;
            align-items: baseline;
            gap: 0.5rem;
        }

        .extension-version {
            font-size: 0.9em;
            color: #666;
        }

        .extension-desc {
            font-size: 0.9em;
            line-height: 1.3;
        }

        .extension-author {
            font-size: 0.78em;
            font-style: italic;
            color: #888;
            margin-top: 0.1rem;
        }

        .extension-item-actions {
            display: flex;
            gap: 0.35rem;
            align-items: center;
        }

        .extension-visibility {
            cursor: pointer;
            color: #999;

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

</style>
