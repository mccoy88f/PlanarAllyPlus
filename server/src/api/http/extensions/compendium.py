"""Compendium extension - multi-compendium knowledge base from JSON files."""

import json
import re
import uuid
from pathlib import Path

from aiohttp import web

from ....auth import get_authorized_user
from ....utils import EXTENSIONS_DIR

EXT_ID = "compendium"


def _ext_dir() -> Path:
    """Restituisce la cartella dell'estensione."""
    direct = EXTENSIONS_DIR / EXT_ID
    if direct.exists():
        return direct
    for p in EXTENSIONS_DIR.iterdir():
        if p.is_dir() and p.name.startswith(f"{EXT_ID}-"):
            return p
    return direct


def _db_dir() -> Path:
    d = _ext_dir() / "db"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slugify(name: str) -> str:
    """Genera uno slug da un nome."""
    s = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[-\s]+", "-", s).strip("-") or "compendium"


def _config_path() -> Path:
    return _db_dir() / "compendiums.json"


def _load_config() -> dict:
    path = _config_path()
    if not path.exists():
        return {"compendiums": [], "defaultId": None}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"compendiums": [], "defaultId": None}


def _save_config(config: dict) -> None:
    with open(_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _migrate_legacy() -> bool:
    """Migra quintaedizione-export.json a un compendium se config vuota."""
    config = _load_config()
    if config["compendiums"]:
        return True
    legacy_json = _db_dir() / "quintaedizione-export.json"
    if not legacy_json.exists():
        return False
    comp_id = str(uuid.uuid4())[:8]
    comp = {
        "id": comp_id,
        "name": "Quinta Edizione",
        "slug": "quinta-edizione",
        "jsonFile": "quintaedizione-export.json",
        "isDefault": True,
    }
    config["compendiums"] = [comp]
    config["defaultId"] = comp_id
    _save_config(config)
    return True


def _get_compendium(comp_id_or_slug: str) -> dict | None:
    """Cerca per id o slug."""
    config = _load_config()
    for c in config["compendiums"]:
        if c.get("id") == comp_id_or_slug or c.get("slug") == comp_id_or_slug:
            return c
    return None


def _resolve_compendium_id(comp_id_or_slug: str) -> str | None:
    """Ritorna l'id del compendium dato id o slug."""
    comp = _get_compendium(comp_id_or_slug)
    return comp.get("id") if comp else None


def _json_path(comp: dict) -> Path:
    return _db_dir() / (comp.get("jsonFile") or "compendium.json")


def _db_path(comp_id: str) -> Path:
    return _db_dir() / f"compendium-{comp_id}.db"


def _convert_json_to_sqlite(json_path: Path, db_path: Path) -> bool:
    """Converte JSON in SQLite. Ritorna True se OK."""
    import sqlite3

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    collections = data.get("collections", [])
    if not collections:
        return False
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE collections (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL)
    """)
    conn.execute("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL, slug TEXT NOT NULL,
            name TEXT NOT NULL, markdown TEXT NOT NULL,
            FOREIGN KEY (collection_id) REFERENCES collections(id), UNIQUE(collection_id, slug)
        )
    """)
    conn.execute("CREATE INDEX idx_items_collection ON items(collection_id)")
    conn.execute("CREATE INDEX idx_items_slug ON items(slug)")
    conn.execute("""
        CREATE VIRTUAL TABLE items_fts USING fts5(name, markdown, content='items', content_rowid='id', tokenize='unicode61')
    """)
    conn.execute("""
        CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
            INSERT INTO items_fts(rowid, name, markdown) VALUES (new.id, new.name, new.markdown);
        END
    """)
    conn.execute("""
        CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
            INSERT INTO items_fts(items_fts, rowid, name, markdown) VALUES ('delete', old.id, old.name, old.markdown);
        END
    """)
    conn.execute("""
        CREATE TRIGGER items_au AFTER UPDATE ON items BEGIN
            INSERT INTO items_fts(items_fts, rowid, name, markdown) VALUES ('delete', old.id, old.name, old.markdown);
            INSERT INTO items_fts(rowid, name, markdown) VALUES (new.id, new.name, new.markdown);
        END
    """)
    for coll in collections:
        slug = coll.get("slug", "")
        name = coll.get("name", slug)
        conn.execute("INSERT INTO collections (slug, name) VALUES (?, ?)", (slug, name))
        coll_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for item in coll.get("items", []):
            conn.execute(
                "INSERT INTO items (collection_id, slug, name, markdown) VALUES (?, ?, ?, ?)",
                (coll_id, item.get("slug", ""), item.get("name", ""), item.get("markdown", "")),
            )
    conn.commit()
    conn.close()
    return True


