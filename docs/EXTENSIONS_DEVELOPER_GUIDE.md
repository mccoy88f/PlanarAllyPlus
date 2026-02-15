# Guida per sviluppatori di estensioni PlanarAlly

Questa guida spiega come creare un'estensione per PlanarAlly, quali caratteristiche sono disponibili e come integrarle nel sistema.

---

## Indice

1. [Introduzione](#1-introduzione)
2. [Mods vs Extensions](#2-mods-vs-extensions)
3. [Architettura](#3-architettura)
4. [Creare un'estensione passo a passo](#4-creare-unestensione-passo-a-passo) (include [Stili UI predefiniti](#44-stili-ui-predefiniti))
5. [API server](#5-api-server) (include [Storage file/cartelle](#storage-file-e-cartelle-utente-assetsextensionsid))
6. [Integrazione client](#6-integrazione-client)
7. [Integrazione con la mappa](#7-integrazione-con-la-mappa)
8. [Riferimento: DungeonGen](#8-riferimento-dungeongen)

---

## 1. Introduzione

Le **estensioni** permettono di aggiungere funzionalità a PlanarAlly che richiedono backend (generazione, API esterne, elaborazione server-side). Ogni estensione:

- **Server**: espone endpoint HTTP sotto `/api/extensions/<id>/`
- **Client**: può avere UI integrata (modali, voci menu, tab nelle proprietà delle forme)
- **Installazione**: ZIP o URL, installato nella cartella `extensions/`

---

## 2. Mods vs Extensions

| Aspetto | Mods | Extensions |
|---------|------|------------|
| **Tipo** | Solo client-side (JavaScript) | Server-side (Python) + Client UI |
| **Caricamento** | Upload file .pam | Installate nella cartella `extensions/` |
| **Scopo** | Estendere UI, eventi, shape | Funzionalità che richiedono backend |
| **Esempio** | Nuove voci menu, tab shape | DungeonGen, generatori mappe |

Le estensioni sono pensate per funzionalità che necessitano di elaborazione server (generazione immagini, chiamate API esterne, ecc.). I mods sono per estensioni puramente client-side.

### Mods: API disponibili

I mods ricevono `initGame` con:

- **`ui.shape.registerTab(tab, filter?)`**: aggiunge una tab nel dialogo "Mostra proprietà" delle forme
- **`ui.shape.registerContextMenuEntry(entry)`**: aggiunge voci al menu contestuale delle forme
- **`getShape(id)`**, **`getGlobalId(id)`**: accesso alle forme
- **`systems`**, **`systemsState`**: accesso ai sistemi di gioco

Vedi `client/src/mods/models.ts` per il tipo `Mod` e `ModLoad`.

---

## 3. Architettura

```
extensions/
├── dungeongen-main/          # Estensione DungeonGen
│   ├── extension.toml
│   ├── pyproject.toml
│   └── src/dungeongen/
│
├── mia-estensione/           # Nuova estensione
│   ├── extension.toml
│   └── ...
└── ...
```

**Flusso:**

1. **Server**: avvia, scandisce `extensions/`, carica le estensioni
2. **API discovery**: `GET /api/extensions` restituisce lista estensioni con metadati
3. **Client**: menu Extensions mostra lista, clic apre modale/azione
4. **Utilizzo**: client chiama endpoint specifici (es. `POST /api/extensions/dungeongen/generate`)

---

## 4. Creare un'estensione passo a passo

### 4.1 Struttura cartella

Crea una cartella in `extensions/<nome-estensione>/` con:

```
mia-estensione/
├── extension.toml       # Obbligatorio (manifest)
├── pyproject.toml      # Dipendenze Python
├── src/
│   └── mia_estensione/
│       └── ...
└── ...
```

### 4.2 Manifest (extension.toml)

Ogni estensione deve avere un file `extension.toml` nella root:

```toml
[extension]
id = "mia-estensione"
name = "Mia Estensione"
version = "1.0.0"
description = "Descrizione dell'estensione"
author = "Autore"
```

**Campi opzionali per estensioni con UI (entry):**

- **`entry`**: percorso del file UI principale (default: `"ui/index.html"`). Se presente e il file esiste, l'estensione viene aperta in un modale generico che carica l'UI in un iframe.
- **`titleBarColor`**: colore della barra del titolo del modale (es. `"#f9f9f9"`, `"rgb(249,249,249)"`).
- **`icon`**: icona FontAwesome da mostrare prima del titolo (es. `"book"`, `"file-pdf"`, `"far fa-book"`).

### 4.3 Intestazione standard dei modali estensione

Tutti i modali delle estensioni mostrano nella barra del titolo:

- **Chiudi** (X): chiude il modale
- **A tutto schermo**: espande/comprime il modale a schermo intero
- **Finestra separata**: apre il modale in una finestra del browser separata (utile per lavorare su più schermi)

I modali delle estensioni sono **indipendenti dal menu impostazioni**: restano aperti anche se si chiude il pannello laterale.

**Dimensioni standard della barra del titolo:**
- Altezza: `padding: 0.5rem 1rem`
- Titolo: `font-size: 1.1rem`, `font-weight: 600`
- Pulsanti (chiudi, fullscreen, finestra): `font-size: 1.1rem`

### 4.4 Stili UI predefiniti

PlanarAlly fornisce un foglio di stile condiviso per unificare l'aspetto delle UI delle estensioni. Includilo nel tuo `ui/index.html`:

```html
<link rel="stylesheet" href="../../../../static/extensions/ui.css" />
```

Poi applica la classe `ext-ui-root` al `<body>` e usa le classi predefinite per gli elementi. Puoi sovrascrivere qualsiasi stile con il tuo CSS.

**Classi disponibili (prefisso `.ext-ui-`):**

| Categoria | Classi | Uso |
|-----------|--------|-----|
| **Layout** | `ext-ui-root` | Contenitore principale (body) |
| **Tipografia** | `ext-ui-title`, `ext-ui-subtitle`, `ext-ui-text`, `ext-ui-muted` | Titoli e testo |
| **Pulsanti** | `ext-ui-btn`, `ext-ui-btn-primary`, `ext-ui-btn-danger` | Pulsanti standard |
| **Input** | `ext-ui-input`, `ext-ui-select`, `ext-ui-textarea`, `ext-ui-label` | Campi modulo |
| **Liste** | `ext-ui-list`, `ext-ui-list-item`, `ext-ui-list-item-content`, `ext-ui-list-item-name` | Liste cliccabili |
| **Messaggi** | `ext-ui-msg`, `ext-ui-msg-success`, `ext-ui-msg-error`, `ext-ui-msg-info` | Feedback (successo, errore, info) |
| **Stati** | `ext-ui-loading`, `ext-ui-empty` | Caricamento e stato vuoto |
| **Sezioni** | `ext-ui-section`, `ext-ui-section-title` | Suddivisione del contenuto |
| **Utility** | `ext-ui-file-input`, `ext-ui-icon-btn`, `ext-ui-icon-btn-danger` | Input file nascosto, pulsanti icona |

**Esempio minimo:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <link rel="stylesheet" href="../../../../static/extensions/ui.css" />
</head>
<body class="ext-ui-root">
    <div class="ext-ui-title">Mia Estensione</div>
    <button class="ext-ui-btn ext-ui-btn-primary">Azione</button>
</body>
</html>
```

L'autore può estendere o sovrascrivere gli stili a piacere; il set predefinito serve a velocizzare lo sviluppo e mantenere coerenza tra le estensioni.

### 4.5 API server (Python)

Crea il modulo che gestisce le richieste:

```python
# server/src/api/http/extensions/mia_estensione.py
from aiohttp import web

from ....auth import get_authorized_user

async def generate(request: web.Request) -> web.Response:
    await get_authorized_user(request)
    data = await request.json() or {}
    # ... logica ...
    return web.json_response({"result": "ok"})
```

### 4.6 Registrazione route

In `server/src/routes.py` aggiungi:

```python
main_app.router.add_post(f"{subpath}/api/extensions/mia-estensione/generate", extensions.mia_estensione.generate)
```

E in `server/src/api/http/extensions/__init__.py` importa il modulo:

```python
from . import mia_estensione
```

### 4.7 Client UI

Per aggiungere la voce nel menu Extensions e aprire un modale:

1. **Stato** (`client/src/game/systems/extensions/state.ts`): aggiungi `miaEstensioneModalOpen: boolean`
2. **UI** (`client/src/game/systems/extensions/ui.ts`): `openMiaEstensioneModal()`, `closeMiaEstensioneModal()`
3. **Modale** (`client/src/game/ui/extensions/MiaEstensioneModal.vue`): componente Vue
4. **Menu** (`client/src/game/ui/menu/Extensions.vue`): in `onExtensionClick`, se `ext.id === "mia-estensione"` → `openMiaEstensioneModal()`
5. **ModalStack** (`client/src/game/ui/ModalStack.vue`): registra il modale se necessario
6. **Traduzioni** (`client/src/locales/en.json`, `it.json`): chiavi per nome estensione e UI

---

## 5. API server

### API di sistema (gestione estensioni)

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/api/extensions` | Lista estensioni installate |
| POST | `/api/extensions/install/zip` | Installa da file ZIP |
| POST | `/api/extensions/install/url` | Installa da URL (body: `{ "url": "..." }`) |

### API per estensione

Ogni estensione espone endpoint sotto `/api/extensions/<id>/`. Esempio DungeonGen:

- `POST /api/extensions/dungeongen/generate` — genera dungeon, restituisce URL immagine + metadati

### Autenticazione

Tutte le API richiedono utente autenticato. Usa `await get_authorized_user(request)` all'inizio del handler.

### Storage: file e cartelle utente (assets/extensions/&lt;id&gt;)

**Regola standard:** le estensioni che devono creare file o cartelle lato utente devono usarle nella sottocartella `assets/extensions/<extension_id>/`.

Esempio: l'estensione Documents salva i PDF in `assets/extensions/documents/` (struttura logica nel modello Asset: root → extensions → documents → file/cartelle dell'utente).

**Utilizzo nel server (Python):**

```python
from ....db.models.asset import Asset

# Ottieni o crea la cartella per l'estensione (es. "documents", "mia-estensione")
folder = Asset.get_or_create_extension_folder(user, "documents")

# Crea file o sottocartelle sotto folder
asset = Asset.create(name="file.pdf", file_hash=hashname, owner=user, parent=folder)
```

- `extension_id` deve coincidere con l'id dell'estensione (es. `extension.toml` → `id = "documents"`).
- Non usare `..`, `/` o `\` in `extension_id`.
- I file fisici restano in `ASSETS_DIR` con path basato su hash; la gerarchia cartelle è nel modello `Asset`.

### Risposta file statici

Per restituire immagini temporanee:

```python
from ....utils import STATIC_DIR

temp_dir = STATIC_DIR / "temp" / "mia_estensione"
temp_dir.mkdir(parents=True, exist_ok=True)
filepath = temp_dir / f"{uuid.uuid4().hex}.png"
filepath.write_bytes(png_bytes)
url = f"/static/temp/mia_estensione/{filepath.name}"
return web.json_response({"url": url, ...})
```

---

## 6. Integrazione client

### 6.1 Stato estensioni

```typescript
// extensionsState in client/src/game/systems/extensions/state.ts
extensions: ExtensionMeta[]   // Lista da GET /api/extensions
managerOpen: boolean
dungeongenModalOpen: boolean  // Esempio: modale aperto/chiuso
```

### 6.2 Client HTTP

```typescript
import { http } from "../../../core/http";

// GET
const response = await http.get("/api/extensions");

// POST con JSON
const response = await http.postJson("/api/extensions/mia-estensione/azione", { param: 1 });

// POST con body raw (es. file)
const data = await file.arrayBuffer();
const response = await http.post("/api/extensions/install/zip", data);
```

### 6.3 Menu Extensions

Il menu è in `client/src/game/ui/menu/Extensions.vue`:

- Carica lista con `GET /api/extensions`
- Ogni voce mostra nome (tradotto) e al click chiama `onExtensionClick(ext)`
- Per ogni estensione: `if (ext.id === "xxx") openXxxModal()`

### 6.4 Traduzioni

Aggiungi in `client/src/locales/en.json` e `it.json`:

```json
"game.ui.menu.Extensions.extensions.xxx": "Nome Estensione"
```

E sotto `game.ui.extensions.XxxModal` per le etichette del modale.

---

## 7. Integrazione con la mappa

### 7.1 Aggiungere asset alla mappa

Per aggiungere un'immagine generata come Asset sulla mappa:

1. **URL immagine**: deve iniziare con `/static` (es. `/static/temp/dungeons/xxx.png`)
2. **Asset**: usa `Asset` da `./shapes/variants/asset`
3. **Layer**: `floorSystem.getLayer(floor, LayerName.Map)`
4. **Sync**: `layer.addShape(asset, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT)`

Esempio di pattern (vedi `client/src/game/dungeongen.ts`):

```typescript
const asset = new Asset(image, refPoint, width, height, { uuid: uuidv4() });
asset.src = imageUrl;
asset.setLayer(layer.floor, layer.name);
accessSystem.addAccess(asset.id, playerName, { edit: true, movement: true, vision: true }, UI_SYNC);
layer.addShape(asset, SyncMode.FULL_SYNC, InvalidationMode.WITH_LIGHT);
```

### 7.2 Custom data sulle forme

Per salvare parametri sull'asset (es. per rigenerare/sostituire):

```typescript
import { customDataSystem } from "./systems/customData";
import { getGlobalId } from "./id";

customDataSystem.addElement(
  {
    shapeId: getGlobalId(asset.id),
    source: "mia_estensione",
    prefix: "/",
    name: "params",
    kind: "text",
    value: JSON.stringify({ params, seed, ... }),
    reference: null,
    description: null,
  },
  true,
);
```

### 7.3 Tab nelle proprietà

Per mostrare una tab "Mia Estensione" nel dialogo "Mostra proprietà" quando la forma ha custom data:

1. Crea `MiaEstensioneSettings.vue` in `client/src/game/ui/settings/shape/`
2. In `ShapeSettings.vue` aggiungi tab condizionale:

```typescript
if (shapeId !== undefined && hasMiaEstensioneData(shapeId)) {
  tabs.push({
    id: "MiaEstensione",
    label: t("game.ui.extensions.MiaEstensioneSettings.tab"),
    component: MiaEstensioneSettings,
  });
}
```

### 7.4 Aggiornare immagine di un asset

```typescript
import { sendAssetRectImageChange } from "../../api/emits/shape/asset";

(shape as Asset).setImage(newUrl, true);
```

---

## 8. Riferimento: DungeonGen

DungeonGen è l'estensione di riferimento. Struttura:

### Server

- **File**: `server/src/api/http/extensions/dungeongen.py`
- **Endpoint**: `POST /api/extensions/dungeongen/generate`
- **Body**: `{ size, archetype, symmetry, water, pack, roomsize, round_rooms, halls, cross, symmetry_break, show_numbers, seed }`
- **Response**: `{ url, gridCells, imageWidth, imageHeight, syncSquareSize, seed }`

### Client

- **Modale**: `client/src/game/ui/extensions/DungeongenModal.vue` — parametri, anteprima, "Aggiungi alla mappa"
- **Menu**: `Extensions.vue` → click su DungeonGen → `openDungeongenModal()`
- **Stato**: `extensionsState.dungeongenModalOpen`

### Integrazione mappa

- **`addDungeonToMap()`** (`client/src/game/dungeongen.ts`):
  - Crea Asset con immagine
  - Imposta nome = seed
  - Salva custom data con parametri e seed
- **`DungeonGenSettings.vue`**: tab nelle proprietà per forme dungeon, permette rigenerare e sostituire

### Custom data

- `source`: `"dungeongen"`
- `name`: `"params"`
- `value`: JSON con `{ params, seed, gridCells, dungeonMeta }`

### Helper

- `hasDungeonData(shapeId)`: true se la forma ha custom data DungeonGen
- `getDungeonStoredData(shapeId)`: restituisce i dati salvati
- `isDungeonAsset(src)`: true se `src` è un dungeon temporaneo

---

## File da modificare per una nuova estensione

| Componente | File |
|------------|------|
| Manifest | `extensions/<nome>/extension.toml` |
| API server | `server/src/api/http/extensions/<nome>.py` |
| Route | `server/src/routes.py` |
| Import extensions | `server/src/api/http/extensions/__init__.py` |
| Stato | `client/src/game/systems/extensions/state.ts` |
| UI | `client/src/game/systems/extensions/ui.ts` |
| Modale | `client/src/game/ui/extensions/<Nome>Modal.vue` |
| Menu | `client/src/game/ui/menu/Extensions.vue` |
| Tab proprietà (opzionale) | `client/src/game/ui/settings/shape/<Nome>Settings.vue` |
| ShapeSettings (opzionale) | `client/src/game/ui/settings/shape/ShapeSettings.vue` |
| Traduzioni | `client/src/locales/en.json`, `it.json` |

---

## Note importanti

### Estensioni e codice client

Le estensioni hanno **due parti**:

1. **Server (Python)**: può essere installata via ZIP/URL e caricata dinamicamente
2. **Client (Vue/TypeScript)**: modale, voce menu, tab proprietà — **deve essere incluso nel codice PlanarAlly**

Per ora non esiste un sistema di plugin client per estensioni. Per aggiungere una nuova estensione con UI completa, è necessario:

- Includere il codice client nel repository PlanarAlly, oppure
- Usare i **Mods** per estensioni puramente client-side (senza backend)

### Installazione da ZIP

Il file ZIP deve avere `extension.toml` nella root. La cartella estratta sarà `extensions/<id>-<version>/`.

---

## Note sulla sicurezza

- Tutte le API richiedono autenticazione
- Non esporre dati sensibili nelle risposte
- Validare input lato server
- Le estensioni vengono installate nella cartella `extensions/` e caricate dal server
