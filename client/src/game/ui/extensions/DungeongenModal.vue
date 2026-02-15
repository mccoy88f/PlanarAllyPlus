<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import Modal from "../../../core/components/modals/Modal.vue";
import { baseAdjust } from "../../../core/http";
import { http } from "../../../core/http";
import {
    addDungeonToMap,
    type DungeonGenStoredData,
    DUNGEON_PARAMS_CUSTOM_DATA_NAME,
    DUNGEON_PARAMS_CUSTOM_DATA_SOURCE,
    getDungeonStoredData,
} from "../../dungeongen";
import { toGP } from "../../../core/geometry";
import { getGlobalId, getShape } from "../../id";
import type { Asset } from "../../shapes/variants/asset";
import { extensionsState } from "../../systems/extensions/state";
import { closeDungeongenModal } from "../../systems/extensions/ui";
import { customDataSystem } from "../../systems/customData";
import { propertiesSystem } from "../../systems/properties";
import { SERVER_SYNC } from "../../../core/models/types";

const props = defineProps<{
    visible: boolean;
    onClose: () => void;
}>();

const { t } = useI18n();
const toast = useToast();

const editShapeId = computed(() => extensionsState.reactive.dungeongenEditShapeId);
const isEditMode = computed(() => editShapeId.value !== undefined);

const generating = ref(false);
const previewUrl = ref<string | null>(null);
const gridCells = ref<{ width: number; height: number } | null>(null);
const dungeonMeta = ref<{
    imageWidth: number;
    imageHeight: number;
    syncSquareSize: number;
} | null>(null);
const addingToMap = ref(false);
const replacing = ref(false);
const makingRealistic = ref(false);
const openRouterAvailable = ref(false);

const params = ref({
    size: "medium",
    archetype: "classic",
    symmetry: "none",
    water: "dry",
    pack: "normal",
    roomsize: "mixed",
    round_rooms: false,
    halls: true,
    cross: "med",
    symmetry_break: "med",
    show_numbers: true,
    seed: "",
});

const sizeOptions = [
    { value: "tiny", labelKey: "game.ui.extensions.DungeongenModal.size_tiny" },
    { value: "small", labelKey: "game.ui.extensions.DungeongenModal.size_small" },
    { value: "medium", labelKey: "game.ui.extensions.DungeongenModal.size_medium" },
    { value: "large", labelKey: "game.ui.extensions.DungeongenModal.size_large" },
    { value: "xlarge", labelKey: "game.ui.extensions.DungeongenModal.size_xlarge" },
];

const archetypeOptions = [
    { value: "classic", labelKey: "game.ui.extensions.DungeongenModal.archetype_classic" },
    { value: "warren", labelKey: "game.ui.extensions.DungeongenModal.archetype_warren" },
    { value: "temple", labelKey: "game.ui.extensions.DungeongenModal.archetype_temple" },
    { value: "crypt", labelKey: "game.ui.extensions.DungeongenModal.archetype_crypt" },
    { value: "cavern", labelKey: "game.ui.extensions.DungeongenModal.archetype_cavern" },
    { value: "fortress", labelKey: "game.ui.extensions.DungeongenModal.archetype_fortress" },
    { value: "lair", labelKey: "game.ui.extensions.DungeongenModal.archetype_lair" },
];

const symmetryOptions = [
    { value: "none", labelKey: "game.ui.extensions.DungeongenModal.symmetry_none" },
    { value: "bilateral", labelKey: "game.ui.extensions.DungeongenModal.symmetry_bilateral" },
    { value: "radial2", labelKey: "game.ui.extensions.DungeongenModal.symmetry_radial2" },
    { value: "radial4", labelKey: "game.ui.extensions.DungeongenModal.symmetry_radial4" },
    { value: "partial", labelKey: "game.ui.extensions.DungeongenModal.symmetry_partial" },
];

const waterOptions = [
    { value: "dry", labelKey: "game.ui.extensions.DungeongenModal.water_dry" },
    { value: "puddles", labelKey: "game.ui.extensions.DungeongenModal.water_puddles" },
    { value: "pools", labelKey: "game.ui.extensions.DungeongenModal.water_pools" },
    { value: "lakes", labelKey: "game.ui.extensions.DungeongenModal.water_lakes" },
    { value: "flooded", labelKey: "game.ui.extensions.DungeongenModal.water_flooded" },
];

