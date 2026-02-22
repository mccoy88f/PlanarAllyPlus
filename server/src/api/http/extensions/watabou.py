import hashlib
import uuid
from pathlib import Path

import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....db.models.asset import Asset
from ....utils import ASSETS_DIR, STATIC_DIR, get_asset_hash_subpath


async def import_image(request: web.Request) -> web.Response:
    """Download image from Watabou and save to local temp."""
    user = await get_authorized_user(request)

    data = await request.json() or {}
    url = data.get("url")
    generator_name = data.get("generator", "Generic")
    if not url:
        return web.HTTPBadRequest(text="URL is required")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return web.HTTPBadRequest(text=f"Failed to download image: HTTP {response.status}")
                
                content_type = response.headers.get("Content-Type", "").lower()
                if "image/" not in content_type:
                    return web.HTTPBadRequest(text=f"The URL did not return an image (got {content_type}). Note: Direct import from Watabou is limited by browser security.")
                
                img_bytes = await response.read()
                
                # Double check PNG signature if possible
                if content_type == "image/png" and not img_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                    return web.HTTPBadRequest(text="The downloaded file is not a valid PNG image.")

        # Save to assets
        sh = hashlib.sha1(img_bytes)
        hashname = sh.hexdigest()
        full_hash_path = ASSETS_DIR / get_asset_hash_subpath(hashname)

        if not full_hash_path.exists():
            full_hash_path.parent.mkdir(parents=True, exist_ok=True)
            full_hash_path.write_bytes(img_bytes)

        folder = _get_or_create_watabou_folder(user, generator_name)
        filename = f"{generator_name}_{uuid.uuid4().hex[:8]}.png"
        
        asset = Asset.create(name=filename, file_hash=hashname, owner=user, parent=folder)

        from ....thumbnail import generate_thumbnail_for_asset
        generate_thumbnail_for_asset(filename, hashname)

        local_url = f"/static/assets/{get_asset_hash_subpath(hashname).as_posix()}"
        shape_name = Path(filename).stem
        
        # We don't have exact grid info for Watabou, so we return a default guess or the user will resize
        return web.json_response(
            {
                "url": local_url,
                "assetId": asset.id,
                "name": shape_name,
                "gridCells": {"width": 40, "height": 40}, # Default fallback
            }
        )

    except Exception as e:
        return web.HTTPInternalServerError(text=f"Import failed: {e}")


def _get_or_create_watabou_folder(user, generator_name: str):
    root = Asset.get_or_create_extension_folder(user, "watabou-generator")
    if not generator_name:
        return root
    folder = root.get_child(generator_name)
    if folder is None:
        folder = Asset.create(name=generator_name, owner=user, parent=root)
    return folder


async def upload_image(request: web.Request) -> web.Response:
    """Upload a Watabou map image to the Asset Manager."""
    user = await get_authorized_user(request)

    reader = await request.multipart()
    filename = "map.png"
    generator_name = "Generic"
    data = b""

    async for part in reader:
        if part.name == "file":
            filename = part.filename or "map.png"
            data = await part.read()
        elif part.name == "generator":
            generator_name = (await part.text()).strip() or "Generic"

    if not data:
        return web.HTTPBadRequest(text="No file in 'file' field")

    # Only allow PNG/JPG for maps
    ext = Path(filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg"}:
        return web.HTTPBadRequest(text=f"Invalid file type: {ext}")

    sh = hashlib.sha1(data)
    hashname = sh.hexdigest()
    full_hash_path = ASSETS_DIR / get_asset_hash_subpath(hashname)

    if not full_hash_path.exists():
        full_hash_path.parent.mkdir(parents=True, exist_ok=True)
        full_hash_path.write_bytes(data)

    folder = _get_or_create_watabou_folder(user, generator_name)
    asset = Asset.create(name=filename, file_hash=hashname, owner=user, parent=folder)

    # Generate thumbnail
    from ....thumbnail import generate_thumbnail_for_asset

    generate_thumbnail_for_asset(filename, hashname)

    url = f"/static/assets/{get_asset_hash_subpath(hashname).as_posix()}"
    return web.json_response(
        {
            "ok": True,
            "url": url,
            "assetId": asset.id,
            "name": Path(filename).stem,
            "gridCells": {"width": 40, "height": 40},
        }
    )
