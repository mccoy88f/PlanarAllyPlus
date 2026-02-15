import type { LocalId } from "../../../core/id";

import { buildState } from "../../../core/systems/state";

export interface ExtensionMeta {
    id: string;
    name: string;
    version: string;
    description?: string;
    folder?: string;
    visibleToPlayers?: boolean;
    uiUrl?: string;
}

interface ReactiveExtensionsState {
    managerOpen: boolean;
    extensions: ExtensionMeta[];
    dungeongenModalOpen: boolean;
    /** When set, DungeonGen modal opens in edit mode for this shape */
    dungeongenEditShapeId: LocalId | undefined;
    documentsModalOpen: boolean;
    /** PDF viewer: which document is being viewed (fileHash, name, optional page) */
    documentsPdfViewer: { fileHash: string; name: string; page?: number } | undefined;
    quintaedizioneModalOpen: boolean;
    /** When set, Quinta Edizione modal opens and navigates to this item */
    quintaedizioneOpenItem: { collectionSlug: string; itemSlug: string } | undefined;
    openrouterModalOpen: boolean;
    /** Generic extension modal: when set, opens modal with iframe from extension uiUrl */
    extensionModalOpen: {
        id: string;
        name: string;
        folder: string;
        uiUrl: string;
        titleBarColor?: string;
        icon?: string | [string, string];
    } | null;
}

const state = buildState<ReactiveExtensionsState>({
    managerOpen: false,
    extensions: [],
    dungeongenModalOpen: false,
    dungeongenEditShapeId: undefined,
    documentsModalOpen: false,
    documentsPdfViewer: undefined,
    quintaedizioneModalOpen: false,
    quintaedizioneOpenItem: undefined,
    openrouterModalOpen: false,
    extensionModalOpen: null,
});

export const extensionsState = {
    ...state,
};
