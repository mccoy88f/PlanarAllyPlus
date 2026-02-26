"""Character Sheet extension - D&D 5e in formato D&D Beyond."""

import copy
import datetime
import hashlib
import json
import re
import uuid

from aiohttp import web

from .dndbeyond_adapter import migrate_old_to_beyond
from .dndbeyond_schema import empty_character, get_character_name
from pathlib import Path

from ....auth import get_authorized_user
from ....db.models.asset import Asset
from ....db.models.character import Character
from ....db.models.character_sheet import CharacterSheet
from ....db.models.character_sheet_default import CharacterSheetDefault
from ....db.models.user_options import UserOptions
from ....db.models.player_room import PlayerRoom
from ....db.models.room import Room
from ....db.models.user import User
from ....models.role import Role
from ....utils import ASSETS_DIR, DATA_DIR, get_asset_hash_subpath

SHEETS_FILE = DATA_DIR / "character_sheets.json"
DEFAULTS_FILE = DATA_DIR / "character_sheet_defaults.json"
EXTENSION_ID = "character-sheet"


def _get_or_create_portrait_folder(user: User) -> Asset:
    """Get or create the portraits folder at assets/extensions/character-sheet."""
    return Asset.get_or_create_extension_folder(user, EXTENSION_ID)


def _migrate_json_to_db() -> None:
    """Migrate old JSON sheets and defaults to SQLite database."""
    if SHEETS_FILE.exists() or DEFAULTS_FILE.exists():
        try:
            from ....db.db import db as ACTIVE_DB
            
            with ACTIVE_DB.atomic():
                sheets_data = {}
                if SHEETS_FILE.exists():
                    try:
                        with open(SHEETS_FILE, encoding="utf-8") as f:
                            data = json.load(f)
                            sheets_data = data.get("sheets", {}) if isinstance(data, dict) else {}
                    except (json.JSONDecodeError, OSError):
                        pass

                sheet_db_mapping = {}
                for sheet_uuid, rec in sheets_data.items():
                    try:
                        # Convert to DB
                        owner = User.get_or_none(User.id == rec.get("ownerId"))
                        room = Room.get_or_none(Room.id == rec.get("roomId"))
                        if not owner or not room:
                            continue

                        char_id = rec.get("characterId")
                        character = Character.get_or_none(Character.id == char_id) if char_id else None

                        sheet_db = CharacterSheet.create(
                            owner=owner,
                            room=room,
                            character=character,
                            name=rec.get("name", "Untitled"),
                            data=json.dumps(rec.get("data", {})),
                            visible_to_players=rec.get("visibleToPlayers", False),
                            created_at=rec.get("createdAt", datetime.datetime.now(datetime.UTC).isoformat()),
                            updated_at=rec.get("updatedAt", datetime.datetime.now(datetime.UTC).isoformat())
                        )
                        sheet_db_mapping[sheet_uuid] = sheet_db
                    except Exception as e:
                        print(f"Error migrating sheet {sheet_uuid}: {e}")

                if DEFAULTS_FILE.exists():
                    try:
                        with open(DEFAULTS_FILE, encoding="utf-8") as f:
                            defaults_data = json.load(f)
                        
                        for key, sheet_uuid in defaults_data.items():
                            parts = key.split("_")
                            if len(parts) != 2:
                                continue
                            user_id, room_id = parts
                            owner = User.get_or_none(User.id == user_id)
                            room = Room.get_or_none(Room.id == room_id)
                            if not owner or not room or sheet_uuid not in sheet_db_mapping:
                                continue
                            
                            CharacterSheetDefault.create(
                                user=owner,
                                room=room,
                                sheet=sheet_db_mapping[sheet_uuid]
                            )
                    except (json.JSONDecodeError, OSError):
                        pass

                # Rename the files so migration doesn't run again
                if SHEETS_FILE.exists():
                    SHEETS_FILE.rename(SHEETS_FILE.with_suffix(".json.bak"))
                if DEFAULTS_FILE.exists():
                    DEFAULTS_FILE.rename(DEFAULTS_FILE.with_suffix(".json.bak"))
        except Exception as e:
            print(f"Character Sheet migration failed: {e}")



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

    from ....db.db import db as ACTIVE_DB

    # Run DB migration code lazily on first access if needed
    _migrate_json_to_db()

    with ACTIVE_DB.atomic():
        default_record = CharacterSheetDefault.get_or_none(CharacterSheetDefault.user == user, CharacterSheetDefault.room == room)
        default_sheet_id = str(default_record.sheet.id) if default_record else None

        sheets_query = CharacterSheet.select().where(CharacterSheet.room == room)
        if not is_dm:
            sheets_query = sheets_query.where((CharacterSheet.owner == user) | (CharacterSheet.visible_to_players == True))

        result_sheets = []
        for sheet_record in sheets_query:
            sheet_data = {}
            try:
                sheet_data = json.loads(sheet_record.data) if sheet_record.data else {}
            except json.JSONDecodeError:
                pass

            char_id = sheet_record.character.id if sheet_record.character else None
            char = char_by_id.get(char_id) if char_id else None
            can_edit = is_dm or sheet_record.owner.id == user.id
            char_name = char.name if char else None

            migrated = migrate_old_to_beyond(sheet_data)
            if migrated:
                sheet_data = migrated
                sheet_record.data = json.dumps(sheet_data)
                sheet_record.name = get_character_name(migrated)
                sheet_record.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
                sheet_record.save()
            
            name = sheet_record.name or get_character_name(sheet_data) or (char_name or "")
            result_sheets.append({
                "id": str(sheet_record.id),
                "name": name,
                "characterId": char_id,
                "characterName": char_name,
                "canEdit": can_edit,
                "isDefault": default_sheet_id == str(sheet_record.id),
                "visibleToPlayers": sheet_record.visible_to_players,
                "canToggleVisibility": is_dm or sheet_record.owner.id == user.id,
            })

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
    sheet_id_str = request.match_info.get("sheet_id", "").strip()
    if not sheet_id_str:
        return web.HTTPBadRequest(text="sheet_id required")
    try:
        sheet_id = int(sheet_id_str)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

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

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id)
    if not sheet_record:
        return web.HTTPNotFound(text="Sheet not found")
    if sheet_record.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and sheet_record.owner.id != user.id and not sheet_record.visible_to_players:
        return web.HTTPForbidden(text="Cannot access this sheet")

    try:
        sheet_data = json.loads(sheet_record.data) if sheet_record.data else {}
    except json.JSONDecodeError:
        sheet_data = {}

    migrated = migrate_old_to_beyond(sheet_data)
    if migrated:
        sheet_data = migrated
        sheet_record.data = json.dumps(sheet_data)
        sheet_record.name = get_character_name(migrated)
        sheet_record.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
        sheet_record.save()

    return web.json_response({
        "sheet": sheet_data,
        "name": sheet_record.name or "",
        "characterId": sheet_record.character.id if sheet_record.character else None,
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

    sheet_data = empty_character()
    if isinstance(sheet_overlay, dict):
        sheet_data = _merge_sheet_data(sheet_data, sheet_overlay)
    _clean_spell_arrays(sheet_data)
    final_name = name or get_character_name(sheet_data) or _default_new_character_name(user)
    sheet_data["name"] = final_name

    new_sheet = CharacterSheet.create(
        owner=user,
        room=room,
        character=None,
        name=final_name,
        data=json.dumps(sheet_data),
        visible_to_players=False,
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        updated_at=datetime.datetime.now(datetime.UTC).isoformat()
    )

    return web.json_response({"ok": True, "sheetId": str(new_sheet.id)})


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

    try:
        sheet_id_int = int(sheet_id)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
    if not sheet_record:
        return web.HTTPNotFound(text="Sheet not found")
    if sheet_record.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and sheet_record.owner.id != user.id:
        return web.HTTPForbidden(text="Cannot edit this sheet")

    migrated = migrate_old_to_beyond(sheet_data)
    if migrated:
        sheet_data = migrated
    _clean_spell_arrays(sheet_data)
    
    sheet_record.data = json.dumps(sheet_data)
    sheet_record.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
    sheet_record.name = get_character_name(sheet_data) or sheet_record.name
    sheet_record.save()
    
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

    try:
        sheet_id_int = int(sheet_id)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
    if not sheet_record:
        return web.json_response({"ok": True})  # already gone

    if sheet_record.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and sheet_record.owner.id != user.id:
        return web.HTTPForbidden(text="Cannot delete this sheet")

    # The default sheet association is set to CASCADE, so deleting the sheet
    # will also automatically delete the corresponding CharacterSheetDefault.
    sheet_record.delete_instance()

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

    try:
        sheet_id_int = int(sheet_id)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

    src = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
    if not src:
        return web.HTTPNotFound(text="Sheet not found")
    if src.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and src.owner.id != user.id:
        return web.HTTPForbidden(text="Cannot duplicate this sheet")

    try:
        sheet_data = json.loads(src.data) if src.data else empty_character()
    except json.JSONDecodeError:
        sheet_data = empty_character()

    migrated = migrate_old_to_beyond(sheet_data)
    if migrated:
        sheet_data = migrated
    
    name = new_name or (src.name or "Copy")
    sheet_data["name"] = name

    new_sheet = CharacterSheet.create(
        owner=user,
        room=room,
        character=None,
        name=name,
        data=json.dumps(sheet_data),
        visible_to_players=False,
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        updated_at=datetime.datetime.now(datetime.UTC).isoformat()
    )

    return web.json_response({"ok": True, "sheetId": str(new_sheet.id)})


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

    try:
        sheet_id_int = int(sheet_id)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
    if not sheet_record:
        return web.HTTPNotFound(text="Sheet not found")
    if sheet_record.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and sheet_record.owner.id != user.id:
        return web.HTTPForbidden(text="Cannot use this sheet")

    # Check no other sheet is linked to this character
    existing_link = CharacterSheet.get_or_none(CharacterSheet.character == char)
    if existing_link and existing_link.id != sheet_record.id:
        return web.HTTPBadRequest(text="Character already has a sheet linked")

    sheet_record.character = char
    sheet_record.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
    # Set sheet appearance from character's asset image
    try:
        sheet_data = json.loads(sheet_record.data) if sheet_record.data else {}
    except json.JSONDecodeError:
        sheet_data = {}
    
    ds = sheet_data.get("dndsheets") or {}
    if char.asset and char.asset.file_hash:
        app_url = f"/static/assets/{get_asset_hash_subpath(char.asset.file_hash).as_posix()}"
        ds["appearance"] = app_url
    else:
        ds.pop("appearance", None)
    
    sheet_data["dndsheets"] = ds
    sheet_record.data = json.dumps(sheet_data)
    sheet_record.save()
    
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

    try:
        sheet_id_int = int(sheet_id)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
    if not sheet_record:
        return web.json_response({"ok": True})
    if sheet_record.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and sheet_record.owner.id != user.id:
        return web.HTTPForbidden(text="Cannot modify this sheet")

    sheet_record.character = None
    sheet_record.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
    
    # Clear appearance when unlinking character
    try:
        sheet_data = json.loads(sheet_record.data) if sheet_record.data else {}
    except json.JSONDecodeError:
        sheet_data = {}
        
    ds = sheet_data.get("dndsheets") or {}
    ds.pop("appearance", None)
    sheet_data["dndsheets"] = ds
    
    sheet_record.data = json.dumps(sheet_data)
    sheet_record.save()
    
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
        try:
            sheet_id_int = int(sheet_id)
        except ValueError:
            return web.HTTPBadRequest(text="Invalid sheet_id")

        sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
        if not sheet_record or sheet_record.room.id != room.id:
            return web.HTTPNotFound(text="Sheet not found")
        if pr.role != Role.DM and sheet_record.owner.id != user.id:
            return web.HTTPForbidden(text="Cannot set as default")

    default_record = CharacterSheetDefault.get_or_none(CharacterSheetDefault.user == user, CharacterSheetDefault.room == room)
    
    if sheet_id is None:
        if default_record:
            default_record.delete_instance()
    else:
        if default_record:
            default_record.sheet = sheet_record
            default_record.save()
        else:
            CharacterSheetDefault.create(user=user, room=room, sheet=sheet_record)
            
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

    try:
        sheet_id_int = int(sheet_id)
    except ValueError:
        return web.HTTPBadRequest(text="Invalid sheet_id")

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.id == sheet_id_int)
    if not sheet_record:
        return web.HTTPNotFound(text="Sheet not found")
    if sheet_record.room.id != room.id:
        return web.HTTPNotFound(text="Sheet not in this room")
    if pr.role != Role.DM and sheet_record.owner.id != user.id:
        return web.HTTPForbidden(text="Cannot change visibility of this sheet")

    sheet_record.visible_to_players = not sheet_record.visible_to_players
    sheet_record.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
    sheet_record.save()
    
    return web.json_response({"ok": True, "visibleToPlayers": sheet_record.visible_to_players})


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

    sheet_record = CharacterSheet.get_or_none(CharacterSheet.room == room, CharacterSheet.character == char)
    
    if sheet_record:
        if pr.role != Role.DM and sheet_record.owner.id != user.id:
            return web.HTTPForbidden(text="Cannot access sheet for this character")
        return web.json_response({"sheetId": str(sheet_record.id)})
        
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

    default_record = CharacterSheetDefault.get_or_none(CharacterSheetDefault.user == user, CharacterSheetDefault.room == room)
    sheet_id = str(default_record.sheet.id) if default_record else None
    return web.json_response({"defaultSheetId": sheet_id})


async def upload_portrait(request: web.Request) -> web.Response:
    """Upload a portrait image to the extension's assets folder."""
    user = await get_authorized_user(request)

    reader = await request.multipart()
    filename = "portrait.png"
    data = b""

    async for part in reader:
        if part.name == "file":
            filename = part.filename or "portrait.png"
            data = await part.read()

    if not data:
        return web.HTTPBadRequest(text="No file in 'file' field")

    # Simple validation: common image extensions
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        return web.HTTPBadRequest(text=f"Invalid file type: {ext}")

    sh = hashlib.sha1(data)
    hashname = sh.hexdigest()
    full_hash_path = ASSETS_DIR / get_asset_hash_subpath(hashname)

    if not full_hash_path.exists():
        full_hash_path.parent.mkdir(parents=True, exist_ok=True)
        full_hash_path.write_bytes(data)

    folder = _get_or_create_portrait_folder(user)
    asset = Asset.create(name=filename, file_hash=hashname, owner=user, parent=folder)

    # Generate thumbnail
    from ....thumbnail import generate_thumbnail_for_asset

    generate_thumbnail_for_asset(filename, hashname)

    url = f"/static/assets/{get_asset_hash_subpath(hashname).as_posix()}"
    return web.json_response({"ok": True, "url": url, "assetId": asset.id})
