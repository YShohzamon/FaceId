# Stop processes using port 8000
Write-Host "Stopping processes on port 8000..."
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $conns) {
    Write-Host "Port 8000 is free."
} else {
    $conns | ForEach-Object {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" -ErrorAction SilentlyContinue).CommandLine
        Write-Host "Stopping PID $($_.OwningProcess) on $($_.LocalAddress):8000"
        if ($cmd) { Write-Host "  $cmd" }
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

Start-Sleep -Seconds 1
$left = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($left) {
    Write-Host "WARNING: port 8000 still in use. Close other terminals and retry."
} else {
    Write-Host "Port 8000 is free. Now run: .\run.ps1"
}
