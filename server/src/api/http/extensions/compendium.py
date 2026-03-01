"""Compendium extension - multi-compendium knowledge base from JSON files."""

import json
import re
import uuid
import time
import sqlite3
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


def _clean_5etools_tags(text: str) -> str:
    """Converte i tag specifici di 5etools in Markdown."""
    if not isinstance(text, str):
        return str(text)
    # Grassetti, corsivi, etc
    text = re.sub(r"\{@b (.*?)\}", r"**\1**", text)
    text = re.sub(r"\{@i (.*?)\}", r"*\1*", text)
    text = re.sub(r"\{@u (.*?)\}", r"<u>\1</u>", text)
    text = re.sub(r"\{@s (.*?)\}", r"~~\1~~", text)
    # Item, spell, creature, etc
    text = re.sub(r"\{@item (.*?)\}", r"**\1**", text)
    text = re.sub(r"\{@spell (.*?)\}", r"*\1*", text)
    text = re.sub(r"\{@creature (.*?)\}", r"**\1**", text)
    text = re.sub(r"\{@condition (.*?)\}", r"*\1*", text)
    text = re.sub(r"\{@skill (.*?)\}", r"**\1**", text)
    text = re.sub(r"\{@sense (.*?)\}", r"*\1*", text)
    text = re.sub(r"\{@filter (.*?)\|.*?\}", r"\1", text)
    text = re.sub(r"\{@link (.*?)\|(.*?)\}", r"[\1](\2)", text)
    # Rimuove riferimenti alle fonti come |PHB] lasciando solo il nome
    text = re.sub(r"\{@([a-z]+) ([^|}]+)(\|[^}]*)?\}", r"**\2**", text)
    return text


def _entries_to_markdown(entries: list, level: int = 1) -> str:
    """Converte un array di entries 5etools in un blocco Markdown."""
    md = ""
    for entry in entries:
        if isinstance(entry, str):
            md += _clean_5etools_tags(entry) + "\n\n"
        elif isinstance(entry, dict):
            e_type = entry.get("type")
            name = entry.get("name")
            if name:
                md += "#" * (level + 1) + " " + _clean_5etools_tags(name) + "\n\n"

            if e_type in ["entries", "section"] or "entries" in entry:
                md += _entries_to_markdown(entry.get("entries", []), level + 1)
            elif e_type == "list":
                for item in entry.get("items", []):
                    if isinstance(item, str):
                        md += "- " + _clean_5etools_tags(item) + "\n"
                    elif isinstance(item, dict) and "entry" in item:
                        md += "- " + _clean_5etools_tags(item["entry"]) + "\n"
                    elif isinstance(item, dict) and "entries" in item:
                        # Liste annidate o liste con entries
                        md += "- " + _entries_to_markdown(item["entries"], level + 2).strip() + "\n"
                md += "\n"
            elif e_type == "table":
                col_labels = entry.get("colLabels", [])
                if col_labels:
                    md += "| " + " | ".join([_clean_5etools_tags(str(c)) for c in col_labels]) + " |\n"
                    md += "| " + " | ".join(["---"] * len(col_labels)) + " |\n"
                for row in entry.get("rows", []):
                    md += "| " + " | ".join([_clean_5etools_tags(str(c)) for c in row]) + " |\n"
                md += "\n"
            elif e_type == "inset":
                inner = _entries_to_markdown(entry.get("entries", []), level + 2).strip()
                md += "> " + inner.replace("\n", "\n> ") + "\n\n"
            elif "entries" in entry:
                 md += _entries_to_markdown(entry.get("entries", []), level + 1)
    return md


# ── Known generic 5etools types ──────────────────────────────────────────────

KNOWN_5ETOOLS_TYPES: set[str] = {
    "spell", "feat", "background", "item", "baseitem", "magicvariant",
    "race", "subrace", "condition", "disease", "status",
    "deity", "variantrule", "trap", "hazard",
    "optionalfeature", "reward", "vehicle", "object",
    "action", "language", "psionics", "charoption",
    "facility", "cult", "boon", "deck",
}

