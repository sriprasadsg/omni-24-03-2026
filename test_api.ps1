#Requires -Version 5.1
# Quick API smoke-test. Run after services are up.
# Usage: .\test_api.ps1 [-BaseUrl http://127.0.0.1:5000] [-Email ...] [-Password ...]

param(
    [string]$BaseUrl  = "http://127.0.0.1:5000",
    [string]$Email    = "super@omni.ai",
    [string]$Password = "Admin@2030"
)

$pass = 0; $fail = 0; $results = @()

function Test-Endpoint {
    param([string]$Label, [string]$Url, [string]$Method = "GET", [hashtable]$Headers = @{})
    try {
        $null = Invoke-RestMethod -Uri $Url -Method $Method -Headers $Headers -ErrorAction Stop
        $script:pass++
        $script:results += "  [PASS] $Label"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        $script:fail++
        $script:results += "  [FAIL] $Label  ($code)"
    }
}

# ── Login ─────────────────────────────────────────────────────────────────────
Write-Host "Logging in as $Email ..." -ForegroundColor Cyan
try {
    $resp  = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method Post `
                 -Body (@{ email = $Email; password = $Password } | ConvertTo-Json) `
                 -ContentType "application/json" -ErrorAction Stop
    $token = $resp.access_token
    Write-Host "  Login OK. Tenant: $($resp.user.tenantId)" -ForegroundColor Green
} catch {
    Write-Host "  Login FAILED: $_" -ForegroundColor Red
    exit 1
}

$h = @{ Authorization = "Bearer $token" }

# ── Core ──────────────────────────────────────────────────────────────────────
Write-Host "`n--- Core ---"
Test-Endpoint "Health"                   "$BaseUrl/api/health"                       -Headers $h
Test-Endpoint "Auth Me"                  "$BaseUrl/api/auth/me"                      -Headers $h
Test-Endpoint "Agents List"              "$BaseUrl/api/agents"                       -Headers $h
Test-Endpoint "Agents Stats (alias)"     "$BaseUrl/api/agents/stats"                 -Headers $h
Test-Endpoint "Assets"                   "$BaseUrl/api/assets"                       -Headers $h

# ── MITRE ATT&CK ─────────────────────────────────────────────────────────────
Write-Host "`n--- MITRE ATT&CK ---"
Test-Endpoint "Matrix"                   "$BaseUrl/api/mitre/matrix"                 -Headers $h
Test-Endpoint "Techniques (alias)"       "$BaseUrl/api/mitre/techniques"             -Headers $h
Test-Endpoint "Tactics (alias)"          "$BaseUrl/api/mitre/tactics"                -Headers $h
Test-Endpoint "Heatmap (alias)"          "$BaseUrl/api/mitre/heatmap"                -Headers $h
Test-Endpoint "Coverage"                 "$BaseUrl/api/mitre/coverage"               -Headers $h
Test-Endpoint "Navigator (alias)"        "$BaseUrl/api/mitre/matrix"                 -Headers $h

# ── Zero Trust ────────────────────────────────────────────────────────────────
Write-Host "`n--- Zero Trust ---"
Test-Endpoint "Device Scores"            "$BaseUrl/api/zero-trust/device-trust-scores" -Headers $h
Test-Endpoint "Session Risks"            "$BaseUrl/api/zero-trust/session-risks"     -Headers $h

# ── Network (real + aliases) ──────────────────────────────────────────────────
Write-Host "`n--- Network ---"
Test-Endpoint "Devices (real)"           "$BaseUrl/api/network-devices"              -Headers $h
Test-Endpoint "Topology (real)"          "$BaseUrl/api/network-devices/topology"     -Headers $h
Test-Endpoint "Subnets (real)"           "$BaseUrl/api/network-devices/subnets"      -Headers $h
Test-Endpoint "Devices (alias)"          "$BaseUrl/api/network/devices"              -Headers $h
Test-Endpoint "Topology (alias)"         "$BaseUrl/api/network/topology"             -Headers $h
Test-Endpoint "Segments (alias)"         "$BaseUrl/api/network/segments"             -Headers $h

# ── SBOM ──────────────────────────────────────────────────────────────────────
Write-Host "`n--- SBOM ---"
Test-Endpoint "SBOMs (real)"             "$BaseUrl/api/sboms"                        -Headers $h
Test-Endpoint "SBOM (alias)"             "$BaseUrl/api/sbom"                         -Headers $h
Test-Endpoint "SBOM Components"          "$BaseUrl/api/sboms/components"             -Headers $h

# ── Compliance ────────────────────────────────────────────────────────────────
Write-Host "`n--- Compliance ---"
Test-Endpoint "Frameworks"               "$BaseUrl/api/compliance"                   -Headers $h
Test-Endpoint "Policies (alias)"         "$BaseUrl/api/compliance/policies"          -Headers $h
Test-Endpoint "Checks (alias)"           "$BaseUrl/api/compliance/checks"            -Headers $h
Test-Endpoint "Benchmarks (alias)"       "$BaseUrl/api/compliance/benchmarks"        -Headers $h
Test-Endpoint "CIS (alias)"              "$BaseUrl/api/compliance/cis"               -Headers $h
Test-Endpoint "Reports"                  "$BaseUrl/api/compliance/reports"           -Headers $h
Test-Endpoint "Evidence"                 "$BaseUrl/api/compliance/evidence"          -Headers $h
Test-Endpoint "Artifacts"                "$BaseUrl/api/compliance/artifacts"         -Headers $h

