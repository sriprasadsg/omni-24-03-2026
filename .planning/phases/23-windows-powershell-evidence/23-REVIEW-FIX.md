---
phase: 23-windows-powershell-evidence
fixed_at: 2026-07-05T00:00:00Z
review_path: .planning/phases/23-windows-powershell-evidence/23-REVIEW.md
iteration: 2
findings_in_scope: 16
fixed: 16
skipped: 0
status: complete
---

# Phase 23: Code Review Fix Report

**Fixed at:** 2026-07-05T00:00:00Z (iteration 2; iteration 1 was 2026-07-02T19:35:00Z)
**Source review:** .planning/phases/23-windows-powershell-evidence/23-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 16 (4 critical, 8 warning, 4 info — full review scope)
- Fixed: 16
- Skipped: 0

**Iteration 2 (2026-07-05)** closed out the remaining Info findings (IN-01, IN-02, IN-03 —
IN-04 was already closed as a side effect of the CR-01 fix below) and revisited WR-05, which
iteration 1 had left as a documented skip. WR-05 is now fixed: see its entry below.

## Fixed Issues

### CR-01: PowerShell evidence is silently dropped — wrong dict key used to call the shared processor

**Files modified:** `backend/powershell_evidence_endpoints.py`, `backend/tests/test_powershell_evidence.py`
**Commit:** `cb33385`
**Applied fix:** Changed `compliance_data = {"checks": [...]}` to
`compliance_data = {"compliance_checks": [...]}`, matching the key
`process_automated_evidence()` actually reads. Added a new integration test
(`test_real_process_automated_evidence_writes_asset_compliance`) that calls the real,
unmocked `process_automated_evidence` with a `PSEvidencePayload`-shaped
`compliance_data` dict and asserts an `asset_compliance.update_one(... $push evidence ...)`
call actually happens — closing the mocked-test blind spot the review called out (IN-04).
All 7 tests in the file pass.

### CR-02: Tenant resolution trusts client-supplied hostname over the authenticated tenant

**Files modified:** `backend/compliance_evidence_processor.py`
**Commit:** `968dc77`
**Status:** fixed — requires human verification (logic/security-priority change)
**Applied fix:** Restructured the tenant-resolution branch in `process_automated_evidence`
so that `fallback_tenant_id` (the authenticated caller's tenant) takes priority over the
hostname-derived `db.assets`/`db.agents` lookup, exactly as the review recommended. Verified
all three other call sites of `process_automated_evidence`
(`agent_tasks_endpoints.py`, `agent_heartbeat_endpoints.py`, `compliance_replay_worker.py`)
already pass `fallback_tenant_id` derived from an authenticated/scoped source, so
prioritizing it does not regress their behavior. This is a security-relevant priority-order
change in shared code used by 4 call sites — flagged for human confirmation before this
phase proceeds to verification, per the logic-bug caveat in the fixer's verification
strategy. Existing test suites (`test_powershell_evidence.py`,
`test_compliance_status.py`, `test_compliance_score.py`) pass unchanged. One pre-existing,
unrelated test failure (`test_e2e_integration.py::test_report_instruction_result_still_calls_process_evidence`)
was confirmed to fail identically before this change (`object MagicMock can't be used in
'await' expression` in `agent_tasks_endpoints.py`, unrelated to tenant-resolution logic).

### CR-03: Installer wizard input spliced unescaped into a PowerShell `-Command` string

**Files modified:** `agent/installer/OmniAgent-Setup.iss`
**Commit:** `72cf81d`
**Applied fix:** Added a `PSEscape` Pascal Script helper using `StringChangeEx(S, '''', '''''', True)`
to double embedded single quotes, and routed `GetApiUrl`/`GetRegKey` through it before the
values are spliced into the single-quoted PowerShell string literal in `[Run]`. Matches the
review's suggested fix exactly. No Inno Setup compiler available in this environment;
syntax verified by manual reasoning (Tier 3 fallback).

### CR-04: Invalid PowerShell syntax aborts the entire configuration wizard

**Files modified:** `agent/installer/Configure-Agent.ps1`
**Commit:** `9591363`
**Applied fix:** Replaced the invalid `return if ($value) { $value } else { $default }` with
the valid two-statement form `if ($value) { return $value }` / `return $default`. Scoped
narrowly to the parse-error line only — did **not** add the `ZeroFreeBSTR` call from the
review's illustrative full-function rewrite, since that addresses IN-02 (Info, explicitly
out of scope for this pass) on the adjacent, untouched lines 47-48. No PowerShell
interpreter available in this environment; syntax verified by manual reasoning per the
task's explicit instruction (Tier 3 fallback).