# Human-readable labels for each type key
_TYPE_LABELS: dict[str, str] = {
    "spell": "Spells",
    "feat": "Feats",
    "background": "Backgrounds",
    "item": "Items",
    "baseitem": "Base Items",
    "magicvariant": "Magic Variants",
    "race": "Races",
    "subrace": "Subraces",
    "condition": "Conditions",
    "disease": "Diseases",
    "status": "Status Effects",
    "deity": "Deities",
    "variantrule": "Variant Rules",
    "trap": "Traps",
    "hazard": "Hazards",
    "optionalfeature": "Optional Features",
    "reward": "Rewards",
    "vehicle": "Vehicles",
    "object": "Objects",
    "action": "Actions",
    "language": "Languages",
    "psionics": "Psionics",
    "charoption": "Character Options",
    "facility": "Bastions",
    "cult": "Cults",
    "boon": "Boons",
    "deck": "Decks",
}


def _detect_format(data: dict) -> str:
    """Auto-detects compendium JSON format.
    Returns: 'native' | 'book' | 'generic_5etools' | 'unknown'
    """
    if "collections" in data:
        return "native"
    if "data" in data or "adventureData" in data:
        return "book"
    detected = set(data.keys()) & KNOWN_5ETOOLS_TYPES
    if detected:
        return "generic_5etools"
    return "unknown"


def _school_name(abbr: str) -> str:
    schools = {
        "A": "Abjuration", "C": "Conjuration", "D": "Divination",
        "E": "Enchantment", "V": "Evocation", "I": "Illusion",
        "N": "Necromancy", "T": "Transmutation",
    }
    return schools.get(abbr, abbr)


def _time_str(time_list: list) -> str:
    if not time_list:
        return ""
    t = time_list[0]
    return f"{t.get('number', '')} {t.get('unit', '')}".strip()


def _duration_str(dur_list: list) -> str:
    if not dur_list:
        return ""
    d = dur_list[0]
    if d.get("type") == "instant":
        return "Instantaneous"
    if d.get("type") == "permanent":
        return "Until dispelled"
    inner = d.get("duration", {})
    conc = " (Concentration)" if d.get("concentration") else ""
    return f"{inner.get('amount', '')} {inner.get('type', '')}".strip() + conc


def _components_str(comp: dict) -> str:
    parts = []
    if comp.get("v"):
        parts.append("V")
    if comp.get("s"):
        parts.append("S")
    if comp.get("m"):
        m = comp["m"]
        mat = m if isinstance(m, str) else m.get("text", "")
        parts.append(f"M ({mat})")
    return ", ".join(parts)


