# PowerShell script to update MongoDB connection string in .env file
# Version 2 - Fixed special character handling

$envFile = "backend\.env"
$backupFile = "backend\.env.backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "MongoDB Authentication - .env Updater v2" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-Not (Test-Path $envFile)) {
    Write-Host "❌ ERROR: .env file not found at $envFile" -ForegroundColor Red
    exit 1
}

# Backup existing .env
Write-Host "📋 Creating backup: $backupFile" -ForegroundColor Yellow
Copy-Item $envFile $backupFile
Write-Host "✅ Backup created" -ForegroundColor Green
Write-Host ""

# Read current content as array of lines
$lines = Get-Content $envFile

# Show current MONGODB_URL
Write-Host "Current configuration:" -ForegroundColor Yellow
foreach ($line in $lines) {
    if ($line -like "MONGODB_URL=*") {
        Write-Host "  $line" -ForegroundColor Gray
    }
}
Write-Host ""

# Define the new connection string (URL-encoded password)
$newMongoUrl = 'MONGODB_URL=mongodb://omni_app:SecureApp%232025!MongoDB@localhost:27017/omni_platform?authSource=omni_platform'

# Process lines
$newLines = @()
$foundMongoUrl = $false

foreach ($line in $lines) {
    if ($line -like "MONGODB_URL=*") {
        # Replace this line
        $newLines += $newMongoUrl
        $foundMongoUrl = $true
        Write-Host "🔄 Replaced existing MONGODB_URL" -ForegroundColor Yellow
    }
    else {
        $newLines += $line
    }
}

# If MONGODB_URL wasn't found, add it at the top
if (-not $foundMongoUrl) {
    $newLines = @($newMongoUrl) + $newLines
    Write-Host "➕ Added MONGODB_URL to beginning" -ForegroundColor Yellow
}

# Write updated content back to .env
$newLines | Out-File -FilePath $envFile -Encoding UTF8

Write-Host "✅ Updated .env file" -ForegroundColor Green
Write-Host ""

# Show new configuration
Write-Host "New configuration:" -ForegroundColor Green
$updatedLines = Get-Content $envFile
foreach ($line in $updatedLines) {
    if ($line -like "MONGODB_URL=*") {
        Write-Host "  $line" -ForegroundColor Gray
    }
}
Write-Host ""

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "✅ MongoDB Authentication Enabled" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📋 Summary:" -ForegroundColor Cyan
Write-Host "  • Backup: $backupFile" -ForegroundColor White
Write-Host "  • Username: omni_app" -ForegroundColor White
Write-Host "  • Password: SecureApp#2025!MongoDB" -ForegroundColor Yellow
Write-Host "  • Database: omni_platform" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Restart the backend server (it will reload .env)" -ForegroundColor White
Write-Host "2. MongoDB will still work WITHOUT auth enabled" -ForegroundColor White
Write-Host "3. Later we'll enable MongoDB --auth mode" -ForegroundColor White
Write-Host ""
