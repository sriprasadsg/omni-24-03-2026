# Check for Administrator privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Warning "This script requires Administrator privileges to start the MongoDB service."
    Write-Warning "Please right-click and select 'Run as Administrator'."
    exit
}

Write-Host "Attempting to start MongoDB Service..." -ForegroundColor Cyan
try {
    Start-Service -Name "MongoDB" -ErrorAction Stop
    Write-Host "MongoDB started successfully!" -ForegroundColor Green
    
    # Wait a moment for DB to be ready
    Start-Sleep -Seconds 5
    
    # Run the main startup script
    Write-Host "Launching Platform Services..." -ForegroundColor Cyan
    ./start-all-services.ps1
}
catch {
    Write-Error "Failed to start MongoDB. Please explicitly install MongoDB or ensure the service name is 'MongoDB'."
    Write-Error $_
    Write-Host "You can try running 'net start MongoDB' manually in an Admin Command Prompt." -ForegroundColor Yellow
}
