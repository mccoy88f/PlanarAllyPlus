<script setup lang="ts">
import type { ExtensionModalData } from "../../systems/extensions/state";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import Modal from "../../../core/components/modals/Modal.vue";
import { useModal } from "../../../core/plugins/modals/plugin";
import { baseAdjust, http } from "../../../core/http";
import { extensionsState } from "../../systems/extensions/state";
import { gameState } from "../../systems/game/state";
import { addDungeonToMap } from "../../dungeongen";
import {
    requestCloseExtensionModal,
    focusExtension,
    openDocumentsPdfViewer,
    openCompendiumModalForItem,
} from "../../systems/extensions/ui";

const props = defineProps<{ extension: ExtensionModalData }>();

const { t, locale } = useI18n();
const toast = useToast();
const modals = useModal();
const iframeEl = ref<HTMLIFrameElement | null>(null);

async function handleMessage(event: MessageEvent): Promise<void> {
    if (event.source !== iframeEl.value?.contentWindow) return;
    const ext = props.extension;
    const data = event.data;
    const source = event.source as Window | null;

    if (data?.type === "planarally-confirm" && data.id && ext && source) {
        const result = await modals.confirm(data.title || "", data.message || "", {
            yes: t("common.confirm"),
            no: t("common.cancel"),
        });
        source.postMessage({ type: "planarally-confirm-response", id: data.id, result: result ?? false }, "*");
        return;
    }
    if (data?.type === "planarally-prompt" && data.id && ext && source) {
        const result = await modals.prompt(data.question || "", data.title || "", undefined, data.defaultValue ?? "");
        source.postMessage({ type: "planarally-prompt-response", id: data.id, result }, "*");
        return;
    }

    if (data?.type === "planarally-add-to-map" && data.url) {
        await addDungeonToMap(data.url, data.gridCells || { width: 40, height: 40 }, undefined, { name: data.name, params: undefined, seed: "" });
        toast.success(t("game.ui.extensions.watabou.added_to_map"));
        return;
    }

    if (data?.type === "planarally-import-image" && data.url) {
        const toastId = toast.info(t("game.ui.extensions.watabou.importing"), { timeout: false });
        try {
            const response = await http.postJson("/api/extensions/watabou/import", { url: data.url, generator: data.generator });
            if (response.ok) {
                const resData = (await response.json()) as { url: string; name: string; gridCells: { width: number; height: number }; doors?: any[] };
                await addDungeonToMap(resData.url, resData.gridCells, undefined, { name: resData.name, params: undefined, seed: "", doors: resData.doors });
                toast.dismiss(toastId);
                toast.success(t("game.ui.extensions.watabou.added_to_map"));
            } else {
                toast.dismiss(toastId);
                toast.error(t("game.ui.extensions.watabou.import_failed"), { timeout: 10000 });
                setTimeout(() => {
                    toast.info(t("game.ui.extensions.watabou.import_guide"), { timeout: 15000 });
                }, 1000);
            }
        } catch (e) {
            toast.dismiss(toastId);
            toast.error("An unexpected error occurred during import.");
            console.error(e);
        }
        return;
    }

    if (data?.type === "planarally-open-document" && ext?.id === "documents" && data.fileHash && data.name) {
        openDocumentsPdfViewer(data.fileHash, data.name, data.page);
    } else if (data?.type === "planarally-open-qe" && data.collection && data.slug) {
        openCompendiumModalForItem(data.collection, data.slug, data.compendium);
    } else if (data?.type === "planarally-toast" && typeof data.message === "string") {
        if (data.error) {
            toast.error(data.message);
        } else {
            toast.success(data.message);
        }
    } else if (data?.type === "ambient-music-playing" && typeof data.playing === "boolean") {
        extensionsState.mutableReactive.ambientMusicPlaying = data.playing;
    } else if (data?.type === "planarally-close-extension") {
        close();
    }
}

onMounted(() => {
    window.addEventListener("message", handleMessage);
});
onUnmounted(() => {
    window.removeEventListener("message", handleMessage);
});

const currentExtension = computed(() => props.extension);

