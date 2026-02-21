"""Documents extension - PDF upload and management in assets."""

import hashlib
import json
from pathlib import Path

from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.asset import Asset
from ....db.models.player_room import PlayerRoom
from ....db.models.room import Room
from ....db.models.user import User
from ....models.role import Role
from ....thumbnail import generate_thumbnail_for_asset
from ....utils import ASSETS_DIR, DATA_DIR, THUMBNAILS_DIR, get_asset_hash_subpath

DOCUMENT_VISIBILITY_FILE = DATA_DIR / "document_visibility.json"

EXTENSION_ID = "documents"


def _get_or_create_documents_folder(user: User) -> Asset:
    """Get or create the documents folder at assets/extensions/documents."""
    return Asset.get_or_create_extension_folder(user, EXTENSION_ID)


def _is_in_documents_tree(asset: Asset, user: User) -> bool:
    """Check if asset is under the user's documents folder."""
    docs_folder = _get_or_create_documents_folder(user)
    current = asset.parent
    while current is not None:
        if current.id == docs_folder.id:
            return True
        current = current.parent
    return False


async def serve_document(request: web.Request) -> web.Response:
    """Serve a PDF with Content-Disposition: inline so it displays in browser instead of downloading."""
    user = await get_authorized_user(request)
    file_hash = request.match_info.get("file_hash", "").strip()
    if not file_hash or len(file_hash) < 40:
        return web.HTTPBadRequest(text="Invalid file hash")

    # Find asset: owned by user in documents tree, or DM's doc visible to players in user's room
    docs_folder = _get_or_create_documents_folder(user)
    asset = Asset.get_or_none(
        (Asset.file_hash == file_hash) & (Asset.owner == user),
    )
    if asset and _is_in_documents_tree(asset, user):
        pass  # User's own document
    else:
        asset = None
        for candidate in Asset.select().where(Asset.file_hash == file_hash):
            if not candidate.name or not candidate.name.lower().endswith(".pdf"):
                continue
            if candidate.owner == user:
                continue
            vis_data = _load_document_visibility()
            for room_key, vis_map in vis_data.items():
                visible_ids = _get_visible_document_ids(candidate.owner, vis_map)
                if candidate.id not in visible_ids:
                    continue
                parts = room_key.split("/", 1)
                if len(parts) != 2:
                    continue
                cr, rn = parts[0], parts[1]
                room = _get_room(cr, rn)
                if not room or room.creator != candidate.owner:
                    continue
                if PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user):
                    asset = candidate
                    break
            if asset is not None:
                break

    if not asset:
        return web.HTTPNotFound(text="Document not found")

    path = ASSETS_DIR / get_asset_hash_subpath(file_hash)
    if not path.exists():
        return web.HTTPNotFound(text="File not found")

    return web.FileResponse(
        path,
        headers={
            "Content-Type": "application/pdf",
            "Content-Disposition": f'inline; filename="{asset.name}"',
        },
    )


def _thumbnail_path(file_hash: str) -> str | None:
    """Return static URL path for PDF thumbnail if it exists, else None."""
    subpath = get_asset_hash_subpath(file_hash)
    thumb_rel = f"{subpath}.thumb.webp"
    if (THUMBNAILS_DIR / thumb_rel).exists():
        return f"/static/thumbnails/{thumb_rel}"
    if (ASSETS_DIR / thumb_rel).exists():
        return f"/static/assets/{thumb_rel}"
    return None


def _room_key(creator_name: str, room_name: str) -> str:
    return f"{creator_name}/{room_name}"