def _ensure_sqlite(comp_id: str) -> bool:
    """Converte JSON in SQLite se necessario per il compendium."""
    comp = _get_compendium(comp_id)
    if not comp:
        return False
    json_path = _json_path(comp)
    db_path = _db_path(comp_id)
    if db_path.exists():
        return True
    if not json_path.exists():
        return False
    return _convert_json_to_sqlite(json_path, db_path)


def _get_conn(comp_id: str):
    import sqlite3

    _ensure_sqlite(comp_id)
    return sqlite3.connect(_db_path(comp_id), check_same_thread=False)


# --- API handlers ---


async def get_compendiums(request: web.Request) -> web.Response:
    """Elenco compendi con id, name, slug, isDefault."""
    await get_authorized_user(request)
    _migrate_legacy()
    config = _load_config()
    comps_list = config["compendiums"]
    default_id = config.get("defaultId")
    if not default_id and len(comps_list) == 1:
        default_id = comps_list[0].get("id")
    comps = []
    for c in comps_list:
        comps.append({
            "id": c.get("id"),
            "name": c.get("name", "?"),
            "slug": c.get("slug", _slugify(c.get("name", ""))),
            "isDefault": c.get("id") == default_id,
        })
    return web.json_response({"compendiums": comps, "defaultId": default_id})


async def install_compendium(request: web.Request) -> web.Response:
    """Installa un compendio: POST multipart con name + file (JSON)."""
    await get_authorized_user(request)
    try:
        reader = await request.multipart()
        name = ""
        file_content = None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "name":
                name = (await part.read()).decode("utf-8").strip() or "Compendium"
            elif part.name == "file":
                file_content = await part.read()
        if not file_content:
            return web.json_response({"error": "File required"}, status=400)
        data = json.loads(file_content.decode("utf-8"))
        collections = data.get("collections", [])
        if not collections:
            return web.json_response({"error": "Invalid JSON: no collections"}, status=400)
        comp_id = str(uuid.uuid4())[:8]
        slug = _slugify(name)
        config = _load_config()
        existing_slugs = {c.get("slug") for c in config["compendiums"]}
        base_slug = slug
        i = 0
        while slug in existing_slugs:
            i += 1
            slug = f"{base_slug}-{i}"
        json_filename = f"compendium-{comp_id}.json"
        json_path = _db_dir() / json_filename
        with open(json_path, "wb") as f:
            f.write(file_content)
        comp = {
            "id": comp_id,
            "name": name,
            "slug": slug,
            "jsonFile": json_filename,
            "isDefault": len(config["compendiums"]) == 0,
        }
        config["compendiums"].append(comp)
        if comp["isDefault"]:
            config["defaultId"] = comp_id
        _save_config(config)
        _ensure_sqlite(comp_id)
        return web.json_response({
            "id": comp_id,
            "name": name,
            "slug": slug,
            "isDefault": comp["isDefault"],
        })
    except json.JSONDecodeError as e:
        return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def uninstall_compendium(request: web.Request) -> web.Response:
    """Disinstalla un compendio: DELETE /compendiums/:id."""
    await get_authorized_user(request)
    comp_id = request.match_info.get("compendium_id", "").strip()
    if not comp_id:
        return web.json_response({"error": "compendium_id required"}, status=400)
    config = _load_config()
    comps = [c for c in config["compendiums"] if c.get("id") != comp_id]
    if len(comps) == len(config["compendiums"]):
        return web.json_response({"error": "Compendium not found"}, status=404)
    comp_to_remove = _get_compendium(comp_id)
    config["compendiums"] = comps
    if config.get("defaultId") == comp_id:
        config["defaultId"] = comps[0]["id"] if comps else None
    _save_config(config)
    db_path = _db_path(comp_id)
    if db_path.exists():
        db_path.unlink(missing_ok=True)
    if comp_to_remove:
        json_path = _json_path(comp_to_remove)
        if json_path.exists():
            json_path.unlink(missing_ok=True)
    return web.json_response({"ok": True})


