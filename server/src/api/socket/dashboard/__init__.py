from aiohttp import web

from ....api.socket.constants import DASHBOARD_NS
from ....app import sio
from ....auth import get_authorized_user
from ....config import cfg
from ....logs import logger
from ....state.dashboard import dashboard_state
from . import campaign  # noqa: F401


@sio.on("connect", namespace=DASHBOARD_NS)
async def dashboard_connect(sid: str, environ):
    try:
        user = await get_authorized_user(environ["aiohttp.request"])
    except web.HTTPUnauthorized:
        return False
    if user is not None:
        await dashboard_state.add_sid(sid, user)
        config = cfg()
        if config.general.enable_export:
            await sio.emit("Export.Enabled", True, to=sid, namespace=DASHBOARD_NS)
        admin_name = (config.general.admin_user or "admin").strip()
        is_admin_match = admin_name and user.name.lower() == admin_name.lower()
        logger.info(
            f"Dashboard connect: user={user.name!r} admin_config={admin_name!r} is_admin={is_admin_match}"
        )
        if is_admin_match:
            await sio.emit("Admin.Enabled", True, to=sid, namespace=DASHBOARD_NS)


@sio.on("disconnect", namespace=DASHBOARD_NS)
async def disconnect(sid):
    if not dashboard_state.has_sid(sid):
        return

    await dashboard_state.remove_sid(sid)
