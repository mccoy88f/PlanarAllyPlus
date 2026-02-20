# Guida - Documentazione PlanarAlly

Questa estensione integra la documentazione in PlanarAlly. La lingua viene sincronizzata con l'impostazione dell'app (italiano o inglese).

## Lingue

- **Italiano** (`docs/`) — da planarally-docs-ita
- **Inglese** (`docs-en/`) — da planarally-docs (originale)

La lingua mostrata segue il `locale` dell'utente (impostazioni PlanarAlly).

## Aggiornare la documentazione

### Italiano

```bash
cd ../planarally-docs-ita
npm run build
rm -rf ../PlanarAlly-dev/extensions/Guida/docs
cp -R dist ../PlanarAlly-dev/extensions/Guida/docs
cd ../PlanarAlly-dev/extensions/Guida
node fix-docs-links.js docs guida-docs
```

### Inglese

```bash
cd ../planarally-docs
npm run build
rm -rf ../PlanarAlly-dev/extensions/Guida/docs-en
cp -R dist ../PlanarAlly-dev/extensions/Guida/docs-en
cd ../PlanarAlly-dev/extensions/Guida
node fix-docs-links.js docs-en guida-docs-en
```

(planarally-docs è già configurato con base `/guida-docs-en/`)

**Nota**: Lo script `fix-docs-links.js` corregge i link e le immagini che usano path assoluti (`/docs/`, `/logos/`, `/blog/`, ecc.) aggiungendo il prefisso base, necessario perché il layout delle docs usa path hardcoded che non rispettano il `base` di Astro.

## Struttura

- `ui/index.html` — wrapper con barra di ricerca e iframe (legge `?locale=` dall'URL)
- `docs/` — build italiano (planarally-docs-ita)
- `docs-en/` — build inglese (planarally-docs)
