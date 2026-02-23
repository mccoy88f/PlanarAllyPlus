<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { useToast } from "vue-toastification";

import LoadingBar from "../../../core/components/LoadingBar.vue";
import HeaderModeSelector from "../../../core/components/HeaderModeSelector.vue";
import Modal from "../../../core/components/modals/Modal.vue";
import { baseAdjust } from "../../../core/http";
import { http } from "../../../core/http";
import {
    addDungeonToMap,
    type BuildingGenParams,
    type DungeonGenParams,
    type DungeonGenStoredData,
    DUNGEON_PARAMS_CUSTOM_DATA_NAME,
    DUNGEON_PARAMS_CUSTOM_DATA_SOURCE,
    getDungeonStoredData,
    type WallData,
    type DoorData,
} from "../../dungeongen";
import { toGP } from "../../../core/geometry";
import { getGlobalId, getShape } from "../../id";
import type { Asset } from "../../shapes/variants/asset";
import { extensionsState } from "../../systems/extensions/state";
import { closeDungeongenModal, focusExtension } from "../../systems/extensions/ui";
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
const dungeonWalls = ref<WallData | null>(null);
const dungeonDoors = ref<DoorData[] | null>(null);
const generatedName = ref<string>("");
const addingToMap = ref(false);
const replacing = ref(false);
const makingRealistic = ref(false);
const openRouterAvailable = ref(false);

const mode = ref<"dungeon" | "building">("dungeon");
const modeOptions = computed(() => [
    { label: t("game.ui.extensions.DungeongenModal.mode_dungeon"), value: "dungeon" as const },
    { label: t("game.ui.extensions.DungeongenModal.mode_building"), value: "building" as const },
]);

const showPromptModal = ref(false);
const extraAiPrompt = ref("");

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

// ── Building mode params ──────────────────────────────────────────────────

const buildingParams = ref<BuildingGenParams>({
    archetype: "tavern",
    footprint: "rectangle",
    layout:    "open_plan",
    seed:      "",
});

const buildingArchetypeOptions = [
    { value: "house",  labelKey: "game.ui.extensions.DungeongenModal.barch_house"  },
    { value: "shop",   labelKey: "game.ui.extensions.DungeongenModal.barch_shop"   },
    { value: "tavern", labelKey: "game.ui.extensions.DungeongenModal.barch_tavern" },
    { value: "inn",    labelKey: "game.ui.extensions.DungeongenModal.barch_inn"    },
];

const footprintOptions = [
    { value: "rectangle", labelKey: "game.ui.extensions.DungeongenModal.fp_rectangle" },
    { value: "l_shape",   labelKey: "game.ui.extensions.DungeongenModal.fp_l_shape"   },
    { value: "cross",     labelKey: "game.ui.extensions.DungeongenModal.fp_cross"     },
    { value: "offset",    labelKey: "game.ui.extensions.DungeongenModal.fp_offset"    },
];

