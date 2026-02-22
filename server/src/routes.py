import os
import sys

import aiohttp
from aiohttp import web

from .api import http
from .api.http import auth, extensions, mods, notifications, rooms, server, users, version
from .app import app as main_app
from .config import cfg
from .utils import ASSETS_DIR, EXTENSIONS_DIR, FILE_DIR, STATIC_DIR, THUMBNAILS_DIR

subpath = os.environ.get("PA_BASEPATH", "/")
if subpath[-1] == "/":
    subpath = subpath[:-1]


def __replace_config_data(data: bytes) -> bytes:
    config = cfg()

    if not config.general.allow_signups:
        data = data.replace(b'name="PA-signup" content="true"', b'name="PA-signup" content="false"')
    if not config.mail or not config.mail.enabled:
        data = data.replace(b'name="PA-mail" content="true"', b'name="PA-mail" content="false"')
    return data


async def root(request):
    template = "index.html"
    with open(FILE_DIR / "templates" / template, "rb") as f:
        data = __replace_config_data(f.read())
        return web.Response(body=data, content_type="text/html")


async def root_dev(request):
    port = 8080
    target_url = f"http://localhost:{port}{request.rel_url}"
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    headers["Host"] = f"localhost:{port}"
    data = await request.read()
    async with aiohttp.ClientSession() as client:
        async with client.get(target_url, headers=headers, data=data) as response:
            raw = __replace_config_data(await response.read())
    return web.Response(body=raw, status=response.status, headers=response.headers)


# MAIN ROUTES

main_app.router.add_static(f"{subpath}/static/assets", ASSETS_DIR)
main_app.router.add_static(f"{subpath}/static/thumbnails", THUMBNAILS_DIR)
main_app.router.add_static(f"{subpath}/static", STATIC_DIR)


def _make_guida_docs_handler(docs_dir):
    """Handler che serve i file dalla cartella docs; per le directory restituisce index.html (add_static restituisce 403)."""
    docs_dir = docs_dir.resolve()

    async def _serve(request):
        path = request.match_info.get("path", "").strip().lstrip("/")
        if path and (".." in path or path.startswith("/")):
            return web.HTTPForbidden(text="Invalid path")
        file_path = (docs_dir / path).resolve() if path else docs_dir
        try:
            file_path.relative_to(docs_dir)
        except ValueError:
            return web.HTTPForbidden(text="Invalid path")
        if not file_path.exists():
            return web.HTTPNotFound(text="Not found")
        if file_path.is_dir():
            index_path = file_path / "index.html"
            if index_path.is_file():
                return web.FileResponse(index_path)
            return web.HTTPNotFound(text="Not found")
        return web.FileResponse(file_path)

    return _serve


# Documentazione Guida: italiano (docs) e inglese (docs-en) - lingua da locale utente
_guida_docs_it = EXTENSIONS_DIR / "Guida" / "docs"
_guida_docs_en = EXTENSIONS_DIR / "Guida" / "docs-en"
if _guida_docs_it.exists() and _guida_docs_it.is_dir():
    _serve_it = _make_guida_docs_handler(_guida_docs_it)
    main_app.router.add_get(f"{subpath}/guida-docs", _serve_it)
    main_app.router.add_get(f"{subpath}/guida-docs/", _serve_it)
    main_app.router.add_get(f"{subpath}/guida-docs/{{path:.+}}", _serve_it)
if _guida_docs_en.exists() and _guida_docs_en.is_dir():
    _serve_en = _make_guida_docs_handler(_guida_docs_en)
    main_app.router.add_get(f"{subpath}/guida-docs-en", _serve_en)
    main_app.router.add_get(f"{subpath}/guida-docs-en/", _serve_en)
    main_app.router.add_get(f"{subpath}/guida-docs-en/{{path:.+}}", _serve_en)
