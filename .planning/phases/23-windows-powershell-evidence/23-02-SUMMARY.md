---
phase: 23
plan: "02"
subsystem: windows-agent-installers
tags: [powershell, windows, compliance, evidence-collection, installer, scheduled-task]
dependency_graph:
  requires: [23-01]
  provides: [Collect-Evidence.ps1, OmniAgent-Setup.iss, collect-evidence-script-endpoint]
  affects: [backend/agent_download_endpoints.py, backend/static, agent-rust, agent/installer]
tech_stack:
  added: [Inno Setup 6 (.iss), Windows Task Scheduler API, Windows PowerShell 5+]
  patterns: [scheduled-task-evidence, script-distribution-endpoint, bundled-installer]
key_files:
  created:
    - backend/static/Collect-Evidence.ps1
    - agent/installer/Collect-Evidence.ps1
    - agent/installer/OmniAgent-Setup.iss
  modified:
    - backend/static/win-install.ps1
    - backend/agent_download_endpoints.py
    - agent-rust/install-service.ps1
    - agent/installer/install_agent.ps1
    - agent/installer/Configure-Agent.ps1
decisions:
  - win-install.ps1 trimmed to exactly 200 lines to meet plan constraint
  - Collect-Evidence.ps1 uses Check-* function naming convention consistent with plan
  - agent/installer/Collect-Evidence.ps1 is byte-for-byte identical to backend/static version (verified via diff)
metrics:
  duration: 336s
  completed: "2026-06-24T08:51:35Z"
  tasks_completed: 9
  files_changed: 8
status: complete
---

# Phase 23 Plan 02: PowerShell Scripts Full Rebuild Summary

## One-liner

Rebuilt all Windows agent installers with 28-check PowerShell evidence collector, scheduled task setup, download endpoint, and Inno Setup 6 EXE script.

## What Was Built

### backend/static/win-install.ps1 (rebuilt, 200 lines)

Fully rebuilt installer script served at `GET /api/agent/install-script`. Adds to the existing Rust binary download + service install flow:
- `-SkipFirstRun` switch parameter
- Downloads `Collect-Evidence.ps1` from `$ApiUrl/api/agent/collect-evidence-script` after binary install
- Writes `config.yaml` with `evidence_collection: true` and `evidence_interval_hours: 24`
- Registers Windows Scheduled Task `OmniAgentEvidenceCollection` (daily 06:00, SYSTEM)
- Runs first evidence collection immediately (unless `-SkipFirstRun`)
- Uninstall branch removes the scheduled task
- Summary block lists evidence script path and task name

### backend/static/Collect-Evidence.ps1 (new, 336 lines)

New file served at `GET /api/agent/collect-evidence-script`. Implements all 28 Windows compliance checks. Check names match `COMPLIANCE_CHECK_MAPPINGS` keys exactly in `compliance_evidence_processor.py`.

28 checks implemented:
1. Windows Firewall Profiles
2. Windows Defender Antivirus
3. Password Policy (Min Length)
4. Guest Account Disabled
5. RDP NLA Required
6. BitLocker Encryption
7. Secure Boot
8. Windows Update Service
9. User Access Control
10. Audit Logging Policy
11. Risky Network Ports
12. TLS Security Config
13. Prohibited Software
14. Maximum Password Age
15. Account Lockout Policy
16. Password Complexity
17. Password History
18. Minimum Password Age
19. Remote Desktop Service
20. SMBv1 Protocol Disabled
21. LLMNR/NetBIOS Protection
22. PowerShell Script Block Logging
23. WinRM Service Status
24. Credential Guard
25. Device Guard/WDAC
26. Exploit Protection (DEP/ASLR)
27. Attack Surface Reduction
28. Controlled Folder Access

Script reads `config.yaml` from its directory for `api_base_url` and `registration_key`. Computes SHA256 hash of each evidence string. POSTs to `/api/powershell-evidence/submit` with `X-Registration-Key` header. Supports `-DryRun` to print results without submitting.

### backend/agent_download_endpoints.py (modified)

Added `GET /api/agent/collect-evidence-script` endpoint immediately after the `serve_install_script` endpoint. Serves `backend/static/Collect-Evidence.ps1` with `Content-Disposition: attachment; filename="Collect-Evidence.ps1"`. No auth required (same pattern as install-script endpoint).

### agent-rust/install-service.ps1 (modified)

After writing `config.yaml` (now includes `evidence_collection: true` and `evidence_interval_hours: 24`):
- Downloads `Collect-Evidence.ps1` from platform API
- Registers `OmniAgentEvidenceCollection` daily scheduled task (06:00, SYSTEM)
- Summary block updated to show evidence script path and task name

### agent/installer/install_agent.ps1 (modified)

Added evidence collection setup section between service registration and environment variables:
- Copies `Collect-Evidence.ps1` from distribution folder if present, else downloads from platform
- Registers `OmniAgentEvidenceCollection` daily scheduled task (06:00, SYSTEM)

### agent/installer/Configure-Agent.ps1 (modified)

Added to the generated `config.yaml` content block:
```yaml
# Evidence Collection
evidence_collection: true
evidence_interval_hours: 24
evidence_submit_url: $ApiUrl/api/powershell-evidence/submit
```

### agent/installer/Collect-Evidence.ps1 (new)

Byte-for-byte identical copy of `backend/static/Collect-Evidence.ps1`. Bundled with distribution package for offline/EXE installer deployments. Verified identical via `diff`.

### agent/installer/OmniAgent-Setup.iss (new, 103 lines)

Inno Setup 6 script producing `dist/OmniAgent-Setup.exe` when compiled with `iscc.exe` on Windows. Includes:
- Custom wizard page for Platform URL and Registration Key input
- Bundles `Collect-Evidence.ps1`, `Configure-Agent.ps1`, `uninstall_agent.ps1`
- Bundles `omni-agent.exe` (pre-built Rust binary from `../target/release/`)
- Start menu shortcuts for Configure, Collect Evidence Now, Uninstall
- `[Run]` section: writes `config.yaml`, installs Windows service, registers scheduled task
- Optional first evidence run via `[Tasks]` checkbox (checked by default)
- `[UninstallRun]` stops service, deletes service, removes scheduled task

## Commits

| Hash | Description |
|------|-------------|
| a221c73 | feat(windows): rebuild all Windows installers + PowerShell evidence collector (Phase 23-02) |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as specified with one minor constraint adjustment.

### Constraint Adjustments

**win-install.ps1 line count:** The rebuilt file reached 202 lines. Trimmed to exactly 200 by removing one blank line in the summary block and one trailing blank line. All functionality preserved.

## Known Stubs

None. All 28 check functions collect real data from the Windows registry, WMI, PowerShell cmdlets, and `net accounts` / `auditpol`. The script is functional as written.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: unauthenticated-script-serve | backend/agent_download_endpoints.py | New `/api/agent/collect-evidence-script` endpoint serves script without auth — consistent with existing `/api/agent/install-script` pattern (no-auth by design for agent onboarding) |

## Self-Check: PASSED
