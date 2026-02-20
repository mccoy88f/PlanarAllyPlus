#!/usr/bin/env bash
# PlanarAlly Plus - Avvia solo il server (senza install)
# Usato dal launcher per avvio/riavvio veloce

# Carica profilo utente - necessario quando lanciato da app GUI
for f in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
    [ -f "$f" ] && . "$f" 2>/dev/null
done
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/server"
exec uv run planarally.py
