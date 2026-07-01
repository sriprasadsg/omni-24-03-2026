param(
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [string]$Email = "super@omni.ai",
    [string]$Password = "Admin@2030"
)

Write-Host "`nAuthenticating as $Email ..." -ForegroundColor Cyan
$loginBody = @{ email = $Email; password = $Password } | ConvertTo-Json
try {
    $auth = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api/auth/login" -Body $loginBody -ContentType "application/json"
    $token = $auth.access_token
    Write-Host "  Login OK`n" -ForegroundColor Green
} catch {
    Write-Host "  Login FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
$headers = @{ Authorization = "Bearer $token" }

$newEndpoints = @(
    @{ path = "/api/sca/policies";              label = "SCA Policies" },
    @{ path = "/api/sca/stats";                 label = "SCA Stats" },
    @{ path = "/api/agent-groups/";             label = "Agent Groups" },
    @{ path = "/api/config-drift/stats";        label = "Config Drift Stats" },
    @{ path = "/api/fim/paths";                 label = "FIM Paths" },
    @{ path = "/api/fim/stats";                 label = "FIM Stats" },
    @{ path = "/api/active-response/rules";     label = "Active Response Rules" },
    @{ path = "/api/active-response/stats";     label = "Active Response Stats" },
    @{ path = "/api/active-response/triggers";  label = "Active Response Triggers" },
    @{ path = "/api/advanced-hunting/queries";  label = "Advanced Hunting Queries" },
    @{ path = "/api/detection-rules/";          label = "Detection Rules" },
    @{ path = "/api/connectors-hub/";           label = "Connectors Hub" },
    @{ path = "/api/security-copilot/history";  label = "Security Copilot History" },
    @{ path = "/api/mssp/dashboard";            label = "MSSP Dashboard" },
    @{ path = "/api/retention-tiers/";          label = "Retention Tiers" },
    @{ path = "/api/retention-tiers/stats";     label = "Retention Tiers Stats" }
)

Write-Host "--- New Feature Endpoints ---`n"
$pass = 0; $fail = 0
foreach ($ep in $newEndpoints) {
    try {
        $res = Invoke-RestMethod -Uri "$BaseUrl$($ep.path)" -Headers $headers -TimeoutSec 10
        Write-Host "  [PASS] $($ep.label)" -ForegroundColor Green
        $pass++
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Host "  [FAIL] $($ep.label)  ($code)" -ForegroundColor Red
        $fail++
    }
}

Write-Host "`n============================================="
Write-Host " New Features: $pass/$($pass+$fail) passed"
Write-Host "============================================="
if ($fail -eq 0) {
    Write-Host " All new endpoints healthy!" -ForegroundColor Green
} else {
    Write-Host " $fail endpoint(s) need attention." -ForegroundColor Yellow
}
