"""Watabou extension - image importing API."""

import uuid
import aiohttp
from aiohttp import web

from ....auth import get_authorized_user
from ....utils import STATIC_DIR


async def import_image(request: web.Request) -> web.Response:
    """Download image from Watabou and save to local temp."""
    await get_authorized_user(request)

    data = await request.json() or {}
    url = data.get("url")
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

        # Save to static temp
        temp_dir = STATIC_DIR / "temp" / "watabou"
        temp_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.png"
        filepath = temp_dir / filename
        filepath.write_bytes(img_bytes)

        local_url = f"/static/temp/watabou/{filename}"
        
        # We don't have exact grid info for Watabou, so we return a default guess or the user will resize
        return web.json_response(
            {
                "url": local_url,
                "gridCells": {"width": 40, "height": 40}, # Default fallback
            }
        )

    except Exception as e:
        return web.HTTPInternalServerError(text=f"Import failed: {e}")