const packOptions = [
    { value: "sparse", labelKey: "game.ui.extensions.DungeongenModal.pack_sparse" },
    { value: "normal", labelKey: "game.ui.extensions.DungeongenModal.pack_normal" },
    { value: "tight", labelKey: "game.ui.extensions.DungeongenModal.pack_tight" },
];

const roomsizeOptions = [
    { value: "cozy", labelKey: "game.ui.extensions.DungeongenModal.roomsize_cozy" },
    { value: "mixed", labelKey: "game.ui.extensions.DungeongenModal.roomsize_mixed" },
    { value: "grand", labelKey: "game.ui.extensions.DungeongenModal.roomsize_grand" },
];

const crossOptions = [
    { value: "none", labelKey: "game.ui.extensions.DungeongenModal.cross_none" },
    { value: "low", labelKey: "game.ui.extensions.DungeongenModal.cross_low" },
    { value: "med", labelKey: "game.ui.extensions.DungeongenModal.cross_med" },
    { value: "high", labelKey: "game.ui.extensions.DungeongenModal.cross_high" },
];

const symmetryBreakOptions = [
    { value: "low", labelKey: "game.ui.extensions.DungeongenModal.symmetry_break_low" },
    { value: "med", labelKey: "game.ui.extensions.DungeongenModal.symmetry_break_med" },
    { value: "high", labelKey: "game.ui.extensions.DungeongenModal.symmetry_break_high" },
];

const symmetryBreakMap: Record<string, number> = { low: 0.1, med: 0.2, high: 0.5 };

onMounted(() => {
    checkOpenRouter();
});

watch(
    () => [props.visible, editShapeId.value] as const,
    ([visible, shapeId]) => {
        if (visible) {
            checkOpenRouter();
        }
        if (visible && shapeId) {
            const stored = getDungeonStoredData(shapeId);
            if (stored) {
                params.value = { ...stored.params };
                gridCells.value = stored.gridCells ?? null;
                dungeonMeta.value = stored.dungeonMeta ?? null;
            }
        }
    },
    { immediate: true },
);

