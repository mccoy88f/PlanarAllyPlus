# PlanarAlly Plus - Script avvio per Windows (PowerShell)
# Verifica prerequisiti, installa dipendenze e avvia il server

$ErrorActionPreference = "Stop"
$Root = if ($PSScriptRoot) { Split-Path -Parent $PSScriptRoot } else { (Get-Location).Path }
if (-not $Root) { $Root = (Get-Location).Path }
Set-Location $Root

Write-Host "=== PlanarAlly Plus - Verifica prerequisiti ===" -ForegroundColor Cyan

# Verifica Node.js (richiesto 20+)
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) {
    Write-Host "Node.js non trovato." -ForegroundColor Red
    Write-Host "Installa da: https://nodejs.org/ (consigliato: LTS 20+)" -ForegroundColor Yellow
    exit 1
}
$nodeVer = (node -v) -replace 'v', '' -split '\.' | Select-Object -First 1
if ([int]$nodeVer -lt 20) {
    Write-Host "Node.js $nodeVer troppo vecchio. Richiesto 20+." -ForegroundColor Red
    exit 1
}
Write-Host "Node.js: $(node -v)" -ForegroundColor Green

# Verifica npm
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "npm non trovato." -ForegroundColor Red
    exit 1
}
Write-Host "npm: $(npm -v)" -ForegroundColor Green

# Verifica Python (richiesto 3.13+)
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Host "Python non trovato." -ForegroundColor Red
    Write-Host "Installa Python 3.13+ da: https://www.python.org/" -ForegroundColor Yellow
    exit 1
}
try {
    $pyVer = & $python.Source -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')" 2>$null
    $pyMajor = [int]($pyVer -split '\.')[0]
    $pyMinor = [int]($pyVer -split '\.')[1]
    if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 13)) {
        Write-Host "Python $pyVer trovato. Richiesto 3.13+." -ForegroundColor Red
        exit 1
    }
    Write-Host "Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Host " impossibile verificare versione Python" -ForegroundColor Yellow
}

# Verifica uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv non trovato." -ForegroundColor Red
    Write-Host "Installa con PowerShell: irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Yellow
    Write-Host "oppure: winget install --id=astral-sh.uv -e" -ForegroundColor Yellow
    exit 1
}
Write-Host "uv: $(uv --version 2>$null | Select-Object -First 1)" -ForegroundColor Green

Write-Host ""
Write-Host "=== Installazione dipendenze ===" -ForegroundColor Cyan

# Client
Write-Host "Installo dipendenze client..."
Set-Location "$Root\client"
npm ci

Write-Host "Build client..."
npm run build

# Server
Write-Host "Installo dipendenze server..."
Set-Location "$Root\server"
uv sync --no-group dev

Write-Host ""
Write-Host "=== Avvio server PlanarAlly Plus ===" -ForegroundColor Green
Write-Host "Apri http://localhost:8000 nel browser"
Write-Host ""

uv run planarally.py
