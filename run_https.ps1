# Start FaceID server with HTTPS on port 8000 (required for phone camera)
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Key  = Join-Path $Root "certs\key.pem"
$Cert = Join-Path $Root "certs\cert.pem"

# Stop any old servers on port 8000 (HTTP + HTTPS conflicts break phone access)
& "$Root\stop_servers.ps1"

# Allow phone access through Windows Firewall
$fwRule = "FaceID HTTPS 8000"
$existing = netsh advfirewall firewall show rule name="$fwRule" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Adding Windows Firewall rule for port 8000..."
    netsh advfirewall firewall add rule name="$fwRule" dir=in action=allow protocol=TCP localport=8000 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Firewall rule added."
    } else {
        Write-Host "Could not add firewall rule. Run PowerShell as Administrator."
    }
}

if (-not (Test-Path $Key) -or -not (Test-Path $Cert)) {
    Write-Host "Generating SSL certificate..."
    & "$Root\.venv\Scripts\python.exe" "$Root\scripts\generate_ssl_cert.py"
}

# Detect Wi-Fi IP for phone
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
Write-Host "Starting HTTPS server on port 8000..."
Write-Host "Desktop: https://localhost:8000"
if ($wifiIp) {
    Write-Host "Phone  : https://${wifiIp}:8000"
} else {
    Write-Host "Phone  : https://<your-PC-IP>:8000"
}
Write-Host ""
Write-Host "On phone: use HTTPS (not http). Accept security warning."
Write-Host ""

& "$Root\.venv\Scripts\python.exe" -m uvicorn app.main:app `
    --host 0.0.0.0 `
    --port 8000 `
    --ssl-keyfile $Key `
    --ssl-certfile $Cert `
    --reload
