import type { AssetId } from "../assets/models";
import { assetState } from "../assets/state";
import { type GlobalPoint, toGP, addP, Vector } from "../core/geometry";
import { DEFAULT_GRID_SIZE, snapPointToGrid } from "../core/grid";
import { baseAdjust } from "../core/http";
import type { LocalId } from "../core/id";
import { SyncMode, InvalidationMode, SERVER_SYNC, UI_SYNC } from "../core/models/types";
import { uuidv4 } from "../core/utils";

import { getAssetEntryMetadataText, updateShapeMetadataCustomDataValue } from "./assetEntryMetadata";
import { getGlobalId, getShape } from "./id";
import type { ILayer } from "./interfaces/layer";
import { Asset } from "./shapes/variants/asset";
import { Polygon } from "./shapes/variants/polygon";
import { customDataSystem } from "./systems/customData";
import { accessSystem } from "./systems/access";
import { floorState } from "./systems/floors/state";
import { floorSystem } from "./systems/floors";
import { LayerName } from "./models/floor";
import { playerSystem } from "./systems/players";
import { propertiesSystem } from "./systems/properties";
import { locationSettingsState } from "./systems/settings/location/state";
import { playerSettingsState } from "./systems/settings/players/state";
import { VisionBlock } from "./systems/properties/types";
import { doorSystem } from "./systems/logic/door";

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

export interface DoorData {
    x: number;
    y: number;
    direction: string;
    type: string;
}

export interface WallData {
    lines: [[number, number], [number, number]][];
}

export interface BuildingGenParams {
    archetype: string; // "house" | "shop" | "tavern" | "inn"
    footprint: string; // "rectangle" | "l_shape" | "cross" | "offset"
    layout:    string; // "open_plan" | "corridor"
    size:      string; // "small" | "medium" | "large" | "xlarge"
    seed:      string;
}

export interface DungeonGenStoredData {
    params: DungeonGenParams | BuildingGenParams;
    seed: string;
    gridCells?: { width: number; height: number };
    dungeonMeta?: { imageWidth: number; imageHeight: number; syncSquareSize: number; padding?: number };
    walls?: WallData;
    doors?: DoorData[];
    /** ID forme muro/porta create da MapsGen (per rimuoverle al riposizionamento) */
    wallLocalIds?: LocalId[];
    doorLocalIds?: LocalId[];
}

/** Estrae il file hash da un URL `/static/assets/aa/bb/...`. */
export function parseFileHashFromStaticAssetUrl(url: string): string | undefined {
    const m = url.match(/\/static\/assets\/[0-9a-f]{2}\/[0-9a-f]{2}\/([0-9a-f]{40})(?:\?|$)/i);
    return m?.[1];
}

function resolveAssetModelIdFromHash(fileHash: string, explicit?: AssetId | null): AssetId | undefined {
    if (explicit !== undefined && explicit !== null) return explicit;
    for (const a of assetState.reactive.idMap.values()) {
        if (a.fileHash === fileHash && a.assetId != null) return a.assetId;
    }
    return undefined;
}

/** Interpreta asset_entry.options come metadati MapsGen (stesso JSON dei custom data). */
export function parseDungeonStoredDataFromEntryOptions(
    optionsJson: string | null | undefined,
): DungeonGenStoredData | null {
    if (!optionsJson) return null;
    try {
        const o = JSON.parse(optionsJson) as unknown;
        if (o && typeof o === "object" && "params" in o && "seed" in o) {
            return o as DungeonGenStoredData;
        }
    } catch {
        /* ignore */
    }
    return null;
}

