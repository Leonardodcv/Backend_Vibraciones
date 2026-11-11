# Ejecutar manualmente o configurar en Programador de tareas de Windows, cada minuto.
# Usa Python del venv y no inicia servidores adicionales.
$ErrorActionPreference = 'Stop'
$Raiz = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Raiz '.venv\Scripts\python.exe'
Push-Location $Raiz
try {
    & $Python 'manage.py' 'score_vibrations' '--limit' '200'
    if ($LASTEXITCODE -ne 0) { throw 'score_vibrations termino con error.' }
} finally {
    Pop-Location
}
