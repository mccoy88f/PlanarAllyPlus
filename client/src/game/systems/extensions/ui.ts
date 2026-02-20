import type { LocalId } from "../../../core/id";

import { extensionsState } from "./state";

/** Check if this extension's modal is currently open */
export function isExtensionOpen(ext: { id: string; uiUrl?: string }): boolean {
    if (ext.uiUrl && ext.id) {
        return extensionsState.raw.extensionModalsOpen.some((m) => m.id === ext.id);
    }
    if (ext.id === "dungeongen") return extensionsState.raw.dungeongenModalOpen;
    if (ext.id === "compendium") return extensionsState.raw.compendiumModalOpen;
    if (ext.id === "openrouter") return extensionsState.raw.openrouterModalOpen;
    return false;
}

/** Close this extension's modal. For ambient-music: if minimized, restore; else if playing, minimize; else close. */
export function closeExtension(ext: { id: string; uiUrl?: string }): void {
    if (ext.uiUrl && ext.id) {
        if (extensionsState.raw.extensionModalsOpen.some((m) => m.id === ext.id)) {
            if (ext.id === "ambient-music") {
                if (extensionsState.raw.ambientMusicMinimized) {
                    extensionsState.mutableReactive.ambientMusicMinimized = false;
                } else if (extensionsState.raw.ambientMusicPlaying) {
                    extensionsState.mutableReactive.ambientMusicMinimized = true;
                } else {
                    closeExtensionModal(ext.id);
                }
            } else {
                closeExtensionModal(ext.id);
            }
        }
        return;
    }
    if (ext.id === "dungeongen") closeDungeongenModal();
    else if (ext.id === "compendium") closeCompendiumModal();
    else if (ext.id === "openrouter") closeOpenRouterModal();
}

/** Focus extension modal (bring to front) */
export function focusExtension(modalId: string): void {
    extensionsState.mutableReactive.lastFocusedModal = { type: "extension", id: modalId };
}

/** Focus stack modal (bring to front) - called by modal system */
export function focusStackModal(): void {
    extensionsState.mutableReactive.lastFocusedModal = { type: "stack" };
}

function openExtensionsManager(): void {
    extensionsState.mutableReactive.managerOpen = true;
}

export function closeExtensionsManager(): void {
    extensionsState.mutableReactive.managerOpen = false;
}

export function toggleExtensionsManager(): void {
    if (extensionsState.raw.managerOpen) {
        closeExtensionsManager();
    } else {
        openExtensionsManager();
    }
}

export function openDungeongenModal(): void {
    extensionsState.mutableReactive.dungeongenEditShapeId = undefined;
    extensionsState.mutableReactive.dungeongenModalOpen = true;
    focusExtension("dungeongen");
}

export function openDungeongenModalForEdit(shapeId: LocalId): void {
    extensionsState.mutableReactive.dungeongenEditShapeId = shapeId;
    extensionsState.mutableReactive.dungeongenModalOpen = true;
}

export function closeDungeongenModal(): void {
    extensionsState.mutableReactive.dungeongenModalOpen = false;
    extensionsState.mutableReactive.dungeongenEditShapeId = undefined;
}

export function openDocumentsModal(): void {
    extensionsState.mutableReactive.documentsModalOpen = true;
    focusExtension("documents");
}

export function closeDocumentsModal(): void {
    extensionsState.mutableReactive.documentsModalOpen = false;
}

export function openDocumentsPdfViewer(
    fileHash: string,
    name: string,
    page?: number,
): void {
    extensionsState.mutableReactive.documentsPdfViewer = { fileHash, name, page };
    focusExtension("documents-pdf");
}

export function closeDocumentsPdfViewer(): void {
    extensionsState.mutableReactive.documentsPdfViewer = undefined;
}

export function openCompendiumModal(): void {
    extensionsState.mutableReactive.compendiumModalOpen = true;
    extensionsState.mutableReactive.compendiumOpenItem = undefined;
    focusExtension("compendium");
}

export function openCompendiumModalForItem(
    collectionSlug: string,
    itemSlug: string,
    compendiumSlug?: string,
): void {
    extensionsState.mutableReactive.compendiumOpenItem = {
        compendiumSlug,
        collectionSlug,
        itemSlug,
    };
    extensionsState.mutableReactive.compendiumModalOpen = true;
    focusExtension("compendium");
}

export function closeCompendiumModal(): void {
    extensionsState.mutableReactive.compendiumModalOpen = false;
    extensionsState.mutableReactive.compendiumOpenItem = undefined;
}

export function openOpenRouterModal(): void {
    extensionsState.mutableReactive.openrouterModalOpen = true;
    focusExtension("openrouter");
}

export function closeOpenRouterModal(): void {
    extensionsState.mutableReactive.openrouterModalOpen = false;
}

export function openExtensionModal(ext: {
    id: string;
    name: string;
    folder: string;
    uiUrl: string;
    titleBarColor?: string;
    icon?: string | [string, string];
    openSheetId?: string;
}): void {
    const arr = extensionsState.mutableReactive.extensionModalsOpen;
    if (!arr.some((m) => m.id === ext.id)) {
        arr.push(ext);
    }
    focusExtension(ext.id);
}

export function closeExtensionModal(extId: string): void {
    if (extId === "ambient-music") {
        extensionsState.mutableReactive.ambientMusicMinimized = false;
    }
    extensionsState.mutableReactive.extensionModalsOpen = extensionsState.raw.extensionModalsOpen.filter(
        (m) => m.id !== extId,
    );
}

/** Called when user clicks close on extension modal. For ambient-music when playing: minimize instead. */
export function requestCloseExtensionModal(extId: string): void {
    if (extId === "ambient-music" && extensionsState.raw.ambientMusicPlaying) {
        extensionsState.mutableReactive.ambientMusicMinimized = true;
    } else {
        closeExtensionModal(extId);
    }
}
