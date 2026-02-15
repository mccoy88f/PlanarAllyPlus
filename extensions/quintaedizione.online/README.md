# Quinta Edizione - Knowledge Base

Knowledge base con le informazioni della 5a edizione 2024 da [quintaedizione.online](https://quintaedizione.online).

## Database

L'estensione legge i dati da `db/quintaedizione-export.json`.

### Formato del file

```json
{
  "collections": [
    {
      "slug": "incantesimi",
      "name": "incantesimi",
      "count": 1,
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

### Come ottenere i dati

1. Visita [quintaedizione.online](https://quintaedizione.online)
2. Se disponibile, esporta i dati in formato JSON
3. Salva il file come `db/quintaedizione-export.json` in questa cartella

Se il file non esiste o è vuoto (`{"collections":[]}`), l'estensione mostrerà "Nessun dato" o una lista vuota.
