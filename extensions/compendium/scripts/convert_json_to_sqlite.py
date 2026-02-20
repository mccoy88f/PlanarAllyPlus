#!/usr/bin/env python3
"""
Converte quintaedizione-export.json in quintaedizione.db (SQLite con FTS5).

Eseguire manualmente per aggiornare il database dopo aver sostituito il JSON:
    python convert_json_to_sqlite.py

Oppure lasciare che l'estensione converta automaticamente al primo avvio.
"""

from pathlib import Path


def get_paths():
    """Restituisce (path_json, path_db)."""
    script_dir = Path(__file__).resolve().parent
    ext_dir = script_dir.parent
    db_dir = ext_dir / "db"
    return db_dir / "quintaedizione-export.json", db_dir / "quintaedizione.db"


def convert(json_path=None, db_path=None):
    """
    Converte il JSON in SQLite. Ritorna True se OK, False altrimenti.
    """
    import json
    import sqlite3

    if json_path is None or db_path is None:
        json_path, db_path = get_paths()
    if not json_path.exists():
        print(f"File non trovato: {json_path}")
        return False

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Errore lettura JSON: {e}")
        return False

    collections = data.get("collections", [])
    if not collections:
        print("Nessuna collezione nel JSON.")
        return False

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE collections (
            id INTEGER PRIMARY KEY,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            collection_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            markdown TEXT NOT NULL,
            FOREIGN KEY (collection_id) REFERENCES collections(id),
            UNIQUE(collection_id, slug)
        )
    """)
    conn.execute("CREATE INDEX idx_items_collection ON items(collection_id)")
    conn.execute("CREATE INDEX idx_items_slug ON items(slug)")

    # FTS5 per ricerca full-text
    conn.execute("""
        CREATE VIRTUAL TABLE items_fts USING fts5(
            name,
            markdown,
            content='items',
            content_rowid='id',
            tokenize='unicode61'
        )
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
            item_slug = item.get("slug", "")
            item_name = item.get("name", "")
            markdown = item.get("markdown", "")
            conn.execute(
                "INSERT INTO items (collection_id, slug, name, markdown) VALUES (?, ?, ?, ?)",
                (coll_id, item_slug, item_name, markdown),
            )

    conn.commit()
    conn.close()
    print(f"Convertito: {json_path} -> {db_path}")
    return True


def main():
    json_path, db_path = get_paths()
    success = convert(json_path, db_path)
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
