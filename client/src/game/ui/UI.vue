<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import MarkdownModal from "../../core/components/modals/MarkdownModal.vue";
import SliderComponent from "../../core/components/slider/SliderComponent.vue";
import { baseAdjust } from "../../core/http";
import { activeShapeStore } from "../../store/activeShape";
import { coreStore } from "../../store/core";
import { extensionsState } from "../systems/extensions/state";
import {
    closeDocumentsPdfViewer,
    closeDungeongenModal,
    closeOpenRouterModal,
    closeCompendiumModal,
    openCompendiumModalForItem,
} from "../systems/extensions/ui";
import {
    timeManagerHandleMessage,
    COUNTDOWN_COMPLETE_EVENT,
} from "../systems/extensions/time-manager";
import { gameState } from "../systems/game/state";
import { positionSystem } from "../systems/position";
import { positionState } from "../systems/position/state";
import { roomState } from "../systems/room/state";
import { uiState } from "../systems/ui/state";

import Annotation from "./Annotation.vue";
import Chat from "./Chat.vue";
import DungeongenModal from "./extensions/DungeongenModal.vue";
import DocumentsPdfViewer from "./extensions/DocumentsPdfViewer.vue";
import ExtensionModal from "./extensions/ExtensionModal.vue";
import OpenRouterModal from "./extensions/OpenRouterModal.vue";
import CompendiumHoverTooltip from "./extensions/CompendiumHoverTooltip.vue";
import CompendiumModal from "./extensions/CompendiumModal.vue";
import DefaultContext from "./contextmenu/DefaultContext.vue";
import ShapeContext from "./contextmenu/ShapeContext.vue";
import { showDefaultContextMenu, showShapeContextMenu } from "./contextmenu/state";
import Floors from "./Floors.vue";
import { initiativeStore } from "./initiative/state";
import LocationBar from "./menu/LocationBar.vue";
import MenuBar from "./menu/MenuBar.vue";
import ModalStack from "./ModalStack.vue";
import SelectionInfo from "./SelectionInfo.vue";
import CreateTokenDialog from "./tokendialog/CreateTokenDialog.vue";
import { tokenDialogVisible } from "./tokendialog/state";
import TokenDirections from "./TokenDirections.vue";
import Tools from "./tools/Tools.vue";

const uiEl = ref<HTMLDivElement | null>(null);

const coreState = coreStore.state;
const { t } = useI18n();
const toast = useToast();

const visible = reactive({
    locations: false,
    settings: false,
});
const topLeft = computed(() => visible.locations && visible.settings);

const changelogText = computed(() =>
    t("game.ui.ui.changelog_RELEASE_LOG", {
        release: coreState.version.release,
        log: coreState.changelog,
    }),
);

const releaseVersion = computed(() => coreState.version.release);

const showChangelog = computed(() => {
    const version = localStorage.getItem("last-version");
    if (version !== coreState.version.release) {
        localStorage.setItem("last-version", coreState.version.release);
        return true;
    }
    return false;
});

function handleExtensionMessage(event: MessageEvent): void {
    const data = event.data;
    if (timeManagerHandleMessage(data, event.source as Window | null)) return;
    if (data?.type === "planarally-open-qe" && data.collection && data.slug) {
        openCompendiumModalForItem(data.collection, data.slug, data.compendium);
    }
    if (data?.type === "ambient-music-playing" && typeof data.playing === "boolean") {
        extensionsState.mutableReactive.ambientMusicPlaying = data.playing;
        try {
            localStorage.setItem("pa-ambient-music-playing", data.playing ? "1" : "0");
        } catch {
            /* ignore */
        }
    }
}

function handleCountdownComplete(e: CustomEvent<{ name: string }>): void {
    const name = e.detail?.name ?? "Timer";
    toast.info(t("game.ui.extensions.time-manager.countdown_complete", { name }));
}

onMounted(() => {
    // hide all UI elements that were previously open
    activeShapeStore.setShowEditDialog(false);
    initiativeStore.show(false, false);
    showDefaultContextMenu.value = false;
    showShapeContextMenu.value = false;
    tokenDialogVisible.value = false;
    window.addEventListener("message", handleExtensionMessage);
    window.addEventListener(COUNTDOWN_COMPLETE_EVENT, handleCountdownComplete as EventListener);
});

onUnmounted(() => {
    window.removeEventListener("message", handleExtensionMessage);
    window.removeEventListener(COUNTDOWN_COMPLETE_EVENT, handleCountdownComplete as EventListener);
});

