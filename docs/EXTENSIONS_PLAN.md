# Piano per il Sistema Estensioni di PlanarAlly

## Obiettivo

1. Aggiungere la voce **Extensions** nel menu impostazioni DM di PlanarAlly
2. Definire un'architettura per lo sviluppo e l'integrazione di estensioni
3. Creare la prima estensione basata su **Dungeongen** per la generazione procedurale di dungeon

---

## Parte 1: Voce "Extensions" nel Menu Impostazioni (Apri impostazioni)

### 1.1 Posizione

La voce **Extensions** si trova nel menu laterale sinistro (lo stesso di Personaggi, Asset, Note, DM Settings, ecc.), visibile quando si clicca sull'icona ingranaggio per aprire le impostazioni.

### 1.2 Struttura a albero

- **Extensions** – accordion che si espande al click
- Sotto: **nomi delle estensioni installate** (es. "Dungeon Generator")
- Sotto: **Gestisci estensioni** – apre il modale di gestione

### 1.3 Modale Gestisci estensioni

Simile al modale Asset Manager:
- Lista delle estensioni installate
- Campo per **caricare file ZIP**
- Campo per **installare da URL**

### 1.4 File creati/modificati

| File | Modifica |
|------|----------|
| `client/src/game/ui/menu/Extensions.vue` | **Nuovo** – accordion menu con lista estensioni + Gestisci |
| `client/src/game/ui/extensions/ExtensionsManager.vue` | **Nuovo** – modale gestione (lista, upload ZIP, install da URL) |
| `client/src/game/systems/extensions/state.ts` | **Nuovo** – stato (managerOpen, extensions) |
| `client/src/game/systems/extensions/ui.ts` | **Nuovo** – toggle modale |
| `client/src/game/ui/menu/MenuBar.vue` | Aggiunto componente Extensions |
| `client/src/game/ui/ModalStack.vue` | Aggiunto ExtensionsManager |
| `client/src/locales/en.json`, `it.json` | Traduzioni |

---

## Parte 2: Architettura del Sistema Estensioni

### 2.1 Differenza Mods vs Extensions

| Aspetto | Mods | Extensions |
|---------|------|------------|
| **Tipo** | Client-side (JavaScript) | Server-side (Python) + Client UI |
| **Caricamento** | Upload file .pam | Installate nella cartella `extensions/` |
| **Scopo** | Estendere UI, eventi, shape | Funzionalità che richiedono backend (generazione, API esterne, ecc.) |
| **Esempio** | Nuove voci menu, tab shape | Dungeongen, generatori mappe, integrazioni |

### 2.2 Struttura Cartella Extensions

```
extensions/
├── dungeongen-main/          # Estensione Dungeongen (già presente)
│   ├── src/dungeongen/      # Codice sorgente
│   ├── pyproject.toml
│   └── extension.toml       # [NUOVO] Manifest dell'estensione
│
├── _registry/                # [OPZIONALE] Registry delle estensioni
│   └── index.json
└── README.md                 # Guida per sviluppatori
```

### 2.3 Manifest Estensione (extension.toml)

Ogni estensione deve avere un file `extension.toml` nella root:

```toml
[extension]
id = "dungeongen"
name = "Dungeon Generator"
version = "1.0.0"
description = "Procedural dungeon generation for tabletop maps"
author = "PlanarAlly Extensions"

[extension.api]
# Endpoint HTTP che l'estensione espone
generate = "/api/extensions/dungeongen/generate"
```

### 2.4 Flusso di Caricamento Estensioni

1. **Avvio server**: il server scandisce `extensions/` e carica i manifest
2. **API discovery**: `GET /api/extensions` restituisce lista estensioni con metadati
3. **Client**: ExtensionsSettings.vue chiama `/api/extensions` e mostra la lista
4. **Utilizzo**: il client chiama gli endpoint specifici di ogni estensione (es. `/api/extensions/dungeongen/generate`)

---

## Parte 3: Estensione Dungeongen

### 3.1 Componenti Necessari

| Componente | Descrizione |
|------------|-------------|
| **Server API** | Endpoint che riceve parametri e restituisce SVG/PNG del dungeon |
| **Client UI** | Form per parametri (size, symmetry, water, ecc.) + pulsante "Genera" |
| **Integrazione mappa** | Meccanismo per aggiungere il dungeon generato come Asset sulla mappa |

### 3.2 API Server

**Endpoint**: `POST /api/extensions/dungeongen/generate`

**Request body** (JSON):
```json
{
  "size": "medium",
  "archetype": "classic",
  "symmetry": "none",
  "water": "dry",
  "seed": 42,
  "format": "svg"
}
```

**Response**:
- `200`: `{ "svg": "<svg>...</svg>", "seed": 42 }` oppure `{ "png": "base64...", "seed": 42 }`
- `400`: errore validazione parametri
- `500`: errore generazione

### 3.3 Integrazione Codice Dungeongen

Il codice in `extensions/dungeongen-main/` va adattato:

