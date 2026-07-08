# Stop all servers using port 8000 (fixes HTTP/HTTPS conflict)
Write-Host "Stopping processes on port 8000..."
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
    Write-Host "Port 8000 is free."
} else {
    $conns | ForEach-Object {
        $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine
        Write-Host "Stopping PID $($_.OwningProcess) on $($_.LocalAddress):8000"
        if ($cmd) { Write-Host "  $cmd" }
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

# Also stop HTTP-only uvicorn (no SSL) that blocks phone HTTPS access
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -like '*uvicorn*' -and
        $_.CommandLine -notlike '*ssl-keyfile*'
    } |
    ForEach-Object {
        Write-Host "Stopping HTTP uvicorn PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Seconds 1
$left = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($left) {
    Write-Host "WARNING: port 8000 still in use. Close other terminals and retry."
} else {
    Write-Host "Port 8000 is free. Now run: .\run_https.ps1"
}
