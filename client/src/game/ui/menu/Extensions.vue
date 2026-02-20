<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";

import { http } from "../../../core/http";
import { gameState } from "../../systems/game/state";
import { extensionsState } from "../../systems/extensions/state";

import {
    closeExtension,
    isExtensionOpen,
    openDungeongenModal,
    openExtensionModal,
    openOpenRouterModal,
    openCompendiumModal,
    toggleExtensionsManager,
} from "../../systems/extensions/ui";

const { t } = useI18n();
const route = useRoute();

/** In fake player mode, show only extensions visible to players */
const visibleExtensions = computed(() => {
    const exts = extensionsState.reactive.extensions;
    if (gameState.reactive.isFakePlayer) {
        return exts.filter((ext) => ext.visibleToPlayers === true);
    }
    return exts;
});

async function loadExtensions(): Promise<void> {
    try {
        let url = "/api/extensions";
        const creator = route.params.creator as string | undefined;
        const room = route.params.room as string | undefined;
        if (creator && room) {
            url += `?room_creator=${encodeURIComponent(creator)}&room_name=${encodeURIComponent(room)}`;
        }
        const response = await http.get(url);
        if (response.ok) {
            const data = (await response.json()) as {
                extensions: {
                    id: string;
                    name: string;
                    version: string;
                    description?: string;
                    folder?: string;
                    titleBarColor?: string;
                    icon?: string | [string, string];
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

function extensionDisplayName(ext: { id: string; name: string }): string {
    const key = `game.ui.menu.Extensions.extensions.${ext.id}`;
    const translated = t(key);
    return translated !== key ? translated : ext.name;
}

function onExtensionClick(ext: {
    id: string;
    name: string;
    folder?: string;
    uiUrl?: string;
    titleBarColor?: string;
    icon?: string | [string, string];
}): void {
    if (isExtensionOpen(ext)) {
        closeExtension(ext);
        return;
    }
    if (ext.uiUrl && ext.folder) {
        openExtensionModal({
            id: ext.id,
            name: ext.name,
            folder: ext.folder,
            uiUrl: ext.uiUrl,
            titleBarColor: ext.titleBarColor,
            icon: ext.icon,
        });
    } else if (ext.id === "dungeongen") {
        openDungeongenModal();
    } else if (ext.id === "compendium") {
        openCompendiumModal();
    } else if (ext.id === "openrouter") {
        openOpenRouterModal();
    }
}

onMounted(loadExtensions);
</script>

<template>
    <button class="menu-accordion">{{ t("common.extensions") }}</button>
    <div class="menu-accordion-panel">
        <div class="menu-accordion-subpanel">
            <template v-for="ext in visibleExtensions" :key="ext.id">
                <div class="menu-accordion-subpanel-text" style="cursor: pointer" @click="onExtensionClick(ext)">
                    {{ extensionDisplayName(ext) }}
                </div>
            </template>
            <div
                v-if="visibleExtensions.length === 0"
                style="font-style: italic; color: #666"
            >
                {{ t("game.ui.menu.Extensions.no_extensions") }}
            </div>
            <div
                v-if="gameState.isDmOrFake.value && !gameState.reactive.isFakePlayer"
                style="cursor: pointer"
            >
                <div class="menu-accordion-subpanel-text" @click="toggleExtensionsManager">
                    {{ t("game.ui.menu.Extensions.manage_extensions") }}
                </div>
            </div>
        </div>
    </div>
</template>