def _build_generic_item_markdown(item: dict, type_key: str) -> str:
    """Renders a generic 5etools item to Markdown, with type-specific metadata header."""
    md = ""
    source = item.get("source", "")
    page = item.get("page", "")

    # ── Type-specific metadata header ────────────────────────────────────────
    meta_lines: list[str] = []

    if type_key == "spell":
        level = item.get("level", 0)
        school = _school_name(item.get("school", ""))
        level_str = "Cantrip" if level == 0 else f"Level {level}"
        meta_lines.append(f"*{level_str} {school}*")
        casting = _time_str(item.get("time", []))
        if casting:
            meta_lines.append(f"**Casting Time:** {casting}")
        rng = item.get("range", {})
        rng_dist = rng.get("distance", {})
        rng_str = rng_dist.get("type", "") if rng_dist.get("type") in ("self", "touch", "sight", "unlimited") \
            else f"{rng_dist.get('amount', '')} {rng_dist.get('type', '')}".strip()
        if rng_str:
            meta_lines.append(f"**Range:** {rng_str.capitalize()}")
        comp_str = _components_str(item.get("components", {}))
        if comp_str:
            meta_lines.append(f"**Components:** {comp_str}")
        dur = _duration_str(item.get("duration", []))
        if dur:
            meta_lines.append(f"**Duration:** {dur}")

    elif type_key == "item":
        rarity = item.get("rarity", "")
        attune = item.get("reqAttune", "")
        wondrous = item.get("wondrous", False)
        type_str = "Wondrous Item" if wondrous else item.get("type", "")
        line = ", ".join(filter(None, [type_str, rarity.capitalize() if rarity else ""]))
        if attune:
            line += f" (requires attunement{' by ' + attune if isinstance(attune, str) and len(attune) > 3 else ''})"
        if line.strip():
            meta_lines.append(f"*{line.strip(', ')}*")

    elif type_key == "background":
        skills = item.get("skillProficiencies", [{}])
        skill_list = list(skills[0].keys()) if skills else []
        if skill_list:
            meta_lines.append(f"**Skill Proficiencies:** {', '.join(skill_list).title()}")

    elif type_key in ("condition", "disease", "status"):
        pass  # just entries

    elif type_key == "deity":
        pantheon = item.get("pantheon", "")
        domains = ", ".join(item.get("domains", []))
        alignment = "".join(item.get("alignment", []))
        if pantheon:
            meta_lines.append(f"**Pantheon:** {pantheon}")
        if domains:
            meta_lines.append(f"**Domains:** {domains}")
        if alignment:
            meta_lines.append(f"**Alignment:** {alignment}")

    elif type_key == "feat":
        prereqs = item.get("prerequisite", [])
        if prereqs:
            for pr in prereqs:
                for k, v in pr.items():
                    meta_lines.append(f"**Prerequisite:** {k}: {v}")

    elif type_key == "race":
        speed = item.get("speed", "")
        if isinstance(speed, dict):
            speed = ", ".join(f"{k} {v} ft." for k, v in speed.items())
        elif isinstance(speed, int):
            speed = f"{speed} ft."
        if speed:
            meta_lines.append(f"**Speed:** {speed}")

    elif type_key in ("trap", "hazard"):
        rating = item.get("rating", "")
        if rating:
            meta_lines.append(f"**Rating:** {rating}")

    elif type_key == "vehicle":
        vtype = item.get("vehicleType", "")
        if vtype:
            meta_lines.append(f"**Type:** {vtype}")

    elif type_key == "optionalfeature":
        feat_type = item.get("featureType", [])
        if feat_type:
            meta_lines.append(f"**Feature Type:** {', '.join(feat_type)}")

    # Source + page
    if source:
        src_str = f"*Source: {source}"
        if page:
            src_str += f", p. {page}"
        src_str += "*"
        meta_lines.append(src_str)

    if meta_lines:
        md += "\n".join(meta_lines) + "\n\n"

    # ── Main entries ──────────────────────────────────────────────────────────
    entries = item.get("entries", [])
    if entries:
        md += _entries_to_markdown(entries)

    # ── Higher level (spells) ─────────────────────────────────────────────────
    higher = item.get("entriesHigherLevel", [])
    if higher:
        md += _entries_to_markdown(higher)

    return md.strip()


def _create_sqlite_schema(conn) -> None:
    """Creates tables, indexes, FTS and triggers on an open connection."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE collections (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL, parent_slug TEXT DEFAULT NULL)")
    conn.execute("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY, collection_id INTEGER NOT NULL, slug TEXT NOT NULL,
            name TEXT NOT NULL, markdown TEXT NOT NULL,
            FOREIGN KEY (collection_id) REFERENCES collections(id), UNIQUE(collection_id, slug)
        )
    """)
    conn.execute("CREATE INDEX idx_items_collection ON items(collection_id)")
    conn.execute("CREATE INDEX idx_items_slug ON items(slug)")
    conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS translations (id INTEGER PRIMARY KEY, type TEXT NOT NULL, collection_slug TEXT, item_slug TEXT, lang TEXT NOT NULL, content TEXT NOT NULL, UNIQUE(type, collection_slug, item_slug, lang))")
    conn.execute("CREATE VIRTUAL TABLE items_fts USING fts5(name, markdown, content='items', content_rowid='id', tokenize='unicode61')")
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


def _insert_item_safe(conn, coll_id: int, slug: str, name: str, md: str) -> None:
    """Inserts an item, mangling slug on collision."""
    slug = slug[:50]
    try:
        conn.execute(
            "INSERT INTO items (collection_id, slug, name, markdown) VALUES (?, ?, ?, ?)",
            (coll_id, slug, name, md),
        )
    except sqlite3.IntegrityError:
        slug = slug[:44] + f"-{int(time.time()) % 999999}"
        try:
            conn.execute(
                "INSERT INTO items (collection_id, slug, name, markdown) VALUES (?, ?, ?, ?)",
                (coll_id, slug, name, md),
            )
        except sqlite3.IntegrityError:
            pass


