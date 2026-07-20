# Phase 41: CSPM Provider Expansion (OCI, Alibaba, Cloudflare) - Research

**Researched:** 2026-07-20
**Domain:** Multi-tenant CSPM check evaluation engine (FastAPI + Motor/MongoDB) — wiring 3 new cloud providers into an existing findings-import + rule-evaluation architecture
**Confidence:** HIGH — every claim below is sourced from direct reads of this repo's code, plus the already-completed milestone-level `.planning/research/{STACK,ARCHITECTURE,PITFALLS}.md` (dated the same day). Two genuinely new findings not present in those milestone docs are called out explicitly below (the SIEM-vs-CSPM provider-string split, and the missing SIMULATED badge / broken credential field-mapping in the frontend).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 (Findings collection targeting):** Write real findings to `cloud_findings` only (not dual-write to `security_events`). Matches how AWS/Azure/GCP/DigitalOcean already work — single source of truth, no dual-write complexity. The existing `oci_ingest.py`/`cloudflare_ingest.py`/`alibaba_ingest.py` stubs currently write to `security_events` — this phase corrects that target, it doesn't add a second write path.
- **D-02 (Simulated-data fallback):** Match the existing pattern — show labeled `"simulated": true` results when no real import exists for a provider, exactly like AWS/Azure/GCP/DigitalOcean already do. Never present simulated data as real; badge it the same way the existing dashboard does.
- **D-03 (Check catalog scope):** Structure new check catalogs (~8-10 checks each) around the same categories existing providers use (storage exposure, IAM policy, encryption, logging) for dashboard consistency, but check *content* is provider-native: CIS OCI Foundations for OCI, Alibaba Cloud Config/Security Center baseline for Alibaba, Cloudflare Security Center taxonomy for Cloudflare.
- **D-04 (Credential input per provider):** Extend the existing "Connect Cloud Account" form with provider-specific credential fields — OCI (tenancy OCID, user OCID, fingerprint, private key), Alibaba (access key ID + secret, using the V2 typed SDK per STACK.md — not the legacy V1 `AcsClient`), Cloudflare (API token). Verify during planning/research what the existing form/endpoint already supports (`cloud_account_endpoints.py` already allowlists all 3 providers) before assuming new fields are needed from scratch.
- **D-05 (Compliance score integration):** Yes — OCI/Alibaba/Cloudflare check results count toward the tenant's overall compliance score, consistent with every other cloud provider already integrated.

### Claude's Discretion

- Exact field layout/validation for the extended connect-account form (D-04) — verify what the form currently supports before designing new fields.
- Precise mapping of category → provider-native check within each of the ~8-10 checks per provider.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CSPM-01 | A tenant with a connected OCI account can run a posture scan against real, CIS OCI Foundations-aligned checks (not simulated/stub data) | `oci` SDK already pinned in `requirements.txt` (not yet installed in venv — see Environment Availability); `oci_ingest.py` already has the exact OCI API-key auth config shape; new `cloud_checks_oci.py` + un-mocked `oci.cloud_guard.CloudGuardClient` call wired into `cloud_accounts_service.scan_account()` (see Architecture Patterns) |
| CSPM-02 | A tenant with a connected Alibaba Cloud account can run a posture scan against real checks via the Alibaba Cloud Config/Security Center V2 API | 4 new `alibabacloud_*` V2 packages required (not yet in `requirements.txt`, SUS-flagged pending verification — see Package Legitimacy Audit); new `cloud_checks_alibaba.py` + new V2-SDK-backed poll function, kept separate from the existing V1 `AcsClient`-based `alibaba_ingest.py` SIEM path |
| CSPM-03 | A tenant with a connected Cloudflare account can run a posture scan against real checks aligned to Cloudflare's Security Center taxonomy | `cloudflare` SDK already pinned (not yet installed — see Environment Availability); zone-settings API (SSL mode, min TLS, WAF managed rules) maps cleanly to check definitions; new `cloud_checks_cloudflare.py` |
</phase_requirements>

## Summary