def _load_document_visibility() -> dict:
    """Load document visibility: { room_key: { asset_id: true } }."""
    if not DOCUMENT_VISIBILITY_FILE.exists():
        return {}
    try:
        with open(DOCUMENT_VISIBILITY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_document_visibility(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DOCUMENT_VISIBILITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_room_visibility(room_key: str) -> dict[str, bool]:
    """Get visibility map for a room: asset_id -> visible."""
    data = _load_document_visibility()
    return data.get(room_key, {})


def _set_document_visibility(room_key: str, asset_id: int, visible: bool) -> None:
    data = _load_document_visibility()
    if room_key not in data:
        data[room_key] = {}
    data[room_key][str(asset_id)] = visible
    _save_document_visibility(data)


def _get_visible_document_ids(owner: User, vis_map: dict[str, bool]) -> set[int]:
    """Return set of document IDs visible to players. When a folder is visible, all docs inside it are visible."""
    docs_folder = _get_or_create_documents_folder(owner)
    visible_ids: set[int] = set()

    def collect_from_folder(folder: Asset) -> None:
        for child in Asset.select().where((Asset.parent == folder) & (Asset.owner == owner)):
            if child.file_hash and child.name and child.name.lower().endswith(".pdf"):
                visible_ids.add(child.id)
            else:
                collect_from_folder(child)

    for aid_str, is_vis in vis_map.items():
        if not is_vis:
            continue
        try:
            aid = int(aid_str)
        except ValueError:
            continue
        try:
            asset = Asset.get_by_id(aid)
        except Asset.DoesNotExist:
            continue
        if asset.owner != owner or not _is_in_documents_tree(asset, owner):
            continue
        if asset.file_hash and asset.name.lower().endswith(".pdf"):
            visible_ids.add(asset.id)
        else:
            collect_from_folder(asset)

    return visible_ids


def _build_documents_tree(
    user: User,
    parent: Asset | None,
    *,
    owner_filter: User | None = None,
    visible_asset_ids: set[int] | None = None,
    visibility_map: dict[str, bool] | None = None,
    can_toggle_visibility: bool = False,
    parent_visible: bool = False,
) -> list[dict]:
    """Build tree of folders and documents. owner_filter limits to that user's assets.
    visible_asset_ids: when set, only include these asset IDs (for player view of DM's docs).
    visibility_map: asset_id -> visibleToPlayers for DM view.
    parent_visible: when True, this subtree inherits visibility from parent folder."""
    docs_folder = _get_or_create_documents_folder(owner_filter or user)
    folder = parent if parent is not None else docs_folder
    items: list[dict] = []
    owner = owner_filter or user

    for asset in Asset.select().where((Asset.parent == folder) & (Asset.owner == owner)):
        direct_vis = visibility_map.get(str(asset.id), False) if visibility_map else False
        effective_vis = parent_visible or direct_vis

        if asset.file_hash:
            if asset.name.lower().endswith(".pdf"):
                if visible_asset_ids is not None and asset.id not in visible_asset_ids:
                    continue
                doc_item: dict = {
                    "id": asset.id,
                    "name": asset.name,
                    "fileHash": asset.file_hash,
                    "folderId": asset.parent_id,
                    "type": "document",
                }
                if thumb := _thumbnail_path(asset.file_hash):
                    doc_item["thumbnailUrl"] = thumb
                if visibility_map is not None:
                    doc_item["visibleToPlayers"] = effective_vis
                if can_toggle_visibility:
                    doc_item["canToggleVisibility"] = True
                items.append(doc_item)
        else:
            children = _build_documents_tree(
                user,
                asset,
                owner_filter=owner_filter,
                visible_asset_ids=visible_asset_ids,
                visibility_map=visibility_map,
                can_toggle_visibility=can_toggle_visibility,
                parent_visible=effective_vis,
            )
            if visible_asset_ids is not None and not children:
                continue
            folder_item: dict = {
                "id": asset.id,
                "name": asset.name,
                "folderId": asset.parent_id,
                "type": "folder",
                "children": children,
            }
            if visibility_map is not None:
                folder_item["visibleToPlayers"] = effective_vis
            if can_toggle_visibility:
                folder_item["canToggleVisibility"] = True
            items.append(folder_item)
    return items


def _get_room(creator_name: str, room_name: str) -> Room | None:
    creator = User.get_or_none(User.name == creator_name)
    if not creator:
        return None
    return Room.get_or_none(Room.creator == creator, Room.name == room_name)


async def list_documents(request: web.Request) -> web.Response:
    """List documents and folders in tree structure.
    Query params: room_creator, room_name for game context (visibility to players)."""
    user = await get_authorized_user(request)
    room_creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()

    docs_folder = _get_or_create_documents_folder(user)
    visibility_map: dict[str, bool] | None = None
    can_toggle = False
    dm_visible_docs: list[dict] = []

    if room_creator and room_name:
        room = _get_room(room_creator, room_name)
        if room:
            pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
            if pr:
                room_key = _room_key(room_creator, room_name)
                vis = _get_room_visibility(room_key)
                if pr.role == Role.DM:
                    visibility_map = vis
                    can_toggle = True
                    tree = _build_documents_tree(
                        user, None, visibility_map=visibility_map, can_toggle_visibility=True
                    )
                else:
                    dm = room.creator
                    if dm != user:
                        visible_ids = _get_visible_document_ids(dm, vis)
                        dm_tree = _build_documents_tree(
                            user, None, owner_filter=dm, visible_asset_ids=visible_ids
                        )

                        def extract_docs(items: list) -> list[dict]:
                            out: list[dict] = []
                            for it in items:
                                if it["type"] == "document":
                                    out.append({**it, "folderId": -1, "visibleToPlayers": True})
                                else:
                                    out.extend(extract_docs(it.get("children", [])))
                            return out

                        dm_visible_docs = extract_docs(dm_tree)
                    tree = _build_documents_tree(user, None)
                    if dm_visible_docs:
                        tree.insert(0, {
                            "id": -1,
                            "name": "Visible to players",
                            "nameKey": "visible_to_players",
                            "folderId": docs_folder.id,
                            "type": "folder",
                            "children": dm_visible_docs,
                        })
                docs_folder = _get_or_create_documents_folder(user)
            else:
                tree = _build_documents_tree(user, None)
        else:
            tree = _build_documents_tree(user, None)
    else:
        tree = _build_documents_tree(user, None)

    def flatten(items: list, parent_id: int | None) -> list[dict]:
        out: list[dict] = []
        for it in items:
            if it["type"] == "document":
                out.append({**it, "folderId": it.get("folderId") or parent_id})
            else:
                out.append({**{k: v for k, v in it.items() if k != "children"}, "folderId": it.get("folderId") or parent_id})
                out.extend(flatten(it.get("children", []), it["id"]))
        return out

    flat = flatten(tree, docs_folder.id)
    return web.json_response({"documents": flat, "tree": tree, "rootId": docs_folder.id})


def _get_documents_parent(user: User, parent_id: int | None) -> Asset:
    """Get parent folder for upload/create; must be in documents tree."""
    docs_folder = _get_or_create_documents_folder(user)
    if parent_id is None:
        return docs_folder
    try:
        parent = Asset.get_by_id(parent_id)
    except Asset.DoesNotExist:
        return docs_folder
    if parent.owner != user or not _is_in_documents_tree(parent, user):
        return docs_folder
    if parent.file_hash is not None:
        return docs_folder  # parent must be a folder
    return parent


async def upload_document(request: web.Request) -> web.Response:
    """Upload a PDF file to the documents folder or a subfolder."""
    user = await get_authorized_user(request)

    reader = await request.multipart()
    parent_id: int | None = None
    filename = "document.pdf"
    data = b""

    async for part in reader:
        if part.name == "file":
            filename = part.filename or "document.pdf"
            data = await part.read()
        elif part.name in ("parentId", "parent_id"):
            raw = await part.read()
            try:
                parent_id = int(raw.decode().strip()) if raw else None
            except (ValueError, UnicodeDecodeError):
                parent_id = None

    if not data:
        return web.HTTPBadRequest(text="No file in 'file' field")

    if not filename.lower().endswith(".pdf"):
        return web.HTTPBadRequest(text="Only PDF files are allowed")

    sh = hashlib.sha1(data)
    hashname = sh.hexdigest()
    full_hash_path = ASSETS_DIR / get_asset_hash_subpath(hashname)

    if not full_hash_path.exists():
        full_hash_path.parent.mkdir(parents=True, exist_ok=True)
        full_hash_path.write_bytes(data)

    folder = _get_documents_parent(user, parent_id)
    asset = Asset.create(name=filename, file_hash=hashname, owner=user, parent=folder)

    generate_thumbnail_for_asset(filename, hashname)

    return web.json_response(
        {"id": asset.id, "name": asset.name, "fileHash": asset.file_hash, "folderId": folder.id}
    )


async def create_folder(request: web.Request) -> web.Response:
    """Create a folder in the documents tree."""
    user = await get_authorized_user(request)
    data = await request.json()
    name = (data.get("name") or "").strip()
    parent_id = data.get("parentId") or data.get("parent_id")
    if not name:
        return web.HTTPBadRequest(text="Folder name is required")

    pid = int(parent_id) if parent_id is not None else None
    folder = _get_documents_parent(user, pid)
    existing = Asset.get_or_none(
        (Asset.parent == folder) & (Asset.name == name) & (Asset.owner == user),
    )
    if existing:
        return web.HTTPBadRequest(text="A folder or file with this name already exists")

    asset = Asset.create(name=name, file_hash=None, owner=user, parent=folder)
    return web.json_response({"id": asset.id, "name": asset.name, "folderId": folder.id, "type": "folder"})


async def rename_document(request: web.Request) -> web.Response:
    """Rename a document or folder."""
    user = await get_authorized_user(request)
    data = await request.json()
    item_id = data.get("id")
    name = (data.get("name") or "").strip()
    if item_id is None:
        return web.HTTPBadRequest(text="Id is required")
    if not name:
        return web.HTTPBadRequest(text="Name is required")

    try:
        asset = Asset.get_by_id(item_id)
    except Asset.DoesNotExist:
        return web.HTTPNotFound(text="Item not found")

    if asset.owner != user:
        return web.HTTPForbidden(text="Not owner")
    if not _is_in_documents_tree(asset, user):
        return web.HTTPBadRequest(text="Item not in documents")

    sibling = Asset.get_or_none(
        (Asset.parent == asset.parent) & (Asset.name == name) & (Asset.owner == user),
    )
    if sibling and sibling.id != asset.id:
        return web.HTTPBadRequest(text="A folder or file with this name already exists")

    asset.name = name
    asset.save()
    return web.json_response({"id": asset.id, "name": asset.name})


async def move_document(request: web.Request) -> web.Response:
    """Move a document or folder to another folder."""
    user = await get_authorized_user(request)
    data = await request.json()
    item_id = data.get("id")
    parent_id = data.get("parentId") or data.get("parent_id")
    if item_id is None:
        return web.HTTPBadRequest(text="Id is required")

    try:
        asset = Asset.get_by_id(item_id)
    except Asset.DoesNotExist:
        return web.HTTPNotFound(text="Item not found")

    if asset.owner != user:
        return web.HTTPForbidden(text="Not owner")
    if not _is_in_documents_tree(asset, user):
        return web.HTTPBadRequest(text="Item not in documents")

    docs_folder = _get_or_create_documents_folder(user)
    new_parent = docs_folder if parent_id is None else None
    if parent_id is not None:
        try:
            p = Asset.get_by_id(parent_id)
            if p.owner == user and _is_in_documents_tree(p, user) and p.file_hash is None:
                if p.id != asset.id and not _is_descendant(p, asset):
                    new_parent = p
        except Asset.DoesNotExist:
            pass

    if new_parent is None:
        new_parent = docs_folder

    if new_parent.id == asset.parent_id:
        return web.json_response({"id": asset.id, "folderId": asset.parent_id})

    sibling = Asset.get_or_none(
        (Asset.parent == new_parent) & (Asset.name == asset.name) & (Asset.owner == user),
    )
    if sibling:
        return web.HTTPBadRequest(text="A folder or file with this name already exists in the destination")

    asset.parent = new_parent
    asset.save()
    return web.json_response({"id": asset.id, "folderId": new_parent.id})


def _is_descendant(ancestor: Asset, node: Asset) -> bool:
    """Check if node is a descendant of ancestor."""
    current = node.parent
    while current is not None:
        if current.id == ancestor.id:
            return True
        current = current.parent
    return False


async def generate_thumbnails(request: web.Request) -> web.Response:
    """Generate thumbnails for documents that don't have them. Body: { "fileHashes": ["abc..."] }."""
    user = await get_authorized_user(request)
    try:
        data = await request.json()
    except Exception:
        data = {}
    hashes = data.get("fileHashes") or data.get("file_hashes") or []
    if not isinstance(hashes, list):
        return web.HTTPBadRequest(text="fileHashes must be a list")

    docs_folder = _get_or_create_documents_folder(user)
    generated = 0
    for h in hashes:
        if not isinstance(h, str) or len(h) < 40:
            continue
        asset = Asset.get_or_none((Asset.file_hash == h) & (Asset.owner == user))
        if not asset or not _is_in_documents_tree(asset, user):
            continue
        if not asset.name or not asset.name.lower().endswith(".pdf"):
            continue
        if _thumbnail_path(h):
            continue
        generate_thumbnail_for_asset(asset.name, h)
        generated += 1

    return web.json_response({"generated": generated})


async def toggle_document_visibility(request: web.Request) -> web.Response:
    """Toggle visibleToPlayers for a document or folder in a room. DM only.
    When a folder is visible, all its contents (recursively) are visible to players."""
    user = await get_authorized_user(request)
    data = await request.json()
    asset_id = data.get("id")
    room_creator = (data.get("roomCreator") or data.get("room_creator") or "").strip()
    room_name = (data.get("roomName") or data.get("room_name") or "").strip()
    if asset_id is None:
        return web.HTTPBadRequest(text="Document or folder id is required")
    if not room_creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName are required")

    room = _get_room(room_creator, room_name)
    if not room:
        return web.HTTPNotFound(text="Room not found")
    pr = PlayerRoom.get_or_none(PlayerRoom.room == room, PlayerRoom.player == user)
    if not pr or pr.role != Role.DM:
        return web.HTTPForbidden(text="Only the DM can toggle document visibility")

    try:
        asset = Asset.get_by_id(asset_id)
    except Asset.DoesNotExist:
        return web.HTTPNotFound(text="Item not found")
    if asset.owner != user:
        return web.HTTPForbidden(text="Not owner of this item")
    if not _is_in_documents_tree(asset, user):
        return web.HTTPBadRequest(text="Item not in documents")
    if asset.file_hash and not asset.name.lower().endswith(".pdf"):
        return web.HTTPBadRequest(text="Only documents and folders can have visibility toggled")

    room_key = _room_key(room_creator, room_name)
    current = _get_room_visibility(room_key).get(str(asset_id), False)
    new_val = not current
    _set_document_visibility(room_key, asset_id, new_val)
    return web.json_response({"ok": True, "visibleToPlayers": new_val})


async def delete_document(request: web.Request) -> web.Response:
    """Delete a PDF document or folder from the documents tree."""
    user = await get_authorized_user(request)
    data = await request.json()
    doc_id = data.get("id")
    if doc_id is None:
        return web.HTTPBadRequest(text="Document id is required")

    try:
        asset = Asset.get_by_id(doc_id)
    except Asset.DoesNotExist:
        return web.HTTPNotFound(text="Document not found")

    if asset.owner != user:
        return web.HTTPForbidden(text="Not owner of this document")

    if not _is_in_documents_tree(asset, user):
        return web.HTTPBadRequest(text="Item not in documents folder")

    if asset.file_hash and not asset.name.lower().endswith(".pdf"):
        return web.HTTPBadRequest(text="Not a valid document")

    asset.delete_instance()
    return web.json_response({"ok": True})
