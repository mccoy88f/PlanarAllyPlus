"""Character Sheet extension - D&D 5e in formato D&D Beyond."""

import copy
import datetime
import json
import re
import uuid

from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.character import Character
from ....db.models.user_options import UserOptions
from ....db.models.player_room import PlayerRoom
from ....db.models.room import Room
from ....db.models.user import User
from ....models.role import Role
from ....utils import DATA_DIR, get_asset_hash_subpath

from .dndbeyond_adapter import migrate_old_to_beyond
from .dndbeyond_schema import empty_character, get_character_name

SHEETS_FILE = DATA_DIR / "character_sheets.json"
DEFAULTS_FILE = DATA_DIR / "character_sheet_defaults.json"


def _load_sheets() -> dict:
    if not SHEETS_FILE.exists():
        return {"sheets": {}}
    try:
        with open(SHEETS_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data.get("sheets"), dict) else {"sheets": {}}
    except (json.JSONDecodeError, OSError):
        return {"sheets": {}}


def _save_sheets(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if "sheets" not in data:
        data = {"sheets": data}
    with open(SHEETS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_defaults() -> dict:
    if not DEFAULTS_FILE.exists():
        return {}
    try:
        with open(DEFAULTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_defaults(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DEFAULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_room(creator_name: str, room_name: str) -> Room | None:
    creator = User.get_or_none(User.name == creator_name)
    if not creator:
        return None
    return Room.get_or_none(Room.creator == creator, Room.name == room_name)


def _can_edit_character(user: User, character: Character, is_dm: bool) -> bool:
    if is_dm:
        return True
    return character.owner_id == user.id


def _get_characters_for_room(room: Room, user: User, is_dm: bool) -> list[Character]:
    characters = Character.select().where(Character.campaign == room)
    if not is_dm:
        characters = characters.where(Character.owner == user)
    return list(characters)


async def list_all(request: web.Request) -> web.Response:
    """List all sheets + characters. Sheets can be standalone or linked to a character."""
    user = await get_authorized_user(request)
    creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="room_creator and room_name required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    is_dm = pr.role == Role.DM
    characters = _get_characters_for_room(room, user, is_dm)
    char_by_id = {c.id: c for c in characters}

    data = _load_sheets()
    sheets_dict = data.get("sheets", {})
    defaults = _load_defaults()
    default_key = f"{user.id}_{room.id}"
    default_sheet_id = defaults.get(default_key)

    # Filter sheets: owner must match; for players: own OR visibleToPlayers
    result_sheets = []
    needs_save = False
    for sheet_id, rec in sheets_dict.items():
        if rec.get("roomId") != room.id:
            continue
        owner_id = rec.get("ownerId")
        visible_to_players = rec.get("visibleToPlayers", False)
        if not is_dm and owner_id != user.id and not visible_to_players:
            continue
        char_id = rec.get("characterId")
        char = char_by_id.get(char_id) if char_id else None
        can_edit = is_dm or owner_id == user.id
        char_name = char.name if char else None
        sheet_data = rec.get("data") or {}
        migrated = migrate_old_to_beyond(sheet_data)
        if migrated:
            rec["data"] = migrated
            rec["name"] = get_character_name(migrated)
            rec["updatedAt"] = datetime.datetime.utcnow().isoformat()
            needs_save = True
        name = rec.get("name") or get_character_name(sheet_data) or (char_name or "")
        result_sheets.append({
            "id": sheet_id,
            "name": name,
            "characterId": char_id,
            "characterName": char_name,
            "canEdit": can_edit,
            "isDefault": default_sheet_id == sheet_id,
            "visibleToPlayers": visible_to_players,
            "canToggleVisibility": is_dm or owner_id == user.id,
        })
    if needs_save:
        _save_sheets(data)

    result_sheets.sort(key=lambda s: (s.get("name") or "").lower())

    return web.json_response({
        "sheets": result_sheets,
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "hasSheet": any(s["characterId"] == c.id for s in result_sheets),
                "canEdit": _can_edit_character(user, c, is_dm),
            }
            for c in characters
        ],
        "defaultSheetId": default_sheet_id,
    })


async def get_sheet(request: web.Request) -> web.Response:
    """Get a sheet by id."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="room_creator and room_name required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    rec = data.get("sheets", {}).get(sheet_id)
    if not rec:
        return web.HTTPNotFound(text="Sheet not found")
    if rec.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    owner_id = rec.get("ownerId")
    visible_to_players = rec.get("visibleToPlayers", False)
    if pr.role != Role.DM and owner_id != user.id and not visible_to_players:
        return web.HTTPForbidden(text="Cannot access this sheet")

    sheet_data = rec.get("data") or {}
    migrated = migrate_old_to_beyond(sheet_data)
    if migrated:
        rec["data"] = migrated
        rec["name"] = get_character_name(migrated)
        rec["updatedAt"] = datetime.datetime.utcnow().isoformat()
        _save_sheets(data)
        sheet_data = migrated

    return web.json_response({
        "sheet": sheet_data,
        "name": rec.get("name", ""),
        "characterId": rec.get("characterId"),
        "characterName": None,
    })


def _unwrap_sheet_overlay(data: dict) -> dict:
    """Unwrap common AI/export wrappers (e.g. {"character": {...}})."""
    if not data or not isinstance(data, dict):
        return data
    # D&D Beyond export format or AI wrapping
    for key in ("character", "data", "characterData"):
        inner = data.get(key)
        if isinstance(inner, dict) and ("name" in inner or "classes" in inner):
            return inner
    return data


def _clean_spell_arrays(sheet_data: dict) -> None:
    """Rimuove oggetti vuoti dagli array incantesimi in dndsheets (evita slot vuoti in export)."""
    ds = sheet_data.get("dndsheets") or {}
    for key in ("cantrips", "lvl1Spells", "lvl2Spells", "lvl3Spells", "lvl4Spells",
                "lvl5Spells", "lvl6Spells", "lvl7Spells", "lvl8Spells", "lvl9Spells"):
        arr = ds.get(key)
        if isinstance(arr, list):
            cleaned = [el for el in arr if isinstance(el, dict) and (el.get("name") or "").strip()]
            ds[key] = cleaned


def _normalize_inventory(items: list) -> list:
    """Converte inventory da array di stringhe (es. AI) al formato atteso {definition:{name}, quantity}."""
    out = []
    for it in items or []:
        if isinstance(it, dict):
            defn = it.get("definition")
            iname = (defn or {}).get("name") if isinstance(defn, dict) else it.get("name")
            if iname:
                qty_raw = it.get("quantity") if "quantity" in it else it.get("amount", 1)
                qty = int(qty_raw) if isinstance(qty_raw, (int, float)) else 1
                out.append({"definition": {"name": str(iname)}, "quantity": max(1, qty)})
            continue
        s = str(it).strip()
        if not s:
            continue
        # "Handaxe (2)" o "Greataxe x2" o "Item x 2"
        m = re.match(r"^(.+?)\s*x\s*(\d+)\s*$", s, re.IGNORECASE)
        if not m:
            m = re.match(r"^(.+?)\s*\(\s*(\d+)\s*\)\s*$", s)
        if m:
            name = m.group(1).strip()
            qty = int(m.group(2)) or 1
        else:
            name = s
            qty = 1
        out.append({"definition": {"name": name}, "quantity": qty})
    return out


def _merge_sheet_data(base: dict, overlay: dict) -> dict:
    """Merge overlay into base (shallow). Only include keys that exist in base or are safe."""
    overlay = _unwrap_sheet_overlay(overlay)
    safe_keys = {
        "name", "classes", "race", "background", "alignmentId", "currentXp", "inspiration",
        "baseHitPoints", "currentHitPoints", "temporaryHitPoints", "stats", "bonusStats", "overrideStats",
        "traits", "notes", "currencies", "inventory", "planarally", "modifiers", "feats",
        "age", "size", "height", "weight", "eyes", "hair", "skin", "faith", "dndsheets",
    }
    result = copy.deepcopy(base)
    for k, v in overlay.items():
        if k.startswith("_") or k not in safe_keys:
            continue
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            for sk, sv in v.items():
                if not sk.startswith("_"):
                    result.setdefault(k, {})[sk] = sv
        else:
            result[k] = v
    # Assicura che il nome sia sia a livello top che in dndsheets (l'UI usa entrambi)
    name_val = (result.get("name") or "").strip()
    if not name_val:
        ds = result.get("dndsheets") or {}
        name_val = (ds.get("name") or "").strip()
    if name_val:
        result["name"] = name_val
        result.setdefault("dndsheets", {})["name"] = name_val
    # Normalizza inventory se è array di stringhe (output AI)
    inv = result.get("inventory")
    if isinstance(inv, list) and inv:
        result["inventory"] = _normalize_inventory(inv)
    # Normalizza incantesimi in dndsheets: l'UI si aspetta {name: string}[], non string[]
    ds = result.get("dndsheets") or {}
    for key in ("cantrips", "lvl1Spells", "lvl2Spells", "lvl3Spells", "lvl4Spells",
                "lvl5Spells", "lvl6Spells", "lvl7Spells", "lvl8Spells", "lvl9Spells"):
        arr = ds.get(key)
        if isinstance(arr, list) and arr:
            normalized = []
            for el in arr:
                if isinstance(el, dict) and el.get("name"):
                    normalized.append(el)
                elif isinstance(el, str) and el.strip():
                    normalized.append({"name": el.strip()})
            if normalized:
                result.setdefault("dndsheets", {})[key] = normalized
    # Propaga campi profilo da dndsheets a top-level (per export D&D Beyond)
    ds = result.get("dndsheets") or {}
    for top_key in ("age", "height", "weight", "eyes", "hair", "skin"):
        if not (result.get(top_key) or "").strip() and (ds.get(top_key) or "").strip():
            result[top_key] = (ds.get(top_key) or "").strip()
    return result


def _default_new_character_name(user: User) -> str:
    """Nome predefinito per scheda nuova, in base alla lingua utente."""
    try:
        opts = UserOptions.get_by_id(user.default_options)
        lang = (opts.openrouter_default_language or "it").strip().lower()
    except Exception:
        lang = "it"
    return "Nuovo personaggio" if lang == "it" else "New character"


async def create_sheet(request: web.Request) -> web.Response:
    """Create a new standalone sheet (no character linked). Optionally import sheet data from JSON."""
    user = await get_authorized_user(request)
    body = await request.json()
    creator = (body.get("roomCreator") or request.query.get("room_creator") or "").strip()
    room_name = (body.get("roomName") or request.query.get("room_name") or "").strip()
    name = (body.get("name") or "").strip()
    sheet_overlay = body.get("sheet")
    if not creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    sheets = data.setdefault("sheets", {})
    sheet_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    sheet_data = empty_character()
    if isinstance(sheet_overlay, dict):
        sheet_data = _merge_sheet_data(sheet_data, sheet_overlay)
    _clean_spell_arrays(sheet_data)
    final_name = name or get_character_name(sheet_data) or _default_new_character_name(user)
    sheet_data["name"] = final_name

    sheets[sheet_id] = {
        "ownerId": user.id,
        "roomId": room.id,
        "characterId": None,
        "name": final_name,
        "data": sheet_data,
        "createdAt": now,
        "updatedAt": now,
    }
    _save_sheets(data)
    return web.json_response({"ok": True, "sheetId": sheet_id})


async def update_sheet(request: web.Request) -> web.Response:
    """Update a sheet."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    body = await request.json()
    creator = (body.get("roomCreator") or request.query.get("room_creator") or "").strip()
    room_name = (body.get("roomName") or request.query.get("room_name") or "").strip()
    sheet_data = body.get("sheet")
    if not creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName required")
    if sheet_data is None:
        return web.HTTPBadRequest(text="sheet data required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    rec = data.get("sheets", {}).get(sheet_id)
    if not rec:
        return web.HTTPNotFound(text="Sheet not found")
    if rec.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and rec.get("ownerId") != user.id:
        return web.HTTPForbidden(text="Cannot edit this sheet")

    now = datetime.datetime.utcnow().isoformat()
    migrated = migrate_old_to_beyond(sheet_data)
    if migrated:
        sheet_data = migrated
    _clean_spell_arrays(sheet_data)
    rec["data"] = sheet_data
    rec["updatedAt"] = now
    rec["name"] = get_character_name(sheet_data)
    _save_sheets(data)
    return web.json_response({"ok": True})


async def delete_sheet(request: web.Request) -> web.Response:
    """Delete a sheet."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="room_creator and room_name required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    rec = data.get("sheets", {}).get(sheet_id)
    if not rec:
        return web.json_response({"ok": True})  # already gone
    if rec.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and rec.get("ownerId") != user.id:
        return web.HTTPForbidden(text="Cannot delete this sheet")

    del data["sheets"][sheet_id]
    _save_sheets(data)

    defaults = _load_defaults()
    default_key = f"{user.id}_{room.id}"
    if defaults.get(default_key) == sheet_id:
        del defaults[default_key]
        _save_defaults(defaults)
    return web.json_response({"ok": True})


async def duplicate_sheet(request: web.Request) -> web.Response:
    """Duplicate a sheet (creates new standalone sheet with same data)."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    body = await request.json()
    creator = (body.get("roomCreator") or request.query.get("room_creator") or "").strip()
    room_name = (body.get("roomName") or request.query.get("room_name") or "").strip()
    new_name = (body.get("newName") or "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    src = data.get("sheets", {}).get(sheet_id)
    if not src:
        return web.HTTPNotFound(text="Sheet not found")
    if src.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and src.get("ownerId") != user.id:
        return web.HTTPForbidden(text="Cannot duplicate this sheet")

    new_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    sheet_data = copy.deepcopy(src.get("data") or empty_character())
    migrated = migrate_old_to_beyond(sheet_data)
    if migrated:
        sheet_data = migrated
    name = new_name or (src.get("name") or "Copy")
    sheet_data["name"] = name

    data["sheets"][new_id] = {
        "ownerId": user.id,
        "roomId": room.id,
        "characterId": None,
        "name": name,
        "data": sheet_data,
        "createdAt": now,
        "updatedAt": now,
    }
    _save_sheets(data)
    return web.json_response({"ok": True, "sheetId": new_id})


async def associate_sheet(request: web.Request) -> web.Response:
    """Associate a sheet to a character. One sheet per character."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    body = await request.json()
    character_id = body.get("characterId")
    creator = (body.get("roomCreator") or "").strip()
    room_name = (body.get("roomName") or "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName required")
    if character_id is None:
        return web.HTTPBadRequest(text="characterId required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    try:
        char = Character.get_by_id(character_id)
    except Character.DoesNotExist:
        return web.HTTPNotFound(text="Character not found")
    if char.campaign_id != room.id:
        return web.HTTPNotFound(text="Character not in this room")
    if not _can_edit_character(user, char, pr.role == Role.DM):
        return web.HTTPForbidden(text="Cannot associate to this character")

    data = _load_sheets()
    rec = data.get("sheets", {}).get(sheet_id)
    if not rec:
        return web.HTTPNotFound(text="Sheet not found")
    if rec.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and rec.get("ownerId") != user.id:
        return web.HTTPForbidden(text="Cannot use this sheet")

    # Check no other sheet is linked to this character
    for sid, r in data.get("sheets", {}).items():
        if r.get("characterId") == char.id and sid != sheet_id:
            return web.HTTPBadRequest(text="Character already has a sheet linked")

    rec["characterId"] = char.id
    rec["updatedAt"] = datetime.datetime.utcnow().isoformat()
    # Set sheet appearance from character's asset image
    sheet_data = rec.get("data") or {}
    ds = sheet_data.get("dndsheets") or {}
    if char.asset and char.asset.file_hash:
        app_url = f"/static/assets/{get_asset_hash_subpath(char.asset.file_hash).as_posix()}"
        ds["appearance"] = app_url
    else:
        ds.pop("appearance", None)
    sheet_data["dndsheets"] = ds
    rec["data"] = sheet_data
    _save_sheets(data)
    return web.json_response({"ok": True, "appearanceUrl": ds.get("appearance")})


async def dissociate_sheet(request: web.Request) -> web.Response:
    """Remove association between sheet and character."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="room_creator and room_name required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    rec = data.get("sheets", {}).get(sheet_id)
    if not rec:
        return web.json_response({"ok": True})
    if rec.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and rec.get("ownerId") != user.id:
        return web.HTTPForbidden(text="Cannot modify this sheet")

    rec["characterId"] = None
    rec["updatedAt"] = datetime.datetime.utcnow().isoformat()
    # Clear appearance when unlinking character
    sheet_data = rec.get("data") or {}
    ds = sheet_data.get("dndsheets") or {}
    ds.pop("appearance", None)
    sheet_data["dndsheets"] = ds
    rec["data"] = sheet_data
    _save_sheets(data)
    return web.json_response({"ok": True})


async def set_default(request: web.Request) -> web.Response:
    """Set default sheet for the current user in this room."""
    user = await get_authorized_user(request)
    data = await request.json()
    sheet_id = data.get("sheetId")
    creator = (data.get("roomCreator") or "").strip()
    room_name = (data.get("roomName") or "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    if sheet_id is not None:
        data = _load_sheets()
        rec = data.get("sheets", {}).get(sheet_id)
        if not rec or rec.get("roomId") != room.id:
            return web.HTTPNotFound(text="Sheet not found")
        if pr.role != Role.DM and rec.get("ownerId") != user.id:
            return web.HTTPForbidden(text="Cannot set as default")

    defaults = _load_defaults()
    default_key = f"{user.id}_{room.id}"
    if sheet_id is None:
        defaults.pop(default_key, None)
    else:
        defaults[default_key] = sheet_id
    _save_defaults(defaults)
    return web.json_response({"ok": True})


async def toggle_sheet_visibility(request: web.Request) -> web.Response:
    """Toggle visibleToPlayers for a sheet. Owner or DM only."""
    user = await get_authorized_user(request)
    sheet_id = request.match_info.get("sheet_id", "").strip()
    if not sheet_id:
        return web.HTTPBadRequest(text="sheet_id required")

    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body or {}
    creator = (body.get("roomCreator") or request.query.get("room_creator") or "").strip()
    room_name = (body.get("roomName") or request.query.get("room_name") or "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    data = _load_sheets()
    rec = data.get("sheets", {}).get(sheet_id)
    if not rec:
        return web.HTTPNotFound(text="Sheet not found")
    if rec.get("roomId") != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and rec.get("ownerId") != user.id:
        return web.HTTPForbidden(text="Cannot change visibility of this sheet")

    rec["visibleToPlayers"] = not rec.get("visibleToPlayers", False)
    rec["updatedAt"] = datetime.datetime.utcnow().isoformat()
    _save_sheets(data)
    return web.json_response({"ok": True, "visibleToPlayers": rec["visibleToPlayers"]})


async def get_sheet_for_character(request: web.Request) -> web.Response:
    """Get sheet id linked to a character, if any."""
    user = await get_authorized_user(request)
    character_id_str = request.match_info.get("character_id", "").strip()
    if not character_id_str:
        return web.HTTPBadRequest(text="character_id required")
    try:
        character_id = int(character_id_str)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid character_id")

    creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="room_creator and room_name required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr:
        return web.HTTPForbidden(text="Not in this room")

    try:
        char = Character.get_by_id(character_id)
    except Character.DoesNotExist:
        return web.HTTPNotFound(text="Character not found")
    if char.campaign_id != room.id:
        return web.HTTPNotFound(text="Character not in this room")
    if not _can_edit_character(user, char, pr.role == Role.DM):
        return web.HTTPForbidden(text="Cannot access this character")

    data = _load_sheets()
    for sheet_id, rec in data.get("sheets", {}).items():
        if rec.get("roomId") == room.id and rec.get("characterId") == char.id:
            if pr.role != Role.DM and rec.get("ownerId") != user.id:
                return web.HTTPForbidden(text="Cannot access sheet for this character")
            return web.json_response({"sheetId": sheet_id})
    return web.HTTPNotFound(text="No sheet linked to this character")


async def get_default(request: web.Request) -> web.Response:
    """Get default sheet id for the current user in this room."""
    user = await get_authorized_user(request)
    creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()
    if not creator or not room_name:
        return web.HTTPBadRequest(text="room_creator and room_name required")

    room = _get_room(creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")

    defaults = _load_defaults()
    default_key = f"{user.id}_{room.id}"
    sheet_id = defaults.get(default_key)
    return web.json_response({"defaultSheetId": sheet_id})
