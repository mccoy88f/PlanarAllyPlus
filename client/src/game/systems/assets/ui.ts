import { assetSystem } from "../../../assets";
import { getFolderPath } from "../../../assets/emits";
import type { AssetEntryId } from "../../../assets/models";

import { assetGameState } from "./state";

function openAssetManager(): void {
    assetGameState.mutableReactive.managerOpen = true;
}

export function closeAssetManager(): void {
    if (assetGameState.raw.managerOpen) {
        assetGameState.mutableReactive.managerOpen = false;
        if (assetGameState.raw.picker !== null) {
            assetGameState.raw.picker(null);
        }
    }
}

export function toggleAssetManager(): void {
    if (assetGameState.raw.managerOpen) {
        closeAssetManager();
    } else {
        openAssetManager();
    }
}

export async function pickAsset(): Promise<AssetEntryId | null> {
    openAssetManager();
    return new Promise((resolve) => {
        assetGameState.mutableReactive.picker = resolve;
    });
}

/** Apre il gestore asset, naviga alla cartella che contiene la voce e la seleziona (es. dopo upload da compendio). */
export async function openAssetManagerAfterCompendiumUpload(entryId: AssetEntryId): Promise<void> {
    openAssetManager();
    const path = await getFolderPath(entryId);
    if (path.length < 2) return;
    const parentId = path[path.length - 2]!.id;
    await assetSystem.changeDirectory(parentId);
    assetSystem.clearSelected();
    assetSystem.addSelectedInode(entryId);
}