async function generate(clearSeed = false): Promise<void> {
    generating.value = true;
    previewUrl.value = null;
    gridCells.value = null;
    dungeonMeta.value = null;
    if (clearSeed && !isEditMode.value) params.value.seed = "";
    try {
        const body: Record<string, unknown> = { ...params.value };
        if (params.value.seed) body.seed = parseInt(params.value.seed, 10) || params.value.seed;
        body.symmetry_break = symmetryBreakMap[params.value.symmetry_break] ?? 0.2;
        const response = await http.postJson("/api/extensions/dungeongen/generate", body);
        if (response.ok) {
            const data = (await response.json()) as {
                url: string;
                gridCells: { width: number; height: number };
                imageWidth?: number;
                imageHeight?: number;
                syncSquareSize?: number;
                seed: number;
            };
            previewUrl.value = data.url;
            gridCells.value = data.gridCells;
            dungeonMeta.value =
                data.imageWidth != null && data.imageHeight != null && data.syncSquareSize != null
                    ? {
                          imageWidth: data.imageWidth,
                          imageHeight: data.imageHeight,
                          syncSquareSize: data.syncSquareSize,
                      }
                    : null;
            params.value.seed = String(data.seed);
        } else {
            const text = await response.text();
            toast.error(text || t("game.ui.extensions.DungeongenModal.generate_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.DungeongenModal.generate_error"));
        console.error(e);
    } finally {
        generating.value = false;
    }
}

async function addToMap(): Promise<void> {
    if (!previewUrl.value || !gridCells.value) return;
    if (isEditMode.value) {
        await replaceOnMap();
        return;
    }
    addingToMap.value = true;
    try {
        const asset = await addDungeonToMap(
            previewUrl.value,
            gridCells.value,
            toGP(0, 0),
            {
                ...(dungeonMeta.value ?? {}),
                params: { ...params.value },
                seed: params.value.seed,
            },
        );
        if (asset) {
            toast.success(t("game.ui.extensions.DungeongenModal.added_to_map"));
            props.onClose();
        } else {
            toast.error(t("game.ui.extensions.DungeongenModal.add_failed"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.DungeongenModal.add_failed"));
        console.error(e);
    } finally {
        addingToMap.value = false;
    }
}

async function replaceOnMap(): Promise<void> {
    const shapeId = editShapeId.value;
    if (!shapeId || !previewUrl.value || !gridCells.value) return;
    const shape = getShape(shapeId);
    if (!shape || !("setImage" in shape)) return;
    replacing.value = true;
    try {
        const newSeed = params.value.seed;
        propertiesSystem.setName(shapeId, newSeed, SERVER_SYNC);
        (shape as Asset).setImage(previewUrl.value, true);

        const storedData: DungeonGenStoredData = {
            params: { ...params.value },
            seed: newSeed,
            gridCells: gridCells.value,
            dungeonMeta: dungeonMeta.value ?? undefined,
        };
        const globalId = getGlobalId(shapeId);
        if (globalId) {
            const elemId = customDataSystem.getElementId({
                shapeId: globalId,
                source: DUNGEON_PARAMS_CUSTOM_DATA_SOURCE,
                prefix: "/",
                name: DUNGEON_PARAMS_CUSTOM_DATA_NAME,
            });
            if (elemId !== undefined) {
                customDataSystem.updateValue(shapeId, elemId, JSON.stringify(storedData), true);
            }
        }
        toast.success(t("game.ui.extensions.DungeongenModal.replaced_on_map"));
        closeDungeongenModal();
        props.onClose();
    } catch (e) {
        toast.error(t("game.ui.extensions.DungeongenModal.replace_failed"));
        console.error(e);
    } finally {
        replacing.value = false;
    }
}

function close(): void {
    previewUrl.value = null;
    gridCells.value = null;
    dungeonMeta.value = null;
    closeDungeongenModal();
    props.onClose();
}

async function checkOpenRouter(): Promise<void> {
    try {
        const [extResp, settingsResp] = await Promise.all([
            http.get("/api/extensions"),
            http.get("/api/extensions/openrouter/settings"),
        ]);
        if (!extResp.ok || !settingsResp.ok) {
            openRouterAvailable.value = false;
            return;
        }
        const extData = (await extResp.json()) as { extensions?: { id: string }[] };
        const settingsData = (await settingsResp.json()) as { hasApiKey?: boolean; imageModel?: string };
        const hasExt = (extData.extensions ?? []).some((e) => e.id === "openrouter");
        const hasConfig = settingsData.hasApiKey && settingsData.imageModel;
        openRouterAvailable.value = !!hasExt && !!hasConfig;
    } catch {
        openRouterAvailable.value = false;
    }
}

async function makeRealisticWithAI(): Promise<void> {
    if (!previewUrl.value) return;
    makingRealistic.value = true;
    try {
        const resp = await http.postJson("/api/extensions/openrouter/transform-image", {
            imageUrl: previewUrl.value,
            archetype: params.value.archetype,
        });
        if (resp.ok) {
            const data = (await resp.json()) as { imageUrl?: string };
            if (data.imageUrl) {
                previewUrl.value = data.imageUrl;
                toast.success(t("game.ui.extensions.DungeongenModal.realistic_done"));
            }
        } else {
            const err = (await resp.json().catch(() => ({}))) as { error?: string };
            toast.error(err.error || t("game.ui.extensions.DungeongenModal.realistic_error"));
        }
    } catch (e) {
        toast.error(t("game.ui.extensions.DungeongenModal.realistic_error"));
        console.error(e);
    } finally {
        makingRealistic.value = false;
    }
}
</script>

<template>
    <Modal
        v-if="visible"
        :visible="visible"
        :mask="false"
        :close-on-mask-click="false"
        extra-class="dungeongen-modal"
        @close="close"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="dungeongen-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="dungeongen-modal-title">{{ t("game.ui.extensions.DungeongenModal.title") }}</h2>
                <div class="dungeongen-modal-actions">
                    <font-awesome-icon
                        :icon="['far', 'square']"
                        :title="t('game.ui.extensions.ExtensionModal.window')"
                        class="dungeongen-modal-btn"
                        @click.stop="toggleWindow?.()"
                    />
                    <font-awesome-icon
                        :icon="fullscreen ? 'compress' : 'expand'"
                        :title="fullscreen ? t('common.fullscreen_exit') : t('common.fullscreen')"
                        class="dungeongen-modal-btn"
                        @click.stop="toggleFullscreen?.()"
                    />
                    <font-awesome-icon
                        class="dungeongen-modal-close"
                        :icon="['far', 'window-close']"
                        :title="t('common.close')"
                        @click="close"
                    />
                </div>
            </div>
        </template>
        <div class="modal-body">
                <section class="params-section">
                    <h3>{{ t("game.ui.extensions.DungeongenModal.settings") }}</h3>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.size") }}</label>
                        <select v-model="params.size">
                            <option v-for="opt in sizeOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.archetype") }}</label>
                        <select v-model="params.archetype">
                            <option v-for="opt in archetypeOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.symmetry") }}</label>
                        <select v-model="params.symmetry">
                            <option v-for="opt in symmetryOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.water") }}</label>
                        <select v-model="params.water">
                            <option v-for="opt in waterOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.pack") }}</label>
                        <select v-model="params.pack">
                            <option v-for="opt in packOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.roomsize") }}</label>
                        <select v-model="params.roomsize">
                            <option v-for="opt in roomsizeOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.cross") }}</label>
                        <select v-model="params.cross">
                            <option v-for="opt in crossOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row">
                        <label>{{ t("game.ui.extensions.DungeongenModal.symmetry_break") }}</label>
                        <select v-model="params.symmetry_break">
                            <option v-for="opt in symmetryBreakOptions" :key="opt.value" :value="opt.value">
                                {{ t(opt.labelKey) }}
                            </option>
                        </select>
                    </div>
                    <div class="param-row param-row-checkbox">
                        <label>
                            <input v-model="params.round_rooms" type="checkbox" />
                            {{ t("game.ui.extensions.DungeongenModal.round_rooms") }}
                        </label>
                    </div>
                    <div class="param-row param-row-checkbox">
                        <label>
                            <input v-model="params.halls" type="checkbox" />
                            {{ t("game.ui.extensions.DungeongenModal.halls") }}
                        </label>
                    </div>
                    <div class="param-row param-row-checkbox">
                        <label>
                            <input v-model="params.show_numbers" type="checkbox" />
                            {{ t("game.ui.extensions.DungeongenModal.show_numbers") }}
                        </label>
                    </div>
                    <div class="param-row param-row-full">
                        <label>{{ t("game.ui.extensions.DungeongenModal.seed") }}</label>
                        <input
                            v-model="params.seed"
                            type="text"
                            :placeholder="t('game.ui.extensions.DungeongenModal.seed_placeholder')"
                            :disabled="isEditMode"
                        />
                        <p v-if="isEditMode" class="edit-mode-note">
                            {{ t("game.ui.extensions.DungeongenModal.edit_mode_note") }}
                        </p>
                    </div>
                    <div class="generate-buttons param-row-full">
                        <button
                            class="generate-btn"
                            data-testid="dungeongen-generate"
                            :disabled="generating"
                            @click="generate(false)"
                        >
                            {{ generating ? t("game.ui.extensions.DungeongenModal.generating") : t("game.ui.extensions.DungeongenModal.generate") }}
                        </button>
                        <button
                            v-if="!isEditMode"
                            class="generate-new-btn"
                            data-testid="dungeongen-generate-new"
                            :disabled="generating"
                            @click="generate(true)"
                        >
                            {{ t("game.ui.extensions.DungeongenModal.generate_new") }}
                        </button>
                    </div>
                </section>

                <section class="preview-section">
                    <h3>{{ t("game.ui.extensions.DungeongenModal.preview") }}</h3>
                    <div v-if="!previewUrl" class="preview-placeholder">
                        {{ t("game.ui.extensions.DungeongenModal.click_generate") }}
                    </div>
                    <div v-else class="preview-container">
                        <img :src="previewUrl ? baseAdjust(previewUrl) : ''" alt="Dungeon preview" class="preview-img" />
                        <div v-if="gridCells" class="preview-info">
                            {{ gridCells.width }}×{{ gridCells.height }} cells
                        </div>
                        <button
                            v-if="openRouterAvailable"
                            class="realistic-btn"
                            :disabled="makingRealistic"
                            @click="makeRealisticWithAI"
                        >
                            {{ makingRealistic ? "..." : t("game.ui.extensions.DungeongenModal.make_realistic") }}
                        </button>
                        <button
                            class="add-btn"
                            :data-testid="isEditMode ? 'dungeongen-replace-on-map' : 'dungeongen-add-to-map'"
                            :disabled="addingToMap || replacing"
                            @click="addToMap"
                        >
                            {{ addingToMap || replacing ? "..." : (isEditMode ? t("game.ui.extensions.DungeongenModal.replace_on_map") : t("game.ui.extensions.DungeongenModal.add_to_map")) }}
                        </button>
                    </div>
                </section>
            </div>
    </Modal>