async def set_default_compendium(request: web.Request) -> web.Response:
    """Imposta compendio predefinito: PUT /compendiums/:id/default."""
    await get_authorized_user(request)
    comp_id = request.match_info.get("compendium_id", "").strip()
    if not comp_id:
        return web.json_response({"error": "compendium_id required"}, status=400)
    if not _get_compendium(comp_id):
        return web.json_response({"error": "Compendium not found"}, status=404)
    config = _load_config()
    config["defaultId"] = comp_id
    for c in config["compendiums"]:
        c["isDefault"] = c.get("id") == comp_id
    _save_config(config)
    return web.json_response({"ok": True, "defaultId": comp_id})


async def get_collections(request: web.Request) -> web.Response:
    """Elenco collezioni per compendium. Query: compendium=id o slug (obbligatorio)."""
    await get_authorized_user(request)
    comp_id = _resolve_compendium_id(request.query.get("compendium", "").strip())
    if not comp_id:
        return web.json_response({"collections": []})
    if not _ensure_sqlite(comp_id):
        return web.json_response({"collections": []})
    try:
        conn = _get_conn(comp_id)
        rows = conn.execute(
            """
            SELECT c.slug, c.name, COUNT(i.id) as count
            FROM collections c
            LEFT JOIN items i ON i.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.slug
            """
        ).fetchall()
        conn.close()
        collections = [{"slug": r[0], "name": r[1], "count": r[2]} for r in rows]
        return web.json_response({"collections": collections})
    except Exception as e:
        return web.json_response({"error": str(e), "collections": []}, status=500)


async def get_items(request: web.Request) -> web.Response:
    """Items di una collezione. Query: compendium=id o slug, collection_slug nel path."""
    await get_authorized_user(request)
    comp_id = _resolve_compendium_id(request.query.get("compendium", "").strip())
    slug = request.match_info.get("collection_slug", "").strip()
    if not comp_id or not slug:
        return web.json_response({"items": []})
    if not _ensure_sqlite(comp_id):
        return web.json_response({"items": []})
    try:
        conn = _get_conn(comp_id)
        rows = conn.execute(
            """
            SELECT i.slug, i.name
            FROM items i
            JOIN collections c ON i.collection_id = c.id
            WHERE c.slug = ?
            ORDER BY i.name
            """,
            (slug,),
        ).fetchall()
        conn.close()
        items = [{"slug": r[0], "name": r[1]} for r in rows]
        return web.json_response({"items": items})
    except Exception as e:
        return web.json_response({"error": str(e), "items": []}, status=500)