const layoutOptions = [
    { value: "open_plan", labelKey: "game.ui.extensions.DungeongenModal.layout_open_plan" },
    { value: "corridor",  labelKey: "game.ui.extensions.DungeongenModal.layout_corridor"  },
];

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
                // Detect if stored params are building params
                const storedParams = stored.params as Record<string, unknown>;
                if ("footprint" in storedParams) {
                    mode.value = "building";
                    buildingParams.value = { ...(stored.params as BuildingGenParams) };
                } else {
                    mode.value = "dungeon";
                    params.value = { ...(stored.params as DungeonGenParams) };
                }
                gridCells.value = stored.gridCells ?? null;
                dungeonMeta.value = stored.dungeonMeta ?? null;
                dungeonWalls.value = stored.walls ?? null;
                dungeonDoors.value = stored.doors ?? null;

                const shape = getShape(shapeId);
                if (shape && "src" in shape) {
                    previewUrl.value = (shape as Asset).src;
                }
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
    dungeonWalls.value = null;
    generatedName.value = "";

    try {
        let body: Record<string, unknown>;

        if (mode.value === "building") {
            if (clearSeed && !isEditMode.value) buildingParams.value.seed = "";
            body = {
                mode:      "building",
                archetype: buildingParams.value.archetype,
                footprint: buildingParams.value.footprint,
                layout:    buildingParams.value.layout,
                seed:      buildingParams.value.seed
                               ? (parseInt(buildingParams.value.seed, 10) || buildingParams.value.seed)
                               : "",
            };
        } else {
            if (clearSeed && !isEditMode.value) params.value.seed = "";
            body = { ...params.value, mode: "dungeon" };
            if (params.value.seed) body.seed = parseInt(params.value.seed, 10) || params.value.seed;
            body.symmetry_break = symmetryBreakMap[params.value.symmetry_break] ?? 0.2;
        }

        const response = await http.postJson("/api/extensions/dungeongen/generate", body);
        if (response.ok) {
            const data = (await response.json()) as {
                url: string;
                name?: string;
                gridCells: { width: number; height: number };
                imageWidth?: number;
                imageHeight?: number;
                syncSquareSize?: number;
                seed: number;
                doors?: DoorData[];
            };
            previewUrl.value = data.url;
            generatedName.value = data.name ?? "";
            gridCells.value = data.gridCells;
            dungeonMeta.value =
                data.imageWidth != null && data.imageHeight != null && data.syncSquareSize != null
                    ? {
                          imageWidth: data.imageWidth,
                          imageHeight: data.imageHeight,
                          syncSquareSize: data.syncSquareSize,
                      }
                    : null;
            dungeonWalls.value = (data as any).walls ?? null;
            dungeonDoors.value = data.doors ?? null;
            if (mode.value === "building") {
                buildingParams.value.seed = String(data.seed);
            } else {
                params.value.seed = String(data.seed);
            }
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
        const currentParams = mode.value === "building"
            ? { ...buildingParams.value }
            : { ...params.value };
        const currentSeed = mode.value === "building"
            ? buildingParams.value.seed
            : params.value.seed;
        const asset = await addDungeonToMap(
            previewUrl.value,
            gridCells.value,
            toGP(0, 0),
            {
                ...(dungeonMeta.value ?? {}),
                name: generatedName.value || undefined,
                params: currentParams,
                seed: currentSeed,
                walls: dungeonWalls.value ?? undefined,
                doors: dungeonDoors.value ?? undefined,
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
        const newSeed = mode.value === "building" ? buildingParams.value.seed : params.value.seed;
        const currentParams = mode.value === "building"
            ? { ...buildingParams.value }
            : { ...params.value };
        propertiesSystem.setName(shapeId, newSeed, SERVER_SYNC);
        (shape as Asset).setImage(previewUrl.value, true);

        const storedData: DungeonGenStoredData = {
            params: currentParams,
            seed: newSeed,
            gridCells: gridCells.value,
            dungeonMeta: dungeonMeta.value ?? undefined,
            walls: dungeonWalls.value ?? undefined,
            doors: dungeonDoors.value ?? undefined,
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
    dungeonWalls.value = null;
    generatedName.value = "";
    dungeonDoors.value = null;
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

function promptMakeRealisticWithAI(): void {
    if (!previewUrl.value) return;
    showPromptModal.value = true;
    extraAiPrompt.value = "";
}

async function makeRealisticWithAI(): Promise<void> {
    if (!previewUrl.value) return;
    makingRealistic.value = true;
    showPromptModal.value = false;
    try {
        const resp = await http.postJson("/api/extensions/openrouter/transform-image", {
            imageUrl: previewUrl.value,
            archetype: params.value.archetype,
            extraPrompt: extraAiPrompt.value,
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
        @focus="focusExtension('dungeongen')"
    >
        <template #header="{ dragStart, dragEnd, toggleWindow, toggleFullscreen, fullscreen }">
            <div
                class="ext-modal-header"
                draggable="true"
                @dragstart="dragStart"
                @dragend="dragEnd"
            >
                <h2 class="ext-modal-title">{{ t("game.ui.extensions.DungeongenModal.title") }}</h2>
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
        <div class="ext-modal-body-wrapper">
            <div v-if="generating || makingRealistic" class="ext-progress-top-container">
                <LoadingBar :progress="100" indeterminate height="6px" />
            </div>
            <HeaderModeSelector v-model="mode" :options="modeOptions" />
            <div class="ext-body ext-two-col">
                <section class="ext-ui-section ext-two-col-side ext-two-col-single">
                    <h3 class="ext-ui-section-title">{{ t("game.ui.extensions.DungeongenModal.settings") }}</h3>

                    <!-- ── DUNGEON settings ─────────────────────────────── -->
                    <template v-if="mode === 'dungeon'">
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-size">{{ t("game.ui.extensions.DungeongenModal.size") }}</label>
                                <select id="dg-size" v-model="params.size" class="ext-ui-select">
                                    <option v-for="opt in sizeOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-archetype">{{ t("game.ui.extensions.DungeongenModal.archetype") }}</label>
                                <select id="dg-archetype" v-model="params.archetype" class="ext-ui-select">
                                    <option v-for="opt in archetypeOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-symmetry">{{ t("game.ui.extensions.DungeongenModal.symmetry") }}</label>
                                <select id="dg-symmetry" v-model="params.symmetry" class="ext-ui-select">
                                    <option v-for="opt in symmetryOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-water">{{ t("game.ui.extensions.DungeongenModal.water") }}</label>
                                <select id="dg-water" v-model="params.water" class="ext-ui-select">
                                    <option v-for="opt in waterOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-pack">{{ t("game.ui.extensions.DungeongenModal.pack") }}</label>
                                <select id="dg-pack" v-model="params.pack" class="ext-ui-select">
                                    <option v-for="opt in packOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-roomsize">{{ t("game.ui.extensions.DungeongenModal.roomsize") }}</label>
                                <select id="dg-roomsize" v-model="params.roomsize" class="ext-ui-select">
                                    <option v-for="opt in roomsizeOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-cross">{{ t("game.ui.extensions.DungeongenModal.cross") }}</label>
                                <select id="dg-cross" v-model="params.cross" class="ext-ui-select">
                                    <option v-for="opt in crossOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="dg-symbreak">{{ t("game.ui.extensions.DungeongenModal.symmetry_break") }}</label>
                                <select id="dg-symbreak" v-model="params.symmetry_break" class="ext-ui-select">
                                    <option v-for="opt in symmetryBreakOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="dg-fields-row">
                            <label class="ext-ui-checkbox">
                                <input v-model="params.round_rooms" type="checkbox" />
                                {{ t("game.ui.extensions.DungeongenModal.round_rooms") }}
                            </label>
                        </div>
                        <div class="dg-fields-row">
                            <label class="ext-ui-checkbox">
                                <input v-model="params.halls" type="checkbox" />
                                {{ t("game.ui.extensions.DungeongenModal.halls") }}
                            </label>
                        </div>
                        <div class="dg-fields-row">
                            <label class="ext-ui-checkbox">
                                <input v-model="params.show_numbers" type="checkbox" />
                                {{ t("game.ui.extensions.DungeongenModal.show_numbers") }}
                            </label>
                        </div>
                        <div class="ext-ui-field">
                            <label class="ext-ui-label" for="dg-seed">{{ t("game.ui.extensions.DungeongenModal.seed") }}</label>
                            <input
                                id="dg-seed"
                                v-model="params.seed"
                                type="text"
                                class="ext-ui-input"
                                :placeholder="t('game.ui.extensions.DungeongenModal.seed_placeholder')"
                                :disabled="isEditMode"
                            />
                            <p v-if="isEditMode" class="ext-ui-hint edit-mode-note">
                                {{ t("game.ui.extensions.DungeongenModal.edit_mode_note") }}
                            </p>
                        </div>
                    </template>

                    <!-- ── BUILDING settings ────────────────────────────── -->
                    <template v-else>
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="bg-archetype">{{ t("game.ui.extensions.DungeongenModal.archetype") }}</label>
                                <select id="bg-archetype" v-model="buildingParams.archetype" class="ext-ui-select">
                                    <option v-for="opt in buildingArchetypeOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="dg-fields-row">
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="bg-footprint">{{ t("game.ui.extensions.DungeongenModal.footprint") }}</label>
                                <select id="bg-footprint" v-model="buildingParams.footprint" class="ext-ui-select">
                                    <option v-for="opt in footprintOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                            <div class="ext-ui-field">
                                <label class="ext-ui-label" for="bg-layout">{{ t("game.ui.extensions.DungeongenModal.layout") }}</label>
                                <select id="bg-layout" v-model="buildingParams.layout" class="ext-ui-select">
                                    <option v-for="opt in layoutOptions" :key="opt.value" :value="opt.value">
                                        {{ t(opt.labelKey) }}
                                    </option>
                                </select>
                            </div>
                        </div>
                        <div class="ext-ui-field">
                            <label class="ext-ui-label" for="bg-seed">{{ t("game.ui.extensions.DungeongenModal.seed") }}</label>
                            <input
                                id="bg-seed"
                                v-model="buildingParams.seed"
                                type="text"
                                class="ext-ui-input"
                                :placeholder="t('game.ui.extensions.DungeongenModal.seed_placeholder')"
                                :disabled="isEditMode"
                            />
                            <p v-if="isEditMode" class="ext-ui-hint edit-mode-note">
                                {{ t("game.ui.extensions.DungeongenModal.edit_mode_note") }}
                            </p>
                        </div>
                    </template>
                </section>

                <section class="ext-ui-section ext-two-col-main">
                    <h3 class="ext-ui-section-title">{{ t("game.ui.extensions.DungeongenModal.preview") }}</h3>
                    <div v-if="!previewUrl" class="ext-ui-empty preview-placeholder">
                        {{ t("game.ui.extensions.DungeongenModal.click_generate") }}
                    </div>
                    <div v-else class="preview-container">
                        <img :src="previewUrl ? baseAdjust(previewUrl) : ''" alt="Dungeon preview" class="preview-img" />
                        <div v-if="gridCells" class="preview-info ext-ui-muted">
                            {{ gridCells.width }}×{{ gridCells.height }} cells
                        </div>
                        <button
                            v-if="openRouterAvailable"
                            class="ext-ui-btn ext-ui-btn-success realistic-btn"
                            :disabled="makingRealistic"
                            @click="promptMakeRealisticWithAI"
                        >
                            {{ makingRealistic ? "..." : t("game.ui.extensions.DungeongenModal.make_realistic") }}
                        </button>
                        <button
                            class="ext-ui-btn add-btn"
                            :data-testid="isEditMode ? 'dungeongen-replace-on-map' : 'dungeongen-add-to-map'"
                            :disabled="addingToMap || replacing"
                            @click="addToMap"
                        >
                            {{ addingToMap || replacing ? "..." : (isEditMode ? t("game.ui.extensions.DungeongenModal.replace_on_map") : t("game.ui.extensions.DungeongenModal.add_to_map")) }}
                        </button>
                    </div>
                </section>
            </div>
            <div class="ext-bottom-bar">
                <button
                    class="ext-ui-btn ext-ui-btn-success generate-btn"
                    data-testid="dungeongen-generate"
                    :disabled="generating"
                    @click="generate(false)"
                >
                    {{ generating ? t("game.ui.extensions.DungeongenModal.generating") : t("game.ui.extensions.DungeongenModal.generate") }}
                </button>
                <button
                    v-if="!isEditMode"
                    class="ext-ui-btn"
                    data-testid="dungeongen-generate-new"
                    :disabled="generating"
                    @click="generate(true)"
                >
                    {{ t("game.ui.extensions.DungeongenModal.generate_new") }}
                </button>
            </div>

            <div v-if="showPromptModal" class="ai-prompt-overlay" @click="showPromptModal = false">
                <div class="ai-prompt-box" @click.stop>
                    <h3>{{ t("game.ui.extensions.DungeongenModal.ai_prompt_title") }}</h3>
                    <p>{{ t("game.ui.extensions.DungeongenModal.ai_prompt_desc") }}</p>
                    <textarea v-model="extraAiPrompt" class="ext-ui-textarea" rows="3"></textarea>
                    <div class="ai-prompt-actions">
                        <button class="ext-ui-btn" @click="showPromptModal = false">{{ t("common.cancel") }}</button>
                        <button class="ext-ui-btn ext-ui-btn-success ai-prompt-send" @click="makeRealisticWithAI">
                            {{ extraAiPrompt.trim() ? t("game.ui.extensions.DungeongenModal.ai_prompt_send") : t("game.ui.extensions.DungeongenModal.ai_prompt_send_empty") }}
                        </button>
                    </div>
                </div>
            </div>
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
.ext-two-col-side {
    gap: 0.35rem;
}
.ext-two-col-side .ext-ui-field {
    margin-bottom: 0;
}
.ext-two-col-side .ext-ui-field .ext-ui-label {
    margin-bottom: 0.2rem;
}

.dg-fields-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    margin-bottom: 0.35rem;
}
.dg-fields-row .ext-ui-field {
    flex: 1;
    min-width: 100px;
}
.dg-checkboxes .ext-ui-field {
    flex: 0 0 auto;
}

.ext-two-col-main > h3 {
    font-weight: bold;
    font-size: 1.1em;
    margin-bottom: 0.5rem;
}

.edit-mode-note {
    margin: 0.35rem 0 0;
    font-size: 0.85em;
    color: #666;
    font-style: italic;
}

.ext-two-col-main .preview-placeholder {
    border: 2px dashed #ccc;
    text-align: center;
    min-height: 200px;
    border-radius: 0.25rem;
}

.ext-two-col-main .preview-container {
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

    .add-btn {
        background-color: #ff7052;
        border-color: #ff7052;
        color: white;

        &:hover:not(:disabled) {
            background-color: #e65a3d;
            border-color: #e65a3d;
        }
    }
}

.ai-prompt-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
}
.ai-prompt-box {
    background: white;
    padding: 1.5rem;
    border-radius: 0.5rem;
    width: 80%;
    max-width: 400px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    color: #333;
}
.ai-prompt-box h3 { margin: 0; font-size: 1.2rem; font-weight: bold; }
.ai-prompt-box p { margin: 0; font-size: 0.9rem; color: #555; }
.ai-prompt-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
</style>