def _get_or_create_collection(conn, slug: str, name: str, parent_slug: str | None = None) -> int:
    """Returns the collection id, creating it if needed."""
    row = conn.execute("SELECT id FROM collections WHERE slug = ?", (slug,)).fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO collections (slug, name, parent_slug) VALUES (?, ?, ?)", (slug, name, parent_slug))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _extract_and_save_metadata(conn, data: dict) -> None:
    """Extracts required metadata fields from root JSON dict and saves to SQLite."""
    keys = ["title", "author", "date", "website", "license"]
    for k in keys:
        val = data.get(k)
        if val is not None and isinstance(val, str) and val.strip():
            conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (k, val.strip()))


def _convert_generic_5etools_to_sqlite(data: dict, db_path: Path) -> bool:
    """Converts a generic 5etools file (spell/feat/item/…) to SQLite.

    Grouping strategy:
    - Items with different `source` values → one collection per source (e.g. "PHB Spells")
    - Single source → one collection named after the type label (e.g. "Spells")
    """
    # Collect all recognised type arrays from the file
    type_items: list[tuple[str, dict]] = []  # (type_key, item_obj)
    for key in KNOWN_5ETOOLS_TYPES:
        arr = data.get(key, [])
        if isinstance(arr, list):
            for obj in arr:
                if isinstance(obj, dict) and obj.get("name"):
                    type_items.append((key, obj))

    if not type_items:
        return False

    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    _create_sqlite_schema(conn)

    _extract_and_save_metadata(conn, data)

    # Group by (type_key, source)
    from collections import defaultdict
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    all_sources: set[str] = set()
    for type_key, obj in type_items:
        src = obj.get("source", "")
        groups[(type_key, src)].append(obj)
        if src:
            all_sources.add(src)

    multi_source = len(all_sources) > 1

    for (type_key, src), items in groups.items():
        label = _TYPE_LABELS.get(type_key, type_key.title() + "s")
        if multi_source and src:
            coll_name = f"{src} — {label}"
        else:
            coll_name = label
        coll_slug = _slugify(coll_name)
        coll_id = _get_or_create_collection(conn, coll_slug, coll_name)

        for obj in items:
            name = obj.get("name", "?")
            slug = _slugify(name)
            md = _build_generic_item_markdown(obj, type_key)
            _insert_item_safe(conn, coll_id, slug, name, md)

    conn.commit()
    conn.close()
    return True


def _convert_5etools_to_sqlite(data: dict, db_path: Path) -> bool:
    """Converte JSON in formato 5etools book/adventure in SQLite."""
    sections = data.get("data", [])
    if not sections and "adventureData" in data:
        sections = data.get("adventureData", [])
    if not sections:
        return False

    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    _create_sqlite_schema(conn)

    _extract_and_save_metadata(conn, data)

    for section in sections:
        sec_name = section.get("name", "Unknown Section")
        sec_slug = _slugify(sec_name)
        coll_id = _get_or_create_collection(conn, sec_slug, sec_name)

        sub_sections = [e for e in section.get("entries", []) if isinstance(e, dict) and e.get("name")]

        if not sub_sections:
            md = _entries_to_markdown(section.get("entries", []))
            _insert_item_safe(conn, coll_id, sec_slug, sec_name, md)
        else:
            intro_entries = []
            for e in section.get("entries", []):
                if isinstance(e, dict) and e.get("name"):
                    break
                intro_entries.append(e)
            if intro_entries:
                md = _entries_to_markdown(intro_entries)
                _insert_item_safe(conn, coll_id, sec_slug, sec_name, md)
            for i, sub in enumerate(sub_sections):
                sub_name = sub.get("name")
                sub_slug = _slugify(sub_name)
                sub_coll_slug = f"{sec_slug}-{sub_slug}-{i}"
                sub_coll_id = _get_or_create_collection(conn, sub_coll_slug, sub_name, parent_slug=sec_slug)
                md = _entries_to_markdown([sub])
                _insert_item_safe(conn, sub_coll_id, sub_coll_slug, sub_name, md)

    conn.commit()
    conn.close()
    return True


