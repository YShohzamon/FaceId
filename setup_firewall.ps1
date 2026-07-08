# Run this script AS ADMINISTRATOR (right-click -> Run as administrator)
# Allows phone to connect to FaceID server over Wi-Fi

$ruleName = "FaceID HTTPS 8000"
$exists = netsh advfirewall firewall show rule name="$ruleName" 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host "Firewall rule already exists: $ruleName"
} else {
    netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP localport=8000
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Firewall rule added successfully."
    } else {
        Write-Host "Failed. Make sure you run as Administrator."
    }
}

Write-Host ""
Write-Host "Now run: .\run_https.ps1"
Write-Host "On phone open: https://<PC-IP>:8000"
