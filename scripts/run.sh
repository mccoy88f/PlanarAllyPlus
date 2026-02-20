#!/usr/bin/env bash
# PlanarAlly Plus - Startup script for Linux/macOS
# Checks prerequisites, installs dependencies and starts the server

set -e

# Load user profile (nvm, fnm, etc.) - needed when launched from GUI app
set +e
for f in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
    [ -f "$f" ] && . "$f" 2>/dev/null
done
set -e
# Common paths for node/npm
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.local/share/fnm/current/bin:$HOME/.volta/bin:$HOME/.asdf/shims:$PATH"
[ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" 2>/dev/null

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== PlanarAlly Plus - Verifica prerequisiti ==="

# Check Node.js (required 20+)
if ! command -v node &> /dev/null; then
    echo -e "${RED}Node.js non trovato.${NC}"
    echo "Installa da: https://nodejs.org/ (consigliato: LTS 20+)"
    exit 1
fi
NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VER" -lt 20 ] 2>/dev/null; then
    echo -e "${RED}Node.js ${NODE_VER} troppo vecchio. Richiesto 20+.${NC}"
    exit 1
fi
echo -e "${GREEN}Node.js: $(node -v)${NC}"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}npm non trovato.${NC}"
    exit 1
fi
echo -e "${GREEN}npm: $(npm -v)${NC}"

# Check Python (3.13 recommended - 3.14 has skia-python compatibility issues)
if ! command -v python3.13 &> /dev/null && ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}Python non trovato.${NC}"
    echo "Installa Python 3.13 da: https://www.python.org/ (3.14 non supportato da skia-python)"
    exit 1
fi
# Prefer 3.13 (skia-python only has wheel for cp313)
PYTHON_CMD=$(command -v python3.13 2>/dev/null || command -v python3 2>/dev/null || command -v python)
PYTHON_VER=$("$PYTHON_CMD" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "0")
PY_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] 2>/dev/null || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 13 ]; }; then
    echo -e "${RED}Python $PYTHON_VER trovato. Richiesto 3.13.${NC}"
    exit 1
fi
if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 14 ] 2>/dev/null; then
    echo -e "${RED}Python $PYTHON_VER: skia-python non supporta 3.14+. Usa Python 3.13.${NC}"
    exit 1
fi
echo -e "${GREEN}Python: $PYTHON_VER${NC}"

# Check uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}uv non trovato.${NC}"
    echo "Installa con: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "oppure: brew install uv"
    exit 1
fi
echo -e "${GREEN}uv: $(uv --version 2>/dev/null | head -1)${NC}"

echo ""
# Skip full install if already set up (faster restarts, preserves user data)
NEED_INSTALL=false
if [ ! -d "$ROOT/client/node_modules" ] || [ ! -d "$ROOT/server/.venv" ]; then
    NEED_INSTALL=true
fi
if [ ! -d "$ROOT/server/static/vite" ] || [ -z "$(ls -A "$ROOT/server/static/vite" 2>/dev/null)" ]; then
    NEED_INSTALL=true
fi

if [ "$NEED_INSTALL" = true ]; then
    echo "=== Installazione dipendenze ==="
    echo "Installo dipendenze client..."
    cd "$ROOT/client"
    npm ci
    echo "Build client..."
    npm run build
    echo "Installo dipendenze server..."
    cd "$ROOT/server"
    uv sync --python "$PYTHON_CMD" --no-group dev
    cd "$ROOT"
else
    echo "=== Dipendenze già presenti, avvio diretto ==="
fi

echo ""
echo -e "${GREEN}=== Avvio server PlanarAlly Plus ===${NC}"
echo "Apri http://localhost:8000 nel browser"
echo ""

cd "$ROOT/server"
exec uv run --python "$PYTHON_CMD" planarally.py
