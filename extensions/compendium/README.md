# Quinta Edizione - Knowledge Base

Knowledge base con le informazioni della 5a edizione 2024 da [quintaedizione.online](https://quintaedizione.online).

## Database

L'estensione usa SQLite per prestazioni migliori. Al primo avvio, se `quintaedizione.db` non esiste, converte automaticamente da `quintaedizione-export.json`.

### File nella cartella `db/`

- **quintaedizione-export.json** – sorgente dei dati (da esportare da quintaedizione.online)
- **quintaedizione.db** – database SQLite (creato automaticamente o manualmente)

### Aggiornare il database

Dopo aver sostituito `quintaedizione-export.json` con una nuova export:

```bash
# dalla cartella dell'estensione
cd extensions/compendium
python3 scripts/convert_json_to_sqlite.py

# oppure dalla root del progetto
python3 extensions/compendium/scripts/convert_json_to_sqlite.py
```

Oppure elimina `quintaedizione.db`: l'estensione ricreerà il DB al prossimo avvio.

### Formato JSON di export

```json
{
  "collections": [
    {
      "slug": "incantesimi",
      "name": "incantesimi",
      "items": [
        {
          "slug": "palla-di-fuoco",
          "name": "Palla di Fuoco",
          "markdown": "## Palla di Fuoco\n\n*Incantesimo di 3° livello...*"
        }
      ]
    }
  ]
}
```

### Funzionalità

- **Link qe:** – condividi articoli in chat con `[📖 Nome](qe:collection/slug)`
- **Hover tooltip** – passa il mouse sui link per un'anteprima rapida
- **Autolink** – nel contenuto degli articoli, i riferimenti ad altri articoli (es. "Elfo", "Barbaro") diventano link cliccabili

### Aggiornare il database (convertire JSON in SQLite)

Al primo avvio l'estensione converte automaticamente il JSON in SQLite. Per riconvertire manualmente dopo aver sostituito il file JSON:

```bash
python3 scripts/convert_json_to_sqlite.py
```

(da questa cartella `extensions/compendium`)