This phase closes a **one-line execution gate plus three data-only check-definition modules** — `RUNNABLE_PROVIDERS` in `cloud_checks_service.py` is the only place OCI/Alibaba/Cloudflare are still missing; `cloud_checks_endpoints.py` and `cloud_account_endpoints.py` already allowlist all three. That narrow framing (confirmed correct by this session's own greps) is where the *easy* 20% of the work is. The other 80% — genuinely new, not previously scoped in the milestone-level docs — is: (1) real API-calling ingest functions that write into `cloud_findings` and get invoked from `cloud_accounts_service.scan_account()`'s existing M365/MongoDB-Atlas-shaped if/elif ladder (the actual "real checks, not stub data" requirement), and (2) real frontend work, because the two live CSPM UI surfaces have gaps not mentioned anywhere in the milestone research: `CloudChecksScanner.tsx` hardcodes its provider icon map and both filter dropdowns to `['aws','azure','gcp']` only (DO/K8s/M365/Atlas are *also* invisible there today, not just the 3 new providers), neither live CSPM dashboard renders a SIMULATED badge anywhere despite `result.simulated` already being computed server-side, and the one component that visually matches the phase's "dropdown-only stub" framing (`AddCloudAccountModal.tsx` via the `cloudSecurity` view) submits a payload shape (`name`, `credentials` object) that the real `/api/cloud-accounts` endpoint silently ignores (it wants `account_name`, `credentials_ref` string) — meaning **no cloud account registered through that specific form today has ever stored real credentials**, for any provider, not just the 3 new ones.

There is also a load-bearing distinction the milestone-level ARCHITECTURE.md/PITFALLS.md docs did not surface: this codebase has **two separate, non-overlapping "OCI/Alibaba/Cloudflare" integration domains** that happen to share ingest module filenames. The SIEM domain (`cloud_integrations_endpoints.py`, `cloud_integrations` collection, provider strings `oci_cloud_guard`/`alibaba_sas`/`cloudflare_zero_trust`, `INTEGRATION_ENCRYPTION_KEY`) calls the existing 2-argument `poll_*` functions and writes `security_events`. The CSPM domain (`cloud_account_endpoints.py`, `cloud_accounts` collection, provider strings `oci`/`alibaba`/`cloudflare`, `CLOUD_CREDENTIALS_KEY`) is what `RUNNABLE_PROVIDERS`/`run_checks()`/this phase's Success Criteria actually target, and it needs a **3-argument** `(config, account_id, tenant_id)` ingest shape writing `cloud_findings` — the exact shape `m365_ingest.py`/`mongodb_atlas_ingest.py` already use. CONTEXT.md's D-01 says "retarget the existing stubs, don't add a second write path" — the recommended synthesis (see Architecture Patterns, Pattern 4) is to extend each existing `poll_*` function with an optional `account_id` parameter that switches its write target, rather than forking a duplicate module, satisfying both "one retargeted function" and "don't break the still-live SIEM call sites."

**Primary recommendation:** Add `cloud_checks_oci.py` / `cloud_checks_alibaba.py` / `cloud_checks_cloudflare.py` (DO_CHECKS-shaped, 8-10 checks each) + widen `RUNNABLE_PROVIDERS`; extend `oci_ingest.py`/`alibaba_ingest.py`(new V2-SDK path)/`cloudflare_ingest.py` with an `account_id`-aware real-API code path that writes `cloud_findings`, wired into `cloud_accounts_service.scan_account()`'s existing if/elif ladder; fix the `AddCloudAccountModal.tsx` → `apiService.addCloudAccount()` → `/api/cloud-accounts` field-name mismatch and add provider-conditional credential fields; add the missing SIMULATED badge (clone `IacContainerDashboard.tsx`'s pattern) and extend `CloudChecksScanner.tsx`'s hardcoded provider lists to the 3 new providers.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CIS-OCI/Alibaba-baseline/Cloudflare-Security-Center check definitions | API / Backend | — | Static data modules (`cloud_checks_<provider>.py`), no client involvement, mirrors AWS/Azure/GCP pattern |
| Real findings ingest (OCI Cloud Guard, Alibaba Config/SAS, Cloudflare zone settings) | API / Backend | — | Server-side SDK calls using tenant-stored encrypted credentials; must never touch the browser |
| Check evaluation (`run_checks()`) | API / Backend | Database / Storage | Reads previously-imported `cloud_findings`, writes `cloud_check_results` — unchanged engine, provider-agnostic |
| Credential capture (tenancy OCID/PEM key, AK/SK, API token) | Browser / Client (form) | API / Backend (encrypt + store) | Form collects plaintext once, backend Fernet-encrypts via `CLOUD_CREDENTIALS_KEY` before persisting `credentials_ref` — client never re-reads it back |
| SIMULATED badge / posture dashboard rendering | Browser / Client | — | Pure presentation of `result.simulated`/`scan_status` fields already returned by the API |
| Compliance score contribution | API / Backend | Database / Storage | Existing compliance-score aggregation reads `cloud_check_results` generically; new providers are picked up automatically once `RUNNABLE_PROVIDERS` widens (verify at plan time — see Open Questions) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `oci` (Oracle's official Python SDK) | `>=2.181.1` (pinned; PyPI latest `2.182.0` per STACK.md 2026-07-20) [CITED: .planning/research/STACK.md] | OCI Cloud Guard client for CIS OCI Foundations-aligned posture findings | Already a direct dependency; `oci_ingest.py` already has the exact auth config shape (tenancy/user OCID + PEM key + fingerprint + region) |
| `cloudflare` (official Cloudflare Python SDK) | `>=5.4.0` (pinned; PyPI latest `5.5.0`) [CITED: .planning/research/STACK.md] | Cloudflare API v4 client — zone SSL/TLS settings, WAF managed rules | Official SDK, supersedes deprecated community wrappers; already a direct dependency, sync+async clients on `httpx` |
| `alibabacloud_config20200907` | `4.2.3` [ASSUMED — version from STACK.md training-assisted PyPI query, not independently re-verified this session; SUS per package-legitimacy check, see audit below] | Alibaba Cloud Config service V2 SDK — resource compliance/config-drift state | The correct CSPM-domain SDK (not the legacy alerts-only V1 `AcsClient`) |
| `alibabacloud_sas20181203` | `9.3.3` [ASSUMED — same caveat] | Alibaba Security Center (SAS) V2 SDK — baseline check pass/fail (`DescribeCheckWarningSummary`, `DescribeSecurityCheckSchedule`) | Alibaba's actual posture-scoring surface; maps directly to a `DO_CHECKS`-shaped list |
| `alibabacloud_tea_openapi` | `0.4.5` [ASSUMED] | Shared request/config plumbing required by every `alibabacloud_*` V2 package | Required peer dependency |
| `alibabacloud_credentials` | `1.0.10` [ASSUMED] | AK/SK credential provider for the V2 SDK family | Required peer dependency |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `aliyun-python-sdk-core-v3` | `>=2.13.33` (already installed per requirements.txt; not present in this session's venv — see Environment Availability) | Legacy V1 SDK, `AcsClient` | Keep only for the existing SIEM `alibaba_ingest.py::poll_alibaba_sas_alerts` path; do NOT extend it with new CSPM call sites |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `alibabacloud_sas20181203`/`alibabacloud_config20200907` (V2 typed SDK) | Keep using `aliyun-python-sdk-core-v3`'s `AcsClient` with `CommonRequest` | Avoids a new dependency, but means hand-building untyped action requests — explicitly the wrong pattern per STACK.md and CONTEXT.md's own D-04 note |
| Official `cloudflare` SDK | Community `python-cloudflare`/`pycloudflare` | Both are deprecated predecessors to the already-installed official SDK — do not add |

**Installation:**
```bash
# Already pinned in requirements.txt but NOT installed in this session's venv
# (verify at plan/execute time — pip list showed zero matches):
pip install oci>=2.181.1 cloudflare>=5.4.0

# New — not yet in requirements.txt, SUS-flagged pending human verification
# (see Package Legitimacy Audit — checkpoint:human-verify before installing):
pip install alibabacloud_config20200907==4.2.3 \
            alibabacloud_sas20181203==9.3.3 \
            alibabacloud_tea_openapi==0.4.5 \
            alibabacloud_credentials==1.0.10
```

**Version verification:** `.planning/research/STACK.md` (dated 2026-07-20, same session) already ran `pip index versions` against live PyPI for all of the above. This session independently confirmed via `backend/venv/bin/pip list` that **none of `oci`, `cloudflare`, `aliyunsdkcore`, or any `alibabacloud_*` package is actually installed in the project's venv today**, despite `oci`/`cloudflare` being pinned in `requirements.txt` — see Environment Availability.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `oci` | PyPI | Mature (years, Oracle-maintained) | N/A — not re-queried this session, already an existing direct dependency | github.com/oracle/oci-python-sdk | OK (existing dep) | Approved — no new check needed, already in `requirements.txt` |
| `cloudflare` | PyPI | Mature, official org | N/A — existing direct dependency | github.com/cloudflare/cloudflare-python | OK (existing dep) | Approved — already in `requirements.txt` |
| `alibabacloud_config20200907` | PyPI | Published 2026-03-31 per registry metadata | Unknown (registry API returned null) | github.com/aliyun/alibabacloud-python-sdk | **SUS** | Flagged — planner must add `checkpoint:human-verify` before install |
| `alibabacloud_sas20181203` | PyPI | Published 2026-06-22 | Unknown | github.com/aliyun/alibabacloud-python-sdk | **SUS** ("too-new", "unknown-downloads") | Flagged — planner must add `checkpoint:human-verify` before install |
| `alibabacloud_tea_openapi` | PyPI | Published 2026-07-14 | Unknown | github.com/aliyun/darabonba-openapi | **SUS** ("too-new", "unknown-downloads") | Flagged — planner must add `checkpoint:human-verify` before install |
| `alibabacloud_credentials` | PyPI | Published 2026-07-16 | Unknown | github.com/aliyun/credentials-python | **SUS** ("too-new", "unknown-downloads") | Flagged — planner must add `checkpoint:human-verify` before install |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `alibabacloud_config20200907`, `alibabacloud_sas20181203`, `alibabacloud_tea_openapi`, `alibabacloud_credentials`.

Interpretation: all four resolve to `github.com/aliyun/...` repos under Alibaba's own official GitHub org, and the package-name convention (`alibabacloud_<service><api-version>`) matches Alibaba's well-documented, widely-used V2/Tea-based SDK naming scheme (used by dozens of other `alibabacloud_*` service packages already on PyPI) — this is very likely a registry-metadata artifact (point releases with genuinely recent publish timestamps + a download-count API that returned null for this query) rather than a slopsquat. That said, per protocol these are **not** upgraded to `[VERIFIED]` on registry existence alone — `[ASSUMED]` tag applies to their exact version pins above, and the planner must gate installation behind a `checkpoint:human-verify` task (e.g., a human confirms `pip show <pkg>` after install resolves to the `aliyun` org's PyPI project page, or cross-checks against `https://github.com/aliyun/alibabacloud-python-sdk`'s own package index).

## Architecture Patterns

### System Architecture Diagram

```
Browser (AddCloudAccountModal.tsx / CloudAccountsDashboard.tsx)
    │  POST {provider, account_name, credentials_ref: JSON string}
    ▼
POST /api/cloud-accounts  (cloud_account_endpoints.py — _VALID_PROVIDERS already has oci/alibaba/cloudflare)
    ▼
cloud_accounts_service.register_account()
    │  Fernet-encrypts credentials_ref with CLOUD_CREDENTIALS_KEY, stores on cloud_accounts doc
    ▼
POST /api/cloud-accounts/{id}/scan
    ▼
cloud_accounts_service.scan_account()
    │  decrypt credentials_ref → json.loads → config dict
    │  if provider == "oci": await poll_oci_cspm_findings(config, account_id, tenant_id)   [NEW real API call]
    │  elif provider == "alibaba": await poll_alibaba_cspm_findings(config, account_id, tenant_id)  [NEW, V2 SDK]
    │  elif provider == "cloudflare": await poll_cloudflare_cspm_findings(config, account_id, tenant_id)  [NEW]
    │        └─ each writes real findings into db.cloud_findings (shape: id/tenantId/accountId/provider/
    │           service/checkId/title/severity/status/remediation) — same shape m365_ingest.py/
    │           mongodb_atlas_ingest.py already use
    ▼
cloud_checks_service.run_checks(account_id, provider, tenant_id)   [NEW: provider now in RUNNABLE_PROVIDERS]
    │  reads db.cloud_findings for this account
    │  provider_checks = CLOUD_CHECKS filtered to this provider  [NEW: OCI_CHECKS/ALIBABA_CHECKS/CLOUDFLARE_CHECKS now contribute]
    │  matches findings → PASS/FAIL, simulated = not has_real_findings
    ▼
upsert db.cloud_check_results
    ▼
GET /api/cloud-checks/results, /api/cloud-checks/summary, /api/cloud-accounts/{id}/results
    ▼
CloudChecksScanner.tsx / CloudAccountsDashboard.tsx  [NEW: SIMULATED badge, provider icon/filter entries]
    ▼
Compliance score aggregation (reads cloud_check_results generically — verify at plan time, see Open Questions)
```

### Recommended Project Structure

```
backend/
├── cloud_checks_oci.py           # NEW — OCI_CHECKS list, CIS OCI Foundations-aligned, DO_CHECKS-shaped
├── cloud_checks_alibaba.py       # NEW — ALIBABA_CHECKS list, Config/SAS-baseline-aligned
├── cloud_checks_cloudflare.py    # NEW — CLOUDFLARE_CHECKS list, Security Center-taxonomy-aligned
├── cloud_checks_service.py       # MODIFIED — import 3 new lists, extend CLOUD_CHECKS, extend RUNNABLE_PROVIDERS
├── oci_ingest.py                 # MODIFIED — un-mock _make_oci_client(); add account_id-aware real-findings path
├── alibaba_ingest.py             # MODIFIED — add V2-SDK-backed real-findings path (new function, separate from AcsClient path)
├── cloudflare_ingest.py          # MODIFIED — un-mock _make_cloudflare_client(); add account_id-aware real-findings path
├── cloud_accounts_service.py     # MODIFIED — extend scan_account()'s if/elif ladder with 3 new branches
└── requirements.txt              # MODIFIED — add 4 new alibabacloud_* pins (checkpoint:human-verify first)

components/
├── AddCloudAccountModal.tsx      # MODIFIED — provider-conditional credential fields; fix payload shape
├── CloudAccountsDashboard.tsx    # MODIFIED (likely) — SIMULATED badge on result rows, or credential fields if this is the chosen form
├── CloudChecksScanner.tsx        # MODIFIED — PROVIDER_ICONS + 2 filter-dropdown arrays + provider-tile loop extended; SIMULATED badge on results table
└── services/apiService.ts        # MODIFIED — fix addCloudAccount() field-name mismatch (name→account_name, credentials object→credentials_ref JSON string)
```

### Pattern 1: New check-definition module — dedicated file, DO_CHECKS dict shape

**What:** Each provider gets its own `cloud_checks_<provider>.py` exporting a flat list of dicts shaped exactly like `AWS_CHECKS`/`AZURE_CHECKS` entries.

**When to use:** Always, for this phase — matches the dominant pattern (6 of 7 existing providers use dedicated modules; only DigitalOcean is inline, and only because its list is small).

**Example:**
```python
# Source: backend/cloud_checks_aws.py (existing pattern, verbatim shape)
OCI_CHECKS = [
    {"id": "oci-iam-001", "name": "Root/Administrator MFA enabled",
     "description": "OCI tenancy administrators must have MFA enabled",
     "provider": "oci", "service": "iam", "severity": "critical",
     "frameworks": ["CIS-OCI-1.1"],
     "remediation": "Enable MFA for all users with the Administrators group via IAM console."},
    # ... 7-9 more, one per D-03's shared category: storage exposure, IAM policy, encryption, logging
]
```

### Pattern 2: Real ingest wired at `scan_account()`, not at `run_checks()`

**What:** `run_checks()` (`cloud_checks_service.py`) never calls a live cloud API — it only matches previously-imported `cloud_findings`. Real API calls belong in `cloud_accounts_service.scan_account()`'s existing if/elif ladder, exactly where `microsoft365`/`mongodb_atlas` already call `poll_m365_secure_scores`/`poll_mongodb_atlas_findings` before invoking `run_checks()`.

**When to use:** This is the *only* place in the request path where a tenant's decrypted credentials are available and an account_id/tenant_id pair is in scope.

**Example:**
```python
# Source: backend/cloud_accounts_service.py:107-124 (existing, verified by direct read)
elif provider == "oci":
    from oci_ingest import poll_oci_cspm_findings
    creds = _decrypt(account.get("credentials_ref", ""))
    try: config = json.loads(creds)
    except: config = {}
    await poll_oci_cspm_findings(config, account_id, tenant_id)
elif provider == "alibaba":
    from alibaba_ingest import poll_alibaba_cspm_findings
    ...
elif provider == "cloudflare":
    from cloudflare_ingest import poll_cloudflare_cspm_findings
    ...
```

### Pattern 3: Real-findings ingest shape — clone `m365_ingest.py`/`mongodb_atlas_ingest.py` exactly

**What:** A poll function `(config: Dict, account_id: str, tenant_id: str) -> int` that calls the real SDK, maps results into a `cloud_findings` document, and `insert_many`s them. This is the actual close analog D-01 should point to — **not** AWS/Azure/GCP (which have zero live-ingest modules in this codebase at all; they rely purely on whatever populated `cloud_findings` externally, which today is nothing, so they also run 100% simulated).

**Example:**
```python
# Source: backend/mongodb_atlas_ingest.py (existing, verified — the closest working real-ingest template)
def _parse_oci_cloud_guard_problem(problem, account_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()), "tenantId": tenant_id, "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "oci", "service": "cloud_guard",
        "checkId": f"OCI-{getattr(problem, 'detector_rule_id', 'UNKNOWN')}",
        "title": f"OCI Cloud Guard: {getattr(problem, 'title', 'Unknown Problem')}",
        "severity": _severity_map(getattr(problem, "risk_level", "MEDIUM")),
        "status": "FAIL",
        "remediation": "Review and remediate the flagged OCI Cloud Guard problem.",
        "raw_message": str(problem),
    }

async def poll_oci_cspm_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    if not _OCI_SDK_AVAILABLE:
        return 0
    client = _make_oci_client(config)   # now un-mocked: oci.cloud_guard.CloudGuardClient(oci_config)
    if not client:
        return 0
    problems = client.list_problems(compartment_id=config.get("oci_compartment_id")).data
    if not problems:
        return 0
    set_tenant_id(tenant_id)
    db = get_database()
    findings = [_parse_oci_cloud_guard_problem(p, account_id, tenant_id) for p in problems]
    await db.cloud_findings.insert_many(findings)
    return len(findings)
```

### Pattern 4: Reconciling D-01 ("retarget, don't add a second write path") with the SIEM/CSPM split — RECOMMENDED

**What:** The existing `poll_oci_cloud_guard_problems`/`poll_alibaba_sas_alerts`/`poll_cloudflare_zero_trust_events` (2-arg, `security_events`-writing) are still live call sites for `cloud_integrations_endpoints.py`'s **separate** SIEM-alert domain (`cloud_integrations` collection, `oci_cloud_guard`/`alibaba_sas`/`cloudflare_zero_trust` provider strings — distinct from the CSPM domain's `oci`/`alibaba`/`cloudflare` strings). Naively retargeting those exact functions to write `cloud_findings` instead would silently break the SIEM integration flow (`cloud_integrations_endpoints.py:342-350,396-404`), which this phase does not touch and has no reason to regress.

**Recommended reconciliation:** Add a new function per provider (`poll_oci_cspm_findings`/`poll_alibaba_cspm_findings`/`poll_cloudflare_cspm_findings`) in the *same file*, sharing the un-mocked client-construction helper (`_make_oci_client()` etc. — this is the actual "retargeted" piece per STACK.md's own framing: "real work is un-mocking `_make_oci_client()`"), but with its own account_id-aware signature and `cloud_findings` write target. This keeps "one file, one un-mocking effort, no second write *destination*" (satisfying D-01's intent) while not silently breaking the still-live 2-arg SIEM call sites (a regression D-01's author likely wasn't aware of, since `cloud_integrations_endpoints.py` wasn't in this phase's CONTEXT.md discussion). Flag this reconciliation for a quick confirmation at plan time rather than treating it as fully settled — see Open Questions.

### Pattern 5: SIMULATED badge — clone `IacContainerDashboard.tsx`'s existing pattern, not a new design

**What:** `result.simulated` is already computed correctly and generically by `run_checks()` for any provider (`"simulated": not has_real_findings`). Nothing renders it in either live CSPM dashboard today.

**Example:**
```tsx
// Source: components/IacContainerDashboard.tsx (existing, verified pattern — lines ~380-412)
{containerResult.simulated && (
  <span className="flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400">
    <AlertTriangle className="w-3 h-3 shrink-0" /> SIMULATED — no findings imported yet
  </span>
)}
```
Apply the same conditional span in `CloudChecksScanner.tsx`'s results table row (each `CheckResult` already carries no `simulated` field in its current TS interface — add `simulated: boolean` to the interface, the backend already returns it) and in `CloudAccountsDashboard.tsx`'s per-account results preview list.

### Anti-Patterns to Avoid

- **Modifying the 2-arg SIEM `poll_*` functions' write target in place:** Breaks `cloud_integrations_endpoints.py`'s live `test`/`discover` call sites, which pass no `account_id` and expect `security_events` output. See Pattern 4.
- **Extending `aliyun-python-sdk-core-v3`/`AcsClient` for the new CSPM Alibaba calls:** Legacy, untyped, alerts-only SDK per STACK.md's own recommendation — use the V2 typed packages instead.
- **Assuming `cloud_checks_endpoints.py`/`cloud_account_endpoints.py` need widening:** Verified by direct read this session (again) — both already list `oci`/`alibaba`/`cloudflare`. Only `RUNNABLE_PROVIDERS` in `cloud_checks_service.py` is stale. Don't spend plan/review time re-touching already-correct allowlists (per milestone PITFALLS.md, Anti-Pattern 4).
- **Treating `AddCloudAccountModal.tsx`'s existing accessKey/secretKey fields as "already working, just needs provider-specific labels":** They are wired to a payload shape (`credentials` object, `name` field) the backend endpoint silently discards. Any provider — not just the 3 new ones — registered through this exact form today never actually stores real credentials. This must be fixed as part of D-04, not assumed already correct.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Alibaba Config/Security-Center API requests | Hand-built `CommonRequest` action calls via `AcsClient` | `alibabacloud_config20200907` / `alibabacloud_sas20181203` typed clients | Typed response models, official V2 SDK, avoids manual param/action-name construction |
| Cloudflare zone-settings polling/retry | Custom `httpx` calls with manual 429/5xx retry | Official `cloudflare` SDK (already installed, built-in retry) | Already a direct dependency, handles auth + retry + typed models |
| Credential encryption at rest | New encryption scheme for OCI/Alibaba/Cloudflare-specific secrets | Existing `CLOUD_CREDENTIALS_KEY` Fernet encryption in `cloud_accounts_service.py` (`_encrypt`/`_decrypt`) | Already the exact mechanism M365/Atlas credentials use; no new key management needed |
| Provider allowlist validation | A 4th hardcoded provider tuple somewhere new | The 3 existing locations only — `RUNNABLE_PROVIDERS` (stale), `cloud_checks_endpoints.py`/`cloud_account_endpoints.py` (already correct); `mcp_server.py` imports `RUNNABLE_PROVIDERS` directly, self-updates | Duplicating a 4th list reintroduces the exact "duplicated gate" bug class this phase is fixing |

**Key insight:** Everything genuinely new in this domain is *data* (check definitions) or a *thin real-API adapter* (ingest functions) — the evaluation engine, credential storage, and tenant-isolation machinery are all proven, unchanged, reused as-is.

## Common Pitfalls

### Pitfall 1: "Add checks" touches only 1 of the 3 real gates, not the 4 the milestone decision log implies

**What goes wrong:** A developer widens `RUNNABLE_PROVIDERS`, ships it, and assumes `cloud_checks_endpoints.py`/`cloud_account_endpoints.py` also need edits per the Phase-25 precedent — wasting review time re-touching already-correct code, or worse, skipping the one gate that *does* need it.
**Why it happens:** `cloud_checks_endpoints.py:73` and `cloud_account_endpoints.py:13` were pre-widened in an earlier pass (verified again this session — both already list `oci`/`alibaba`/`cloudflare`); only `cloud_checks_service.py:37`'s `RUNNABLE_PROVIDERS` lags.
**How to avoid:** `grep -n "oci.*alibaba.*cloudflare\|RUNNABLE_PROVIDERS" backend/*.py` before touching anything; confirm current state, don't trust the historical decision log's "4 locations" framing literally.
**Warning signs:** `POST /api/cloud-accounts` succeeds for `provider: "oci"` but `POST /api/cloud-checks/run`/`.../scan` 400s.

### Pitfall 2: New "real" checks silently stay 100% simulated forever because ingest was never wired into `scan_account()`

**What goes wrong:** `cloud_checks_oci.py` etc. get written and imported into `CLOUD_CHECKS`, `RUNNABLE_PROVIDERS` gets widened, checks run — but every result is `simulated: true` and defaults to PASS, because nothing ever populates `cloud_findings` for these 3 providers. CSPM-01/02/03's "not simulated/stub data" requirement silently fails despite the UI looking functional.
**Why it happens:** `run_checks()` never calls a live API itself (by design, provider-agnostic) — it only evaluates whatever is already in `cloud_findings`. The only place that imports real findings is `cloud_accounts_service.scan_account()`'s if/elif ladder, currently handling only `microsoft365`/`mongodb_atlas`.
**How to avoid:** Add the 3 new branches to `scan_account()` per Pattern 2, un-mock `_make_oci_client()`/`_make_cloudflare_client()`, and build the V2-SDK Alibaba client — verify with a live account (or realistic mocked SDK response) that `cloud_findings` actually gains documents after a scan, not just that `cloud_check_results` gets upserted.
**Warning signs:** `db.cloud_findings.count_documents({"provider": "oci"})` stays 0 after a scan; every check result has `simulated: true` even for an account with a genuinely misconfigured resource.

### Pitfall 3: SIEM 2-arg `poll_*` call sites silently break if the existing functions are retargeted in place

**What goes wrong:** Literally interpreting D-01 ("retarget the existing stubs") by changing `poll_oci_cloud_guard_problems`'s write target from `security_events` to `cloud_findings` breaks `cloud_integrations_endpoints.py`'s `/test` and `/discover` endpoints, which call these exact functions with a 2-arg signature and expect `security_events` output for the SIEM dashboard.
**Why it happens:** Two independent provider domains (SIEM `cloud_integrations` vs. CSPM `cloud_accounts`) share ingest-module filenames but are otherwise unconnected — not obvious without reading both `cloud_integrations_endpoints.py` and `cloud_accounts_service.py` side by side (this session's own investigation required both).
**How to avoid:** Follow Pattern 4 — add new account_id-aware functions in the same files rather than mutating the existing 2-arg ones; run `grep -rn "poll_oci_cloud_guard_problems\|poll_alibaba_sas_alerts\|poll_cloudflare_zero_trust_events" backend/*.py` before touching signatures, confirm both call sites still resolve after the change.
**Warning signs:** `cloud_integrations_endpoints.py`'s `/test` route starts throwing `TypeError: poll_oci_cloud_guard_problems() missing 1 required positional argument` or silently writes findings to the wrong collection.

### Pitfall 4: Credentials silently never reach the backend through `AddCloudAccountModal.tsx`

**What goes wrong:** A user fills in the OCI private key / Alibaba AK-SK / Cloudflare API token in the "Add Cloud Account" modal, submits, sees success — but `credentials_ref` on the stored account doc is empty, because `apiService.addCloudAccount()` sends `{provider, name, account_id, credentials: {...}}` while the backend endpoint reads `account_name`/`credentials_ref` (a string). A subsequent scan then has no credentials to decrypt, and the ingest function's `required_fields` check fails silently (`return 0`).
**Why it happens:** Verified by direct read this session — `services/apiService.ts:2646-2654`'s `addCloudAccount()` payload keys don't match `cloud_account_endpoints.py`'s `register_account` payload contract. This is a pre-existing bug affecting every provider through this specific form, not something introduced by this phase, but it directly blocks D-04/CSPM-01..03 if left unfixed.
**How to avoid:** Fix the field mapping (`name`→`account_name`, build a JSON string from a structured `credentials` object → `credentials_ref`) as part of this phase's frontend work, and add an explicit end-to-end test (register with credentials → scan → confirm `cloud_findings` gains real documents, not just that the HTTP call returned 200).
**Warning signs:** A registered account's `credentials_ref` is empty in Mongo despite the form showing values entered; ingest poll functions return 0 with a logged "Incomplete credentials" warning even right after registration.

### Pitfall 5: `CloudChecksScanner.tsx`'s hardcoded provider lists silently hide the new providers even after the backend works

**What goes wrong:** Backend scan succeeds, `cloud_check_results` has real OCI/Alibaba/Cloudflare rows, but the dashboard's provider filter dropdown (`['aws','azure','gcp']`, appears twice) and `PROVIDER_ICONS` map (`{aws, azure, gcp}` only) never show them — results are visible only via "All Providers" with no icon, and the provider summary tile loop (also hardcoded to `['aws','azure','gcp']`) never surfaces a per-provider pass/fail tile for the new providers.
**Why it happens:** This is a pre-existing gap affecting DO/K8s/M365/MongoDB-Atlas too (confirmed by direct read — not a regression this phase introduces, but one this phase's "UI hint: yes" work should not perpetuate for the 3 providers it's explicitly adding).
**How to avoid:** Extend all 3 hardcoded arrays/maps in `CloudChecksScanner.tsx` (lines ~45, ~139, ~175) to include `oci`/`alibaba`/`cloudflare` (plus consider fixing the pre-existing DO/K8s/M365/Atlas gap if time allows — flag as out-of-scope-but-adjacent if not).
**Warning signs:** Live browser click-through: select "OCI" in the provider filter — option doesn't exist in the dropdown at all.

## Code Examples

### Widening `RUNNABLE_PROVIDERS` and `CLOUD_CHECKS` (the load-bearing 1-line + 3-import change)

```python
# Source: backend/cloud_checks_service.py (existing file, exact current lines)
from cloud_checks_oci import OCI_CHECKS
from cloud_checks_alibaba import ALIBABA_CHECKS
from cloud_checks_cloudflare import CLOUDFLARE_CHECKS

CLOUD_CHECKS: List[Dict[str, Any]] = (
    AWS_CHECKS + AZURE_CHECKS + GCP_CHECKS + K8S_CHECKS + DO_CHECKS
    + M365_CHECKS + MONGODB_ATLAS_CHECKS + OCI_CHECKS + ALIBABA_CHECKS + CLOUDFLARE_CHECKS
)

RUNNABLE_PROVIDERS = (
    "aws", "azure", "gcp", "kubernetes", "digitalocean",
    "microsoft365", "mongodb_atlas", "oci", "alibaba", "cloudflare",
)
```

### Test template for the new ingest functions

```python
# Source: backend/tests/test_cloud_findings_ingest.py (existing pattern for M365/Atlas,
# verified this session — patch targets must be the flat module attributes since
# scan_account() does function-local imports resolved at call time, not import time)
@pytest.fixture(autouse=True)
def mock_get_db(mock_db):
    with patch("m365_ingest.get_database", return_value=mock_db), \
         patch("mongodb_atlas_ingest.get_database", return_value=mock_db), \
         patch("oci_ingest.get_database", return_value=mock_db), \
         patch("alibaba_ingest.get_database", return_value=mock_db), \
         patch("cloudflare_ingest.get_database", return_value=mock_db):
        yield mock_db
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Alibaba V1 `aliyun-python-sdk-core-v3` `AcsClient`/`CommonRequest` for all Alibaba API calls | Alibaba V2 typed `alibabacloud_*` SDK family (per-service packages) | Alibaba's own stated migration ("V1 in Basic Security Maintenance, bugfixes only") — ongoing, not a single dated event | New Alibaba CSPM call sites must use V2; existing V1 SIEM call site (`alibaba_ingest.py::poll_alibaba_sas_alerts`) is fine to leave as-is |

**Deprecated/outdated:**
- `python-cloudflare`/`pycloudflare` community wrappers: superseded by the official `cloudflare` package, already the pinned dependency.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exact version pins for `alibabacloud_config20200907` (4.2.3), `alibabacloud_sas20181203` (9.3.3), `alibabacloud_tea_openapi` (0.4.5), `alibabacloud_credentials` (1.0.10) | Standard Stack, Installation | If stale, `pip install` will simply resolve to a newer compatible version — low risk, but planner should re-run `pip index versions <pkg>` at execute time rather than trusting these pins blindly, since the package-legitimacy check flagged all 4 as SUS pending human verification |
| A2 | Reconciliation approach for D-01 vs. the SIEM/CSPM split (Pattern 4 — add new account_id-aware functions rather than mutating the existing 2-arg ones) is the right synthesis of user intent | Architecture Patterns, Pattern 4 | If the user actually wants the SIEM `cloud_integrations` OCI/Alibaba/Cloudflare flow deprecated/removed entirely, the "don't break it" caution here would be unnecessary caution — low-cost either way since Pattern 4 is strictly additive and doesn't preclude later removal |
| A3 | The specific OCI Cloud Guard / Alibaba SAS / Cloudflare zone-settings API method names sketched in Code Examples/Pattern 3 (`list_problems`, `DescribeCheckWarningSummary`, zone settings resource) are the right calls for posture data | Architecture Patterns, Pattern 3; Standard Stack | These are carried over from `.planning/research/STACK.md`'s MEDIUM-confidence findings (SDK docs, not exercised live this session) — planner/executor should confirm exact method signatures against the installed SDK version before writing real code, not just from this doc |

## Open Questions

1. **Does compliance-score aggregation actually pick up new providers automatically, or does it have its own allowlist?**
   - What we know: `cloud_check_results` is read by `cloud_checks_service.get_summary()`/`get_results()` generically (no provider allowlist there); D-05 assumes automatic inclusion.
   - What's unclear: This session did not locate and read the tenant-wide compliance-score aggregation logic (separate from the CSPM-specific `cloud_checks_service.get_summary()`) referenced in CONTEXT.md's Integration Points ("Compliance score aggregation logic ... needs to pick up the 3 new providers per D-05; locate during research/planning").
   - Recommendation: Planner should grep for the compliance-score computation entry point (likely `compliance_score_service.py` or similar) and confirm it reads `cloud_check_results` without a provider filter before assuming D-05 is automatic.

2. **Should `AddCloudAccountModal.tsx` (the `cloudSecurity` view, matches "dropdown-only stub" framing) or `CloudAccountsDashboard.tsx` (the `cloudAccounts` view, real API-backed but zero credential fields today) be the target of D-04's form extension — or both?**
   - What we know: Both submit to the same real `/api/cloud-accounts` endpoint. `AddCloudAccountModal.tsx` already has a full provider dropdown (including OCI/Alibaba/Cloudflare) and looks like fields for credentials, but the payload shape is broken (Pitfall 4). `CloudAccountsDashboard.tsx` has a working payload shape but zero credential fields for any provider.
   - What's unclear: Which one users actually reach in the live nav for cloud-account registration, and whether the phase should consolidate to one form.
   - Recommendation: Fix `AddCloudAccountModal.tsx`'s payload bug first (unblocks every provider, not just these 3) and add provider-conditional credential fields there, since its dropdown/UX already most closely matches the phase description's "dropdown-only stub" framing; treat updating `CloudAccountsDashboard.tsx` similarly as a stretch goal, not a hard requirement, unless the plan-checker/user flags both as required reachable paths.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `oci` (PyPI) | CSPM-01 (real OCI checks) | ✗ (pinned in requirements.txt, not installed in `backend/venv`) | — | `pip install oci` before executing this phase's backend work |
| `cloudflare` (PyPI) | CSPM-03 (real Cloudflare checks) | ✗ (pinned, not installed) | — | `pip install cloudflare` before executing |
| `aliyun-python-sdk-core-v3` (PyPI) | Existing SIEM Alibaba path (unaffected by this phase) | ✗ (pinned, not installed) | — | `pip install aliyun-python-sdk-core-v3` if the SIEM path needs live testing during this phase |
| `alibabacloud_config20200907`, `alibabacloud_sas20181203`, `alibabacloud_tea_openapi`, `alibabacloud_credentials` (PyPI) | CSPM-02 (real Alibaba checks) | ✗ (not yet in requirements.txt at all) | — | Add to `requirements.txt` + `pip install`, gated behind `checkpoint:human-verify` per Package Legitimacy Audit |

**Missing dependencies with no fallback:**
- All 7 packages above block the "real, not simulated" portion of CSPM-01/02/03 if left uninstalled — the check-definition/evaluation-engine portion of the phase works without them (checks will just report `simulated: true`), but that alone does not satisfy the requirements' "not simulated/stub data" language.

**Missing dependencies with fallback:**
- None — these are the only viable SDKs per STACK.md's own research; no lighter-weight alternative was identified that avoids installing them.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (`backend/venv/bin/python -m pytest`) |
| Config file | none found — see Wave 0 |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_cloud_checks_expansion.py backend/tests/test_cloud_findings_ingest.py -q` |
| Full suite command | `cd backend && venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CSPM-01 | `run_checks()` evaluates OCI checks once `RUNNABLE_PROVIDERS` includes `"oci"` | unit | `pytest backend/tests/test_cloud_checks_expansion.py -k oci -x` | ❌ Wave 0 (extend existing file's pattern) |
| CSPM-01 | Real OCI Cloud Guard poll writes findings to `cloud_findings` | unit | `pytest backend/tests/test_cloud_findings_ingest.py -k oci -x` | ❌ Wave 0 (extend existing file) |
| CSPM-02 | `run_checks()` evaluates Alibaba checks | unit | `pytest backend/tests/test_cloud_checks_expansion.py -k alibaba -x` | ❌ Wave 0 |
| CSPM-02 | V2-SDK Alibaba poll writes findings to `cloud_findings` | unit | `pytest backend/tests/test_cloud_findings_ingest.py -k alibaba -x` | ❌ Wave 0 |
| CSPM-03 | `run_checks()` evaluates Cloudflare checks | unit | `pytest backend/tests/test_cloud_checks_expansion.py -k cloudflare -x` | ❌ Wave 0 |
| CSPM-03 | Real Cloudflare zone-settings poll writes findings to `cloud_findings` | unit | `pytest backend/tests/test_cloud_findings_ingest.py -k cloudflare -x` | ❌ Wave 0 |
| CSPM-01/02/03 | End-to-end scan via `scan_account()` for each new provider | integration | `pytest backend/tests/test_cloud_accounts.py -k scan -x` (extend existing file) | ⚠️ File exists, new cases needed |
| All | SIMULATED badge renders on fresh account with no imported findings | manual/UAT | live browser click-through | ❌ no automated frontend test framework detected for this component |

### Sampling Rate

- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_cloud_checks_expansion.py backend/tests/test_cloud_findings_ingest.py backend/tests/test_cloud_accounts.py -q`
- **Per wave merge:** `cd backend && venv/bin/python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`; live browser click-through for the SIMULATED badge and credential-form fix (per this codebase's own established CHK-03 verification bar — code inspection alone is not sufficient).

### Wave 0 Gaps

- [ ] Extend `backend/tests/test_cloud_checks_expansion.py` with `oci`/`alibaba`/`cloudflare` cases (clone the existing `kubernetes`/`digitalocean` test shape)
- [ ] Extend `backend/tests/test_cloud_findings_ingest.py` with `oci`/`alibaba`/`cloudflare` poll-function unit tests (clone the M365/Atlas fixture shape)
- [ ] No frontend test framework detected for `CloudChecksScanner.tsx`/`CloudAccountsDashboard.tsx`/`AddCloudAccountModal.tsx` in this repo — SIMULATED badge and credential-field verification rely on the manual/UAT gate only

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Not touched by this phase — existing `rbac_service.has_permission("manage:settings"/"view:cloud_security")` unchanged |
| V3 Session Management | no | Unchanged |
| V4 Access Control | yes | Existing `_tid(user)`/`rbac_service.has_permission(...)` on `/api/cloud-accounts/*` and `/api/cloud-checks/*` already tenant-scope every route — no new access-control surface introduced, just new provider values flowing through existing checks |
| V5 Input Validation | yes | `cloud_account_endpoints.py::register_account` already validates `provider`/`environment`/`credentials_ref` type; new provider-specific credential JSON shapes (OCI PEM key, Alibaba AK/SK, Cloudflare token) are not schema-validated server-side today — recommend the phase add minimal shape checks (e.g., required-keys-present) before `json.loads(creds)` is trusted downstream, since a malformed blob currently fails silently (`except: config = {}` in `scan_account()`) rather than surfacing to the user |
| V6 Cryptography | yes | Never hand-roll — reuse the existing `CLOUD_CREDENTIALS_KEY` Fernet encryption in `cloud_accounts_service.py` (`_encrypt`/`_decrypt`) for all 3 new providers' credential blobs, exactly as M365/Atlas already do |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PEM private key (OCI) embedded as a JSON string value inside `credentials_ref` — multi-line escaping/truncation risk | Tampering | Validate the decoded PEM shape (`-----BEGIN ... KEY-----`) before passing to the SDK; fail loudly rather than silently constructing a broken client |
| Credential leakage via API response | Information Disclosure | Already mitigated — `register_account()`'s return strips `credentials_ref` from every response (`{k: v for k, v in doc.items() if k != "credentials_ref"}`); preserve this for the 3 new providers, no new field name should bypass the strip |
| Cross-tenant account/finding access via `account_id` reuse across tenants | Elevation of Privilege | Already mitigated — every `cloud_accounts`/`cloud_findings`/`cloud_check_results` query in this domain is `tenantId`-scoped (either via `TenantIsolatedCollection` or explicit `db._db` + manual filter in `cloud_accounts_service.py`); no new pattern needed, just don't bypass it when adding the 3 new branches |

## Sources

### Primary (HIGH confidence)
- Direct code reads, this session, `feat/rust-agent-2.1.0-and-fixes` branch: `backend/cloud_checks_service.py`, `backend/cloud_checks_aws.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/cloud_accounts_service.py`, `backend/oci_ingest.py`, `backend/cloudflare_ingest.py`, `backend/alibaba_ingest.py`, `backend/m365_ingest.py`, `backend/mongodb_atlas_ingest.py`, `backend/cloud_integrations_endpoints.py`, `backend/tests/test_cloud_checks_expansion.py`, `backend/tests/test_cloud_findings_ingest.py`, `components/CloudChecksScanner.tsx`, `components/CloudAccountsDashboard.tsx`, `components/CloudSecurityDashboard.tsx`, `components/AddCloudAccountModal.tsx`, `components/IacContainerDashboard.tsx`, `services/apiService.ts`, `App.tsx`, `types.ts`.
- `backend/venv/bin/pip list` run this session — confirms zero installed packages among `oci`/`cloudflare`/`aliyunsdkcore`/`alibabacloud_*`.
- `gsd-tools query package-legitimacy check --ecosystem pypi` run this session against all 4 new Alibaba V2 packages.
- `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` (dated 2026-07-20, same session as this research, HIGH confidence, grounded in this same codebase).

### Secondary (MEDIUM confidence)
- STACK.md's own MEDIUM-confidence citations (carried forward): OCI Cloud Guard Python SDK docs, Cloudflare official SDK GitHub, alibabacloud-python-sdk GitHub, aliyun-openapi-python-sdk GitHub.

### Tertiary (LOW confidence)
- Exact version pins for the 4 new `alibabacloud_*` packages (SUS-flagged, see Package Legitimacy Audit) — treat as `[ASSUMED]`, re-verify at install time.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for `oci`/`cloudflare` (existing pinned deps, verified not-installed via direct `pip list`); MEDIUM/LOW for exact Alibaba V2 package version pins (SUS-flagged, carried from STACK.md, not independently re-verified against live PyPI this session)
- Architecture: HIGH — every wiring point (RUNNABLE_PROVIDERS, scan_account() ladder, SIEM/CSPM domain split, frontend field-mapping bug, missing SIMULATED badge) verified by direct code read this session
- Pitfalls: HIGH — all 5 pitfalls above are either carried from the milestone-level PITFALLS.md (itself HIGH-confidence, code-grounded) or newly discovered this session via direct file reads, not generic domain advice

**Research date:** 2026-07-20
**Valid until:** 30 days for the architecture/pitfalls findings (stable, code-grounded); 7 days for the exact Alibaba SDK version pins (SUS-flagged, fast-moving new packages)

---
*Phase research for: Enterprise OmniAgent v3.2 milestone — Phase 41*
*Researched: 2026-07-20*
