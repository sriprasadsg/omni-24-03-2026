#Requires -RunAsAdministrator
<#
.SYNOPSIS
Spyglass Unified Collection Script for Windows PowerShell Evidence

.DESCRIPTION
Orchestrates the collection, validation, and SHA256 manifest creation of
PowerShell evidence across OmniAgent installer formats (NSIS/WiX/Inno).
Creates a unified spyglass.json manifest consumed by build and CI/CD pipelines.

.PARAMETER InstallDir
Target installation directory (for packagers).

.PARAMETER BuildRoot
Root directory from whence artifacts are collected.
BuildRoot defaults to the same directory as this script.

.PARAMETER DryRun
If supplied, does NOT write anything to disk.

.EXAMPLE
# Create spyglass.json in the same directory as the script
./unified-collection.ps1

.EXAMPLE
# Point build root to 'artifacts/evidence' and write spyglass.json there
./unified-collection.ps1 -BuildRoot artifacts/evidence

.NOTES
Outputs:
• spyglass/spyglass.json — structured manifest of all artifacts
• spyglass/evidence_output.json — detailed evidence collection
• Evidence artifacts hashed and timestamped
#>

param(
    [string]$InstallDir = "",
    [string]$BuildRoot = $(Split-Path -Parent $MyInvocation.MyCommand.Definition),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Constants
$SPYGLASS_DIR = Join-Path $BuildRoot "spyglass"
$COLLECT_SCRIPT = Join-Path $BuildRoot "Collect-Evidence.ps1"
$CONFIG_YAML = Join-Path $BuildRoot "config.yaml"
$EVIDENCE_OUTPUT = Join-Path $BuildRoot "evidence_output.json"

function Get-SHA256 {
    param([string]$file)
    if (-not (Test-Path $file)) { return $null }
    $bytes = [System.IO.File]::ReadAllBytes($file)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    $digest = $hash.ComputeHash($bytes)
    -join ($digest | ForEach-Object { $_.ToString("x2") })
}

function Validate-Script {
    param([string]$script)
    $errVar = $null
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors) {
        Write-Error "Script syntax errors in $script:"`n$($parseErrors | Out-String)"
        return $false
    }
    $true
}

function Collect-PSEnv {
    @{
        version = $PSVersionTable.PSVersion.ToString()
        edition = $PSVersionTable.PSEdition
        modules = Get-Module -ListAvailable | Where-Object {
            $_.ModuleType -in @("Script", "Binary") -and
            $_.Name -notin @("Microsoft.PowerShell.Management", "CimCmdlets")
        } | Select-Object Name, Version | ConvertTo-Json -Compress
        registry = @{
            hives = @{}
            "HKLM:\\SOFTWARE\\Microsoft\\PowerShell" | Get-ChildItem | Where-Object {
                $_.Name -like "*PowerShell*" }
            | ForEach-Object { $hives[$_.Name] = Get-ItemProperty $_.PSPath }
        }
    }
}

function New-SpyglassManifest {
    param(
        [object]$psEnv,
        [hashtable]$artifacts,
        [string]$installDir
    )
    @{
        schema = "spyglass/v1"
        timestamp = [DateTime]::Now.ToUniversalTime().ToString("o")
        host = $env:COMPUTERNAME
        powershell = $psEnv
        artifacts = $artifacts
        install_dir = $installDir
        downlink = @{
            build = ""
            packaging = ""
            evidence = ""
        }
    }
}

# ── Main ──────────────────────────────────────────────────────
Write-Host "`n[OmniAgent:Spyglass] Unifying PowerShell evidence collection... ($BuildRoot)`" -ForegroundColor Cyan

# Check prerequisites
if (-not (Test-Path $COLLECT_SCRIPT)) {
    Write-Error "[$COLLECT_SCRIPT] does not exist"
}
if (-not (Validate-Script $COLLECT_SCRIPT)) {
    exit 1
}

# Ensure spyglass directory
if (-not $DryRun) {
    if (-not (Test-Path $SPYGLASS_DIR)) {
        New-Item -ItemType Directory -Path $SPYGLASS_DIR -Force | Out-Null
    }
}

# Collect PowerShell environment
$psEnv = Collect-PSEnv
Write-Host "  Collecting environment: $($psEnv.version)..."

# Run Collect-Evidence.ps1
if (Test-Path $COLLECT_SCRIPT) {
    Write-Host "  Executing Collect-Evidence.ps1..."
    $collectParams = @{}
    if ($InstallDir) { $collectParams.InstallDir = $InstallDir }
    $evidenceResults = & $COLLECT_SCRIPT @collectParams -DryRun
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Evidence collection failed"
    }
    # Save detailed evidence
    if (-not $DryRun) {
        $evidenceResults | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $EVIDENCE_OUTPUT -Encoding UTF8
    }
}

# Hash artifacts
$artifacts = @{}
"collect_script", "config_yaml", "evidence_output" | ForEach-Object {
    $file = ""
    switch ($_) {
        "collect_script" { $file = $COLLECT_SCRIPT }
        "config_yaml" { $file = $CONFIG_YAML }
        "evidence_output" { $file = $EVIDENCE_OUTPUT }
    }
    if ($file -and (Test-Path $file)) {
        $sha = Get-SHA256 $file
        if ($sha) { $artifacts[$_] = @{ path = $file; sha256 = $sha } }
    }
}
Write-Host "  Hashed $(($artifacts | Measure-Object).Count) artifacts"

# Produce spyglass.json
$manifest = New-SpyglassManifest -psEnv $psEnv -artifacts $artifacts -installDir $InstallDir
$manifestPath = Join-Path $SPYGLASS_DIR "spyglass.json"
if (-not $DryRun) {
    $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Host "  → $manifestPath" -ForegroundColor Green
} else {
    Write-Host "  [DryRun] → [Skipping write]"; $manifest
}

Write-Host "[OmniAgent:Spyglass] Complete." -ForegroundColor Cyan