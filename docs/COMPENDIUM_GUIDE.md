# Compendium Data Structure Guide / Guida alla Struttura dei Dati del Compendio

This document explains how to create and structure JSON and ZIP files for the PlanarAlly Plus Compendium extension.

Questo documento spiega come creare e strutturare i file JSON e ZIP per l'estensione Compendio di PlanarAlly Plus.

---

## English: Creating a Compendium

### 1. JSON Structure (Native Format)
The "native" format is a hierarchical JSON structure that allows for nested collections and items with Markdown content.

```json
{
  "title": "My Awesome Compendium",
  "author": "Your Name",
  "date": "2026-03-02",
  "website": "https://example.com",
  "license": "CC BY 4.0",
  "collections": [
    {
      "name": "Spells",
      "slug": "spells",
      "order": 1,
      "items": [
        {
          "name": "Fireball",
          "slug": "fireball",
          "order": 1,
          "markdown": "# Fireball\n\nA bright streak flashes from your pointing finger..."
        }
      ],
      "collections": [
        {
          "name": "First Level Spells",
          "slug": "1st-level-spells",
          "order": 1,
          "items": [ ... ]
        }
      ]
    }
  ]
}
```

- **Metadata**: Top-level fields like `title`, `author`, `date`, `website`, and `license` are optional but recommended.
- **Collections**: Use `collections` to group items or other sub-collections.
- **Items**: Each item must have a `name`, a unique `slug` (within the collection), and `markdown` content.
- **Order**: Use the `order` field (integer) to control the display sequence in the tree.

### 2. ZIP Package
To install multiple files or assets (like images) alongside your JSON, create a ZIP file:
- Place your main JSON file at the root.
- If your Markdown refers to images (e.g., `![Alt Text](images/map.png)`), include an `images` folder in the ZIP.

---

## Italiano: Creare un Compendio

### 1. Struttura JSON (Formato Nativo)
Il formato "nativo" è una struttura JSON gerarchica che permette di avere collezioni nidificate ed elementi con contenuto in Markdown.

```json
{
  "title": "Il Mio Fantastico Compendio",
  "author": "Tuo Nome",
  "date": "2026-03-02",
  "website": "https://esempio.it",
  "license": "CC BY 4.0",
  "collections": [
    {
      "name": "Incantesimi",
      "slug": "incantesimi",
      "order": 1,
      "items": [
        {
          "name": "Palla di Fuoco",
          "slug": "palla-di-fuoco",
          "order": 1,
          "markdown": "# Palla di Fuoco\n\nUn raggio luminoso parte dal tuo dito..."
        }
      ],
      "collections": [
        {
          "name": "Incantesimi di Primo Livello",
          "slug": "incantesimi-1-livello",
          "order": 1,
          "items": [ ... ]
        }
      ]
    }
  ]
}
```

- **Metadati**: I campi principali come `title`, `author`, `date`, `website`, e `license` sono opzionali ma consigliati.
- **Collezioni**: Usa `collections` per raggruppare elementi o altre sottocollezioni.
- **Elementi**: Ogni elemento deve avere un `name`, uno `slug` unico (all'interno della collezione) e il contenuto in `markdown`.
- **Ordine**: Usa il campo `order` (intero) per controllare la sequenza di visualizzazione nell'albero.

### 2. Pacchetto ZIP
Per installare più file o asset (come immagini) insieme al tuo JSON, crea un file ZIP:
- Inserisci il file JSON principale nella root dello ZIP.
- Se il tuo Markdown fa riferimento a immagini (es. `![Testo](images/mappa.png)`), includi una cartella `images` nello ZIP.