async def get_item(request: web.Request) -> web.Response:
    """Singolo item. Query: compendium=id o slug (opzionale, default=predefinito), collection=, slug=."""
    await get_authorized_user(request)
    _migrate_legacy()
    config = _load_config()
    comp_param = request.query.get("compendium", "").strip()
    comp_id = _resolve_compendium_id(comp_param) if comp_param else config.get("defaultId")
    coll_slug = request.query.get("collection", "").strip()
    item_slug = request.query.get("slug", "").strip()
    if not comp_id or not coll_slug or not item_slug:
        return web.json_response({"error": "compendium, collection and slug required"}, status=400)
    if not _ensure_sqlite(comp_id):
        return web.json_response({"error": "Database not found"}, status=404)
    comp = _get_compendium(comp_id)
    comp_name = comp.get("name", "") if comp else ""
    try:
        conn = _get_conn(comp_id)
        row = conn.execute(
            """
            SELECT c.slug, c.name, i.slug, i.name, i.markdown
            FROM items i
            JOIN collections c ON i.collection_id = c.id
            WHERE c.slug = ? AND i.slug = ?
            """,
            (coll_slug, item_slug),
        ).fetchone()
        conn.close()
        if not row:
            return web.json_response({"error": "Item not found"}, status=404)
        return web.json_response({
            "compendiumId": comp_id,
            "compendiumName": comp_name,
            "collectionSlug": row[0],
            "collectionName": row[1],
            "slug": row[2],
            "name": row[3],
            "markdown": row[4],
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def _search_in_compendium(conn, q: str, comp_id: str, comp_name: str) -> list:
    like_pattern = f"%{q}%"
    q_lower = q.lower()
    try:
        safe = q.replace('"', '""')
        fts_query = f'"{safe}"*'
        rows = conn.execute(
            """
            SELECT c.slug, c.name, i.slug, i.name
            FROM items_fts f
            JOIN items i ON i.id = f.rowid
            JOIN collections c ON i.collection_id = c.id
            WHERE items_fts MATCH ?
            LIMIT 150
            """,
            (fts_query,),
        ).fetchall()
    except Exception:
        rows = conn.execute(
            """
            SELECT c.slug, c.name, i.slug, i.name
            FROM items i
            JOIN collections c ON i.collection_id = c.id
            WHERE LOWER(i.name) LIKE LOWER(?) OR LOWER(i.markdown) LIKE LOWER(?)
            LIMIT 150
            """,
            (like_pattern, like_pattern),
        ).fetchall()
    def sort_key(r):
        name_lower = (r[3] or "").lower()
        if name_lower == q_lower:
            return (0, name_lower)
        if name_lower.startswith(q_lower):
            return (1, name_lower)
        return (2, name_lower)
    rows = sorted(rows, key=sort_key)[:100]
    return [
        {
            "compendiumId": comp_id,
            "compendiumName": comp_name,
            "collectionSlug": r[0],
            "collectionName": r[1],
            "itemSlug": r[2],
            "itemName": r[3],
        }
        for r in rows
    ]


async def search(request: web.Request) -> web.Response:
    """Ricerca. Query: q=..., compendium=id o slug (opzionale, se omesso cerca in tutti)."""
    await get_authorized_user(request)
    q = request.query.get("q", "").strip()
    comp_filter = request.query.get("compendium", "").strip() or None
    if not q:
        return web.json_response({"results": []})
    _migrate_legacy()
    config = _load_config()
    comps = config["compendiums"]
    if comp_filter:
        resolved = _resolve_compendium_id(comp_filter)
        comps = [c for c in comps if c.get("id") == resolved] if resolved else []
    results = []
    for comp in comps:
        comp_id = comp.get("id")
        if not comp_id or not _ensure_sqlite(comp_id):
            continue
        try:
            conn = _get_conn(comp_id)
            part = _search_in_compendium(conn, q, comp_id, comp.get("name", ""))
            conn.close()
            results.extend(part)
        except Exception:
            pass
    return web.json_response({"results": results})


async def get_names(request: web.Request) -> web.Response:
    """Lista nomi per autolink. Query: compendium=id o slug (opzionale, default=predefinito)."""
    await get_authorized_user(request)
    _migrate_legacy()
    config = _load_config()
    comp_param = request.query.get("compendium", "").strip()
    comp_id = _resolve_compendium_id(comp_param) if comp_param else config.get("defaultId")
    if not comp_id:
        return web.json_response({"names": []})
    if not _ensure_sqlite(comp_id):
        return web.json_response({"names": []})
    comp = _get_compendium(comp_id)
    comp_slug = comp.get("slug", comp_id) if comp else comp_id
    try:
        conn = _get_conn(comp_id)
        rows = conn.execute(
            """
            SELECT i.name, c.slug, i.slug
            FROM items i
            JOIN collections c ON i.collection_id = c.id
            ORDER BY LENGTH(i.name) DESC
            """
        ).fetchall()
        conn.close()
        names = [
            {"name": r[0], "compendiumSlug": comp_slug, "collectionSlug": r[1], "itemSlug": r[2]}
            for r in rows
        ]
        return web.json_response({"names": names})
    except Exception as e:
        return web.json_response({"error": str(e), "names": []}, status=500)


async def get_db(request: web.Request) -> web.Response:
    """Legacy: ritorna struttura del compendium predefinito."""
    await get_authorized_user(request)
    _migrate_legacy()
    config = _load_config()
    comp_id = config.get("defaultId")
    if not comp_id or not _ensure_sqlite(comp_id):
        return web.json_response({"error": "Database not found", "collections": []})
    try:
        conn = _get_conn(comp_id)
        coll_rows = conn.execute(
            "SELECT id, slug, name FROM collections ORDER BY slug"
        ).fetchall()
        collections = []
        for cid, cslug, cname in coll_rows:
            items = conn.execute(
                "SELECT slug, name, markdown FROM items WHERE collection_id = ? ORDER BY name",
                (cid,),
            ).fetchall()
            collections.append({
                "slug": cslug,
                "name": cname,
                "count": len(items),
                "items": [{"slug": s, "name": n, "markdown": m} for s, n, m in items],
            })
        conn.close()
        return web.json_response({"collections": collections})
    except Exception as e:
        return web.json_response(
            {"error": str(e), "collections": []},
            status=500,
        )
