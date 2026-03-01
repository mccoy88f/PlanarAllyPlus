"""Assets Installer extension - upload ZIP files to extract into assets folder."""

import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import traceback

from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.asset import Asset
from ....thumbnail import generate_thumbnail_for_asset
from ....utils import ASSETS_DIR, DATA_DIR, THUMBNAILS_DIR, get_asset_hash_subpath

INSTALLER_BASE = "assets_installer"
MANIFEST_FILE = DATA_DIR / "assets_installer_installs.json"


def _load_manifest() -> list[dict]:
    """Load installations manifest."""
    if not MANIFEST_FILE.exists():
        return []
    try:
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("installs", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_manifest(installs: list[dict]) -> None:
    """Save installations manifest."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump({"installs": installs}, f, indent=2)


def _safe_zip_path(name: str) -> bool:
    """Check if zip member path is safe (no path traversal)."""
    normalized = Path(name).as_posix()
    if ".." in normalized or normalized.startswith("/"):
        return False
    return True


def _safe_target_path(path: str) -> Path | None:
    """Validate target path and return path relative to ASSETS_DIR, or None if invalid."""
    if not path or not path.strip():
        return Path("")
    clean = path.strip().replace("\\", "/").rstrip("/")
    if ".." in clean or clean.startswith("/"):
        return None
    parts = [p for p in clean.split("/") if p]
    for p in parts:
        if not p or p in (".", ".."):
            return None
    return Path(*parts)


def _get_or_create_target_folder(user, target_path: str):
    """Resolve target_path to an Asset folder. Empty path = root of assets."""
    root = Asset.get_root_folder(user)
    if not target_path or not target_path.strip():
        return root
    parent = root
    for part in target_path.strip().replace("\\", "/").strip("/").split("/"):
        if part:
            parent, _ = Asset.get_or_create(name=part, owner=user, parent=parent)
    return parent


async def upload_zip(request: web.Request) -> web.Response:
    """Upload a ZIP file, extract to hash storage, and register assets in DB."""
    user = await get_authorized_user(request)

    reader = await request.multipart()
    data = b""
    filename = "archive.zip"
    target_path = ""
    static_extract = False
    async for part in reader:
        if part.name == "file":
            data = await part.read()
            if part.filename:
                filename = part.filename
        elif part.name == "targetPath":
            raw = await part.read()
            target_path = raw.decode("utf-8").strip() if raw else ""
        elif part.name == "staticExtract":
            raw = await part.read()
            static_extract = (raw.decode("utf-8").strip().lower() == "true") if raw else False

    if not data:
        return web.HTTPBadRequest(text="No file in 'file' field")

    safe_target = _safe_target_path(target_path)
    if safe_target is None:
        return web.HTTPBadRequest(text="Invalid target path")

    try:
        with ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if not names:
                return web.HTTPBadRequest(text="ZIP file is empty")

            install_id = str(uuid.uuid4())[:8]
            install_name = Path(filename).stem

            target_folder = _get_or_create_target_folder(user, target_path)
            base_path_str = str(safe_target).replace("\\", "/") if str(safe_target) else ""

            files_extracted: list[str] = []
            asset_ids: list[int] = []
            file_hashes: list[str] = []

            for name in names:
                if not _safe_zip_path(name):
                    continue
                info = zf.getinfo(name)
                if info.is_dir():
                    continue
                rel = Path(name).as_posix()
                if not rel or rel == ".":
                    continue

                file_data = zf.read(name)
                
                if static_extract:
                    # Extract directly to the folder structure
                    full_static_path = ASSETS_DIR / base_path_str / rel
                    full_static_path.parent.mkdir(parents=True, exist_ok=True)
                    full_static_path.write_bytes(file_data)
                    files_extracted.append(rel)
                else:
                    hashname = hashlib.sha1(file_data).hexdigest()
                    full_hash_path = ASSETS_DIR / get_asset_hash_subpath(hashname)

                    if not full_hash_path.exists():
                        full_hash_path.parent.mkdir(parents=True, exist_ok=True)
                        full_hash_path.write_bytes(file_data)

                    parent_folder = target_folder
                    rel_path = Path(rel)
                    for part in rel_path.parent.parts:
                        if part:
                            parent_folder, _ = Asset.get_or_create(
                                name=part, owner=user, parent=parent_folder
                            )

                    asset = Asset.create(
                        name=rel_path.name,
                        file_hash=hashname,
                        owner=user,
                        parent=parent_folder,
                    )
                    asset_ids.append(asset.id)
                    file_hashes.append(hashname)
                    files_extracted.append(rel)

                    try:
                        generate_thumbnail_for_asset(rel_path.name, hashname)
                    except Exception:
                        pass

            folders_created: set[str] = {str(Path(f).parent) for f in files_extracted if "/" in f or "\\" in f}
            folders_created.discard(".")
            folders_sorted = sorted(folders_created, key=lambda x: x.count("/"), reverse=True)

            install_record = {
                "id": install_id,
                "name": install_name,
                "files": files_extracted,
                "folders": folders_sorted,
                "basePath": base_path_str,
                "assetIds": asset_ids,
                "fileHashes": file_hashes,
                "installedAt": datetime.now(timezone.utc).isoformat(),
            }

            installs = _load_manifest()
            installs.append(install_record)
            _save_manifest(installs)

            return web.json_response({
                "id": install_id,
                "name": install_name,
                "fileCount": len(files_extracted),
            })

    except BadZipFile:
        return web.HTTPBadRequest(text="Invalid or corrupted ZIP file")
    except OSError as e:
        return web.HTTPInternalServerError(text=f"Failed to extract: {e}")
    except Exception as e:
        return web.HTTPInternalServerError(text=f"Upload error: {e}")


def _scan_db_folder_tree(user, parent_id: int | None, rel_path: str) -> list[dict]:
    """Recursively build folder tree from DB."""
    folders = Asset.select().where((Asset.owner == user) & (Asset.parent == parent_id) & (Asset.file_hash == None)).order_by(Asset.name)
    children = []
    for f in folders:
        path = f"{rel_path}/{f.name}" if rel_path else f.name
        children.append({
            "name": f.name,
            "path": path,
            "children": _scan_db_folder_tree(user, f.id, path)
        })
    return children


async def list_folders(request: web.Request) -> web.Response:
    """List folder tree for upload target selection."""
    user = await get_authorized_user(request)
    root_folder = Asset.get_root_folder(user)
    
    tree = {
        "name": "/",
        "path": "",
        "children": _scan_db_folder_tree(user, root_folder.id, "")
    }
    return web.json_response({"tree": tree})


async def list_installs(request: web.Request) -> web.Response:
    """List installed asset packs."""
    await get_authorized_user(request)
    installs = _load_manifest()
    result = [
        {
            "id": i["id"],
            "name": i["name"],
            "fileCount": len(i.get("files", [])),
            "basePath": i.get("basePath", ""),
            "installedAt": i.get("installedAt"),
        }
        for i in installs
    ]
    result.sort(key=lambda x: (x["name"] or "").lower())
    return web.json_response({"installs": result})


async def uninstall(request: web.Request) -> web.Response:
    """Uninstall an asset pack: remove files and empty folders."""
    await get_authorized_user(request)

    data = await request.json()
    install_id = data.get("id", "").strip()
    if not install_id:
        return web.HTTPBadRequest(text="Install id is required")

    if ".." in install_id or "/" in install_id or "\\" in install_id:
        return web.HTTPBadRequest(text="Invalid install id")

    installs = _load_manifest()
    idx = next((i for i, x in enumerate(installs) if x.get("id") == install_id), None)
    if idx is None:
        return web.HTTPNotFound(text="Installation not found")

    record = installs[idx]

    try:
        asset_ids = record.get("assetIds", [])
        file_hashes = record.get("fileHashes", [])
        if asset_ids:
            # Pre-flight check: ensure no asset is locked by a Character RESTRICT constraint
            in_use = []
            for aid in asset_ids:
                try:
                    asset = Asset.get_by_id(aid)
                    if asset.characters.count() > 0:
                        in_use.append(asset.name)
                except Asset.DoesNotExist:
                    pass
            
            if in_use:
                locked_names = ", ".join(in_use[:3])
                if len(in_use) > 3:
                    locked_names += " and others"
                return web.HTTPBadRequest(text=f"Cannot uninstall: Assets are in use by Characters ({locked_names})")

            for aid in asset_ids:
                try:
                    asset = Asset.get_by_id(aid)
                    fh = asset.file_hash
                    asset.delete_instance()
                    if fh and not Asset.select().where(Asset.file_hash == fh).exists():
                        hp = ASSETS_DIR / get_asset_hash_subpath(fh)
                        if hp.exists():
                            hp.unlink()
                        base = str(get_asset_hash_subpath(fh))
                        for ext in (".thumb.webp", ".thumb.jpeg"):
                            tp = THUMBNAILS_DIR / f"{base}{ext}"
                            if tp.exists():
                                tp.unlink()
                except Asset.DoesNotExist:
                    pass
        else:
            base_path = record.get("basePath", "")
            if base_path:
                target_base = (ASSETS_DIR / base_path).resolve()
            else:
                target_base = ASSETS_DIR.resolve()
            if str(target_base).startswith(str(ASSETS_DIR.resolve())):
                for rel in record.get("files", []):
                    if _safe_zip_path(rel):
                        fp = target_base / rel
                        if fp.exists() and fp.is_file():
                            fp.unlink()
                for rel in sorted(record.get("folders", []), key=lambda x: x.count("/"), reverse=True):
                    if _safe_zip_path(rel):
                        fp = target_base / rel
                        if fp.exists() and fp.is_dir():
                            try:
                                fp.rmdir()
                            except OSError:
                                pass
                if target_base.exists() and target_base != ASSETS_DIR:
                    try:
                        target_base.rmdir()
                    except OSError:
                        pass

        installs.pop(idx)
        _save_manifest(installs)

        return web.json_response({"ok": True})
    except Exception as e:
        return web.HTTPInternalServerError(text=f"Failed to uninstall: {e}\n{traceback.format_exc()}")
