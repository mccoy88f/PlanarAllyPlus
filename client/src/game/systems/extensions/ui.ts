import type { LocalId } from "../../../core/id";

import { extensionsState } from "./state";

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
}

export function closeDocumentsPdfViewer(): void {
    extensionsState.mutableReactive.documentsPdfViewer = undefined;
}

export function openQuintaedizioneModal(): void {
    extensionsState.mutableReactive.quintaedizioneModalOpen = true;
    extensionsState.mutableReactive.quintaedizioneOpenItem = undefined;
}

export function openQuintaedizioneModalForItem(collectionSlug: string, itemSlug: string): void {
    extensionsState.mutableReactive.quintaedizioneOpenItem = { collectionSlug, itemSlug };
    extensionsState.mutableReactive.quintaedizioneModalOpen = true;
}

export function closeQuintaedizioneModal(): void {
    extensionsState.mutableReactive.quintaedizioneModalOpen = false;
    extensionsState.mutableReactive.quintaedizioneOpenItem = undefined;
}

export function openOpenRouterModal(): void {
    extensionsState.mutableReactive.openrouterModalOpen = true;
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
}): void {
    extensionsState.mutableReactive.extensionModalOpen = ext;
}

export function closeExtensionModal(): void {
    extensionsState.mutableReactive.extensionModalOpen = null;
}