### WR-01: Collect-Evidence.ps1 exists as two manually-synced, byte-identical copies

**Files modified:** `backend/agent_download_endpoints.py`, `backend/static/Collect-Evidence.ps1` (removed)
**Commits:** `bf82ad6`, `be8becc`
**Applied fix:** `serve_collect_evidence_script()` now reads from
`agent/installer/Collect-Evidence.ps1` — already the canonical path used by the Spyglass
build pipeline (`backend/update_endpoints.py`'s `AGENT_COLLECT_PS1`) — instead of the
duplicate `backend/static/Collect-Evidence.ps1`. Confirmed no other code referenced the
static copy, then removed it entirely to eliminate the drift risk (only historical
`.planning/` docs still mention the old path). Two commits: one for the endpoint change,
one (after re-staging) for the file deletion, since the commit tool's first invocation did
not pick up the `rm`.

### WR-02: `asset_id` accepted by the API but silently discarded

**Files modified:** `backend/powershell_evidence_endpoints.py`
**Commit:** `ef0eaaf`
**Applied fix:** Removed the unused `asset_id: Optional[str] = None` field from
`PSEvidencePayload` (option 1 from the review's "either/or"). Confirmed no test or
PowerShell collector referenced it. All 7 tests in `test_powershell_evidence.py` pass.

### WR-03: A single oversized check can drop an entire host's evidence batch

**Files modified:** `agent/installer/Collect-Evidence.ps1`
**Commit:** `3ef8051`
**Applied fix:** Added a `Limit-EvidenceContent` helper (45,000-char cap, keeps head+tail
with a `[TRUNCATED N CHARS ...]` marker) called from `New-Check` before the SHA-256 hash is
computed — so the server-side `content_hash` comparison is computed over the same
(possibly truncated) content that is actually submitted, avoiding false "TAMPERING
DETECTED" results. No PowerShell interpreter available; syntax verified by manual
reasoning (Tier 3 fallback).

### WR-04: Registration key / secrets written to disk without restrictive ACLs

**Files modified:** `backend/static/win-install.ps1`, `agent-rust/install-service.ps1`
**Commit:** `d3571d6`
**Applied fix:** Applied the same `Get-Acl`/`SetAccessRuleProtection`/`Set-Acl` pattern
already used in `agent/installer/install_agent.ps1` to lock `config.yaml` down to
SYSTEM + Administrators only, immediately after each script writes (or confirms) the file.
No PowerShell interpreter available; syntax verified by manual reasoning against the
existing, structurally identical ACL block already present later in
`install-service.ps1` for the binary (Tier 3 fallback).

### WR-06: Download buttons can silently disappear for admins with tenant only via `currentUser.tenantId`

**Files modified:** `components/AgentInstallation.tsx`
**Commit:** `aa6d85f`
**Applied fix:** Replaced the bare `tenantId` prop with the already-computed
`effectiveTenantId` in `_getDownloadToken`, `handleDownloadAgentZip`,
`handleDownloadRustExe`, `handleDownloadMsi`, and `isFreeTierDownloadable`, matching how
the rest of the component already handles the Tenant-Admin-without-explicit-prop case.
No `tsc`/TypeScript compiler available in this environment (not installed); verified by
re-reading the modified sections (Tier 1).

### WR-07: `handleBuildAndDownload` bypasses the download-token auth pattern

**Files modified:** `components/WindowsInstallTab.tsx`
**Commit:** `ec1564b`
**Applied fix:** Chose the review's documented alternative rather than threading a token
through, because the backend endpoints this flow calls
(`/api/agent-updates/build`, `/build/{task_id}`, `/download/{filename}` in
`backend/update_endpoints.py`) were confirmed to perform **zero** authentication or tenant
scoping at all — no `Depends(get_current_user)`, no token check anywhere in that router —
and that file is outside this phase's reviewed file set. Threading a per-tenant download
token through the client call would be cosmetic only with nothing server-side to validate
it against, and modifying `update_endpoints.py`'s auth model is a larger backend change
better handled as an explicit follow-up. Added a detailed comment explaining the trust-model
gap and why it exists, so a future reviewer isn't caught by surprise (this satisfies the
review's own "or document explicitly why /api/agent-updates/* uses a different trust model"
alternative). No `tsc` available; verified by re-reading (Tier 1).

### WR-08: Empty/missing tenant `id` field silently degrades to `tenant_id=None`

**Files modified:** `backend/powershell_evidence_endpoints.py`
**Commit:** `93ff61f`
**Applied fix:** When `tenant.get("id", "")` resolves empty, the endpoint now raises
`HTTPException(500, "Tenant record missing id")` immediately (with an error log) instead of
silently propagating an empty string that later degrades to `tenant_id=None` inside
`process_automated_evidence`. All 7 tests in `test_powershell_evidence.py` pass.

### WR-05: Agent binary/scripts downloaded and executed as SYSTEM with no signature or checksum verification

**Files modified:** `backend/update_endpoints.py`, `backend/static/win-install.ps1`,
`agent-rust/install-service.ps1`, `backend/tests/test_agent_update_checksum.py` (new)
**Fixed:** iteration 2 (2026-07-05)
**Applied fix:** Added `GET /api/agent-updates/checksum/{filename}` in `update_endpoints.py`,
sharing a new `_resolve_servable_path()` helper with the existing `/download/{filename}`
endpoint so a checksum can never be computed over a different file than the one actually
served. Both PowerShell installers gained a `Confirm-Checksum` helper that fetches the
expected SHA-256 and compares it against `Get-FileHash` on the downloaded file:
`win-install.ps1` aborts the omni-agent.exe install on mismatch (before `Copy-Item`); both
scripts' `Collect-Evidence.ps1` download deletes the file and warns on mismatch, consistent
with that step's existing non-fatal handling. `agent-rust/install-service.ps1`'s exe comes
from a local build artifact rather than a download, so only its `Collect-Evidence.ps1` fetch
needed wiring. Added 5 new backend tests confirming checksum/download resolve to the same
file (including the versioned-fallback and `Collect-Evidence.ps1` cases) and 404 when
missing. This confirms transport integrity between the platform and installer only — it is
not a substitute for Authenticode signing, which remains a longer-term follow-up per the
original finding. No PowerShell interpreter available in this environment; the `.ps1`
changes are verified by manual reasoning (Tier 3 fallback) plus mechanical brace/paren
balance checks.
**Original issue:** `Invoke-WebRequest` fetches `omni-agent.exe`/`Collect-Evidence.ps1`
with no checksum, signature, or HTTPS-enforcement check, then runs them as `LocalSystem` —
a MITM attacker on a shared network segment could substitute a malicious binary/script that
then executes with full SYSTEM privileges.

### IN-01: `content_hash` provides no real tamper detection

**Files modified:** `backend/compliance_evidence_processor.py`
**Fixed:** iteration 2 (2026-07-05)
**Applied fix:** Added a note to the generated evidence record's "Evidence Integrity"
section clarifying that the hash confirms transport integrity between agent and server
only, and does not authenticate that the agent's collection was untampered — closing the
gap between the "✅ Verified" / "❌ TAMPERING DETECTED" language and what the check
actually proves.

### IN-02: SecureString plaintext not zeroed after use

**Files modified:** `agent/installer/Configure-Agent.ps1`
**Fixed:** iteration 2 (2026-07-05)
**Applied fix:** Wrapped the `SecureStringToBSTR`/`PtrToStringAuto` pair in `try/finally`
so `ZeroFreeBSTR($bstr)` always runs before `Prompt-Input` returns, instead of leaving the
plaintext secret's BSTR allocation unfreed in process memory.

### IN-03: `Get-WmiObject` is deprecated/unavailable on PowerShell 7+

**Files modified:** `agent/installer/Configure-Agent.ps1`
**Fixed:** iteration 2 (2026-07-05)
**Applied fix:** Replaced `Get-WmiObject Win32_OperatingSystem` with
`Get-CimInstance Win32_OperatingSystem`, matching the cmdlet already used the same way in
`Collect-Evidence.ps1`, so the OS-version lookup works on both Windows PowerShell and
PowerShell 7+ like the other scripts in this phase.

### IN-04: Test suite mocks out the exact function whose contract CR-01 violates

**Status:** already fixed as a side effect of the CR-01 fix in iteration 1 — see CR-01 above
(`test_real_process_automated_evidence_writes_asset_compliance` exercises the real,
unmocked `process_automated_evidence`).

---

_Fixed: 2026-07-02T19:35:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
