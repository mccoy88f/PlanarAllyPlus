# Guida per sviluppatori di estensioni PlanarAlly

Questa guida spiega come creare un'estensione per PlanarAlly, quali caratteristiche sono disponibili, il framework UI disponibile e come integrarle nel sistema.

---

## Indice

1. [Introduzione](#1-introduzione)
2. [Mods vs Extensions](#2-mods-vs-extensions)
3. [Architettura](#3-architettura)
4. [Estensioni e framework disponibili](#4-estensioni-e-framework-disponibili)
5. [Guida alla UI](#5-guida-alla-ui)
6. [Creare un'estensione passo a passo](#6-creare-unestensione-passo-a-passo)
7. [API server](#7-api-server)
8. [Integrazione client](#8-integrazione-client)
9. [Integrazione con la mappa](#9-integrazione-con-la-mappa)
10. [Riferimento: DungeonGen](#10-riferimento-dungeongen)

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

## 4. Estensioni e framework disponibili

### 4.1 Estensioni incluse in PlanarAlly

| Estensione | ID | Descrizione |
|------------|-----|-------------|
| **Compendium** | `compendium` | Compendio di conoscenza: installa più JSON nello stesso formato, cerca nella scheda personaggio e altrove |
| **Character Sheet** | `character-sheet` | Schede personaggio D&D 5e per token. Master vede tutto, giocatori vedono le proprie |
| **Documents** | `documents` | Upload e visualizzazione PDF in una cartella dedicata. Condivisione con i giocatori |
| **Assets Installer** | `assets-installer` | Carica file ZIP per estrarre asset nella cartella assets. Installa e disinstalla asset pack |
| **AI Generator** | `openrouter` | Connetti modelli AI via OpenRouter o Google AI Studio. Genera personaggi, storie, migliora mappe |
| **MapsGen** | `dungeongen` | Generazione procedurale di dungeon e **edifici** per mappe da tavolo. Supporta muri automatici, porte, modalità AI realistica |

### 4.2 Framework tecnico

- **Server**: Python (aiohttp), estensioni in `extensions/<id>/`, API sotto `/api/extensions/<id>/`
- **Client**: Vue 3, TypeScript; modali estensione con `ExtensionModal` o modali dedicati
- **UI condivisa**: `server/static/extensions/ui.css` — classi `.ext-ui-*` e `.ext-*` per uniformare l’aspetto
- **Comunicazione**: `postMessage` tra iframe estensione e client. Includi `ext-bridge.js` per facilitare la comunicazione. Messaggi supportati: `planarally-open-qe` (apri compendio), `planarally-toast`, `planarally-confirm`, `planarally-prompt`, `planarally-open-document`

---

## 5. Guida alla UI

Le barre superiori e inferiori di qualsiasi estensione **seguono le stesse regole estetiche** per unificare l’interfaccia. Usa sempre le classi predefinite di `ui.css`.

### 5.1 Inclusione del foglio di stile

Includi `ui.css` nel tuo `ui/index.html`:

```html
<link rel="stylesheet" href="../../../../static/extensions/ui.css" />
```

Applica `ext-ui-root` al `<body>`.

### 5.2 Standard layout

| Elemento | Classe | Valori standard |
|----------|--------|-----------------|
| **Contenuto principale** | `ext-body` | padding 1rem 1.5rem, overflow-y auto |
| **Barra superiore** | `ext-toolbar-bar` | min-height 2.75rem, padding 0.625rem 1.5rem |
| **Barra inferiore** | `ext-bottom-bar` | min-height 2.75rem, padding 0.625rem 1.5rem, margin 0 1.5rem 1rem |
| **Pulsanti icona (barre)** | `ext-toolbar-btn`, `ext-search-add-btn` | 32×32px, icone 16×16px |
| **Barra di ricerca** | `ext-search-bar` | Ricerca + pulsante +: icona lente a sinistra, input centrale, pulsante + (32×32) a destra |

### 5.3 Barra di ricerca unificata (ext-search-bar)

La barra di ricerca deve **sempre** avere a sinistra l’icona della lente e a destra il pulsante +, come nelle altre estensioni (Compendium, Gestione estensioni, ecc.).

**Struttura HTML:**

```html
<div class="ext-search-bar">
    <span class="ext-search-icon" aria-hidden="true">&#128269;</span>
    <!-- oppure con FontAwesome: <font-awesome-icon icon="search" class="ext-search-icon" /> -->
    <input type="text" class="ext-search-input" placeholder="Cerca..." />
    <button type="button" class="ext-search-add-btn" title="Aggiungi">
        <span>+</span>
        <!-- oppure: <font-awesome-icon icon="plus" /> -->
    </button>
</div>
```

**Classi:**
- `ext-search-icon`: icona lente a sinistra (24px, grigio)
- `ext-search-input`: campo testo che occupa lo spazio centrale
- `ext-search-add-btn`: pulsante + (verde, 32×32, bordo #2e7d32)

### 5.4 Esempio layout completo

```
┌─────────────────────────────────────────────────────────┐
│ Header (titolo + chiudi/fullscreen/finestra)            │
├─────────────────────────────────────────────────────────┤
│ ext-toolbar-bar / ext-search-bar                        │
│   [🔍] [_____ input ricerca _____] [+]                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   Contenuto principale (pannelli, liste, ecc.)          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ ext-bottom-bar (opzionale)                              │
│   [Pulsante 1] [Pulsante 2]                    →        │
└─────────────────────────────────────────────────────────┘
```

### 5.5 Altre classi UI disponibili

Vedi [sezione 6.4](#64-stili-ui-predefiniti) per l’elenco completo di tipografia, pulsanti, form, liste e messaggi.

### 5.6 Comunicazione iframe–client (postMessage)

Le estensioni con `entry` in `extension.toml` vengono caricate in un iframe. Per dialoghi e integrazioni usa `postMessage` verso `window.top` o `window.parent`.

**Inclusione del bridge:**

```html
<script src="../../../../static/extensions/ext-bridge.js"></script>
```

**Messaggi dall’iframe verso il client:**

| Tipo | Payload | Effetto |
|------|---------|---------|
| `planarally-confirm` | `{ id, title, message }` | Modale conferma (sì/no) — risponde con `planarally-confirm-response` |
| `planarally-prompt` | `{ id, question, title, defaultValue }` | Modale prompt — risponde con `planarally-prompt-response` |
| `planarally-toast` | `{ message, error? }` | Toast successo o errore |
| `planarally-open-qe` | `{ collection, slug, compendium? }` | Apre il Compendium sull’articolo |
| `planarally-open-document` | `{ fileHash, name, page? }` | Apre il visualizzatore PDF (est. Documents) |
| `planarally-qe-hover` | `{ collection, slug, compendium?, clientX, clientY }` | Mostra tooltip compendio in hover |
| `planarally-qe-hover-end` | — | Nasconde tooltip compendio |
| `planarally-close-extension` | — | Chiede al client di chiudere l'estensione (usato per ESC) |

**Note sul tasto ESC:**
PlanarAlly chiude automaticamente l'estensione focalizzata quando viene premuto il tasto ESC. Se l'estensione usa un iframe, `ext-bridge.js` invia automaticamente il messaggio `planarally-close-extension` al client.

**Funzioni helper (ext-bridge.js):**
- `parentConfirm(title, message)` → `Promise<boolean>`
- `parentPrompt(question, title, defaultValue)` → `Promise<string>`

---

## 6. Creare un'estensione passo a passo

### 6.1 Struttura cartella

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

### 6.2 Manifest (extension.toml)

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

### 6.3 Intestazione standard dei modali estensione

Tutti i modali delle estensioni mostrano nella barra del titolo:

- **Chiudi** (X): chiude il modale
- **A tutto schermo**: espande/comprime il modale a schermo intero
- **Finestra separata**: apre il modale in una finestra del browser separata (utile per lavorare su più schermi)

I modali delle estensioni sono **indipendenti dal menu impostazioni**: restano aperti anche se si chiude il pannello laterale.

**Dimensioni standard della barra del titolo:**
- Altezza: `padding: 0.5rem 1rem`
- Titolo: `font-size: 1.1rem`, `font-weight: 600`
- Pulsanti (chiudi, fullscreen, finestra): `font-size: 1.1rem`

### 6.4 Stili UI predefiniti

PlanarAlly fornisce un foglio di stile condiviso per unificare l'aspetto delle UI delle estensioni. Includilo nel tuo `ui/index.html`:

```html
<link rel="stylesheet" href="../../../../static/extensions/ui.css" />
```

Poi applica la classe `ext-ui-root` al `<body>` e usa le classi predefinite per gli elementi. Puoi sovrascrivere qualsiasi stile con il tuo CSS.

**Barre (vedi [Guida alla UI](#5-guida-alla-ui) per dettagli):**
- **Barra superiore**: `ext-toolbar-bar` per il contenitore; usa `ext-search-bar` con `ext-search-icon`, `ext-search-input`, `ext-search-add-btn`
- **Barra inferiore**: `ext-bottom-bar` per azioni finali (genera, esporta)
- **Pannelli laterali collassabili**: `.ext-sidebar`, `.ext-sidebar-left`, `.ext-sidebar-right`, `.ext-sidebar-content`, `.ext-sidebar-toggle`
- **Pulsanti toolbar**: `.ext-toolbar-btn` (32×32), `.ext-toolbar-btn-add` (verde), `.ext-toolbar-btn-more` (overflow)

**Classi disponibili (prefisso `.ext-ui-` e `.ext-`):**

| Categoria | Classi | Uso |
|-----------|--------|-----|
| **Layout** | `ext-ui-root` | Contenitore principale (body) |
| **Barre** | `ext-toolbar-bar`, `ext-bottom-bar` | Barre superiore e inferiore (unificate) |
| **Ricerca** | `ext-search-bar`, `ext-search-icon`, `ext-search-input`, `ext-search-add-btn` | Barra ricerca con lente + input + pulsante + |
| **Sidebar** | `ext-sidebar`, `ext-sidebar-left`, `ext-sidebar-right`, `ext-sidebar-collapsed`, `ext-sidebar-content`, `ext-sidebar-toggle` | Pannelli laterali collassabili |
| **Toolbar** | `ext-toolbar-btn`, `ext-toolbar-btn-add`, `ext-toolbar-btn-more` | Pulsanti icona uniformi (32×32) |
| **Tipografia** | `ext-ui-title`, `ext-ui-subtitle`, `ext-ui-text`, `ext-ui-muted` | Titoli e testo |
| **Pulsanti** | `ext-ui-btn`, `ext-ui-btn-primary`, `ext-ui-btn-success`, `ext-ui-btn-danger` | Pulsanti standard (primario blu, successo verde, pericolo rosso) |
| **Campi form** | `ext-ui-field`, `ext-ui-label`, `ext-ui-hint`, `ext-ui-field-error` | Wrapper campo (label + input + hint/errore). Aggiungi `.has-error` al field per bordo rosso |
| **Input** | `ext-ui-input`, `ext-ui-select`, `ext-ui-textarea`, `ext-ui-label` | Campi modulo base |
| **Dropdown** | `ext-ui-dropdown` | Select stilizzato (alias per `<select>`) |
| **Data** | `ext-ui-date` | Input `type="date"` o `type="datetime-local"` |
| **Checkbox** | `ext-ui-checkbox`, `ext-ui-checkbox-group` | Checkbox con label; gruppo verticale di checkbox |
| **Lista multipla** | `ext-ui-multiselect`, `ext-ui-multiselect-list`, `ext-ui-multiselect-list-item` | Select multiple nativo; lista custom con checkbox |
| **Liste** | `ext-ui-list`, `ext-ui-list-item`, `ext-ui-list-item-content`, `ext-ui-list-item-name` | Liste cliccabili |
| **Lista stacked** | `ext-ui-stacked`, `ext-ui-list-item-subtitle` | Variante: sottotitolo (piccolo) sopra, titolo sotto |
| **Messaggi** | `ext-ui-msg`, `ext-ui-msg-success`, `ext-ui-msg-error`, `ext-ui-msg-info` | Feedback (successo, errore, info) |
| **Stati** | `ext-ui-loading`, `ext-ui-empty` | Caricamento e stato vuoto |
| **Sezioni** | `ext-ui-section`, `ext-ui-section-title` | Suddivisione del contenuto |
| **Utility** | `ext-ui-file-input`, `ext-ui-icon-btn`, `ext-ui-icon-btn-danger` | Input file nascosto, pulsanti icona |
| **Header modale** | `ext-modal-header`, `ext-modal-title`, `ext-modal-icon`, `ext-modal-actions`, `ext-modal-btn`, `ext-modal-close` | Header standard per modali estensione (draggable, chiudi, fullscreen, finestra) |

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

**Esempio form con componenti standard:**

```html
<form>
  <!-- Campo con label e hint -->
  <div class="ext-ui-field">
    <label class="ext-ui-label" for="nome">Nome</label>
    <input id="nome" type="text" class="ext-ui-input" />
    <span class="ext-ui-hint">Inserisci il nome desiderato</span>
  </div>

  <!-- Dropdown -->
  <div class="ext-ui-field">
    <label class="ext-ui-label" for="tipo">Tipo</label>
    <select id="tipo" class="ext-ui-dropdown">
      <option value="a">Opzione A</option>
      <option value="b">Opzione B</option>
    </select>
  </div>

  <!-- Data -->
  <div class="ext-ui-field">
    <label class="ext-ui-label" for="data">Data</label>
    <input id="data" type="date" class="ext-ui-date" />
  </div>

  <!-- Checkbox singola -->
  <label class="ext-ui-checkbox">
    <input type="checkbox" /> Abilita opzione
  </label>

  <!-- Gruppo checkbox -->
  <div class="ext-ui-checkbox-group">
    <span class="ext-ui-label">Seleziona</span>
    <label class="ext-ui-checkbox"><input type="checkbox" name="x" value="1" /> Uno</label>
    <label class="ext-ui-checkbox"><input type="checkbox" name="x" value="2" /> Due</label>
  </div>

  <!-- Lista multipla (nativa) -->
  <div class="ext-ui-field">
    <label class="ext-ui-label" for="multi">Selezione multipla</label>
    <select id="multi" class="ext-ui-multiselect" multiple>
      <option>Item 1</option>
      <option>Item 2</option>
    </select>
  </div>

  <!-- Lista multipla custom (con checkbox, label rende la riga cliccabile) -->
  <div class="ext-ui-field">
    <label class="ext-ui-label">Selezione da lista</label>
    <ul class="ext-ui-multiselect-list">
      <li class="ext-ui-multiselect-list-item"><label><input type="checkbox" /> Elemento A</label></li>
      <li class="ext-ui-multiselect-list-item"><label><input type="checkbox" /> Elemento B</label></li>
    </ul>
  </div>
</form>
```

L'autore può estendere o sovrascrivere gli stili a piacere; il set predefinito serve a velocizzare lo sviluppo e mantenere coerenza tra le estensioni.

### 6.5 API server (Python)

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

### 6.6 Registrazione route

In `server/src/routes.py` aggiungi:

```python
main_app.router.add_post(f"{subpath}/api/extensions/mia-estensione/generate", extensions.mia_estensione.generate)
```

E in `server/src/api/http/extensions/__init__.py` importa il modulo:

```python
from . import mia_estensione
```

### 6.7 Client UI

Per aggiungere la voce nel menu Extensions e aprire un modale:

1. **Stato** (`client/src/game/systems/extensions/state.ts`): aggiungi `miaEstensioneModalOpen: boolean`
2. **UI** (`client/src/game/systems/extensions/ui.ts`): `openMiaEstensioneModal()`, `closeMiaEstensioneModal()`
3. **Modale** (`client/src/game/ui/extensions/MiaEstensioneModal.vue`): componente Vue
4. **Menu** (`client/src/game/ui/menu/Extensions.vue`): in `onExtensionClick`, se `ext.id === "mia-estensione"` → `openMiaEstensioneModal()`
5. **ModalStack** (`client/src/game/ui/ModalStack.vue`): registra il modale se necessario
6. **Traduzioni** (`client/src/locales/en.json`, `it.json`): chiavi per nome estensione e UI

---

## 7. API server

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

## 8. Integrazione client

### 8.1 Stato estensioni

```typescript
// extensionsState in client/src/game/systems/extensions/state.ts
extensions: ExtensionMeta[]   // Lista da GET /api/extensions
managerOpen: boolean
dungeongenModalOpen: boolean  // Esempio: modale aperto/chiuso
```

### 8.2 Client HTTP

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

### 8.3 Menu Extensions

Il menu è in `client/src/game/ui/menu/Extensions.vue`:

- Carica lista con `GET /api/extensions`
- Ogni voce mostra nome (tradotto) e al click chiama `onExtensionClick(ext)`
- **Toggle**: se l'estensione è già aperta, il click la chiude; altrimenti la apre
- **Bring-to-front**: quando si apre un'estensione, il suo modale viene portato in primo piano (z-index)
- Per ogni estensione: `if (ext.id === "xxx") openXxxModal()`

### 8.4 Traduzioni

Aggiungi in `client/src/locales/en.json` e `it.json`:

```json
"game.ui.menu.Extensions.extensions.xxx": "Nome Estensione"
```

E sotto `game.ui.extensions.XxxModal` per le etichette del modale.

---

## 9. Integrazione con la mappa

### 9.1 Aggiungere asset alla mappa

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

### 9.2 Custom data sulle forme

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

### 9.3 Tab nelle proprietà

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

### 9.4 Aggiornare immagine di un asset

```typescript
import type { AssetId } from "../../../assets/models";

// Firma completa: setImage(assetId: AssetId, url: string, sync: boolean)
// assetId deve essere il numero ID dell'asset nel database (restituito da Asset.create() lato server).
// Non passare la URL al posto dell'assetId: sono tipi diversi.
(shape as Asset).setImage(assetId, newUrl, true);
```

> **Attenzione**: le immagini temporanee salvate in `/static/temp/` non hanno un `AssetId` valido.
> Per poter chiamare `setImage()` correttamente, l'endpoint server deve salvare l'immagine come asset
> permanente (`Asset.create()`) e restituire `assetId` nella risposta JSON.

### 9.5 Sub-modali draggable dentro un'estensione

Quando un'estensione ha bisogno di un pannello secondario (es. opzioni AI, configurazione rapida) che non blocchi la vista del contenuto principale, usa un **sub-modale draggable** anziché un overlay opaco.

**Pattern standard**: `position: absolute` dentro il contenitore del modale principale (che deve avere `position: relative`), con una handle bar che avvia il drag via `mousedown`.

**Esempio Vue 3 (TypeScript)**:

```typescript
const subModalPos = ref({ x: 40, y: 40 });
let _drag: { startX: number; startY: number; origX: number; origY: number } | null = null;

function dragStart(e: MouseEvent): void {
    e.preventDefault();
    _drag = { startX: e.clientX, startY: e.clientY, origX: subModalPos.value.x, origY: subModalPos.value.y };
    window.addEventListener("mousemove", dragMove);
    window.addEventListener("mouseup", dragEnd);
}
function dragMove(e: MouseEvent): void {
    if (!_drag) return;
    subModalPos.value = { x: _drag.origX + (e.clientX - _drag.startX), y: _drag.origY + (e.clientY - _drag.startY) };
}
function dragEnd(): void {
    _drag = null;
    window.removeEventListener("mousemove", dragMove);
    window.removeEventListener("mouseup", dragEnd);
}
```

```html
<!-- Il contenitore padre deve avere position: relative -->
<div
    v-if="showSubModal"
    class="ext-sub-modal"
    :style="{ left: subModalPos.x + 'px', top: subModalPos.y + 'px' }"
>
    <div class="ext-sub-modal-handle" @mousedown="dragStart">
        <span>Titolo sotto-modale</span>
        <button class="ext-sub-modal-close" @click="showSubModal = false">✕</button>
    </div>
    <div class="ext-sub-modal-body">
        <!-- contenuto -->
    </div>
</div>
```

**Classi CSS** (usa direttamente in un blocco `<style scoped>` — non sono in `ui.css` in quanto specific per questo pattern):

```scss
.ext-sub-modal {
    position: absolute;
    z-index: 200;
    background: white;
    border: 1px solid #ccc;
    border-radius: 0.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    min-width: 300px;
    display: flex;
    flex-direction: column;
    user-select: none;
}
.ext-sub-modal-handle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    background: #f0f0f0;
    border-bottom: 1px solid #ddd;
    border-radius: 0.5rem 0.5rem 0 0;
    cursor: grab;
    font-weight: 600;
    &:active { cursor: grabbing; }
}
.ext-sub-modal-close {
    background: none; border: none; cursor: pointer;
    font-size: 0.9rem; color: #666;
    &:hover { color: #333; }
}
.ext-sub-modal-body { padding: 1rem; }
```

> **Regola UX**: il sub-modale non usa overlay opaco, così il contenuto principale resta visibile e consultabile. Resettare la posizione ad ogni apertura (`subModalPos.value = { x: 40, y: 40 }`) per mostrarlo sempre in un punto noto.

---

## 10. Riferimento: MapsGen (ex DungeonGen)

MapsGen è l'estensione di riferimento per la generazione procedurale di mappe. Struttura:

### Server

- **File principale**: `server/src/api/http/extensions/dungeongen.py`
- **Generatore edifici**: `server/src/api/http/extensions/building_generator.py`
- **Endpoint**: `POST /api/extensions/dungeongen/generate`
- **Body modalità dungeon**: `{ mode: "dungeon", size, archetype, symmetry, water, pack, roomsize, round_rooms, halls, cross, symmetry_break, show_numbers, seed }`
- **Body modalità edificio**: `{ mode: "building", archetype, footprint, layout, size, seed }`
- **Response comune**: `{ url, assetId, name, gridCells, imageWidth, imageHeight, syncSquareSize, padding, seed, walls: { lines }, doors }`

**Parametri specifici dungeon** (`mode: "dungeon"`):
| Campo | Valori | Default |
|-------|--------|---------|
| `size` | `tiny`, `small`, `medium`, `large`, `xlarge` | `medium` |
| `archetype` | `classic`, `warren`, `temple`, `crypt`, `cavern`, `fortress`, `lair` | `classic` |
| `symmetry` | `none`, `bilateral`, `radial2`, `radial4`, `partial` | `none` |
| `water` | `dry`, `puddles`, `pools`, `lakes`, `flooded` | `dry` |
| `pack` | `sparse`, `normal`, `tight` | `normal` |
| `roomsize` | `cozy`, `mixed`, `grand` | `mixed` |
| `cross` | `none`, `low`, `med`, `high` | `med` |

**Parametri specifici edificio** (`mode: "building"`):
| Campo | Valori | Default |
|-------|--------|---------|
| `size` | `small`, `medium`, `large`, `xlarge` | `medium` |
| `archetype` | `house`, `shop`, `tavern`, `inn` | `tavern` |
| `footprint` | `rectangle`, `l_shape`, `cross`, `offset` | `rectangle` |
| `layout` | `open_plan`, `corridor` | `open_plan` |

**Numero di stanze per dimensione** (edifici, casuale nel range):
| Size | Stanze |
|------|--------|
| `small` | 1–3 |
| `medium` | 3–5 |
| `large` | 5–10 |
| `xlarge` | 10–15 |

**Connettività garantita**: il generatore di edifici esegue fino a 20 tentativi con seed consecutivi per garantire che tutte le stanze siano raggiungibili dalla stanza primaria (BFS).

### Rendering

- Le immagini generate non contengono più il **quadrato di sincronizzazione** nell'angolo in alto a sinistra. Il sizing è interamente basato sui metadati JSON (`syncSquareSize`, `imageWidth`, `imageHeight`, `padding`).
- Le immagini sono salvate come asset permanenti nel DB (`Asset.create()`): il client riceve `assetId` nella risposta e può chiamare correttamente `setImage(assetId, url, sync)`.

### Client

- **Modale**: `client/src/game/ui/extensions/DungeongenModal.vue` — parametri, anteprima, "Aggiungi alla mappa", "Rendi realistico con AI", "Sostituisci sulla mappa"
- **Menu**: `Extensions.vue` → click su MapsGen → `openDungeongenModal()`
- **Stato**: `extensionsState.dungeongenModalOpen`
- **Selettore modalità**: `HeaderModeSelector` nella parte alta del modale permette di passare tra `dungeon` e `building`; il cambio modalità azzera l'anteprima corrente

### AI realistica

L'endpoint `POST /api/extensions/openrouter/transform-image` riceve l'URL dell'immagine generata e la trasforma con un modello AI (Google Gemini Image o OpenRouter). La risposta contiene `imageUrl` (URL asset permanente) e `assetId`, così il client può sostituire correttamente la forma sulla mappa.

### Integrazione mappa

- **`addDungeonToMap()`** (`client/src/game/dungeongen.ts`):
  - Crea Asset con immagine
  - Imposta nome = seed
  - Salva custom data con parametri e seed
  - Aggiunge automaticamente muri (layer Lighting) e porte (layer Map)
- **`DungeonGenSettings.vue`**: tab nelle proprietà per forme dungeon/edificio, permette rigenerare e sostituire

### Custom data

- `source`: `"dungeongen"`
- `name`: `"params"`
- `value`: JSON con `{ params, seed, gridCells, dungeonMeta, walls, doors }`

### Helper

- `hasDungeonData(shapeId)`: true se la forma ha custom data MapsGen
- `getDungeonStoredData(shapeId)`: restituisce i dati salvati

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