function placeDungeonWallsAndDoors(
    refPoint: GlobalPoint,
    gridSize: number,
    dungeonMeta: { imageWidth: number; imageHeight: number; syncSquareSize: number; padding?: number } | undefined,
    wallPadding: number | undefined,
    walls: WallData | undefined,
    doors: DoorData[] | undefined,
    fowLayer: ILayer | undefined,
    mapLayer: ILayer,
): { wallIds: LocalId[]; doorIds: LocalId[] } {
    const wallIds: LocalId[] = [];
    const doorIds: LocalId[] = [];

    if (walls && fowLayer) {
        const scale = dungeonMeta ? gridSize / dungeonMeta.syncSquareSize : 1;
        const basePadding = wallPadding ?? dungeonMeta?.padding ?? 50;
        const scaledPadding = basePadding * scale;
        const wallOffset = addP(refPoint, new Vector(scaledPadding, scaledPadding));

        for (const line of walls.lines) {
            const vertices = line.map(v => addP(wallOffset, new Vector(v[0] * gridSize, v[1] * gridSize)));
            const wallShape = new Polygon(
                vertices[0]!,
                vertices.slice(1),
                { openPolygon: true, lineWidth: [10], uuid: uuidv4() },
                {
                    blocksMovement: true,
                    blocksVision: VisionBlock.Complete,
                    strokeColour: ["#00ff00"],
                },
            );
            fowLayer.addShape(wallShape, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);
            wallIds.push(wallShape.id);
        }
        fowLayer.invalidate(false);
    }

    if (doors && mapLayer) {
        const scale = dungeonMeta ? gridSize / dungeonMeta.syncSquareSize : 1;
        const basePadding = wallPadding ?? dungeonMeta?.padding ?? 50;
        const scaledPadding = basePadding * scale;
        const doorOffset = addP(refPoint, new Vector(scaledPadding, scaledPadding));

        for (const door of doors) {
            const center = addP(doorOffset, new Vector((door.x + 0.5) * gridSize, (door.y + 0.5) * gridSize));
            let vertices: GlobalPoint[] = [];

            if (door.direction === "north" || door.direction === "south") {
                vertices = [
                    addP(center, new Vector(-gridSize * 0.5, 0)),
                    addP(center, new Vector(gridSize * 0.5, 0)),
                ];
            } else {
                vertices = [
                    addP(center, new Vector(0, -gridSize * 0.5)),
                    addP(center, new Vector(0, gridSize * 0.5)),
                ];
            }

            const doorShape = new Polygon(
                vertices[0]!,
                vertices.slice(1),
                { openPolygon: true, lineWidth: [10], uuid: uuidv4() },
                {
                    blocksMovement: true,
                    blocksVision: VisionBlock.Complete,
                },
            );

            doorShape.setLayer(mapLayer.floor, mapLayer.name);
            mapLayer.addShape(doorShape, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);

            doorSystem.toggle(doorShape.id, true, SERVER_SYNC);
            doorSystem.setToggleMode(doorShape.id, "both", SERVER_SYNC);

            propertiesSystem.setName(doorShape.id, "Door", SERVER_SYNC);
            doorIds.push(doorShape.id);
        }
    }

    return { wallIds, doorIds };
}

