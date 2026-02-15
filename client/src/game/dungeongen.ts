/**
 * Add a generated dungeon image to the map as an Asset.
 * Uses sync square (1 cell = syncSquareSize px in image) to scale to PlanarAlly's grid.
 */
import type { LocalId } from "../core/id";
import { type GlobalPoint, toGP } from "../core/geometry";
import { DEFAULT_GRID_SIZE, snapPointToGrid } from "../core/grid";
import { baseAdjust } from "../core/http";
import { SyncMode, InvalidationMode, SERVER_SYNC, UI_SYNC } from "../core/models/types";
import { uuidv4 } from "../core/utils";

import { getGlobalId } from "./id";
import { Asset } from "./shapes/variants/asset";
import { customDataSystem } from "./systems/customData";
import { accessSystem } from "./systems/access";
import { floorState } from "./systems/floors/state";
import { floorSystem } from "./systems/floors";
import { LayerName } from "./models/floor";
import { playerSystem } from "./systems/players";
import { propertiesSystem } from "./systems/properties";
import { locationSettingsState } from "./systems/settings/location/state";
import { playerSettingsState } from "./systems/settings/players/state";

export const DUNGEON_ASSET_SRC_PREFIX = "/static/temp/dungeons/";

export const DUNGEON_PARAMS_CUSTOM_DATA_SOURCE = "dungeongen";
export const DUNGEON_PARAMS_CUSTOM_DATA_NAME = "params";

export interface DungeonGenParams {
    size: string;
    archetype: string;
    symmetry: string;
    water: string;
    pack: string;
    roomsize: string;
    round_rooms: boolean;
    halls: boolean;
    cross: string;
    symmetry_break: string;
    show_numbers: boolean;
    seed: string;
}

export interface DungeonGenStoredData {
    params: DungeonGenParams;
    seed: string;
    gridCells?: { width: number; height: number };
    dungeonMeta?: { imageWidth: number; imageHeight: number; syncSquareSize: number };
}

export async function addDungeonToMap(
    imageUrl: string,
    gridCells: { width: number; height: number },
    position: GlobalPoint = toGP(0, 0),
    options?: {
        imageWidth: number;
        imageHeight: number;
        syncSquareSize: number;
        params: DungeonGenParams;
        seed: string;
    },
): Promise<Asset | undefined> {
    if (!imageUrl.startsWith("/static")) return undefined;

    const floor = floorState.currentFloor.value ?? floorState.reactive.floors[0];
    if (!floor) return undefined;

    const layer = floorSystem.getLayer(floor, LayerName.Map);
    if (!layer) return undefined;

    const gridSize = playerSettingsState.gridSize.value ?? DEFAULT_GRID_SIZE;
    let width: number;
    let height: number;

    const dungeonMeta = options?.imageWidth != null && options?.imageHeight != null && options?.syncSquareSize != null
        ? { imageWidth: options.imageWidth, imageHeight: options.imageHeight, syncSquareSize: options.syncSquareSize }
        : undefined;
    if (dungeonMeta) {
        const scale = gridSize / dungeonMeta.syncSquareSize;
        width = dungeonMeta.imageWidth * scale;
        height = dungeonMeta.imageHeight * scale;
    } else {
        width = gridCells.width * gridSize;
        height = gridCells.height * gridSize;
    }

    const image = document.createElement("img");
    image.src = baseAdjust(imageUrl);

    return new Promise((resolve) => {
        image.addEventListener("load", () => {
            let refPoint = position;
            if (locationSettingsState.raw.useGrid.value) {
                const gridType = locationSettingsState.raw.gridType.value;
                refPoint = snapPointToGrid(position, gridType, {
                    snapDistance: Number.MAX_VALUE,
                })[0];
            }

            const asset = new Asset(
                image,
                refPoint,
                width,
                height,
                { uuid: uuidv4() },
            );

            asset.src = imageUrl;

            asset.setLayer(layer.floor, layer.name);

            accessSystem.addAccess(
                asset.id,
                playerSystem.getCurrentPlayer()!.name,
                { edit: true, movement: true, vision: true },
                UI_SYNC,
            );

            layer.addShape(asset, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);

            const seed = options?.seed ?? "";
            propertiesSystem.setName(asset.id, seed, SERVER_SYNC);

            if (options?.params) {
                const shapeId = getGlobalId(asset.id);
                if (shapeId) {
                    const storedData: DungeonGenStoredData = {
                        params: options.params,
                        seed,
                        gridCells,
                        dungeonMeta: dungeonMeta ?? undefined,
                    };
                    customDataSystem.addElement(
                        {
                            shapeId,
                            source: DUNGEON_PARAMS_CUSTOM_DATA_SOURCE,
                            prefix: "/",
                            name: DUNGEON_PARAMS_CUSTOM_DATA_NAME,
                            kind: "text",
                            value: JSON.stringify(storedData),
                            reference: null,
                            description: null,
                        },
                        true,
                    );
                }
            }

            resolve(asset);
        });
        image.addEventListener("error", () => resolve(undefined));
    });
}

export function isDungeonAsset(src: string | undefined): boolean {
    return (src ?? "").startsWith(DUNGEON_ASSET_SRC_PREFIX);
}

export function hasDungeonData(shapeId: LocalId): boolean {
    const data = customDataSystem.export(shapeId);
    return data.some(
        (el) => el.source === DUNGEON_PARAMS_CUSTOM_DATA_SOURCE && el.name === DUNGEON_PARAMS_CUSTOM_DATA_NAME,
    );
}

export function getDungeonStoredData(shapeId: LocalId): DungeonGenStoredData | null {
    const data = customDataSystem.export(shapeId);
    const el = data.find(
        (e) => e.source === DUNGEON_PARAMS_CUSTOM_DATA_SOURCE && e.name === DUNGEON_PARAMS_CUSTOM_DATA_NAME,
    );
    if (!el || el.kind !== "text" || typeof el.value !== "string") return null;
    try {
        return JSON.parse(el.value) as DungeonGenStoredData;
    } catch {
        return null;
    }
}
