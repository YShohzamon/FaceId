# Start FaceID server over HTTP (simple — works on phone without SSL)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

& "$Root\stop_servers.ps1"

$wifiIp = $null
ipconfig | ForEach-Object {
    if ($_ -match "IPv4.*:\s*(\d+\.\d+\.\d+\.\d+)") {
        $ip = $Matches[1]
        if ($ip -notlike "169.254.*" -and $ip -ne "127.0.0.1" -and $ip -notlike "172.29.*") {
            $wifiIp = $ip
        }
    }
}

Write-Host ""
Write-Host "Starting HTTP server on port 8000..."
Write-Host "Desktop: http://localhost:8000"
if ($wifiIp) {
    Write-Host "Phone  : http://${wifiIp}:8000  (same Wi-Fi)"
}
Write-Host ""

& "$Root\.venv\Scripts\python.exe" -m uvicorn app.main:app `
    --host 0.0.0.0 `
    --port 8000 `
    --reload
