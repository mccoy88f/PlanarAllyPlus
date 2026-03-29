import type { LocalId } from "../core/id";

import { getGlobalId } from "./id";
import { Asset } from "./shapes/variants/asset";
import { customDataSystem } from "./systems/customData";

/**
 * Metadati serializzati da `AssetEntry.options` (libreria) copiati sui dati personalizzati dello shape.
 * Qualsiasi estensione può leggere lo stesso JSON lato server e usarlo in sessione.
 */
export const ASSET_ENTRY_METADATA_SOURCE = "asset_entry";
export const ASSET_ENTRY_METADATA_NAME = "metadata";

/** Voce legacy MapsGen sui dati personalizzati (aggiunta mappa da modal). */
const DUNGEON_LEGACY_SOURCE = "dungeongen";
const DUNGEON_LEGACY_NAME = "params";

/**
 * Chiavi da non copiare dalla libreria al tavolo: puntano a forme (muri/porte) valide solo nella sessione
 * in cui sono stati creati; sulla nuova mappa quegli ID non esistono.
 */
const SESSION_ONLY_SHAPE_ID_KEYS = ["wallLocalIds", "doorLocalIds"] as const;

/**
 * Rimuove dai metadati JSON gli ID locali di forme (muri/porte) salvati in un’altra sessione.
 * Senza questa pulizia, «Riposiziona muri» cercherebbe di cancellare ID inesistenti o incoerenti.
 */
export function stripSessionOnlyShapeIdsFromOptionsJson(optionsJson: string): string {
    const t = optionsJson.trim();
    if (!t) return t;
    try {
        const o = JSON.parse(t) as unknown;
        if (o && typeof o === "object" && !Array.isArray(o)) {
            const copy = { ...(o as Record<string, unknown>) };
            for (const k of SESSION_ONLY_SHAPE_ID_KEYS) {
                delete copy[k];
            }
            return JSON.stringify(copy);
        }
    } catch {
        return optionsJson;
    }
    return optionsJson;
}

/**
 * Copia `AssetEntry.options` (stringa JSON dal server) nei dati personalizzati dello shape.
 * Usabile da qualsiasi estensione che salva metadati sulla riga asset in libreria.
 */
export function syncAssetEntryMetadataToCustomData(asset: Asset, optionsJson: string | null | undefined): void {
    if (!optionsJson?.trim()) return;
    const cleaned = stripSessionOnlyShapeIdsFromOptionsJson(optionsJson);
    const shapeId = getGlobalId(asset.id);
    if (!shapeId) return;
    customDataSystem.addElement(
        {
            shapeId,
            source: ASSET_ENTRY_METADATA_SOURCE,
            prefix: "/",
            name: ASSET_ENTRY_METADATA_NAME,
            kind: "text",
            value: cleaned,
            reference: null,
            description: null,
        },
        true,
    );
}

/** Testo grezzo `asset_entry`/`metadata` sullo shape, se presente. */
export function getAssetEntryMetadataText(shapeId: LocalId): string | null {
    const data = customDataSystem.export(shapeId);
    const el = data.find(
        (e) => e.source === ASSET_ENTRY_METADATA_SOURCE && e.name === ASSET_ENTRY_METADATA_NAME,
    );
    if (!el || el.kind !== "text" || typeof el.value !== "string") return null;
    return el.value;
}

/**
 * Aggiorna il blob metadati (prima voce MapsGen legacy `dungeongen`/`params`, altrimenti `asset_entry`/`metadata`).
 */
export function updateShapeMetadataCustomDataValue(shapeId: LocalId, newValue: string): boolean {
    const globalId = getGlobalId(shapeId);
    if (!globalId) return false;

    const legacyId = customDataSystem.getElementId({
        shapeId: globalId,
        source: DUNGEON_LEGACY_SOURCE,
        prefix: "/",
        name: DUNGEON_LEGACY_NAME,
    });
    if (legacyId !== undefined) {
        customDataSystem.updateValue(shapeId, legacyId, newValue, true);
        return true;
    }

    const entryId = customDataSystem.getElementId({
        shapeId: globalId,
        source: ASSET_ENTRY_METADATA_SOURCE,
        prefix: "/",
        name: ASSET_ENTRY_METADATA_NAME,
    });
    if (entryId !== undefined) {
        customDataSystem.updateValue(shapeId, entryId, newValue, true);
        return true;
    }

    return false;
}
