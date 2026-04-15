"""Persistenza e API HTTP per ACL risorse estensioni (chiave ``namespace:id``)."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from ....auth import get_authorized_user
from ....utils import DATA_DIR
from .permission_acl import ExtensionResourceAclPayload, acl_payload_from_dict, user_can_view_acl

RESOURCE_ACL_FILE = DATA_DIR / "extension_resource_acl.json"


def _load_raw() -> dict[str, Any]:
    if not RESOURCE_ACL_FILE.exists():
        return {}
    try:
        with open(RESOURCE_ACL_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESOURCE_ACL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_stored_acl_dict(resource_key: str) -> dict[str, Any] | None:
    """Ritorna il dict ACL o ``None`` se assente."""
    raw = _load_raw()
    v = raw.get(resource_key)
    return v if isinstance(v, dict) else None


def get_stored_acl(resource_key: str) -> ExtensionResourceAclPayload | None:
    d = get_stored_acl_dict(resource_key)
    if d is None:
        return None
    try:
        return acl_payload_from_dict(d)
    except Exception:
        return None


def set_stored_acl_payload(resource_key: str, acl: ExtensionResourceAclPayload) -> None:
    """Scrive l'ACL senza controlli HTTP (uso interno da altre estensioni)."""
    raw = _load_raw()
    raw[resource_key] = acl.model_dump(by_alias=True)
    _save_raw(raw)


async def get_resource_acl(request: web.Request) -> web.Response:
    """GET /api/extensions/resource-acl?key=documents:123"""
    user = await get_authorized_user(request)
    key = request.query.get("key", "").strip()
    if not key or ":" not in key:
        return web.HTTPBadRequest(text="Invalid key")

    data = get_stored_acl_dict(key)
    if data is None:
        return web.json_response({"acl": None})

    try:
        acl = acl_payload_from_dict(data)
    except Exception:
        return web.HTTPBadRequest(text="Invalid stored ACL")

    if not user_can_view_acl(user.name, acl):
        return web.HTTPForbidden(text="Cannot read this ACL")

    return web.json_response({"acl": data})


async def put_resource_acl(request: web.Request) -> web.Response:
    """PUT /api/extensions/resource-acl — body: { key, acl: ExtensionResourceAclPayload }"""
    user = await get_authorized_user(request)
    try:
        body = await request.json()
    except Exception:
        return web.HTTPBadRequest(text="Invalid JSON")

    key = str(body.get("key", "")).strip()
    acl_obj = body.get("acl")
    if not key or ":" not in key or not isinstance(acl_obj, dict):
        return web.HTTPBadRequest(text="key and acl object required")

    try:
        acl = acl_payload_from_dict(acl_obj)
    except Exception as e:
        return web.HTTPBadRequest(text=f"Invalid acl: {e}")

    if acl.creator_name != user.name:
        return web.HTTPForbidden(text="creatorName must match the authenticated user")

    raw = _load_raw()
    raw[key] = acl.model_dump(by_alias=True)
    _save_raw(raw)
    return web.json_response({"ok": True, "acl": acl.model_dump(by_alias=True)})


async def delete_resource_acl(request: web.Request) -> web.Response:
    """DELETE /api/extensions/resource-acl?key=... — solo il creatore (come da ACL salvata)."""
    user = await get_authorized_user(request)
    key = request.query.get("key", "").strip()
    if not key or ":" not in key:
        return web.HTTPBadRequest(text="Invalid key")

    raw = _load_raw()
    existing = raw.get(key)
    if not isinstance(existing, dict):
        return web.HTTPNotFound(text="ACL not found")
    try:
        acl = acl_payload_from_dict(existing)
    except Exception:
        return web.HTTPBadRequest(text="Invalid stored ACL")

    if acl.creator_name != user.name:
        return web.HTTPForbidden(text="Only the creator can remove ACL")

    del raw[key]
    _save_raw(raw)
    return web.json_response({"ok": True})
