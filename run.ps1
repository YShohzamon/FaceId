# Start FaceID server
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

& "$Root\stop_servers.ps1"

Write-Host ""
Write-Host "Starting server on http://localhost:8000"
Write-Host ""

& "$Root\.venv\Scripts\python.exe" -m uvicorn app.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --reload