</template>

<style lang="scss">
.dungeongen-modal {
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

<style scoped lang="scss">
.dungeongen-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    cursor: grab;
    border-bottom: 1px solid #eee;
    background: #f9f9f9;

    .dungeongen-modal-title {
        margin: 0;
        font-size: 1.1rem;
        font-weight: 600;
    }

    .dungeongen-modal-actions {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }

    .dungeongen-modal-btn,
    .dungeongen-modal-close {
        font-size: 1.1rem;
        cursor: pointer;
        flex-shrink: 0;

        &:hover {
            opacity: 0.7;
        }
    }
}

.modal-body {
    flex: 1;
    min-height: 0;
    display: flex;
    gap: 1.5rem;
    padding: 1.5rem 2rem;
    overflow: auto;
}

.params-section {
    flex: 1;
    min-width: 220px;
    max-width: 320px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 1rem;
    align-content: start;

    > h3 {
        grid-column: 1 / -1;
        font-weight: bold;
        font-size: 1.1em;
        margin-bottom: 0.5rem;
    }
}

.preview-section {
    flex: 1;
    min-width: 200px;

    > h3 {
        font-weight: bold;
        font-size: 1.1em;
        margin-bottom: 0.5rem;
    }
}

.params-section h3,
.preview-section h3 {
    margin: 0 0 0.75rem;
}

