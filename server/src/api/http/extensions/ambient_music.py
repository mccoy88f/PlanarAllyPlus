"""Ambient Music extension - play audio files from assets."""

import hashlib
import json
from pathlib import Path

from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.asset import Asset
from ....db.models.user import User
from ....utils import ASSETS_DIR, get_asset_hash_subpath

AUDIO_EXTENSIONS = frozenset({".mp3", ".ogg", ".wav", ".m4a", ".aac", ".flac", ".webm", ".weba", ".opus"})


def _is_audio(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_EXTENSIONS


def _is_playlist(name: str) -> bool:
    return Path(name).suffix.lower() == ".json"


def _build_audio_tree(user: User, parent: Asset | None) -> list[dict]:
    """Build tree of folders and audio files. parent=None = root."""
    root = Asset.get_root_folder(user)
    folder = parent if parent is not None else root
    items: list[dict] = []
    for asset in Asset.select().where((Asset.parent == folder) & (Asset.owner == user)):
        if asset.file_hash:
            if _is_audio(asset.name):
                items.append({
                    "id": asset.id,
                    "name": asset.name,
                    "fileHash": asset.file_hash,
                    "type": "audio",
                })
        else:
            children = _build_audio_tree(user, asset)
            items.append({
                "id": asset.id,
                "name": asset.name,
                "type": "folder",
                "children": children,
            })
    return items


def _flatten_for_browser(items: list[dict], parent_id: int) -> list[dict]:
    """Flatten tree to list with folderId (Documents-style) for file browser."""
    out: list[dict] = []
    for it in items:
        if it["type"] == "audio":
            out.append({**it, "folderId": parent_id})
        else:
            out.append({
                "id": it["id"],
                "name": it["name"],
                "type": "folder",
                "folderId": parent_id,
            })
            out.extend(_flatten_for_browser(it.get("children", []), it["id"]))
    return out


def _build_playlist_tree(user: User, parent: Asset | None) -> list[dict]:
    """Build tree of folders and playlist (.json) files. parent=None = root."""
    root = Asset.get_root_folder(user)
    folder = parent if parent is not None else root
    items: list[dict] = []
    for asset in Asset.select().where((Asset.parent == folder) & (Asset.owner == user)):
        if asset.file_hash:
            if _is_playlist(asset.name):
                items.append({
                    "id": asset.id,
                    "name": asset.name,
                    "fileHash": asset.file_hash,
                    "type": "playlist",
                })
        else:
            children = _build_playlist_tree(user, asset)
            items.append({
                "id": asset.id,
                "name": asset.name,
                "type": "folder",
                "children": children,
            })
    return items


def _flatten_playlists(items: list[dict], parent_id: int) -> list[dict]:
    out: list[dict] = []
    for it in items:
        if it["type"] == "playlist":
            out.append({**it, "folderId": parent_id})
        else:
            out.append({
                "id": it["id"],
                "name": it["name"],
                "type": "folder",
                "folderId": parent_id,
            })
            out.extend(_flatten_playlists(it.get("children", []), it["id"]))
    return out


async def list_audio(request: web.Request) -> web.Response:
    """List audio files and folders (Documents-style: flat items + rootId)."""
    user = await get_authorized_user(request)
    root = Asset.get_root_folder(user)
    tree = _build_audio_tree(user, None)
    items = _flatten_for_browser(tree, root.id)
    return web.json_response({"items": items, "rootId": root.id})


async def serve_audio(request: web.Request) -> web.Response:
    """Serve an audio file by hash. User must have access to the asset."""
    user = await get_authorized_user(request)
    file_hash = request.match_info.get("file_hash", "").strip()
    if not file_hash or len(file_hash) < 40:
        return web.HTTPBadRequest(text="Invalid file hash")

    asset = Asset.get_or_none((Asset.file_hash == file_hash) & (Asset.owner == user))
    if not asset:
        for candidate in Asset.select().where(Asset.file_hash == file_hash):
            if _is_audio(candidate.name) and candidate.can_be_accessed_by(user, right="view"):
                asset = candidate
                break
        else:
            asset = None

    if not asset:
        return web.HTTPNotFound(text="Audio not found")

    path = ASSETS_DIR / get_asset_hash_subpath(file_hash)
    if not path.exists():
        return web.HTTPNotFound(text="File not found")

    ext = Path(asset.name).suffix.lower()
    mime = {
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".weba": "audio/webm",
        ".opus": "audio/opus",
    }.get(ext, "audio/*")
    return web.FileResponse(
        path,
        headers={
            "Content-Type": mime,
            "Content-Disposition": f'inline; filename="{asset.name}"',
        },
    )


async def list_playlists(request: web.Request) -> web.Response:
    """List folders and playlist (.json) files in assets (Documents-style)."""
    user = await get_authorized_user(request)
    root = Asset.get_root_folder(user)
    tree = _build_playlist_tree(user, None)
    items = _flatten_playlists(tree, root.id)
    return web.json_response({"items": items, "rootId": root.id})


async def serve_playlist(request: web.Request) -> web.Response:
    """Serve a playlist (.json) file by hash."""
    user = await get_authorized_user(request)
    file_hash = request.match_info.get("file_hash", "").strip()
    if not file_hash or len(file_hash) < 40:
        return web.HTTPBadRequest(text="Invalid file hash")

    asset = Asset.get_or_none((Asset.file_hash == file_hash) & (Asset.owner == user))
    if not asset:
        for candidate in Asset.select().where(Asset.file_hash == file_hash):
            if _is_playlist(candidate.name) and candidate.can_be_accessed_by(user, right="view"):
                asset = candidate
                break
        else:
            asset = None

    if not asset:
        return web.HTTPNotFound(text="Playlist not found")

    path = ASSETS_DIR / get_asset_hash_subpath(file_hash)
    if not path.exists():
        return web.HTTPNotFound(text="File not found")

    return web.FileResponse(
        path,
        headers={
            "Content-Type": "application/json",
            "Content-Disposition": f'inline; filename="{asset.name}"',
        },
    )


def _get_playlist_parent(user: User, parent_id: int | None) -> Asset:
    """Get parent folder for upload; must be in user's assets."""
    root = Asset.get_root_folder(user)
    if parent_id is None:
        return root
    try:
        parent = Asset.get_by_id(parent_id)
    except Asset.DoesNotExist:
        return root
    if parent.owner != user:
        return root
    if parent.file_hash is not None:
        return root  # parent must be a folder
    return parent


async def upload_playlist(request: web.Request) -> web.Response:
    """Save playlist JSON to a folder in assets."""
    user = await get_authorized_user(request)
    data = await request.json()
    parent_id = data.get("parentId") or data.get("parent_id")
    name = (data.get("name") or "playlist.json").strip()
    tracks = data.get("tracks") or []

    if not name.lower().endswith(".json"):
        name = name + ".json"

    display_name = name[:-5] if name.lower().endswith(".json") else name
    playlist_data = {"version": 1, "name": display_name, "tracks": tracks}
    content = json.dumps(playlist_data, indent=2).encode("utf-8")
    hashname = hashlib.sha1(content).hexdigest()
    full_path = ASSETS_DIR / get_asset_hash_subpath(hashname)

    if not full_path.exists():
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)

    folder = _get_playlist_parent(user, parent_id)
    existing = Asset.get_or_none(
        (Asset.parent == folder) & (Asset.name == name) & (Asset.owner == user),
    )
    if existing:
        existing.file_hash = hashname
        existing.save()
        return web.json_response(
            {"id": existing.id, "name": existing.name, "fileHash": hashname, "folderId": folder.id},
        )

    asset = Asset.create(name=name, file_hash=hashname, owner=user, parent=folder)
    return web.json_response(
        {"id": asset.id, "name": asset.name, "fileHash": asset.file_hash, "folderId": folder.id},
    )