# ── Reports ───────────────────────────────────────────────────────────────────
Write-Host "`n--- Reports ---"
Test-Endpoint "Report List (alias)"      "$BaseUrl/api/reports"                      -Headers $h
Test-Endpoint "Templates (alias)"        "$BaseUrl/api/reports/templates"            -Headers $h
Test-Endpoint "Executive Summary"        "$BaseUrl/api/reports/executive-summary"    -Headers $h
Test-Endpoint "SLA Report"               "$BaseUrl/api/reports/sla-compliance"       -Headers $h
Test-Endpoint "Vuln Exposure"            "$BaseUrl/api/reports/vulnerability-exposure" -Headers $h
Test-Endpoint "Change Mgmt"              "$BaseUrl/api/reports/change-management"    -Headers $h
Test-Endpoint "Scheduled"                "$BaseUrl/api/reports/scheduled"            -Headers $h

# ── AI / LLM ──────────────────────────────────────────────────────────────────
Write-Host "`n--- AI / LLM ---"
Test-Endpoint "Test Connection GET"      "$BaseUrl/api/ai/test-connection"           -Headers $h
Test-Endpoint "AI Audit Logs"            "$BaseUrl/api/ai-proxy/audit-logs"          -Headers $h
Test-Endpoint "LLM Settings"             "$BaseUrl/api/settings/llm"                 -Headers $h
Test-Endpoint "Guardrail Policy (alias)" "$BaseUrl/api/ai-proxy/guardrail-policy"    -Headers $h
Test-Endpoint "AI Governance Models"     "$BaseUrl/api/ai-governance/models"         -Headers $h

# ── UEBA ──────────────────────────────────────────────────────────────────────
Write-Host "`n--- UEBA ---"
Test-Endpoint "Shadow AI (alias)"        "$BaseUrl/api/ueba/shadow-ai"               -Headers $h
Test-Endpoint "UEBA Alerts"              "$BaseUrl/api/ueba/alerts"                  -Headers $h
Test-Endpoint "Risk Scores"              "$BaseUrl/api/ueba/risk-scores"             -Headers $h

# ── Security ──────────────────────────────────────────────────────────────────
Write-Host "`n--- Security ---"
Test-Endpoint "Vulnerabilities"          "$BaseUrl/api/vulnerabilities"              -Headers $h
Test-Endpoint "Threat Intel"             "$BaseUrl/api/threat-intel/feed"            -Headers $h
Test-Endpoint "IR Cases"                 "$BaseUrl/api/incidents"                    -Headers $h
Test-Endpoint "DLP Policies"             "$BaseUrl/api/dlp/policies"                 -Headers $h
Test-Endpoint "Pentest"                  "$BaseUrl/api/pentest/jobs"                 -Headers $h
Test-Endpoint "Secrets Findings (alias)" "$BaseUrl/api/secrets/findings"             -Headers $h

# ── Tenants ───────────────────────────────────────────────────────────────────
Write-Host "`n--- Tenants ---"
Test-Endpoint "Tenant Me (alias)"        "$BaseUrl/api/tenants/me"                   -Headers $h

# ── System ────────────────────────────────────────────────────────────────────
Write-Host "`n--- System ---"
Test-Endpoint "Audit Logs"               "$BaseUrl/api/audit-logs"                   -Headers $h
Test-Endpoint "DB Settings"              "$BaseUrl/api/settings/database"            -Headers $h
Test-Endpoint "Notifications"            "$BaseUrl/api/notifications"                -Headers $h
Test-Endpoint "KPIs"                     "$BaseUrl/api/kpi/summary"                  -Headers $h
Test-Endpoint "System Health"            "$BaseUrl/api/system/health"                -Headers $h

# ── Analytics ─────────────────────────────────────────────────────────────────
Write-Host "`n--- Analytics ---"
Test-Endpoint "Traces"                   "$BaseUrl/api/tracing/traces"               -Headers $h
Test-Endpoint "Logs"                     "$BaseUrl/api/logs"                         -Headers $h

# ── Automation ────────────────────────────────────────────────────────────────
Write-Host "`n--- Automation ---"
Test-Endpoint "Playbooks"                "$BaseUrl/api/playbooks"                    -Headers $h
Test-Endpoint "Alerts"                   "$BaseUrl/api/alerts"                       -Headers $h
Test-Endpoint "Jobs"                     "$BaseUrl/api/jobs"                         -Headers $h

# ── Risk ──────────────────────────────────────────────────────────────────────
Write-Host "`n--- Risk ---"
Test-Endpoint "Risks"                    "$BaseUrl/api/risks"                        -Headers $h
Test-Endpoint "Vendors"                  "$BaseUrl/api/vendors"                      -Headers $h
Test-Endpoint "PQC Keys (alias)"         "$BaseUrl/api/pqc/keys"                     -Headers $h

# ── Summary ───────────────────────────────────────────────────────────────────
$total = $pass + $fail
Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Results: $pass/$total passed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
Write-Host "=============================================" -ForegroundColor Cyan
$results | ForEach-Object {
    $color = if ($_ -like "*PASS*") { "Green" } else { "Red" }
    Write-Host $_ -ForegroundColor $color
}
Write-Host ""
if ($fail -gt 0) {
    Write-Host "  $fail endpoint(s) failed. Check backend logs for details." -ForegroundColor Red
} else {
    Write-Host "  All endpoints OK!" -ForegroundColor Green
}
