import { baseAdjust } from "../core/http";
import { coreStore } from "../store/core";

import type { AssetEntryId } from "./models";
import { assetState } from "./state";

/** Estensione dal nome file (ultimo segmento dopo il punto). */
export function extensionFromAssetName(name: string): string {
    const i = name.lastIndexOf(".");
    if (i <= 0 || i >= name.length - 1) return "";
    return name.slice(i + 1).toLowerCase();
}

const AUDIO_EXTENSIONS = new Set(["mp3", "ogg", "wav", "m4a", "aac", "flac", "weba", "opus"]);

const VIDEO_EXTENSIONS = new Set(["mp4", "mov", "mkv", "avi", "ogv", "m4v", "wmv", "webm"]);

const RASTER_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "gif", "bmp", "svg", "ico"]);

/**
 * Il server genera miniature solo per contenuti che PIL/PDF possono aprire (immagini, PDF).
 * Audio/video non hanno thumb: non ha senso richiedere /static/thumbnails/...
 */
export function serverCanGenerateThumbnailForAssetName(name: string): boolean {
    const ext = extensionFromAssetName(name);
    if (!ext) return true;
    if (AUDIO_EXTENSIONS.has(ext) || VIDEO_EXTENSIONS.has(ext)) return false;
    return true;
}

/**
 * Dopo un fallimento thumb, l'URL /static/assets/{hash} è un'immagine solo per questi tipi.
 */
export function rawAssetUrlWorksAsImageTag(name: string): boolean {
    const ext = extensionFromAssetName(name);
    if (!ext) return false;
    return RASTER_IMAGE_EXTENSIONS.has(ext);
}

export type AssetThumbPlaceholderIcon = "music" | "video" | "file";

export function placeholderIconForNonImageAsset(name: string): AssetThumbPlaceholderIcon {
    const ext = extensionFromAssetName(name);
    if (ext && AUDIO_EXTENSIONS.has(ext)) return "music";
    if (ext && VIDEO_EXTENSIONS.has(ext)) return "video";
    return "file";
}

export function getImageSrcFromAssetId(file: AssetEntryId, options?: { thumbnailFormat?: string }): string {
    const fileHash = assetState.raw.idMap.get(file)!.fileHash ?? "";
    return getImageSrcFromHash(fileHash, options);
}

export function getImageSrcFromHash(
    fileHash: string,
    options?: { addBaseUrl?: boolean; thumbnailFormat?: string },
): string {
    const hashPath = `${fileHash.slice(0, 2)}/${fileHash.slice(2, 4)}/${fileHash}`;
    const assetUrlBase = coreStore.state.assetUrlBase;

    let suffix = hashPath;
    if (options?.thumbnailFormat !== undefined) {
        suffix = `${suffix}.thumb.${options.thumbnailFormat}`;
    }

    if (assetUrlBase !== null) {
        return `${assetUrlBase}/${suffix}`;
    }

    const base = options?.thumbnailFormat !== undefined ? "/static/thumbnails" : "/static/assets";
    const path = `${base}/${suffix}`;
    return (options?.addBaseUrl ?? true) ? baseAdjust(path) : path;
}
