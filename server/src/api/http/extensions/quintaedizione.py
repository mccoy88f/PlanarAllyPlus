"""Quinta Edizione extension - knowledge base from quintaedizione.online."""

import json

from aiohttp import web

from ....auth import get_authorized_user
from ....utils import EXTENSIONS_DIR

DB_PATH = EXTENSIONS_DIR / "quintaedizione.online" / "db" / "quintaedizione-export.json"


async def get_db(request: web.Request) -> web.Response:
    """Return the full knowledge base JSON."""
    await get_authorized_user(request)

    if not DB_PATH.exists():
        return web.json_response({"error": "Database not found", "collections": []})

    try:
        with open(DB_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return web.json_response(
            {"error": str(e), "collections": []},
            status=500,
        )

    return web.json_response(data)
