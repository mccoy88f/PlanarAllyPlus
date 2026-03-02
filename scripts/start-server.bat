@echo off
REM PlanarAlly Plus - Avvia solo il server (senza install)
REM Usato dal launcher per avvio/riavvio veloce

cd /d "%~dp0\..\server"
uv run --python 3.13 planarally.py
