# Ejecutar SIN administrador: powershell -ExecutionPolicy Bypass -NoProfile -File .\scripts\iniciar_backend.ps1
# Solo servidor de desarrollo; no reemplaza IIS/servicio WSGI en produccion.
$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw 'No existe .venv. Siga primero las instrucciones del README.md.'
}
Push-Location $Raiz
try {
    & $Python 'manage.py' 'check'
    if ($LASTEXITCODE -ne 0) { throw 'La configuracion Django no paso las verificaciones.' }
    & $Python 'manage.py' 'runserver' '0.0.0.0:8006'
} finally {
    Pop-Location
}
