
Write-Host "Killing processes..."
Stop-Process -Name "node" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "python" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Starting Backend..."
$backend = Start-Process -FilePath "backend\venv\Scripts\python.exe" -ArgumentList "run_backend.py" -WorkingDirectory "." -PassThru -WindowStyle Minimized

Write-Host "Starting Frontend..."
$frontend = Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory "." -PassThru -WindowStyle Minimized

Write-Host "Waiting for Backend (5000)..."
$retries = 0
while (!(Test-NetConnection -ComputerName 127.0.0.1 -Port 5000 -WarningAction SilentlyContinue).TcpTestSucceeded) { 
    Start-Sleep -Seconds 3
    $retries++
    if ($retries -gt 30) { Write-Error "Backend failed to start"; exit 1 }
}
Write-Host "Backend is UP."

Write-Host "Waiting for Frontend (3000)..."
$retries = 0
while (!(Test-NetConnection -ComputerName 127.0.0.1 -Port 3000 -WarningAction SilentlyContinue).TcpTestSucceeded) { 
    Start-Sleep -Seconds 3
    $retries++
    if ($retries -gt 30) { Write-Error "Frontend failed to start"; exit 1 }
}
Write-Host "Frontend is UP."
