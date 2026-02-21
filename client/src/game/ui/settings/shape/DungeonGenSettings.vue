<script setup lang="ts">
import { useI18n } from "vue-i18n";

import { activeShapeStore } from "../../../../store/activeShape";
import { openDungeongenModalForEdit } from "../../../systems/extensions/ui";

const { t } = useI18n();

function editInDungeongen(): void {
    const shapeId = activeShapeStore.isComposite.value ? activeShapeStore.state.parentUuid : activeShapeStore.state.id;
    if (shapeId) {
        openDungeongenModalForEdit(shapeId);
        activeShapeStore.setShowEditDialog(false);
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

.edit-btn {
    padding: 0.6rem 1.2rem;
    background-color: #ff7052;
    color: white;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 500;
    align-self: flex-start;

    &:hover {
        opacity: 0.9;
    }
}
</style>
