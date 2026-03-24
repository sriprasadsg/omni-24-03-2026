$baseUrl = "http://127.0.0.1:5000"
$loginUrl = "$baseUrl/api/auth/login"
$loginBody = @{
    email = "admin@exafluence.com"
    password = "password123"
} | ConvertTo-Json

Write-Host "Logging in..."
$resp = Invoke-RestMethod -Uri $loginUrl -Method Post -Body $loginBody -ContentType "application/json"
$token = $resp.access_token
Write-Host "Login Success. Tenant: $($resp.user.tenantId)"

$headers = @{
    Authorization = "Bearer $token"
}

Write-Host "`n--- AI Models Check ---"
try {
    $models = Invoke-RestMethod -Uri "$baseUrl/api/ai-governance/models" -Method Get -Headers $headers
    Write-Host "Models Count: $($models.Count)"
} catch {
    Write-Host "Models Failed: $_"
}

Write-Host "`n--- Compliance Frameworks Check ---"
$frameworks = Invoke-RestMethod -Uri "$baseUrl/api/compliance" -Method Get -Headers $headers
Write-Host "Frameworks Count: $($frameworks.Count)"
