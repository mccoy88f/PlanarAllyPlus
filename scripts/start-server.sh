#!/usr/bin/env bash
# PlanarAlly Plus - Avvia solo il server (senza install)
# Usato dal launcher per avvio/riavvio veloce

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/server"
exec uv run planarally.py