1. **Rimuovere dipendenza Flask** – Dungeongen usa Flask per la webview; PlanarAlly usa aiohttp. La logica di generazione va estratta e usata direttamente.
2. **Rimuovere path hardcoded** – In `app.py` riga 216: `sys.path.insert(0, '/Users/benjamincooley/...')` va sostituito con path relativo al progetto.
3. **Wrapper aiohttp** – Creare `server/src/api/http/extensions/dungeongen.py` che:
   - Importa `DungeonGenerator`, `GenerationParams`, ecc. da `extensions/dungeongen-main`
   - Espone l'endpoint POST
   - Restituisce SVG (o PNG in base64)

### 3.4 Client: DungeonGeneratorPanel

Componente Vue da includere in ExtensionsSettings o come sottopannello:

- **Parametri**: Size, Archetype, Symmetry, Water, Seed (opzionale)
- **Pulsante "Generate"**: chiama API, riceve SVG
- **Anteprima**: mostra SVG in un `<div>` o `<img>`
- **Pulsante "Add to Map"**: converte SVG in Asset e lo posiziona sulla mappa corrente

### 3.5 Aggiunta Dungeon alla Mappa

**Opzione A – SVG come Asset**:
- Convertire SVG in PNG lato server (usando skia, già dipendenza dungeongen)
- Restituire PNG in base64
- Client crea blob URL e usa `dropAsset` o equivalente per aggiungere l'immagine

**Opzione B – SVG diretto**:
- PlanarAlly supporta Asset con `src` URL; si può creare un blob da SVG e usarlo
- Verificare se Asset supporta SVG (potrebbero esserci limitazioni)

**Opzione C – Upload come asset temporaneo**:
- Endpoint che salva PNG in `static/` o in una cartella temporanea
- Restituisce URL statico
- Client usa quell'URL per creare l'Asset

---

## Parte 4: Piano di Implementazione (Fasi)

### Fase 1: Infrastruttura base (Completata)
- [x] Aggiungere tab Extensions in DmSettings
- [x] Creare ExtensionsSettings.vue con layout base
- [x] Aggiungere traduzioni
- [x] Creare `GET /api/extensions` che restituisce lista da manifest (o lista hardcoded iniziale)

### Fase 2: Estensione Dungeongen – Backend (Completata)
- [x] Creare `extension.toml` per dungeongen
- [x] Estrarre logica generazione da `app.py` (senza Flask)
- [x] Correggere path e dipendenze in dungeongen
- [x] Creare `server/src/api/http/extensions/` e `dungeongen.py`
- [x] Registrare route `POST /api/extensions/dungeongen/generate`
- [x] Aggiungere dungeongen come dipendenza opzionale o path in `sys.path`

### Fase 3: Estensione Dungeongen – Frontend (Completata)
- [x] Creare `DungeonGeneratorPanel.vue` con form parametri
- [x] Integrare in ExtensionsSettings
- [x] Chiamata API e anteprima SVG
- [x] Logica "Add to Map" (PNG blob → Asset)

### Fase 4: Sviluppo nuove estensioni (In corso)
- [x] **Documents** — Visualizzatore PDF e condivisione
- [x] **Assets Installer** — Caricamento ZIP e gestione asset pack
- [x] **Watabou** — Importazione mappe City Generator e One Page Dungeon
- [x] **Compendium** — Pannello di ricerca e installazione compendi
- [x] **Time Manager** — Timer e countdown
- [x] **Ambient Music** — Audio posizionale e playlist
- [x] **Quality of Life** — ESC globale per chiusura, UI standardizzata

---

## Parte 5: Dipendenze e Configurazione

### Dungeongen
- **Python 3.10+**
- **skia-python** – rendering
- **numpy** – noise
- **Flask** – solo per webview standalone, non necessario se integriamo in PlanarAlly

### Server PlanarAlly
- Aggiungere `extensions/dungeongen-main` al `PYTHONPATH` o installare in modalità editable:
  ```bash
  pip install -e extensions/dungeongen-main
  ```
- Oppure in `planarserver.py`:
  ```python
  sys.path.insert(0, str(Path(__file__).parent.parent / "extensions" / "dungeongen-main" / "src"))
  ```

---

## Parte 6: Estensioni Future

L'architettura permette di aggiungere altre estensioni, ad esempio:
- **Random encounter generator**
- **Integrazione con D&D Beyond / altre API**
- **Generatore di token procedurali**
- **Export/Import formati esterni**

Ogni estensione:
1. Va nella cartella `extensions/<nome>/`
2. Ha un `extension.toml`
3. Espone endpoint sotto `/api/extensions/<id>/`
4. Può avere un pannello UI in ExtensionsSettings

---

## Riepilogo File da Creare/Modificare

### Nuovi file
- `client/src/game/ui/settings/ExtensionsSettings.vue`
- `client/src/game/ui/settings/extensions/DungeonGeneratorPanel.vue` (opzionale, può stare in ExtensionsSettings)
- `server/src/api/http/extensions/__init__.py`
- `server/src/api/http/extensions/dungeongen.py`
- `extensions/dungeongen-main/extension.toml`
- `docs/EXTENSIONS_PLAN.md` (questo file)

### File da modificare
- `client/src/game/ui/settings/dm/categories.ts`
- `client/src/game/ui/settings/dm/DmSettings.vue`
- `server/src/routes.py`
- `client/src/locales/*.json` (tutte le lingue)
- `extensions/dungeongen-main/src/dungeongen/webview/app.py` (rimuovere path hardcoded, estrarre logica)