function toggleLocations(): void {
    const oldState = visible.locations;
    // Split up visible.locations setting to smooth in/out overflow fix
    if (oldState) visible.locations = false;
    let i = 0;
    const interval = setInterval(() => {
        if (uiEl.value === null) return;
        i += 0.625;
        uiEl.value.style.gridTemplateRows = `${!oldState ? i : 6.25 - i}rem auto 1fr auto`;
        if (i >= 6.25) {
            clearInterval(interval);
            // Force height to become auto instead of harcoding it to 100px
            uiEl.value.style.gridTemplateRows = `${!oldState ? "auto" : 0} auto 1fr auto`;
            if (!oldState) visible.locations = true;
        }
    }, 20);
}

function toggleMenu(): void {
    visible.settings = !visible.settings;
    let i = 0;
    const interval = setInterval(() => {
        if (uiEl.value === null) return;
        i += 0.625;
        uiEl.value.style.gridTemplateColumns = `${visible.settings ? i : 12.5 - i}rem repeat(3, 1fr)`;
        if (i >= 12.5) {
            clearInterval(interval);
        }
    }, 20);
}

const EXTENSION_MODAL_BASE_Z = 10000;

function extensionModalZIndex(modalId: string): number {
    const lf = extensionsState.reactive.lastFocusedModal;
    return lf?.type === "extension" && lf.id === modalId
        ? EXTENSION_MODAL_BASE_Z + 100
        : EXTENSION_MODAL_BASE_Z;
}

const zoomDisplay = computed({
    get(): number {
        return positionState.reactive.zoomDisplay;
    },
    set(zoom: number) {
        positionSystem.setZoomDisplay(zoom, { invalidate: true, updateSectors: true, sync: true });
    },
});

function setTempZoomDisplay(value: number): void {
    positionSystem.setZoomDisplay(value, { invalidate: true, updateSectors: true, sync: false });
}
</script>