def _convert_json_to_sqlite(json_path: Path, db_path: Path) -> bool:
    """Converte JSON in SQLite. Ritorna True se OK.
    Riconosce automaticamente: native | book | generic_5etools
    """
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    fmt = _detect_format(data)

    if fmt == "book":
        return _convert_5etools_to_sqlite(data, db_path)

    if fmt == "generic_5etools":
        return _convert_generic_5etools_to_sqlite(data, db_path)

    if fmt == "native":
        collections = data.get("collections", [])
        if not collections:
            return False
        if db_path.exists():
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        _create_sqlite_schema(conn)
        _extract_and_save_metadata(conn, data)
        for coll in collections:
            def insert_recursive(c_obj, parent_slug=None):
                slug = c_obj.get("slug", "")
                name = c_obj.get("name", slug)
                conn.execute("INSERT INTO collections (slug, name, parent_slug) VALUES (?, ?, ?)", (slug, name, parent_slug))
                coll_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                for item in c_obj.get("items", []):
                    conn.execute(
                        "INSERT INTO items (collection_id, slug, name, markdown) VALUES (?, ?, ?, ?)",
                        (coll_id, item.get("slug", ""), item.get("name", ""), item.get("markdown", "")),
                    )
                for sub_coll in c_obj.get("collections", []):
                    insert_recursive(sub_coll, slug)
                    
            insert_recursive(coll)
        conn.commit()
        conn.close()
        return True

    return False  # unknown format


