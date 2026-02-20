import { baseAdjust } from "../core/http";

import type { AssetId } from "./models";
import { assetState } from "./state";

export function getImageSrcFromAssetId(
    file: AssetId,
    options?: { addBaseUrl?: boolean; thumbnailFormat?: string },
): string {
    const fileHash = assetState.raw.idMap.get(file)!.fileHash ?? "";
    return getImageSrcFromHash(fileHash, options);
}

export function getImageSrcFromHash(
    fileHash: string,
    options?: { addBaseUrl?: boolean; thumbnailFormat?: string },
): string {
    const hashPath = `${fileHash.slice(0, 2)}/${fileHash.slice(2, 4)}/${fileHash}`;
    const path =
        options?.thumbnailFormat !== undefined
            ? `/static/thumbnails/${hashPath}.thumb.${options.thumbnailFormat}`
            : `/static/assets/${hashPath}`;
    return (options?.addBaseUrl ?? true) ? baseAdjust(path) : path;
}
