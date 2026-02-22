# PlanarAlly Extensions Developer Guide (English)

This guide explains how to create an extension for PlanarAlly, what features are available, the UI framework, and how to integrate them.

---

## Index
1. [Introduction](#introduction)
2. [Mods vs Extensions](#mods-vs-extensions)
3. [Architecture](#architecture)
4. [Available extensions and frameworks](#available-extensions-and-frameworks)
5. [UI Guide](#ui-guide)
6. [Step‑by‑step extension creation](#step-by-step-extension-creation)
7. [Server API](#server-api)
8. [Client integration](#client-integration)
9. [Map integration](#map-integration)
10. [Reference: DungeonGen](#reference-dungeongen)

---

## Introduction
Extensions allow adding functionality to PlanarAlly that requires a backend (generation, external APIs, server‑side processing). Each extension:
- **Server**: exposes HTTP endpoints under `/api/extensions/<id>/`
- **Client**: may have UI (modals, menu entries, tabs in shape properties)
- **Installation**: ZIP or URL, installed into the `extensions/` folder.

---

## Mods vs Extensions
| Aspect | Mods | Extensions |
|--------|------|------------|
| **Type** | Client‑side only (JavaScript) | Server‑side (Python) + Client UI |
| **Loading** | Upload `.pam` file | Installed in `extensions/` folder |
| **Purpose** | Extend UI, events, shape | Features requiring backend (e.g., AI, map generation) |
| **Example** | New menu items, shape tabs | DungeonGen, AI Generator |

---

## Architecture
```
extensions/
├── dungeongen-main/          # DungeonGen extension
│   ├── extension.toml
│   ├── pyproject.toml
│   └── src/dungeongen/
│
├── my-extension/             # New extension template
│   ├── extension.toml
│   └── ...
└── ...
```

The server scans `extensions/`, loads each `extension.toml`, and registers its API routes. The client fetches the list via `GET /api/extensions` and populates the Extensions menu.

---

## Available extensions and frameworks
| Extension | ID | Description |
|-----------|----|-------------|
| **Compendium** | `compendium` | Knowledge base, install multiple JSON packs, search in character sheets |
| **Character Sheet** | `character-sheet` | D&D 5e character sheets for tokens (DM sees all, players see their own) |
| **Documents** | `documents` | Upload and view PDFs, share with players |
| **Assets Installer** | `assets-installer` | Install asset pack ZIPs, organized folder tree, automatic naming |
| **AI Generator** | `openrouter` | Connect to AI models (OpenRouter, Google AI Studio) for characters, stories, maps |
| **DungeonGen** | `dungeongen` | Procedural dungeon generation for tabletop maps |

---

## UI Guide
All extension UIs follow the same visual style defined in `static/extensions/ui.css`. Use the predefined classes (`ext-ui-root`, `ext-toolbar-bar`, `ext-bottom-bar`, etc.) for a consistent look.

---

## Step‑by‑step extension creation
1. **Create folder** `extensions/<your-id>/`
2. **Add `extension.toml`** with metadata (id, name, version, description)
3. **Write server code** in `src/` (Python, aiohttp) and expose routes under `/api/extensions/<id>/`
4. **Create UI** in `ui/index.html` and include `ext-bridge.js` for communication
5. **Add translations** in `client/src/locales/en.json` and `it.json`
6. **Update client UI** (`Extensions.vue`, state, modal components) to open your extension

---

## Server API
Use aiohttp handlers. Example:
```python
@router.post('/api/extensions/<id>/do-something')
async def do_something(request):
    data = await request.json()
    # ... process ...
    return web.json_response({'result': 'ok'})
```
Register the route in `server/src/routes.py`.

---

## Client integration
Add a menu entry in `client/src/game/ui/menu/Extensions.vue` and a modal component if needed. Use `invoke` to call server endpoints.

---

## Map integration
To add assets to the map, create an `Asset` shape and add it to the floor layer. See `client/src/game/dungeongen.ts` for an example.

---

## Reference: DungeonGen
See the existing DungeonGen extension for a complete example of backend generation, asset creation, and UI integration.

---

*This file is a placeholder translation of the Italian guide. Please review and improve the English wording as needed.*
