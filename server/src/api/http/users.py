from aiohttp import web
from aiohttp_security import forget

from ...auth import get_authorized_user
from ...config import cfg


async def set_email(request: web.Request):
    user = await get_authorized_user(request)
    data = await request.json()
    user.email = data["email"]
    user.save()
    return web.HTTPOk()


async def set_password(request: web.Request):
    user = await get_authorized_user(request)
    data = await request.json()
    user.set_password(data["password"])
    user.save()
    return web.HTTPOk()


async def delete_account(request: web.Request):
    user = await get_authorized_user(request)
    user.delete_instance(recursive=True)
    response = web.HTTPOk()
    await forget(request, response)
    return response


async def set_extensions_enabled(request: web.Request):
    user = await get_authorized_user(request)
    admin_name = (cfg().general.admin_user or "admin").strip()
    if not admin_name or user.name.lower() != admin_name.lower():
        raise web.HTTPForbidden(reason="Only the server administrator can enable extensions.")
    data = await request.json()
    enabled = bool(data["enabled"])
    opts = user.default_options
    opts.extensions_enabled = enabled
    opts.save()
    return web.HTTPOk()