export async function addDungeonToMap(
    imageUrl: string,
    gridCells: { width: number; height: number },
    position: GlobalPoint = toGP(0, 0),
    options?: {
        imageWidth?: number;
        imageHeight?: number;
        syncSquareSize?: number;
        padding?: number;
        wallPadding?: number;
        name?: string;
        params?: DungeonGenParams | BuildingGenParams;
        seed: string;
        walls?: WallData;
        doors?: DoorData[];
        /** ID riga `asset` (file) lato server — obbligatorio se deducibile da hash / commit MapsGen */
        assetModelId?: AssetId | null;
        fileHash?: string;
    },
): Promise<Asset | undefined> {
    if (!imageUrl.startsWith("/static") && !imageUrl.startsWith("data:") && !imageUrl.startsWith("blob:")) return undefined;

    const floor = floorState.currentFloor.value ?? floorState.reactive.floors[0];
    if (!floor) return undefined;

    const layer = floorSystem.getLayer(floor, LayerName.Map);
    if (!layer) return undefined;

    const fowLayer = floorSystem.getLayer(floor, LayerName.Lighting);

    const gridSize = playerSettingsState.gridSize.value ?? DEFAULT_GRID_SIZE;
    let width: number;
    let height: number;

    const dungeonMeta = options?.imageWidth != null && options?.imageHeight != null && options?.syncSquareSize != null
        ? { imageWidth: options.imageWidth, imageHeight: options.imageHeight, syncSquareSize: options.syncSquareSize, padding: options.padding }
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

            const fileHash =
                options?.fileHash ??
                parseFileHashFromStaticAssetUrl(imageUrl);

            if (fileHash === undefined) {
                console.warn("addDungeonToMap: cannot resolve file hash for", imageUrl);
                resolve(undefined);
                return;
            }

            const assetModelId = resolveAssetModelIdFromHash(fileHash, options?.assetModelId ?? null);
            if (assetModelId === undefined) {
                console.warn("addDungeonToMap: cannot resolve asset model id for", imageUrl);
                resolve(undefined);
                return;
            }

            const asset = new Asset(
                image,
                refPoint,
                width,
                height,
                assetModelId,
                fileHash,
                { uuid: uuidv4() },
            );

            (asset as Asset & { src?: string }).src = imageUrl;

            asset.setLayer(layer.floor, layer.name);

            accessSystem.addAccess(
                asset.id,
                playerSystem.getCurrentPlayer()!.name,
                { edit: true, movement: true, vision: true },
                UI_SYNC,
            );

            layer.addShape(asset, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);

            const seed = options?.seed ?? "";
            const shapeName = options?.name ?? seed;
            propertiesSystem.setName(asset.id, shapeName, SERVER_SYNC);

            const walls = options?.walls;
            const { wallIds, doorIds } = placeDungeonWallsAndDoors(
                refPoint,
                gridSize,
                dungeonMeta,
                options?.wallPadding,
                walls,
                options?.doors,
                fowLayer,
                layer,
            );

            if (options?.params) {
                const shapeId = getGlobalId(asset.id);
                if (shapeId) {
                    const storedData: DungeonGenStoredData = {
                        params: options.params,
                        seed,
                        gridCells,
                        dungeonMeta: dungeonMeta ?? undefined,
                        walls,
                        doors: options?.doors,
                        wallLocalIds: wallIds.length > 0 ? wallIds : undefined,
                        doorLocalIds: doorIds.length > 0 ? doorIds : undefined,
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

/**
 * Rimuove muri/porte MapsGen precedenti (se tracciati), li ricrea in base a refPoint attuale dell’asset.
 */
export function repositionMapsGenWalls(shapeId: LocalId): boolean {
    const shape = getShape(shapeId);
    if (!shape || shape.type !== "assetrect") return false;

    const stored = getDungeonStoredData(shapeId);
    if (!stored) return false;

    const hasWalls = (stored.walls?.lines?.length ?? 0) > 0;
    const hasDoors = (stored.doors?.length ?? 0) > 0;
    if (!hasWalls && !hasDoors) return false;

    for (const lid of [...(stored.wallLocalIds ?? []), ...(stored.doorLocalIds ?? [])]) {
        const s = getShape(lid);
        if (s?.layer) {
            s.layer.removeShape(s, { sync: SyncMode.FULL_SYNC, recalculate: true, dropShapeId: true });
        }
    }

    const floor = floorState.currentFloor.value ?? floorState.reactive.floors[0];
    if (!floor) return false;
    const mapLayer = floorSystem.getLayer(floor, LayerName.Map);
    const fowLayer = floorSystem.getLayer(floor, LayerName.Lighting);
    if (!mapLayer) return false;

    const gridSize = playerSettingsState.gridSize.value ?? DEFAULT_GRID_SIZE;
    const refPoint = (shape as Asset).refPoint;

    const { wallIds, doorIds } = placeDungeonWallsAndDoors(
        refPoint,
        gridSize,
        stored.dungeonMeta,
        undefined,
        stored.walls,
        stored.doors,
        fowLayer,
        mapLayer,
    );

    const updated: DungeonGenStoredData = {
        ...stored,
        wallLocalIds: wallIds.length > 0 ? wallIds : undefined,
        doorLocalIds: doorIds.length > 0 ? doorIds : undefined,
    };

    return updateShapeMetadataCustomDataValue(shapeId, JSON.stringify(updated));
}

export function hasDungeonData(shapeId: LocalId): boolean {
    const data = customDataSystem.export(shapeId);
    if (
        data.some(
            (el) => el.source === DUNGEON_PARAMS_CUSTOM_DATA_SOURCE && el.name === DUNGEON_PARAMS_CUSTOM_DATA_NAME,
        )
    ) {
        return true;
    }
    return getDungeonStoredData(shapeId) !== null;
}

export function isDungeonAsset(src: string | undefined, shapeId?: LocalId): boolean {
    if ((src ?? "").startsWith(DUNGEON_ASSET_SRC_PREFIX)) return true;
    if (shapeId !== undefined && hasDungeonData(shapeId)) return true;
    return false;
}

export function getDungeonStoredData(shapeId: LocalId): DungeonGenStoredData | null {
    const data = customDataSystem.export(shapeId);
    const legacy = data.find(
        (e) => e.source === DUNGEON_PARAMS_CUSTOM_DATA_SOURCE && e.name === DUNGEON_PARAMS_CUSTOM_DATA_NAME,
    );
    if (legacy?.kind === "text" && typeof legacy.value === "string") {
        try {
            return JSON.parse(legacy.value) as DungeonGenStoredData;
        } catch {
            /* fall through */
        }
    }

    const raw = getAssetEntryMetadataText(shapeId);
    if (!raw) return null;
    try {
        const o = JSON.parse(raw) as unknown;
        if (o && typeof o === "object" && "params" in o && "seed" in o) {
            return o as DungeonGenStoredData;
        }
    } catch {
        return null;
    }
    return null;
}
