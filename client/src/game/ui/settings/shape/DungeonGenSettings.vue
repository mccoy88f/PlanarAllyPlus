<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import { activeShapeStore } from "../../../../store/activeShape";
import { getDungeonStoredData, repositionMapsGenWalls } from "../../../dungeongen";
import { openDungeongenModalForEdit } from "../../../systems/extensions/ui";

const { t } = useI18n();
const toast = useToast();

/** Stessa logica di «Modifica in MapsGen»: forma principale se è variante composita. */
const targetShapeId = computed(() => {
    if (activeShapeStore.isComposite.value && activeShapeStore.parentUuid.value) {
        return activeShapeStore.parentUuid.value;
    }
    return activeShapeStore.state.id;
});

const stored = computed(() => {
    const id = targetShapeId.value;
    return id !== undefined ? getDungeonStoredData(id) : null;
});

const canRepositionWalls = computed(() => {
    const s = stored.value;
    if (!s) return false;
    return (s.walls?.lines?.length ?? 0) > 0 || (s.doors?.length ?? 0) > 0;
});

function editInDungeongen(): void {
    const shapeId = targetShapeId.value;
    if (shapeId) {
        openDungeongenModalForEdit(shapeId);
        activeShapeStore.setShowEditDialog(false);
    }
}

function repositionWalls(): void {
    const shapeId = targetShapeId.value;
    if (shapeId === undefined) return;
    const ok = repositionMapsGenWalls(shapeId);
    if (ok) {
        toast.success(t("game.ui.extensions.DungeongenSettings.reposition_walls_done"));
    } else {
        toast.warning(t("game.ui.extensions.DungeongenSettings.reposition_walls_failed"));
    }
}
</script>

<template>
    <div class="dungeongen-settings">
        <p class="dungeongen-settings-desc">
            {{ t("game.ui.extensions.DungeongenSettings.desc") }}
        </p>
        <button class="edit-btn" @click="editInDungeongen">
            {{ t("game.ui.extensions.DungeongenSettings.edit_in_dungeongen") }}
        </button>
        <button
            class="reposition-btn"
            type="button"
            :disabled="!canRepositionWalls"
            :title="t('game.ui.extensions.DungeongenSettings.reposition_walls_hint')"
            @click="repositionWalls"
        >
            {{ t("game.ui.extensions.DungeongenSettings.reposition_walls") }}
        </button>
    </div>
</template>

<style scoped lang="scss">
.dungeongen-settings {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
}

.dungeongen-settings-desc {
    margin: 0;
    font-size: 0.95em;
    color: #555;
}

.edit-btn,
.reposition-btn {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 500;
    align-self: flex-start;

    &:hover:not(:disabled) {
        opacity: 0.9;
    }
    &:disabled {
        opacity: 0.45;
        cursor: not-allowed;
    }
}

.edit-btn {
    background-color: #ff7052;
    color: white;
}

.reposition-btn {
    background-color: #2e7d32;
    color: white;
}
</style>