<template>
    <div v-show="uiState.reactive.showUi" id="ui" ref="uiEl">
        <div v-show="topLeft" id="logo">
            <div id="logo-icons">
                <a href="https://www.planarally.io" target="_blank" rel="noopener noreferrer">
                    <img :src="baseAdjust('/static/favicon.png')" alt="" />
                </a>
                <div id="logo-links">
                    <a
                        href="https://github.com/kruptein/PlanarAlly"
                        target="_blank"
                        :title="t('game.ui.ui.github_msg')"
                        rel="noopener noreferrer"
                    >
                        <font-awesome-icon :icon="['fab', 'github']" />
                    </a>
                    <a
                        href="https://discord.gg/mubGnTe"
                        target="_blank"
                        :title="t('game.ui.ui.discord_msg')"
                        rel="noopener noreferrer"
                    >
                        <font-awesome-icon :icon="['fab', 'discord']" />
                    </a>
                    <a
                        href="https://www.patreon.com/planarally"
                        target="_blank"
                        :title="t('game.ui.ui.patreon_msg')"
                        rel="noopener noreferrer"
                    >
                        <font-awesome-icon :icon="['fab', 'patreon']" />
                    </a>
                </div>
            </div>
            <div id="logo-version">
                <span>{{ t("common.version") }}</span>
                <span>{{ releaseVersion }}</span>
            </div>
        </div>
        <!-- RADIAL MENU -->
        <div id="radialmenu">
            <div class="rm-wrapper">
                <div class="rm-toggler">
                    <ul class="rm-list" :class="{ 'rm-list-dm': gameState.reactive.isDm }">
                        <li
                            v-if="gameState.reactive.isDm"
                            id="rm-locations"
                            class="rm-item"
                            :title="t('game.ui.ui.open_loc_menu')"
                            @click="toggleLocations"
                        >
                            <a href="#">
                                <font-awesome-icon :icon="['far', 'compass']" />
                            </a>
                        </li>
                        <li id="rm-settings" class="rm-item" :title="t('game.ui.ui.open_settings')" @click="toggleMenu">
                            <a href="#">
                                <font-awesome-icon icon="cog" />
                            </a>
                        </li>
                    </ul>
                </div>
                <span class="rm-topper"></span>
            </div>
        </div>
        <div v-if="positionState.reactive.outOfBounds" id="oob" @click="positionSystem.returnToBounds">
            {{ t("game.ui.ui.return_to_content") }}
        </div>
        <TokenDirections />
        <!-- Core overlays -->
        <MenuBar />
        <Tools />
        <LocationBar v-if="gameState.reactive.isDm" :active="visible.locations" :menu-active="visible.settings" />
        <div id="floor-and-chat">
            <Chat v-if="roomState.reactive.enableChat" />
            <Floors />
        </div>
        <DefaultContext />
        <ShapeContext />
        <Annotation />
        <SelectionInfo />
        <!-- When updating zoom boundaries, also update store updateZoom function;
            should probably do this using a store variable-->
        <SliderComponent
            id="zoom"
            v-model="zoomDisplay"
            height="6px"
            width="200px"
            :dot-size="[8, 20]"
            :rail-style="{
                backgroundColor: '#fff',
                'box-shadow': '0.5px 0.5px 3px 1px rgba(0, 0, 0, .36)',
            }"
            :dot-style="{ 'border-radius': '15%' }"
            :min="0"
            :max="1"
            @change="setTempZoomDisplay"
        />
        <!-- Modals that can be rearranged -->
        <ModalStack />
        <!-- Extension modals (independent from menu, z-index for bring-to-front) -->
        <div
            v-if="extensionsState.reactive.dungeongenModalOpen"
            class="extension-modal-layer"
            :style="{ zIndex: extensionModalZIndex('dungeongen') }"
        >
            <DungeongenModal
                :visible="extensionsState.reactive.dungeongenModalOpen"
                :on-close="closeDungeongenModal"
            />
        </div>
        <CompendiumHoverTooltip />
        <div
            v-if="extensionsState.reactive.compendiumModalOpen"
            class="extension-modal-layer"
            :style="{ zIndex: extensionModalZIndex('compendium') }"
        >
            <CompendiumModal
                :visible="extensionsState.reactive.compendiumModalOpen"
                :on-close="closeCompendiumModal"
            />
        </div>
        <div
            v-if="extensionsState.reactive.openrouterModalOpen"
            class="extension-modal-layer"
            :style="{ zIndex: extensionModalZIndex('openrouter') }"
        >
            <OpenRouterModal
                :visible="extensionsState.reactive.openrouterModalOpen"
                :on-close="closeOpenRouterModal"
            />
        </div>
        <div
            v-for="ext in extensionsState.reactive.extensionModalsOpen"
            :key="ext.id"
            class="extension-modal-layer"
            :style="{ zIndex: extensionModalZIndex(ext.id) }"
        >
            <ExtensionModal :extension="ext" />
        </div>
        <div
            v-if="extensionsState.reactive.documentsPdfViewer"
            class="extension-modal-layer"
            :style="{ zIndex: extensionModalZIndex('documents-pdf') }"
        >
            <DocumentsPdfViewer
                :visible="!!extensionsState.reactive.documentsPdfViewer"
                :on-close="closeDocumentsPdfViewer"
            />
        </div>
        <!-- Extension modal layer: position fixed, pointer-events none so children receive clicks -->
        <!-- end extension modals -->
        <!-- Modals that require immediate attention -->
        <CreateTokenDialog />
        <div id="teleport-modals"></div>
        <MarkdownModal v-if="showChangelog" :title="t('game.ui.ui.new_ver_msg')" :source="changelogText" />
        <!-- end of main modals -->
    </div>
</template>

<style scoped lang="scss">
.extension-modal-layer {
    position: fixed;
    inset: 0;
    pointer-events: none;
}

/* Modali estensione: la maschera non deve bloccare i click (come Gestisci estensioni).
   Solo il container del modale cattura i click; il resto passa all'interfaccia sotto. */
.extension-modal-layer :deep(.dialog-mask) {
    pointer-events: none;
}
.extension-modal-layer :deep(.modal-container) {
    pointer-events: auto;
}

#ui {
    pointer-events: none;
    position: absolute;
    display: grid;
    grid-template-areas:
        "topleft locations locations locations"
        "menu    menutoggle  annotation   zoom     "
        "menu        .           .          .      "
        "menu    floor-chat      .        tools    ";
    grid-template-rows: 0 auto 1fr auto;
    grid-template-columns: 0 repeat(3, 1fr);
    width: 100%;
    height: 100%;

    z-index: 0;
}

#floor-and-chat {
    grid-area: floor-chat;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}

#logo {
    pointer-events: auto;
    grid-area: topleft;
    background-color: #fa5a5a;
    display: flex;
    align-items: center;
}

#logo-icons {
    flex: 1 1 0px;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-evenly;

    > a {
        display: contents;

        > img {
            display: block;
            max-width: 45%;
        }
    }
}

