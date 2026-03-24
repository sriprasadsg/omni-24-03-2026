# Quick fix to properly enable MongoDB authentication
# Run as Administrator

Write-Host "Fixing MongoDB authentication config..." -ForegroundColor Yellow

$configFile = "C:\Program Files\MongoDB\Server\8.0\bin\mongod.cfg"

# Read the config
$content = Get-Content $configFile

# Replace commented security section with active one
$newContent = @()
$inSecurity = $false

foreach ($line in $content) {
    if ($line -match "^#security:") {
        # Replace commented security with active security + authorization
        $newContent += "security:"
        $newContent += "  authorization: enabled"
        $inSecurity = $true
        Write-Host "Uncommented and enabled security section" -ForegroundColor Green
    }
    elseif ($inSecurity -and $line -match "^#") {
        # Skip other commented lines in security section
        continue
    }
    elseif ($inSecurity -and $line -notmatch "^\s*$") {
        # End of security section
        $inSecurity = $false
        $newContent += $line
    }
    else {
        $newContent += $line
    }
}

# Write back
$newContent | Out-File -FilePath $configFile -Encoding UTF8

Write-Host "`nUpdated config:" -ForegroundColor Cyan
Get-Content $configFile | Select-String -Pattern "security" -Context 2, 2

Write-Host "`nRestarting MongoDB..." -ForegroundColor Yellow
Restart-Service MongoDB
Start-Sleep -Seconds 3

Write-Host "Testing authentication enforcement..." -ForegroundColor Yellow
$test = mongosh --quiet --eval "db.adminCommand({ping: 1})" 2>&1

if ($test -like "*not authorized*" -or $test -like "*Authentication failed*") {
    Write-Host "SUCCESS: Authentication is now REQUIRED!" -ForegroundColor Green
}
else {
    Write-Host "Still not enforced. Manual check needed." -ForegroundColor Yellow
}

Write-Host "`nDone!" -ForegroundColor Green
