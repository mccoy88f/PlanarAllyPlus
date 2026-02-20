<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { http } from "../core/http";
import { useModal } from "../core/plugins/modals/plugin";
import { extensionsState } from "../game/systems/extensions/state";

const { t } = useI18n();
const toast = useToast();
const modals = useModal();

const uploadInput = useTemplateRef<HTMLInputElement>("uploadInput");
const installUrl = ref("");
const installing = ref(false);
const uninstalling = ref(false);
const searchQuery = ref("");

const filteredExtensions = computed(() => {
    const q = searchQuery.value.trim().toLowerCase();
    const exts = extensionsState.mutableReactive.extensions;
    if (!q) return exts;
    return exts.filter(
        (e) =>
            e.name.toLowerCase().includes(q) ||
            (e.description?.toLowerCase().includes(q) ?? false) ||
            (e.folder?.toLowerCase().includes(q) ?? false),
    );
});

async function loadExtensions(): Promise<void> {
    try {
        const response = await http.get("/api/extensions");
        if (response.ok) {
            const data = (await response.json()) as {
                extensions: {
                    id: string;
                    name: string;
                    version: string;
                    description?: string;
                    folder: string;
                }[];
            };
            extensionsState.mutableReactive.extensions = data.extensions ?? [];
        }
    } catch {
        extensionsState.mutableReactive.extensions = [];
    }
}

onMounted(loadExtensions);

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
            await loadExtensions();
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
    <div id="content">
        <div class="content-title">
            <span>MANAGE EXTENSIONS</span>
        </div>

        <div class="extensions-toolbar">
            <input
                v-model="searchQuery"
                type="text"
                class="extensions-search"
                :placeholder="t('game.ui.extensions.ExtensionsManager.search_placeholder')"
            />
            <button
                class="extensions-add-btn"
                :disabled="installing"
                :title="t('game.ui.extensions.ExtensionsManager.add_extension')"
                @click="onAddClick"
            >
                <font-awesome-icon icon="plus" />
            </button>
        </div>

        <section class="extensions-section">
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
                class="extension-item"
            >
                <span class="extension-name">{{ ext.name }}</span>
                <span class="extension-version">v{{ ext.version }}</span>
                <span v-if="ext.description" class="extension-desc">{{ ext.description }}</span>
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

        <input
            ref="uploadInput"
            type="file"
            accept=".zip"
            style="display: none"
            @change="installFromZip"
        />
    </div>
</template>

<style scoped lang="scss">
#content {
    background-color: rgba(77, 59, 64, 0.6);
    border-radius: 20px;
    padding: 3.75rem;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 2rem;

    .content-title {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 3.125em;
        color: white;
        border-bottom: 5px solid #ffa8bf;
        font-weight: bold;
        margin-bottom: 0;
    }
}

.extensions-toolbar {
    display: flex;
    align-items: center;
    gap: 0.75rem;

    .extensions-search {
        flex: 1;
        padding: 0.6rem 1rem;
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-radius: 0.5rem;
        background: rgba(0, 0, 0, 0.2);
        color: white;
        font-size: 1rem;

        &::placeholder {
            color: rgba(255, 255, 255, 0.5);
        }
    }

    .extensions-add-btn {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 2.5rem;
        height: 2.5rem;
        padding: 0;
        border: 2px solid rgba(255, 168, 191, 1);
        border-radius: 0.5rem;
        background: rgba(219, 0, 59, 1);
        cursor: pointer;
        color: white;

        &:hover:not(:disabled) {
            background: rgba(255, 168, 191, 0.3);
        }

        &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    }
}

.extensions-section {
    .section-header {
        font-weight: bold;
        font-size: 1.5em;
        color: #ffa8bf;
        margin-bottom: 1rem;
    }

    .empty-message {
        font-style: italic;
        color: rgba(255, 255, 255, 0.7);
        padding: 1rem 0;
    }

    .extension-item {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.75rem;
        padding: 0.75rem 1rem;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        background-color: rgba(0, 0, 0, 0.2);

        .extension-name {
            font-weight: 600;
            color: white;
        }

        .extension-version {
            font-size: 0.9em;
            color: rgba(255, 255, 255, 0.6);
        }

        .extension-desc {
            width: 100%;
            font-size: 0.9em;
            color: rgba(255, 255, 255, 0.7);
        }

        .extension-delete {
            margin-left: auto;
            cursor: pointer;
            color: rgba(255, 255, 255, 0.5);
            font-size: 1.1rem;

            &:hover:not(.disabled) {
                color: #ff6b6b;
            }

            &.disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        }
    }
}
</style>
