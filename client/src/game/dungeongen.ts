import { type GlobalPoint, toGP, addP, Vector } from "../core/geometry";
import { DEFAULT_GRID_SIZE, snapPointToGrid } from "../core/grid";
import { baseAdjust } from "../core/http";
import type { LocalId } from "../core/id";
import { SyncMode, InvalidationMode, SERVER_SYNC, UI_SYNC } from "../core/models/types";
import { uuidv4 } from "../core/utils";

import { getGlobalId } from "./id";
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

export interface DungeonGenStoredData {
    params: DungeonGenParams;
    seed: string;
    gridCells?: { width: number; height: number };
    dungeonMeta?: { imageWidth: number; imageHeight: number; syncSquareSize: number; padding?: number };
    walls?: WallData;
    doors?: DoorData[];
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
        name?: string;
        params?: DungeonGenParams;
        seed: string;
        walls?: WallData;
        doors?: DoorData[];
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
            const shapeName = options?.name ?? seed;
            propertiesSystem.setName(asset.id, shapeName, SERVER_SYNC);

            const walls = options?.walls;
            console.log("DungeonGen - addDungeonToMap walls:", walls);
            console.log("DungeonGen - fowLayer:", fowLayer?.name);

            if (walls && fowLayer) {
                const scale = dungeonMeta ? (gridSize / dungeonMeta.syncSquareSize) : 1;
                const basePadding = dungeonMeta?.padding ?? 50;
                const scaledPadding = basePadding * scale;
                const wallOffset = addP(refPoint, new Vector(scaledPadding, scaledPadding));
                console.log("DungeonGen - wallOffset:", wallOffset);

                // Add wall lines
                for (const line of walls.lines) {
                    const vertices = line.map(v => addP(wallOffset, new Vector(v[0] * gridSize, v[1] * gridSize)));
                    const wallShape = new Polygon(
                        vertices[0]!,
                        vertices.slice(1),
                        { openPolygon: true, lineWidth: [10], uuid: uuidv4() },
                        {
                            blocksMovement: true,
                            blocksVision: VisionBlock.Complete,
                            strokeColour: ["#00ff00"]
                        }
                    );
                    fowLayer.addShape(wallShape, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);
                }
                console.log(`DungeonGen - Added ${walls.lines.length} wall lines to ${fowLayer.name}`);
                fowLayer.invalidate(false);
            }

            const doorData = options?.doors;
            if (doorData && layer) {
                const scale = dungeonMeta ? (gridSize / dungeonMeta.syncSquareSize) : 1;
                const basePadding = dungeonMeta?.padding ?? 50;
                const scaledPadding = basePadding * scale;
                const doorOffset = addP(refPoint, new Vector(scaledPadding, scaledPadding));

                for (const door of doorData) {
                    const center = addP(doorOffset, new Vector((door.x + 0.5) * gridSize, (door.y + 0.5) * gridSize));
                    let vertices: GlobalPoint[] = [];

                    if (door.direction === "north" || door.direction === "south") {
                        // Horizontal door
                        vertices = [
                            addP(center, new Vector(-gridSize * 0.5, 0)),
                            addP(center, new Vector(gridSize * 0.5, 0)),
                        ];
                    } else {
                        // Vertical door
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
                            // strokeColour is not strictly needed as doorSystem will handle it via registerColour
                        }
                    );
                    
                    doorShape.setLayer(layer.floor, layer.name);
                    layer.addShape(doorShape, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);
                    
                    // Make it a door!
                    doorSystem.toggle(doorShape.id, true, SERVER_SYNC);
                    // Default to movement/vision toggle
                    doorSystem.setToggleMode(doorShape.id, "both", SERVER_SYNC);
                    
                    propertiesSystem.setName(doorShape.id, "Door", SERVER_SYNC);
                }
                console.log(`DungeonGen - Added ${doorData.length} doors to ${layer.name}`);
            }

            if (options?.params) {
                const shapeId = getGlobalId(asset.id);
                if (shapeId) {
                    const storedData: DungeonGenStoredData = {
                        params: options.params,
                        seed,
                        gridCells,
                        dungeonMeta: dungeonMeta ?? undefined,
                        walls,
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