function extensionDisplayName(ext: { id: string; name: string } | undefined): string {
    if (!ext) return "";
    const key = `game.ui.menu.Extensions.extensions.${ext.id}`;
    const translated = t(key);
    return translated !== key ? translated : ext.name;
}

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
    let url = baseAdjust(ext.uiUrl.startsWith("/") ? ext.uiUrl.slice(1) : ext.uiUrl);
    const params = new URLSearchParams();
    params.set("locale", locale.value || "en");
    if (gameState.reactive.roomCreator && gameState.reactive.roomName) {
        params.set("room_creator", gameState.reactive.roomCreator);
        params.set("room_name", gameState.reactive.roomName);
    }
    if (ext?.id === "character-sheet" && ext.openSheetId) {
        params.set("sheet_id", ext.openSheetId);
    }
    if (ext?.id === "character-sheet") {
        params.set("qe_enabled", "1");
    }
    url += "?" + params.toString();
    return url;
});

function close(): void {
    requestCloseExtensionModal(props.extension.id);
}

const extensionModalClass = computed(() => {
    const ext = currentExtension.value;
    const base = "extension-modal";
    const minimized =
        ext?.id === "ambient-music" && extensionsState.reactive.ambientMusicMinimized;
    const hasTopBar =
        ext?.id === "character-sheet" ||
        ext?.folder === "character-sheet" ||
        ext?.id === "documents" ||
        ext?.folder === "documents" ||
        ext?.id === "guida" ||
        ext?.folder === "guida" ||
        ext?.id === "time-manager" ||
        ext?.folder === "time-manager" ||
        ext?.id === "ambient-music" ||
        ext?.folder === "ambient-music" ||
        ext?.id === "openrouter" ||
        ext?.folder === "openrouter";
    let cls = base;
    if (ext?.id === "assets-installer" || ext?.folder === "assets-installer") {
        cls += " extension-modal--compact";
    }
    if (
        ext?.id === "time-manager" ||
        ext?.folder === "time-manager" ||
        ext?.id === "ambient-music" ||
        ext?.folder === "ambient-music"
    ) {
        cls += " extension-modal--compact-small";
    }
    if (ext?.id === "ambient-music" || ext?.folder === "ambient-music") {
        cls += " extension-modal--ambient-music";
    }
    if (ext?.id === "character-sheet" || ext?.folder === "character-sheet" || ext?.id === "guida" || ext?.folder === "guida" || ext?.id === "openrouter" || ext?.folder === "openrouter") {
        cls += " extension-modal--wide";
    }
    if (hasTopBar) {
        cls += " extension-modal--has-top-bar";
    }
    if (minimized) {
        cls += " extension-modal--minimized";
    }
    return cls;
});
</script>

<template>
    <Modal
        v-if="currentExtension"
        :visible="!!currentExtension"
        :mask="false"
        :close-on-mask-click="false"
        :extra-class="extensionModalClass"
        @close="close"
        @focus="currentExtension && focusExtension(currentExtension.id)"
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
                    {{ extensionDisplayName(currentExtension ?? undefined) }}
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
                ref="iframeEl"
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

.extension-modal--compact {
    width: min(90vw, 700px);
    height: min(85vh, 600px);
}

.extension-modal--compact-small {
    width: min(46vw, 345px);
    height: min(29vh, 207px);
    min-width: 260px;
    min-height: 140px;
    resize: both;
}

/* Ambient music: 20% wider, 2x height */
.extension-modal--ambient-music {
    width: min(64vw, 477px);
    height: min(58vh, 414px);
}

.extension-modal--wide {
    width: 95vw;
    max-width: 95vw;
    height: 90vh;
    max-height: 90vh;
}

.extension-modal--minimized {
    position: fixed !important;
    left: -9999px !important;
    width: 1px !important;
    height: 1px !important;
    overflow: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
</style>

<style lang="scss" scoped>
.extension-modal--has-top-bar .ext-modal-header {
    border-bottom: none;
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

.extension-modal--has-top-bar .ext-modal-body {
    display: flex;
    flex-direction: column;
}

.extension-modal--has-top-bar .ext-modal-iframe {
    display: block;
}
</style>
