# PlanarAlly Plus Launcher

App desktop che scarica lo ZIP della repo, lo estrae e avvia il server. Non serve ricompilare i launcher quando il codice cambia.

## Comportamento

1. **Avvio**: scarica lo ZIP dalla repo (se non già presente), lo estrae e avvia il server
2. **Aggiorna**: riscarica lo ZIP e lo riestrae (utile dopo aggiornamenti)
3. I file vengono salvati in `~/Library/Application Support/PlanarAllyPlus` (macOS) o `%LOCALAPPDATA%\PlanarAllyPlus` (Windows)

## Configurazione URL ZIP

Per puntare al tuo fork, crea `config.json` nella cartella dati:

**macOS**: `~/Library/Application Support/PlanarAllyPlus/config.json`  
**Windows**: `%LOCALAPPDATA%\PlanarAllyPlus\config.json`  
**Linux**: `~/.local/share/PlanarAllyPlus/config.json`

```json
{
  "zip_url": "https://github.com/TUO_USER/TUO_REPO/archive/refs/heads/dev.zip"
}
```

Esempio per un fork su branch `main`:
```json
{
  "zip_url": "https://github.com/mioutente/PlanarAlly-dev/archive/refs/heads/main.zip"
}
```

## Build per piattaforme

```bash
cd launcher
npm install
npm run build
npm run tauri build
```

Per target specifici (es. Windows su Mac con cross-compilation):
```bash
npm run tauri build -- --target x86_64-pc-windows-msvc
```

Output in `src-tauri/target/release/bundle/`.

## Release ZIP

I launcher sono **standalone**: basta distribuire l'eseguibile (.app su Mac, .exe su Windows). All'avvio l'app:
- scarica automaticamente lo ZIP dalla repo
- estrae in locale
- esegue gli script (run.sh/run.bat)

Non serve includere client/server/estensioni nello ZIP di release: solo l'eseguibile del launcher.

## GitHub Release

Per creare una release con build macOS, Linux e Windows:

1. **Autorizzazioni**: in GitHub → Settings → Actions → General, imposta "Workflow permissions" su "Read and write"
2. **Tag**: crea un tag `launcher-v0.1.0` (usa la versione da `tauri.conf.json`) e push:
   ```bash
   git tag launcher-v0.1.0
   git push origin launcher-v0.1.0
   ```
3. Oppure **manuale**: GitHub → Actions → "Launcher Release" → Run workflow

La workflow crea una draft release con tutti gli artifacts. Pubblica la release quando pronta.

---

**Altre lingue**: [English](README.md)
