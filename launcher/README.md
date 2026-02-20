# PlanarAlly Plus Launcher

Desktop app that downloads the repo ZIP, extracts it and starts the server. You don't need to rebuild the launcher when the code changes.

<p align="center"><small>Read in: <a href="README.it.md">Italiano</a></small></p>

## Behaviour

1. **Start**: downloads the ZIP from the repo (if not already present), extracts it and starts the server
2. **Update**: re-downloads the ZIP and re-extracts it (useful after updates)
3. Files are stored in `~/Library/Application Support/PlanarAllyPlus` (macOS) or `%LOCALAPPDATA%\PlanarAllyPlus` (Windows)

## ZIP URL configuration

To point to your fork, create `config.json` in the data folder:

**macOS**: `~/Library/Application Support/PlanarAllyPlus/config.json`  
**Windows**: `%LOCALAPPDATA%\PlanarAllyPlus\config.json`  
**Linux**: `~/.local/share/PlanarAllyPlus/config.json`

```json
{
  "zip_url": "https://github.com/YOUR_USER/YOUR_REPO/archive/refs/heads/dev.zip"
}
```

Example for a fork on branch `main`:
```json
{
  "zip_url": "https://github.com/myuser/PlanarAlly-dev/archive/refs/heads/main.zip"
}
```

## Platform builds

```bash
cd launcher
npm install
npm run build
npm run tauri build
```

For specific targets (e.g. Windows on Mac with cross-compilation):
```bash
npm run tauri build -- --target x86_64-pc-windows-msvc
```

Output in `src-tauri/target/release/bundle/`.

## Release ZIP

Launchers are **standalone**: just distribute the executable (.app on Mac, .exe on Windows). On startup the app:
- automatically downloads the ZIP from the repo
- extracts it locally
- runs the scripts (run.sh/run.bat)

You don't need to include client/server/extensions in the release ZIP: only the launcher executable.

## GitHub Release

To create a release with macOS, Linux and Windows builds:

1. **Permissions**: in GitHub → Settings → Actions → General, set "Workflow permissions" to "Read and write"
2. **Tag**: create a tag `launcher-v0.1.0` (use the version from `tauri.conf.json`) and push:
   ```bash
   git tag launcher-v0.1.0
   git push origin launcher-v0.1.0
   ```
3. Or **manual**: GitHub → Actions → "Launcher Release" → Run workflow

The workflow creates a draft release with all artifacts. Publish the release when ready.
