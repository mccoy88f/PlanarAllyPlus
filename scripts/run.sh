#!/usr/bin/env bash
# PlanarAlly Plus - Script avvio per Linux/macOS
# Verifica prerequisiti, installa dipendenze e avvia il server

set -e

# Carica profilo utente (nvm, fnm, mise, ecc.) - necessario quando lanciato da app GUI
for f in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
    [ -f "$f" ] && . "$f" 2>/dev/null
done
# Percorsi comuni per node/npm
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.local/share/fnm/current/bin:$HOME/.volta/bin:$HOME/.asdf/shims:$PATH"
[ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" 2>/dev/null

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== PlanarAlly Plus - Verifica prerequisiti ==="

# Verifica Node.js (richiesto 20+)
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

# Verifica npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}npm non trovato.${NC}"
    exit 1
fi
echo -e "${GREEN}npm: $(npm -v)${NC}"

# Verifica Python (richiesto 3.13+)
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}Python non trovato.${NC}"
    echo "Installa Python 3.13+ da: https://www.python.org/"
    exit 1
fi
PYTHON_CMD=$(command -v python3 2>/dev/null || command -v python)
PYTHON_VER=$("$PYTHON_CMD" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>/dev/null || echo "0")
PY_MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] 2>/dev/null || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 13 ]; }; then
    echo -e "${RED}Python $PYTHON_VER trovato. Richiesto 3.13+.${NC}"
    exit 1
fi
echo -e "${GREEN}Python: $PYTHON_VER${NC}"

# Verifica uv
if ! command -v uv &> /dev/null; then
    echo -e "${RED}uv non trovato.${NC}"
    echo "Installa con: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "oppure: brew install uv"
    exit 1
fi
echo -e "${GREEN}uv: $(uv --version 2>/dev/null | head -1)${NC}"

echo ""
echo "=== Installazione dipendenze ==="

# Client
echo "Installo dipendenze client..."
cd "$ROOT/client"
npm ci

echo "Build client..."
npm run build

# Server
echo "Installo dipendenze server..."
cd "$ROOT/server"
uv sync --no-group dev

echo ""
echo -e "${GREEN}=== Avvio server PlanarAlly Plus ===${NC}"
echo "Apri http://localhost:8000 nel browser"
echo ""

exec uv run planarally.py
