@echo off
REM PlanarAlly Plus - Script avvio per Windows (batch)
REM Verifica prerequisiti, installa dipendenze e avvia il server

setlocal
cd /d "%~dp0\.."

echo === PlanarAlly Plus - Verifica prerequisiti ===

REM Verifica Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Node.js non trovato.
    echo Installa da: https://nodejs.org/ ^(consigliato: LTS 20+^)
    exit /b 1
)
for /f "tokens=*" %%v in ('node -v 2^>nul') do set NODE_VER=%%v
echo Node.js: %NODE_VER%

REM Verifica npm
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: npm non trovato.
    exit /b 1
)
for /f "tokens=*" %%v in ('npm -v 2^>nul') do set NPM_VER=%%v
echo npm: %NPM_VER%

REM Verifica Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERRORE: Python non trovato.
        echo Installa Python 3.13+ da: https://www.python.org/
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)
echo Python: ok

REM Verifica uv
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: uv non trovato.
    echo Installa con PowerShell: irm https://astral.sh/uv/install.ps1 ^| iex
    echo oppure: winget install --id=astral-sh.uv -e
    exit /b 1
)
for /f "tokens=*" %%v in ('uv --version 2^>nul') do set UV_VER=%%v
echo uv: %UV_VER%

echo.
echo === Installazione dipendenze ===

echo Installo dipendenze client...
cd client
call npm ci
if %errorlevel% neq 0 exit /b 1

echo Build client...
call npm run build
if %errorlevel% neq 0 exit /b 1

echo Installo dipendenze server...
cd ..\server
call uv sync --no-group dev
if %errorlevel% neq 0 exit /b 1

echo.
echo === Avvio server PlanarAlly Plus ===
echo Apri http://localhost:8000 nel browser
echo.

uv run planarally.py