def _ensure_sqlite(comp_id: str) -> bool:
    """Converte JSON in SQLite se necessario per il compendium."""
    comp = _get_compendium(comp_id)
    if not comp:
        return False
    json_path = _json_path(comp)
    db_path = _db_path(comp_id)
    if db_path.exists():
        # Ensure translations table exists for legacy DBs
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS translations (id INTEGER PRIMARY KEY, type TEXT NOT NULL, collection_slug TEXT, item_slug TEXT, lang TEXT NOT NULL, content TEXT NOT NULL, UNIQUE(type, collection_slug, item_slug, lang))")
        conn.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        try:
            conn.execute("ALTER TABLE collections ADD COLUMN parent_slug TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()
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
        # Rilevamento automatico formato
        if not isinstance(data, dict) or _detect_format(data) == "unknown":
            return web.json_response(
                {"error": "Formato non supportato. Usare: formato native (collections), book/adventure 5etools, oppure file generici 5etools (spell, feat, item, ...)"},
                status=400
            )
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


async def rename_compendium(request: web.Request) -> web.Response:
    """Rinomina un compendio: PATCH /compendiums/:id/rename."""
    await get_authorized_user(request)
    comp_id = request.match_info.get("compendium_id", "").strip()
    if not comp_id:
        return web.json_response({"error": "compendium_id required"}, status=400)
    
    try:
        body = await request.json()
        new_name = body.get("name", "").strip()
    except Exception:
        new_name = ""
        
    if not new_name:
        return web.json_response({"error": "name is required"}, status=400)
        
    if not _get_compendium(comp_id):
        return web.json_response({"error": "Compendium not found"}, status=404)
        
    config = _load_config()
    for c in config["compendiums"]:
        if c.get("id") == comp_id:
            c["name"] = new_name
            break
            
    _save_config(config)
    return web.json_response({"ok": True, "id": comp_id, "name": new_name})


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
            SELECT c.slug, c.name, c.parent_slug, COUNT(i.id) as count
            FROM collections c
            LEFT JOIN items i ON i.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.slug
            """
        ).fetchall()
        conn.close()
        collections = [{"slug": r[0], "name": r[1], "parentSlug": r[2], "count": r[3]} for r in rows]
        return web.json_response({"collections": collections})
    except Exception as e:
        return web.json_response({"error": str(e), "collections": []}, status=500)


async def get_index(request: web.Request) -> web.Response:
    """Ritorna l'indice (ToC) del compendio. Struttura ad albero 2 livelli."""
    await get_authorized_user(request)
    comp_id = _resolve_compendium_id(request.query.get("compendium", "").strip())
    if not comp_id or not _ensure_sqlite(comp_id):
        return web.json_response({"index": []})
    try:
        conn = _get_conn(comp_id)
        # Reperiamo tutte le collezioni e i relativi item
        rows = conn.execute(
            """
            SELECT c.slug, c.name, c.parent_slug, i.slug, i.name
            FROM collections c
            LEFT JOIN items i ON i.collection_id = c.id
            ORDER BY c.id, i.name
            """
        ).fetchall()
        conn.close()

        index = []
        coll_map = {}
        for c_slug, c_name, p_slug, i_slug, i_name in rows:
            if c_slug not in coll_map:
                coll_map[c_slug] = {"slug": c_slug, "name": c_name, "parentSlug": p_slug, "items": [], "collections": []}
            if i_slug:
                coll_map[c_slug]["items"].append({"slug": i_slug, "name": i_name})

        # Build tree for index
        for c in coll_map.values():
            if c["parentSlug"] and c["parentSlug"] in coll_map:
                coll_map[c["parentSlug"]]["collections"].append(c)
            else:
                index.append(c)
                
        # Get metadata
        try:
            meta_rows = conn.execute("SELECT key, value FROM metadata").fetchall()
            metadata = {r[0]: r[1] for r in meta_rows}
        except sqlite3.OperationalError:
            metadata = {}
            
        return web.json_response({"index": index, "metadata": metadata})
    except Exception as e:
        return web.json_response({"error": str(e), "index": [], "metadata": {}}, status=500)


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


async def get_translation(request: web.Request) -> web.Response:
    """Recupera una traduzione salvata."""
    await get_authorized_user(request)
    comp_id = request.query.get("compendium", "").strip()
    config = _load_config()
    if not comp_id:
        comp_id = config.get("defaultId")
    
    t_type = request.query.get("type", "item")
    coll_slug = request.query.get("collection", "").strip()
    item_slug = request.query.get("slug", "").strip()
    lang = request.query.get("lang", "").strip()

    if not comp_id or not lang:
        return web.json_response({"error": "compendium and lang required"}, status=400)
    
    if not _ensure_sqlite(comp_id):
        return web.json_response({"error": "Database not found"}, status=404)

    try:
        conn = _get_conn(comp_id)
        row = conn.execute(
            "SELECT content FROM translations WHERE type = ? AND collection_slug IS ? AND item_slug IS ? AND lang = ?",
            (t_type, coll_slug or None, item_slug or None, lang)
        ).fetchone()
        conn.close()
        
        if row:
            return web.json_response({"content": row[0]})
        return web.json_response({"content": None})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def save_translation(request: web.Request) -> web.Response:
    """Salva una traduzione."""
    await get_authorized_user(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    comp_id = body.get("compendium", "").strip()
    t_type = body.get("type", "item")
    coll_slug = body.get("collection", "").strip()
    item_slug = body.get("slug", "").strip()
    lang = body.get("lang", "").strip()
    content = body.get("content", "").strip()

    if not comp_id or not lang or not content:
        return web.json_response({"error": "compendium, lang and content required"}, status=400)
    
    if not _ensure_sqlite(comp_id):
        return web.json_response({"error": "Database not found"}, status=404)

    try:
        conn = _get_conn(comp_id)
        conn.execute(
            """
            INSERT INTO translations (type, collection_slug, item_slug, lang, content)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(type, collection_slug, item_slug, lang) DO UPDATE SET content = excluded.content
            """,
            (t_type, coll_slug or None, item_slug or None, lang, content)
        )
        conn.commit()
        conn.close()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def delete_translation(request: web.Request) -> web.Response:
    """Elimina una traduzione."""
    await get_authorized_user(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.HTTPBadRequest(text="Invalid JSON")

    comp_id = body.get("compendium", "").strip()
    t_type = body.get("type", "item")
    coll_slug = body.get("collection", "").strip()
    item_slug = body.get("slug", "").strip()
    lang = body.get("lang", "").strip()

    if not comp_id or not lang:
        return web.json_response({"error": "compendium and lang required"}, status=400)
    
    if not _ensure_sqlite(comp_id):
        return web.json_response({"error": "Database not found"}, status=404)

    try:
        conn = _get_conn(comp_id)
        conn.execute(
            "DELETE FROM translations WHERE type = ? AND collection_slug IS ? AND item_slug IS ? AND lang = ?",
            (t_type, coll_slug or None, item_slug or None, lang)
        )
        conn.commit()
        conn.close()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