.param-row,
.param-row-checkbox {
    grid-column: span 1;
    margin-bottom: 0.75rem;

    label {
        display: block;
        font-weight: 500;
        font-size: 0.95em;
        margin-bottom: 0.25rem;
    }

    select,
    input[type="text"] {
        width: 100%;
        padding: 0.5rem;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
    }
}

.param-row-full {
    grid-column: 1 / -1;
}

.edit-mode-note {
    margin: 0.35rem 0 0;
    font-size: 0.85em;
    color: #666;
    font-style: italic;
}

.param-row-checkbox label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;

    input[type="checkbox"] {
        width: auto;
    }
}

.generate-buttons {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 1rem;
}

.generate-btn,
.generate-new-btn {
    padding: 0.5rem 1rem;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 500;
    border: none;

    &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
}

.generate-btn {
    background-color: #82c8a0;
    color: #333;

    &:hover:not(:disabled) {
        background-color: #6bb88a;
    }
}

.generate-new-btn {
    background-color: #eee;
    color: #444;
    border: 1px solid #ccc;

    &:hover:not(:disabled) {
        background-color: #e0e0e0;
    }
}

.preview-placeholder {
    border: 2px dashed #ccc;
    padding: 2rem;
    text-align: center;
    color: #666;
    min-height: 200px;
    border-radius: 0.25rem;
}

.preview-container {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;

    .preview-img {
        max-width: 100%;
        max-height: 400px;
        object-fit: contain;
        border: 1px solid #eee;
        border-radius: 0.25rem;
    }

    .preview-info {
        font-size: 0.9em;
        color: #666;
    }

    .realistic-btn {
        padding: 0.5rem 1rem;
        background-color: #82c8a0;
        color: #333;
        border: none;
        border-radius: 0.25rem;
        cursor: pointer;
        font-weight: 500;

        &:hover:not(:disabled) {
            opacity: 0.9;
        }

        &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    }

    .add-btn {
        padding: 0.5rem 1rem;
        background-color: #ff7052;
        color: white;
        border: none;
        border-radius: 0.25rem;
        cursor: pointer;
        font-weight: 500;

        &:hover:not(:disabled) {
            opacity: 0.9;
        }

        &:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    }
}
</style>