main_app.router.add_get(f"{subpath}/api/auth", auth.is_authed)
main_app.router.add_post(f"{subpath}/api/users/email", users.set_email)
main_app.router.add_post(f"{subpath}/api/users/password", users.set_password)
main_app.router.add_post(f"{subpath}/api/users/delete", users.delete_account)
main_app.router.add_post(f"{subpath}/api/users/extensions-enabled", users.set_extensions_enabled)
main_app.router.add_post(f"{subpath}/api/login", auth.login)
main_app.router.add_post(f"{subpath}/api/register", auth.register)
main_app.router.add_post(f"{subpath}/api/logout", auth.logout)
main_app.router.add_post(f"{subpath}/api/forgot-password", auth.forgot_password)
main_app.router.add_post(f"{subpath}/api/reset-password", auth.reset_password)
main_app.router.add_get(f"{subpath}/api/server/upload_limit", server.get_limit)
main_app.router.add_get(f"{subpath}/api/rooms", rooms.get_list)
main_app.router.add_post(f"{subpath}/api/rooms", rooms.create)
main_app.router.add_patch(f"{subpath}/api/rooms/{{creator}}/{{roomname}}", rooms.patch)
main_app.router.add_delete(f"{subpath}/api/rooms/{{creator}}/{{roomname}}", rooms.delete)
main_app.router.add_patch(f"{subpath}/api/rooms/{{creator}}/{{roomname}}/info", rooms.set_info)
main_app.router.add_get(f"{subpath}/api/rooms/{{creator}}/{{roomname}}/export", rooms.export)
main_app.router.add_get(f"{subpath}/api/rooms/{{creator}}/export", rooms.export_all)
main_app.router.add_post(f"{subpath}/api/rooms/import/{{name}}", rooms.import_info)
main_app.router.add_post(f"{subpath}/api/rooms/import/{{name}}/{{chunk}}", rooms.import_chunk)
main_app.router.add_post(f"{subpath}/api/invite", http.claim_invite)
main_app.router.add_get(f"{subpath}/api/version", version.get_version)
main_app.router.add_get(f"{subpath}/api/changelog", version.get_changelog)
main_app.router.add_get(f"{subpath}/api/notifications", notifications.collect)
main_app.router.add_post(f"{subpath}/api/mod/upload", mods.upload)
main_app.router.add_get(f"{subpath}/api/extensions", extensions.list_extensions)
main_app.router.add_patch(f"{subpath}/api/extensions/visibility", extensions.set_visibility)
main_app.router.add_post(f"{subpath}/api/extensions/install/zip", extensions.install_from_zip)
main_app.router.add_post(f"{subpath}/api/extensions/install/url", extensions.install_from_url)
main_app.router.add_post(f"{subpath}/api/extensions/uninstall", extensions.uninstall)
main_app.router.add_get(f"{subpath}/api/extensions/documents/list", extensions.documents.list_documents)
main_app.router.add_get(
    f"{subpath}/api/extensions/documents/serve/{{file_hash}}",
    extensions.documents.serve_document,
)
main_app.router.add_post(f"{subpath}/api/extensions/documents/upload", extensions.documents.upload_document)
main_app.router.add_post(f"{subpath}/api/extensions/documents/delete", extensions.documents.delete_document)
main_app.router.add_post(f"{subpath}/api/extensions/documents/folder", extensions.documents.create_folder)
main_app.router.add_patch(f"{subpath}/api/extensions/documents/rename", extensions.documents.rename_document)
main_app.router.add_patch(f"{subpath}/api/extensions/documents/move", extensions.documents.move_document)
main_app.router.add_post(
    f"{subpath}/api/extensions/documents/generate-thumbnails",
    extensions.documents.generate_thumbnails,
)
main_app.router.add_patch(
    f"{subpath}/api/extensions/documents/visibility",
    extensions.documents.toggle_document_visibility,
)
main_app.router.add_get(f"{subpath}/api/extensions/assets-installer/list", extensions.assets_installer.list_installs)
main_app.router.add_get(f"{subpath}/api/extensions/assets-installer/folders", extensions.assets_installer.list_folders)
main_app.router.add_post(f"{subpath}/api/extensions/assets-installer/upload", extensions.assets_installer.upload_zip)
main_app.router.add_post(f"{subpath}/api/extensions/assets-installer/uninstall", extensions.assets_installer.uninstall)
main_app.router.add_get(f"{subpath}/api/extensions/character-sheet/list", extensions.character_sheet.list_all)
main_app.router.add_get(
    f"{subpath}/api/extensions/character-sheet/sheet-for-character/{{character_id}}",
    extensions.character_sheet.get_sheet_for_character,
)
main_app.router.add_get(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}", extensions.character_sheet.get_sheet)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/sheet", extensions.character_sheet.create_sheet)
main_app.router.add_put(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}", extensions.character_sheet.update_sheet)
main_app.router.add_delete(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}", extensions.character_sheet.delete_sheet)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}/duplicate", extensions.character_sheet.duplicate_sheet)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}/associate", extensions.character_sheet.associate_sheet)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}/dissociate", extensions.character_sheet.dissociate_sheet)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/sheet/{{sheet_id}}/visibility", extensions.character_sheet.toggle_sheet_visibility)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/upload", extensions.character_sheet.upload_portrait)
main_app.router.add_post(f"{subpath}/api/extensions/character-sheet/default", extensions.character_sheet.set_default)
main_app.router.add_get(f"{subpath}/api/extensions/character-sheet/default", extensions.character_sheet.get_default)
main_app.router.add_post(f"{subpath}/api/extensions/dungeongen/generate", extensions.dungeongen.generate)
main_app.router.add_post(f"{subpath}/api/extensions/watabou/import", extensions.watabou.import_image)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/db",
    extensions.compendium.get_db,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/compendiums",
    extensions.compendium.get_compendiums,
)
main_app.router.add_post(
    f"{subpath}/api/extensions/compendium/compendiums",
    extensions.compendium.install_compendium,
)
main_app.router.add_delete(
    f"{subpath}/api/extensions/compendium/compendiums/{{compendium_id}}",
    extensions.compendium.uninstall_compendium,
)
main_app.router.add_put(
    f"{subpath}/api/extensions/compendium/compendiums/{{compendium_id}}/default",
    extensions.compendium.set_default_compendium,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/collections",
    extensions.compendium.get_collections,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/collections/{{collection_slug}}/items",
    extensions.compendium.get_items,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/item",
    extensions.compendium.get_item,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/search",
    extensions.compendium.search,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/compendium/names",
    extensions.compendium.get_names,
)
main_app.router.add_get(f"{subpath}/api/extensions/ambient-music/list", extensions.ambient_music.list_audio)
main_app.router.add_get(f"{subpath}/api/extensions/ambient-music/playlists/list", extensions.ambient_music.list_playlists)
main_app.router.add_get(
    f"{subpath}/api/extensions/ambient-music/serve/{{file_hash}}",
    extensions.ambient_music.serve_audio,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/ambient-music/playlists/serve/{{file_hash}}",
    extensions.ambient_music.serve_playlist,
)
main_app.router.add_post(f"{subpath}/api/extensions/ambient-music/playlists/upload", extensions.ambient_music.upload_playlist)
main_app.router.add_get(f"{subpath}/api/extensions/openrouter/models", extensions.openrouter.get_models)
main_app.router.add_post(f"{subpath}/api/extensions/openrouter/chat", extensions.openrouter.chat)
main_app.router.add_get(f"{subpath}/api/extensions/openrouter/settings", extensions.openrouter.get_settings)
main_app.router.add_post(f"{subpath}/api/extensions/openrouter/settings", extensions.openrouter.set_settings)
main_app.router.add_post(f"{subpath}/api/extensions/openrouter/transform-image", extensions.openrouter.transform_image)
main_app.router.add_get(
    f"{subpath}/api/extensions/{{folder}}/ui/{{path:.+}}",
    extensions.serve_extension_ui,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/{{folder}}/ui",
    extensions.serve_extension_ui,
)
main_app.router.add_get(
    f"{subpath}/api/extensions/{{folder}}/ui/",
    extensions.serve_extension_ui,
)

TAIL_REGEX = "/{tail:(?!api).*}"
if "dev" in sys.argv:
    main_app.router.add_route("*", TAIL_REGEX, root_dev)
else:
    main_app.router.add_route("*", TAIL_REGEX, root)
