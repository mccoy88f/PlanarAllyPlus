#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER_DIR="$ROOT_DIR"
TAURI_DIR="$ROOT_DIR/src-tauri"
TARGET_DIR="$TAURI_DIR/target"
APPIMAGE_DIR="$TARGET_DIR/appimage"
APPDIR="$APPIMAGE_DIR/AppDir"

# Prova a caricare l'ambiente Rust (se presente)
if [ -f "$HOME/.cargo/env" ]; then
  # shellcheck disable=SC1090
  . "$HOME/.cargo/env"
fi

echo "==> Build frontend (Vite)…"
cd "$LAUNCHER_DIR"
npm run build

echo "==> Build binario Tauri (cargo release)…"
cd "$TAURI_DIR"
cargo build --release

BIN_NAME="planarally-plus-launcher"
BIN_PATH="$TARGET_DIR/release/$BIN_NAME"

if [ ! -f "$BIN_PATH" ]; then
  echo "Binario non trovato in: $BIN_PATH"
  exit 1
fi

echo "==> Preparo AppDir per linuxdeploy…"
mkdir -p \
  "$APPDIR/usr/bin" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/128x128/apps"

cp "$BIN_PATH" "$APPDIR/usr/bin/$BIN_NAME"
chmod +x "$APPDIR/usr/bin/$BIN_NAME"

ICON_DST="$APPDIR/usr/share/icons/hicolor/128x128/apps/planarally-plus-launcher.png"

if [ -f "$LAUNCHER_DIR/icons/128x128.png" ]; then
  echo "==> Uso icona esistente icons/128x128.png"
  cp "$LAUNCHER_DIR/icons/128x128.png" "$ICON_DST"
else
  echo "==> icons/128x128.png non esiste, provo a generarla da SVG principale…"
  SVG_SRC="$ROOT_DIR/pa-logo.svg"
  if [ ! -f "$SVG_SRC" ]; then
    echo "SVG principale non trovato in: $SVG_SRC"
    exit 1
  fi

  # Prova vari tool di conversione in ordine di preferenza
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w 128 -h 128 "$SVG_SRC" -o "$ICON_DST"
  elif command -v convert >/dev/null 2>&1; then
    convert "$SVG_SRC" -resize 128x128 "$ICON_DST"
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape "$SVG_SRC" --export-type=png -w 128 -h 128 -o "$ICON_DST"
  else
    echo "Nessun tool per convertire SVG in PNG trovato (manca uno tra rsvg-convert, convert, inkscape)."
    echo "Installa ad esempio: sudo apt install librsvg2-bin   # fornisce rsvg-convert"
    exit 1
  fi
fi

DESKTOP_FILE="$APPDIR/usr/share/applications/planarally-plus-launcher.desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PlanarAlly Plus Launcher
Exec=$BIN_NAME
Icon=planarally-plus-launcher
Categories=Game;Utility;
Terminal=false
EOF

echo "==> Creo AppImage con linuxdeploy…"
cd "$APPIMAGE_DIR"

if ! command -v linuxdeploy >/dev/null 2>&1; then
  echo "linuxdeploy non trovato nel PATH. Installa linuxdeploy e riprova."
  exit 1
fi

linuxdeploy \
  --appdir "$APPDIR" \
  --desktop-file "$DESKTOP_FILE" \
  --icon-file "$ICON_DST" \
  --output appimage

echo "==> AppImage generata in: $APPIMAGE_DIR"

