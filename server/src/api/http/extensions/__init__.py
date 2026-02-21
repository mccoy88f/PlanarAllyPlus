"""Extensions API - list, install and uninstall extensions."""

import io
import json
import shutil

from . import ambient_music
from . import assets_installer
from . import character_sheet
from . import documents
from . import dungeongen
from . import openrouter
from . import compendium
from . import watabou
from . import proxy
from zipfile import BadZipFile, ZipFile

import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....utils import DATA_DIR, EXTENSIONS_DIR

VISIBILITY_FILE = DATA_DIR / "extension_visibility.json"


def _load_visibility() -> dict:
    """Load extension visibility from JSON file."""
    if not VISIBILITY_FILE.exists():
        return {}
    try:
        with open(VISIBILITY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_visibility(data: dict) -> None:
    """Save extension visibility to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(VISIBILITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _room_key(creator: str, room_name: str) -> str:
    """Key for per-game visibility: creator/roomname."""
    return f"{creator}/{room_name}"


def _get_room_visibility(room_key: str) -> dict[str, bool]:
    """Get visibility settings for a room. Keys are extension folder names."""
    data = _load_visibility()
    return data.get(room_key, {})


def _set_room_visibility(room_key: str, folder: str, visible: bool) -> None:
    """Set visibility for an extension in a specific game/room."""
    data = _load_visibility()
    if room_key not in data:
        data[room_key] = {}
    data[room_key][folder] = visible
    _save_visibility(data)


async def list_extensions(request: web.Request) -> web.Response:
    """Return list of installed extensions. Optional query: room_creator, room_name for player filtering."""
    user = await get_authorized_user(request)
    room_creator = request.query.get("room_creator", "").strip()
    room_name = request.query.get("room_name", "").strip()

    extensions = []
    if EXTENSIONS_DIR.exists():
        for item in EXTENSIONS_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                ext_id = item.name
                ext_name = item.name
                ext_version = "0.0.0"
                ext_description = ""
                manifest = item / "extension.toml"
                ext_entry = "ui/index.html"
                ext_title_bar_color = None
                ext_icon = None
                if manifest.exists():
                    try:
                        import rtoml

                        data = rtoml.load(manifest)
                        if "extension" in data:
                            ext_id = data["extension"].get("id", ext_id)
                            ext_name = data["extension"].get("name", ext_name)
                            ext_version = data["extension"].get("version", ext_version)
                            ext_description = data["extension"].get("description", "")
                            ext_entry = data["extension"].get("entry", "ui/index.html")
                            ext_title_bar_color = data["extension"].get("titleBarColor")
                            ext_icon = data["extension"].get("icon")
                    except Exception:
                        pass
                ui_path = item / ext_entry
                has_ui = ui_path.exists() and ui_path.is_file()
                ext_obj = {
                    "id": ext_id,
                    "name": ext_name,
                    "version": ext_version,
                    "description": ext_description,
                    "folder": item.name,
                    "entry": ext_entry if has_ui else None,
                }
                if ext_title_bar_color is not None:
                    ext_obj["titleBarColor"] = ext_title_bar_color
                if ext_icon is not None:
                    ext_obj["icon"] = ext_icon
                extensions.append(ext_obj)

    # Visibility is per-game: DM sees all extensions in every game; players see only
    # extensions the room owner enabled for that specific game.
    is_player_view = room_creator and room_name and room_creator != user.name
    room_key = _room_key(room_creator, room_name) if (room_creator and room_name) else ""
    visible_map = _get_room_visibility(room_key) if room_key else {}

    result = []
    for ext in extensions:
        visible_to_players = visible_map.get(ext["folder"], False)
        if is_player_view and not visible_to_players:
            continue
        ext_result = {**ext, "visibleToPlayers": visible_to_players}
        if ext.get("entry"):
            ext_result["uiUrl"] = f"/api/extensions/{ext['folder']}/ui/"
        result.append(ext_result)

    return web.json_response({"extensions": result})


async def install_from_zip(request: web.Request) -> web.Response:
    """Install extension from uploaded ZIP file."""
    await get_authorized_user(request)

    data = await request.read()
    if not data:
        return web.HTTPBadRequest(text="No file uploaded")

    try:
        with ZipFile(io.BytesIO(data)) as zip_file:
            files = zip_file.namelist()
            if "extension.toml" not in files:
                return web.HTTPBadRequest(text="Invalid extension: extension.toml not found")

            try:
                import rtoml

                manifest_data = rtoml.load(zip_file.read("extension.toml").decode("utf-8"))
                ext_id = manifest_data.get("extension", {}).get("id", "unknown")
                ext_version = manifest_data.get("extension", {}).get("version", "0.0.0")
            except Exception as e:
                return web.HTTPBadRequest(text=f"Invalid extension.toml: {e}")

            target_dir = EXTENSIONS_DIR / f"{ext_id}-{ext_version}"
            EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
            zip_file.extractall(target_dir)

    except BadZipFile:
        return web.HTTPBadRequest(text="Invalid extension: not a valid ZIP file")

    return web.json_response({"id": ext_id, "version": ext_version})


async def install_from_url(request: web.Request) -> web.Response:
    """Install extension from URL."""
    await get_authorized_user(request)

    data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return web.HTTPBadRequest(text="URL is required")

    if not url.lower().endswith(".zip"):
        return web.HTTPBadRequest(text="URL must point to a .zip file")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return web.HTTPBadRequest(text=f"Failed to download: HTTP {response.status}")
                zip_data = await response.read()
    except Exception as e:
        return web.HTTPBadRequest(text=f"Failed to download: {e}")

    try:
        with ZipFile(io.BytesIO(zip_data)) as zip_file:
            files = zip_file.namelist()
            if "extension.toml" not in files:
                return web.HTTPBadRequest(text="Invalid extension: extension.toml not found")

            try:
                import rtoml

                manifest_data = rtoml.load(zip_file.read("extension.toml").decode("utf-8"))
                ext_id = manifest_data.get("extension", {}).get("id", "unknown")
                ext_version = manifest_data.get("extension", {}).get("version", "0.0.0")
            except Exception as e:
                return web.HTTPBadRequest(text=f"Invalid extension.toml: {e}")

            target_dir = EXTENSIONS_DIR / f"{ext_id}-{ext_version}"
            EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
            zip_file.extractall(target_dir)

    except BadZipFile:
        return web.HTTPBadRequest(text="Invalid extension: not a valid ZIP file")

    return web.json_response({"id": ext_id, "version": ext_version})


async def uninstall(request: web.Request) -> web.Response:
    """Uninstall an extension by folder name."""
    await get_authorized_user(request)

    data = await request.json()
    folder = data.get("folder", "").strip()
    if not folder:
        return web.HTTPBadRequest(text="Folder name is required")

    # Security: ensure folder doesn't contain path traversal
    if ".." in folder or "/" in folder or "\\" in folder:
        return web.HTTPBadRequest(text="Invalid folder name")

    target_dir = EXTENSIONS_DIR / folder
    if not target_dir.exists():
        return web.HTTPNotFound(text=f"Extension folder '{folder}' not found")

    if not target_dir.is_dir():
        return web.HTTPBadRequest(text="Not a valid extension folder")

    try:
        shutil.rmtree(target_dir)
    except OSError as e:
        return web.HTTPInternalServerError(text=f"Failed to remove extension: {e}")

    return web.json_response({"ok": True})


async def set_visibility(request: web.Request) -> web.Response:
    """Set visibility of an extension to players for a specific game. DM only."""
    await get_authorized_user(request)
    data = await request.json()
    folder = data.get("folder", "").strip()
    room_creator = data.get("roomCreator", "").strip()
    room_name = data.get("roomName", "").strip()
    visible = data.get("visibleToPlayers", False)
    if not folder:
        return web.HTTPBadRequest(text="Folder name is required")
    if not room_creator or not room_name:
        return web.HTTPBadRequest(text="roomCreator and roomName are required")
    if ".." in folder or "/" in folder or "\\" in folder:
        return web.HTTPBadRequest(text="Invalid folder name")
    room_key = _room_key(room_creator, room_name)
    _set_room_visibility(room_key, folder, bool(visible))
    return web.json_response({"ok": True})


async def serve_extension_ui(request: web.Request) -> web.Response:
    """Serve extension UI file (e.g. ui/index.html) or UI assets. Requires auth."""
    await get_authorized_user(request)
    folder = request.match_info.get("folder", "").strip()
    if not folder or ".." in folder or "/" in folder or "\\" in folder:
        return web.HTTPBadRequest(text="Invalid folder name")

    ext_dir = EXTENSIONS_DIR / folder
    if not ext_dir.exists() or not ext_dir.is_dir():
        return web.HTTPNotFound(text="Extension not found")

    subpath = request.match_info.get("path", "").strip()
    manifest = ext_dir / "extension.toml"
    entry = "ui/index.html"
    if manifest.exists():
        try:
            import rtoml

            data = rtoml.load(manifest)
            entry = data.get("extension", {}).get("entry", "ui/index.html")
        except Exception:
            pass

    if subpath:
        # Serve asset: ui_path = ext_dir / "ui" / subpath
        ui_dir = ext_dir / "ui"
        if ".." in subpath or subpath.startswith("/"):
            return web.HTTPForbidden(text="Invalid path")
        file_path = (ui_dir / subpath).resolve()
        try:
            file_path.relative_to(ext_dir.resolve())
        except ValueError:
            return web.HTTPForbidden(text="Invalid path")
        if not file_path.exists():
            return web.HTTPNotFound(text="Asset not found")
        if file_path.is_dir():
            index_path = file_path / "index.html"
            if index_path.is_file():
                return web.FileResponse(index_path)
            return web.HTTPNotFound(text="Asset not found")
        return web.FileResponse(file_path)

    ui_path = ext_dir / entry
    if not ui_path.exists() or not ui_path.is_file():
        return web.HTTPNotFound(text="Extension UI not found")

    try:
        ui_path.resolve().relative_to(ext_dir.resolve())
    except ValueError:
        return web.HTTPForbidden(text="Invalid path")

    return web.FileResponse(ui_path)