#logo-links {
    display: flex;
    justify-content: space-evenly;

    > a {
        padding: 0 3px;
    }
}

#logo-version {
    flex: 1 1 0px;
    display: flex;
    flex-direction: column;
    align-items: center;
}

#zoom {
    pointer-events: auto;
    justify-self: end;
    top: 1rem;
    right: 1.6rem;
    grid-area: zoom;
}

#oob {
    position: fixed;
    bottom: 50px;
    left: 50%;
    transform: translateX(-50%);
    pointer-events: auto;

    background-color: white;
    padding: 20px 50px;
    border-radius: 15px;
    border: solid 3px black;

    &:hover {
        font-weight: bold;
        cursor: pointer;
    }
}

#radialmenu {
    overflow: hidden;
    grid-area: menutoggle;
    z-index: -1;
}

.rm-item {
    pointer-events: auto;
}

/* The svg is added by Font Awesome */

.rm-list-dm #rm-locations svg {
    margin-left: 3rem;
}

.rm-list-dm #rm-settings svg {
    margin-bottom: 3rem;
}

/* https://codepen.io/jonigiuro/pen/kclIu/ */

.rm-wrapper {
    position: relative;
    width: 12.5rem;
    height: 12.5rem;
    top: -6.25rem;
    left: -6.25rem;

    .rm-topper {
        pointer-events: none;
        text-align: center;
        line-height: 3rem;
        font-size: 1.6em;
    }

    .rm-toggler,
    .rm-topper {
        display: block;
        position: absolute;
        width: 3rem;
        height: 3rem;
        left: 50%;
        top: 50%;
        margin-left: -1.6rem;
        margin-top: -1.6rem;
        background: #fa5a5a;
        color: white;
        border-radius: 50%;

        .rm-list {
            opacity: 0.5;
            list-style: none;
            padding: 0;
            width: 12.5rem;
            height: 12.5rem;
            overflow: hidden;
            display: block;
            border-radius: 50%;
            transform: rotate(180deg);
            box-shadow: 0 0 10px 0 rgba(0, 0, 0, 0.2);
            margin: -4.7rem 0 0 -4.7rem;

            .rm-item {
                display: table;
                width: 50%;
                height: 50%;
                float: left;
                text-align: center;
                box-shadow: inset 0 0 2px 0 rgba(0, 0, 0, 0.2);
                background-color: white;

                &:hover {
                    background-color: #82c8a0;

                    a {
                        color: white;
                    }
                }

                a {
                    display: table-cell;
                    vertical-align: middle;
                    transform: rotate(-45deg);
                    text-decoration: none;
                    font-size: 1.6em;
                    color: #82c8a0;
                    border: none;
                    outline: none;
                }
            }
        }

        &:hover .rm-list {
            opacity: 1;
        }
    }
}

.rm-list-dm {
    transform: rotate(135deg) !important; /* total deg: 135 */
}

.settingsfade-enter-active,
.settingsfade-leave-active {
    transition: width 500ms;
}
.settingsfade-leave-to,
.settingsfade-enter {
    width: 0;
}
.settingsfade-enter-to,
.settingsfade-leave {
    width: 200px;
}
</style>

<style lang="scss">
.slider-checkbox {
    display: block;
    box-sizing: border-box;
    border: none;
    color: inherit;
    background: none;
    font: inherit;
    line-height: inherit;
    text-align: left;
    position: relative;
    outline: none;
    width: 2.6em;
    padding: 0.4em 0 0.4em 0.4em;

    &:hover {
        cursor: pointer;

        &::before {
            box-shadow: 0 0 0.5em #333;
        }

        &::after {
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='50' cy='50' r='50' fill='rgba(0,0,0,.25)'/%3E%3C/svg%3E");
            background-size: 30%;
            background-repeat: no-repeat;
            background-position: center center;
        }
    }

    &::before,
    &::after {
        content: "";
        position: absolute;
        height: 1.1em;
        transition: all 0.25s ease;
        left: 0;
    }

    &::before {
        width: 2.6em;
        border: 0.2em solid #767676;
        top: -0.2em;
        background: #767676;
        border-radius: 1.1em;
    }

    &::after {
        background-color: #fff;
        background-position: center center;
        border-radius: 50%;
        width: 1.1em;
        border: 0.15em solid #767676;
        top: -0.15em;
    }

    &[aria-pressed="true"] {
        &::after {
            left: 1.6em;
            border-color: #36a829;
            color: #36a829;
        }

        &::before {
            background-color: #36a829;
            border-color: #36a829;
        }
    }
}
</style>
