#!/usr/bin/env bash
# PlanarAlly Plus - Start server only (no install)
# Used by launcher for quick start/restart

# Load user profile - needed when launched from GUI app
set +e 2>/dev/null
for f in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
    [ -f "$f" ] && . "$f" 2>/dev/null
done
set -e 2>/dev/null || true
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/server"
exec uv run planarally.py
