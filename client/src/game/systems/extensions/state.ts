import type { LocalId } from "../../../core/id";

import { buildState } from "../../../core/systems/state";

export interface ExtensionModalData {
    id: string;
    name: string;
    folder: string;
    uiUrl: string;
    titleBarColor?: string;
    icon?: string | [string, string];
    openSheetId?: string;
}

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
    compendiumModalOpen: boolean;
    /** When set, Compendium modal opens and navigates to this item */
    compendiumOpenItem: {
        compendiumSlug?: string;
        collectionSlug: string;
        itemSlug: string;
    } | undefined;
    openrouterModalOpen: boolean;
    /** Last focused modal: extension id or 'stack' (stack uses modalOrder for which one) */
    lastFocusedModal: { type: "extension"; id: string } | { type: "stack" } | null;
    /** Generic extension modals: multiple can be open at once (guida, time-manager, ambient-music, etc.) */
    extensionModalsOpen: ExtensionModalData[];
    /** Ambient music: audio is playing (for speaker icon in menu) */
    ambientMusicPlaying: boolean;
    /** Ambient music: modal minimized (iframe kept alive for background playback) */
    ambientMusicMinimized: boolean;
}

const state = buildState<ReactiveExtensionsState>({
    managerOpen: false,
    extensions: [],
    dungeongenModalOpen: false,
    dungeongenEditShapeId: undefined,
    documentsModalOpen: false,
    documentsPdfViewer: undefined,
    compendiumModalOpen: false,
    compendiumOpenItem: undefined,
    openrouterModalOpen: false,
    lastFocusedModal: null,
    extensionModalsOpen: [],
    ambientMusicPlaying: false,
    ambientMusicMinimized: false,
});

export const extensionsState = {
    ...state,
};
