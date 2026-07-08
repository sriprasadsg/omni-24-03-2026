# Phase 32: Cloud and SaaS Provider Expansion - Research

**Researched:** 2026-07-08
**Domain:** Multi-provider integration polling (Python/FastAPI/httpx/Motor), OAuth evidence-pull extension, dead-code re-wiring
**Confidence:** MEDIUM (HIGH on architecture/codebase findings — all direct reads; MEDIUM on external SDK package facts — WebSearch-sourced, cross-checked against PyPI registry)

## Summary

This phase touches **three architecturally distinct, previously-separate provider subsystems** in this codebase, plus one dead-code re-wiring. Getting the requirement-to-subsystem mapping right is the single most important thing this research resolves — the phase description's own language ("real polling" vs. "scanned providers" vs. "native posture checks") maps to three different existing patterns, not one:

1. **PROV-01 (OCI/Alibaba/Cloudflare real polling)** targets `cloud_integrations_endpoints.py` — a SIEM-alert-ingestion integration hub (`SUPPORTED_PROVIDERS` dict) that already has two working real-SDK-polling providers (`azure_defender`, `gcp_scc`/`gcp_chronicle`, via `azure_defender_ingest.py`/`gcp_scc_ingest.py`) and seven **stub** providers — including `oci_cloud_guard`, `alibaba_sas`, `cloudflare_zero_trust` — whose `test_integration()` branch falls through to `count = 0` with **no ingest call at all**. This is confirmed by direct read: the phrase "only store connection config" matches `create_integration()`'s behavior exactly, and the file's own docstring/route design is built around "poll" as its verb. **Do not confuse this with** the *separate* `cloud_account_endpoints.py`/`cloud_checks_service.py` CSPM system (Phase 20/25) — that system's `_VALID_PROVIDERS` doesn't even list OCI/Alibaba/Cloudflare, and its frontend (`AddCloudAccountModal.tsx`) offers those three as options that would 400 today (a related, but out-of-scope, pre-existing bug — see Open Questions).

2. **PROV-02 (M365 + MongoDB Atlas as "scanned providers")** targets the *other* system: `cloud_checks_service.py`'s `CLOUD_CHECKS`/`RUNNABLE_PROVIDERS` catalog-and-execution engine (the one Phase 25 just widened for kubernetes/digitalocean). Critically, **this engine does not make live API calls for any provider today, including AWS/Azure/GCP** — `run_checks()` matches check definitions against a `cloud_findings` MongoDB collection that **is never written to anywhere in the codebase** (confirmed by exhaustive grep — only 4 read-sites, 0 write-sites outside tests). Every check for every "runnable" provider therefore evaluates to `PASS` today, because `failing_ids`/`failing_titles` are always empty sets. Extending this exact pattern to `microsoft365`/`mongodb_atlas` (new check-catalog files, following the `K8S_CHECKS`/`DO_CHECKS` precedent) is consistent with how the rest of this engine works and is a Tier-2-appropriately-sized change. Building live Graph-API/Atlas-Admin-API polling that actually populates `cloud_findings` would be a much larger, precedent-breaking scope — see the Critical Scope Resolution below.

3. **PROV-03 (native posture checks for 5 OAuth SaaS providers)** targets `saas_integration_service.py` (Phase 14) — which, unlike system #2, **already makes real live HTTP calls** to GitHub/Jira/Okta/Google Workspace/Slack APIs and already computes a `"status": "pass"/"fail"/"no-data"` per evidence item. The gap is a *data-shape* gap, not a *data-source* gap: today's real API responses are written only as free-text `control_evidence` rows for the compliance-framework engine, never as discrete, catalogued, severity-rated "checks" (the `id`/`severity`/`remediation`/`frameworks` shape used everywhere else in this codebase — `CLOUD_CHECKS`, `IAC_CHECKS`). PROV-03 is best delivered as a thin posture-check layer over data this phase's evidence-pull functions **already fetch for real**, not a new integration.

4. **PROV-04 (attack-path prefers real findings, labels fallback)** is a **dead-code re-wiring bug**, not new functionality. `attack_path_service.py`'s `AttackPathService.get_attack_paths()` already contains a complete, working real-correlation implementation (assets × open vulnerabilities → exploit chains, with a demo-seed fallback only when truly no data exists) — but it is **never imported or instantiated anywhere** (confirmed by grep: zero call sites outside its own file). The registered route, `attack_path_endpoints.py`'s `get_attack_paths()`, instead runs a much thinner inline handler that checks the `attack_paths` collection and, if empty, **immediately** returns hardcoded demo scenarios with no attempt at real correlation. The fix is to delete the endpoint's duplicate logic and call the real service. A second, independent bug was found while reading this code: the frontend `AttackPath` type (`types.ts`) expects edge fields `from`/`to`/`label`, but every backend code path (real and demo) emits `source`/`target`/`vulnerability` — meaning the edge label between nodes has never rendered correctly in the UI. Both must be fixed for PROV-04 to be meaningfully "real."

**Primary recommendation:** Treat PROV-01/02/03/04 as four independent workstreams touching four different files/subsystems, not one unified "add more providers" task. Do not attempt full production-grade live SDK integration for all 5 new providers (OCI, Alibaba, Cloudflare, M365, MongoDB Atlas) uniformly — follow each subsystem's own existing pattern (real-SDK-poll for #1, catalog-match for #2, evidence-pull-plus-labeling for #3).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROV-01 | OCI, Alibaba Cloud, and Cloudflare integrations actually poll for findings instead of only storing connection config | Architecture Patterns — Pattern 1 (`cloud_integrations_endpoints.py` + new `oci_ingest.py`/`alibaba_ingest.py`/`cloudflare_ingest.py` mirroring `azure_defender_ingest.py`); Standard Stack has verified SDK package names; Package Legitimacy Audit covers all 3 |
| PROV-02 | Microsoft 365 (distinct from Azure AD/Entra) and MongoDB Atlas are added as scanned providers | Architecture Patterns — Pattern 2 (extend `cloud_checks_service.py` CLOUD_CHECKS/RUNNABLE_PROVIDERS with `M365_CHECKS`/`MONGODB_ATLAS_CHECKS`, four-gate widening per Phase 25 precedent); Common Pitfalls 1 explains the always-PASS trap this inherits |
| PROV-03 | GitHub, Okta, Google Workspace, Slack, and Jira gain native posture checks, not just evidence-pull | Architecture Patterns — Pattern 3 (new `saas_posture_checks_service.py` — must be a NEW file, `saas_integration_service.py` is already at the exact 500-line CLAUDE.md limit); Common Pitfalls 2 |
| PROV-04 | Attack-path visualization prefers real findings whenever they exist, and clearly labels the demo-seed fallback | Architecture Patterns — Pattern 4 (wire dead `AttackPathService` into `attack_path_endpoints.py`, fix `source/target/vulnerability` vs `from/to/label` field mismatch, add `simulated: true`); Common Pitfalls 3 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Keep files under 500 lines.** `saas_integration_service.py` is **already exactly 500 lines** — PROV-03 work MUST go in a new file (`saas_posture_checks_service.py` or similar), never inline. `cloud_checks_service.py` (146 lines), `cloud_integrations_endpoints.py` (481 lines, close to the limit — new ingest polling logic belongs in new `*_ingest.py` files, not inline), `attack_path_endpoints.py` (86 lines) all have headroom but should still favor new small ingest/check-catalog files over growing existing files.
- **NEVER create files unless absolutely necessary — prefer editing existing files.** Balanced against the 500-line constraint above: new provider check-catalog files (`cloud_checks_m365.py`, `cloud_checks_mongodb_atlas.py`) follow the exact precedent of the existing `cloud_checks_aws.py`/`cloud_checks_azure.py`/`cloud_checks_gcp.py`/`cloud_checks_k8s.py` per-provider split — this is not gratuitous file creation, it's the established pattern. New ingest files (`oci_ingest.py`/`alibaba_ingest.py`/`cloudflare_ingest.py`) mirror the existing `azure_defender_ingest.py`/`gcp_scc_ingest.py` split.
- **Validate input at system boundaries.** New provider config fields (OCI tenancy OCID, Alibaba access keys, Cloudflare API tokens, M365 Graph app credentials, MongoDB Atlas org API key pair) must be validated the same way `cloud_integrations_endpoints.py`'s existing `required_fields`/`_encrypt_secrets` gate validates the other 9 providers already in `SUPPORTED_PROVIDERS`.
- **Do what has been asked; nothing more, nothing less.** Do not build a full CSPM live-scanning engine for AWS/Azure/GCP as a side effect of "fixing" the always-PASS `cloud_findings` gap for M365/MongoDB Atlas — that gap is pre-existing and out of this phase's explicit requirement text (see Common Pitfalls 1 and Open Questions).
- **ALWAYS read a file before editing it.** All files this research touches were read in full this session.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OCI/Alibaba/Cloudflare live alert polling (PROV-01) | API / Backend (`cloud_integrations_endpoints.py` + new `*_ingest.py` files) | Database (`security_events` collection — same sink as `azure_defender_ingest.py`) | Server-side outbound API calls using stored (encrypted) credentials; no client surface change needed beyond existing `CloudIntegrationsDashboard.tsx` "Test"/"Discover" buttons already wired |
| M365 + MongoDB Atlas check catalogs (PROV-02) | API / Backend (`cloud_checks_service.py` + 2 new check-catalog modules) | Database (`cloud_check_results`, `cloud_findings`) | Pure catalog-and-match logic, identical tier to the existing AWS/Azure/GCP/K8s/DO engine it extends |
| SaaS native posture checks (PROV-03) | API / Backend (new `saas_posture_checks_service.py`, reusing `saas_integration_service.py`'s already-real HTTP pulls) | Database (new `saas_check_results` collection, shaped like `cloud_check_results`) | The live data collection is already real (Phase 14) — this phase only adds a structured checks-catalog re-shaping layer, same tier |
| Attack-path real-findings preference + labeling (PROV-04) | API / Backend (`attack_path_endpoints.py` — delete duplicate logic, call `AttackPathService`) | Browser/Client (`AttackPathDashboard.tsx` — simulated badge + edge-label field-name fix) | Backend must emit an unambiguous `simulated: bool` flag and fix the edge-field contract; frontend must render both — same "trust/compliance-integrity" tier split Phase 25 used for CHK-03 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `oci` | 2.181.1 (latest as of check) | Oracle Cloud Infrastructure Python SDK — Cloud Guard problems/alerts | Official Oracle-maintained SDK (`github.com/oracle/oci-python-sdk`), the only supported way to call OCI APIs from Python `[ASSUMED — WebSearch-sourced, PyPI-registry-cross-checked]` |
| `aliyun-python-sdk-core-v3` | 2.13.33 (latest as of check) | Alibaba Cloud SDK core (Python 3) — Security Center (SAS) alert polling | Official Alibaba-maintained core library for Python 3.x; the plain `aliyun-python-sdk-core` name is the legacy Python-2-era package — `-v3` is the correct current name `[ASSUMED — WebSearch-sourced, PyPI-registry-cross-checked]` |
| `cloudflare` | 5.4.0 (latest as of check) | Official Cloudflare API client — Zero Trust gateway/access logs | Official Cloudflare-maintained SDK (`github.com/cloudflare/cloudflare-python`), httpx-backed sync+async, matches this codebase's existing httpx convention `[ASSUMED — WebSearch-sourced, PyPI-registry-cross-checked]` |
| `msal` | 1.37.0 (already present — transitive dep of `azure-identity`, itself a direct dep for the existing Azure integrations) | Microsoft Graph API app-only (client-credentials) auth for M365 posture checks | Already installed in this venv (confirmed via `pip show msal`); should be **promoted to an explicit line in `requirements.txt`** rather than left as an undeclared transitive dependency, since PROV-02 will start depending on it directly `[VERIFIED: pip show msal in project venv]` |
| `requests` | already pinned (`>=2.28.0`) | MongoDB Atlas Administration API digest authentication | `requests.auth.HTTPDigestAuth` is a built-in feature of the already-pinned `requests` library — **no new dependency needed** for MongoDB Atlas Admin API's HTTP Digest auth scheme `[ASSUMED — training knowledge; requests' digest-auth support is long-standing/stable, not independently re-verified this session]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | already pinned (`>=0.27.0,<1.0.0`) | M365 Graph API calls (`GET /security/secureScores`) after `msal` obtains the app-only token | Follow the exact same pattern as `saas_integration_service.py`'s existing GitHub/Okta/GWS/Slack pulls — raw httpx + bearer token, not a heavy SDK, for consistency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Official `oci`/`aliyun-python-sdk-core-v3`/`cloudflare` SDKs | Raw httpx calls against each provider's REST API directly (same pattern `saas_integration_service.py` uses for GitHub/Okta/GWS/Slack) | Raw httpx avoids 3 new heavyweight dependencies and matches the SaaS-integration pattern, but OCI's request-signing scheme (RSA-SHA256 over a canonical string) is genuinely painful to hand-roll correctly — the official SDK is the pragmatic choice for OCI specifically; Alibaba and Cloudflare are more httpx-friendly (Cloudflare especially — simple bearer-token REST API) and the planner may reasonably choose raw httpx for those two to avoid dependency bloat. Recommend: `oci` SDK for OCI (signing complexity), raw httpx acceptable for Alibaba/Cloudflare if the planner prefers minimal dependencies. |
| Official `msgraph-sdk` (Microsoft's fuller Graph SDK) | `msal` (already present) + raw httpx | `msgraph-sdk` is a much larger, actively-evolving dependency; this codebase's established SaaS-integration pattern (Phase 14) is deliberately raw-httpx-based for every OAuth provider including other Microsoft-adjacent ones. Recommend raw httpx + msal for consistency. |
| MongoDB Atlas Admin API keys (legacy digest auth) | Atlas Service Accounts (OAuth2 client-credentials, MongoDB's current recommendation) | MongoDB's own docs now recommend service accounts over legacy API-key digest auth `[CITED via WebSearch summary of mongodb.com/docs/atlas/api/api-authentication]`; digest auth is simpler to implement with zero new dependencies via `requests.auth.HTTPDigestAuth` and is still fully supported — recommend digest auth for this phase's scope, note service-account OAuth2 as a future hardening option in Open Questions. |

**Installation:**
```bash
# backend/requirements.txt additions (exact versions to be pinned at implementation time —
# verify current latest via `pip index versions <pkg>` again just before implementation,
# since this research's version snapshot may be a few days stale by execution time)
pip install oci aliyun-python-sdk-core-v3 cloudflare msal
```

**Version verification:** All four packages confirmed to exist and resolve via `pip index versions` against the live PyPI registry this session (`oci` → 2.181.1, `aliyun-python-sdk-core-v3` → 2.13.33, `cloudflare` → 5.4.0, `msal` → 1.37.0 already installed). None of the four are importable in the current venv (`ModuleNotFoundError` confirmed for `oci`, `cloudflare`, `aliyunsdkcore`; `msal` importable only because `azure-identity` pulled it in transitively) — all four need an explicit `requirements.txt` line added.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|--------------|---------|-------------|
| `oci` | PyPI | Long-lived (180+ published releases going back to 0.0.1; latest 2.181.1) | Unknown — PyPI JSON API doesn't expose download counts to the legitimacy checker | `docs.oracle.com/en-us/iaas/tools/python` (Oracle-owned docs domain; GitHub at `oracle/oci-python-sdk`) | **SUS** (seam flags "too-new"/"unknown-downloads" — see note) | Approved with note — checkpoint:human-verify before install |
| `aliyun-python-sdk-core-v3` | PyPI | Long-lived (releases since ≥2.3.x era; latest 2.13.33) | Unknown | `github.com/aliyun/aliyun-openapi-python-sdk` | **SUS** (unknown-downloads only) | Approved with note — checkpoint:human-verify before install |
| `cloudflare` | PyPI | Long-lived (major-version progression 1.x→5.x; latest 5.4.0) | Unknown | `github.com/cloudflare/cloudflare-python` | **SUS** (seam flags "too-new"/"unknown-downloads" — see note) | Approved with note — checkpoint:human-verify before install |
| `httpx-auth` (considered, not recommended) | PyPI | Long-lived (0.1.0→0.23.1 steady progression) | Unknown | None listed in registry metadata | **SUS** (unknown-downloads + no-repository) | **Not needed** — `requests.auth.HTTPDigestAuth` (already-pinned dependency) covers the MongoDB Atlas digest-auth need without adding this package |
| `msal` | PyPI | Already verified via `pip show` in-project (Microsoft-owned, `Required-by: azure-identity`) | N/A — already trusted transitive dep of an existing direct dependency | `github.com/AzureAD/microsoft-authentication-library-for-python` | OK | Approved — promote from transitive to explicit `requirements.txt` line |

**Note on the SUS verdicts above:** The `package-legitimacy check` seam flags `oci` and `cloudflare` with a `"too-new"` signal. Direct cross-check via `pip index versions` shows this is a **false positive** driven by the seam reading the *latest release's* publish timestamp (both packages ship very frequent releases — `oci` has 180+ historical versions, `cloudflare` has version history back to 1.0.1) rather than the package's *first-publish* date. Both are long-established, vendor-owned SDKs. The `"unknown-downloads"` signal on all three OCI/Alibaba/Cloudflare packages simply reflects that the legitimacy checker's PyPI query doesn't retrieve download-count telemetry — not evidence of low adoption. **Recommendation: proceed with all three, but the planner should still add a `checkpoint:human-verify` task before the actual `pip install` per the SUS-handling protocol**, since automated verdicts (even false-positive-flavored ones) should get a human glance before landing in `requirements.txt`.

**Packages removed due to `[SLOP]` verdict:** none
**Packages flagged as suspicious `[SUS]`:** `oci`, `aliyun-python-sdk-core-v3`, `cloudflare` — all three recommended for approval after manual cross-check (see note above), but still require a `checkpoint:human-verify` task per protocol before `pip install`.

## Architecture Patterns

### System Architecture Diagram

```
════════════════════════════ SUBSYSTEM 1: cloud_integrations_endpoints.py (PROV-01) ════════════════════════════
POST /api/cloud-integrations {provider, config}
      │  SUPPORTED_PROVIDERS validates + _encrypt_secrets() stores config
      ▼
db.cloud_integrations  ── stores connection config only (today, for 7 of 11 providers) ──┐
      │                                                                                    │
      ▼ POST /api/cloud-integrations/{id}/test  (or /discover for bulk)                   │
┌─────────────────────────────────────────────────────────────────┐                       │
│ if provider == azure_defender/microsoft_sentinel:                │──► REAL SDK poll ────►│ security_events
│     azure_defender_ingest.poll_azure_defender_alerts()           │    (azure-mgmt-security,
│ elif provider == gcp_scc/gcp_chronicle:                          │     azure-monitor-query)
│     gcp_scc_ingest.poll_gcp_scc_findings()                       │──► REAL SDK poll ────►│
│ elif provider in (oci_cloud_guard, alibaba_sas,                  │
│                    cloudflare_zero_trust, aws_guardduty,         │──► count = 0, NO CALL  ◄── PROV-01 TARGET:
│                    aws_securityhub, ibm_qradar,                  │    (silent no-op)         add oci_ingest.py /
│                    digitalocean_alerts, huawei_hss):              │                           alibaba_ingest.py /
│     count = 0   # <-- THE GAP                                     │                           cloudflare_ingest.py
└─────────────────────────────────────────────────────────────────┘                           mirroring the two
                                                                                                 working examples

════════════ SUBSYSTEM 2: cloud_checks_service.py CLOUD_CHECKS/RUNNABLE_PROVIDERS (PROV-02) ════════════
POST /api/cloud-accounts {provider: "aws"|"azure"|"gcp"|"kubernetes"|"digitalocean"}  ◄── 4-gate allowlist
      │                                                                                   (Phase 25 pattern —
      ▼                                                                                    PROV-02 widens again
run_checks(): match CLOUD_CHECKS[provider] against db.cloud_findings                       for microsoft365 +
      │            ▲                                                                       mongodb_atlas)
      │            └── db.cloud_findings is NEVER WRITTEN anywhere in this codebase
      │                (0 insert call sites found by grep) → every check evaluates PASS
      ▼                for every provider, today, always. Extending this catalog to M365/
cloud_check_results     Mongo Atlas inherits this exact (pre-existing, out-of-scope) gap.

════════════ SUBSYSTEM 3: saas_integration_service.py (PROV-03 — the one with REAL live data) ════════════
POST /api/saas/connections/{id}/pull-evidence
      │
      ▼
pull_github_evidence() / pull_jira_evidence() / pull_okta_evidence() /
pull_google_workspace_evidence() / pull_slack_evidence()
      │  ── REAL httpx calls against live GitHub/Jira/Okta/GWS/Slack REST APIs ──
      │  ── each evidence item already computes "status": "pass"/"fail"/"no-data" ──
      ▼
db.control_evidence  ── free-text evidence rows only (today) ──┐
                                                                  │  PROV-03 TARGET: new
                                                                  └─► saas_posture_checks_service.py
                                                                      re-shapes the SAME real API
                                                                      responses into id/severity/
                                                                      remediation "check" records
                                                                      → db.saas_check_results
                                                                      (saas_integration_service.py is
                                                                       AT the 500-line cap — new file
                                                                       required, not an inline edit)

════════════ SUBSYSTEM 4: attack_path_* (PROV-04 — dead-code re-wiring) ════════════
GET /api/security/attack-paths  (attack_path_endpoints.py — REGISTERED route)
      │
      ▼
if db.attack_paths has stored docs: return them
else: return _seed_paths() IMMEDIATELY  ◄── never tries real correlation — BUG
                                             (edges use from/to/label per types.ts,
                                              but backend emits source/target/vulnerability
                                              — a SECOND pre-existing bug, edge labels
                                              never render)

attack_path_service.AttackPathService.get_attack_paths()  ◄── DEAD CODE (0 call sites)
      │  Real logic: correlate db.assets × db.vulnerabilities (or db.cspm_findings
      │  fallback) → build entry→hop→target exploit chains → persist → return
      │  Only falls back to _seed_demo_paths() when truly no assets/vulns exist
      ▼
PROV-04 FIX: attack_path_endpoints.py calls get_attack_path_service(db).get_attack_paths()
             instead of its own duplicate seed-first logic; response includes
             "simulated": true/false so the frontend can label demo scenarios.
```

### Recommended Project Structure
```
backend/
├── cloud_integrations_endpoints.py   # PROV-01: wire new ingest calls into test_integration()/trigger_cloud_discovery()
├── oci_ingest.py                     # NEW — mirrors azure_defender_ingest.py shape (poll_*, _AZURE_SDK_AVAILABLE-style guard)
├── alibaba_ingest.py                 # NEW — mirrors gcp_scc_ingest.py shape
├── cloudflare_ingest.py              # NEW — mirrors azure_defender_ingest.py shape
├── cloud_checks_service.py           # PROV-02: RUNNABLE_PROVIDERS + CLOUD_CHECKS widened (4-gate pattern from Phase 25)
├── cloud_checks_m365.py              # NEW — M365_CHECKS list, same dict shape as cloud_checks_aws.py etc.
├── cloud_checks_mongodb_atlas.py     # NEW — MONGODB_ATLAS_CHECKS list, same dict shape
├── cloud_account_endpoints.py        # PROV-02: _VALID_PROVIDERS widened (gate 1)
├── mcp_server_endpoints.py           # PROV-02: provider validation widened (gate 3)
├── saas_integration_service.py       # UNCHANGED — already at 500-line cap; do not add PROV-03 logic here
├── saas_posture_checks_service.py    # NEW — PROV-03: re-shapes saas_integration_service's real API responses into checks
├── saas_posture_checks_endpoints.py  # NEW — PROV-03: GET /api/saas/posture-checks, POST .../run
├── attack_path_endpoints.py          # PROV-04: delete duplicate seed-first logic, call attack_path_service
├── attack_path_service.py            # PROV-04: add "simulated" flag to both real-path and demo-path returns; fix edge field names to source/target (see Pitfall — frontend fix is the other half)
├── requirements.txt                  # + oci, aliyun-python-sdk-core-v3, cloudflare, msal (explicit)
├── tests/
│   ├── test_cloud_integrations.py    # NEW — currently no test file exists for this endpoint file at all
│   ├── test_cloud_checks_expansion.py  # extend with M365/MongoDB Atlas cases (existing file from Phase 25)
│   ├── test_saas_posture_checks.py   # NEW
│   └── test_attack_path.py           # NEW — currently no test file exists for this feature at all
components/
├── CloudIntegrationsDashboard.tsx    # PROV-01: no structural change needed — already renders provider list generically
├── AttackPathDashboard.tsx           # PROV-04: fix edge.from/edge.label → edge.source/edge.vulnerability (or fix backend to emit from/label — pick one side, see Pitfall), add "Simulated Data" badge when path.simulated
types.ts                              # PROV-04: AttackPathEdge fields must match whichever side of the mismatch is NOT changed; AttackPath gains simulated?: boolean
```

### Pattern 1: Real-Poll Ingest Module (PROV-01 — mirrors `azure_defender_ingest.py` exactly)

**What:** Every working real-poll provider in `cloud_integrations_endpoints.py` follows the same shape: a standalone `<provider>_ingest.py` file with (a) a top-level `try/except ImportError` SDK-availability guard that logs a warning and sets a module-level bool if the SDK isn't installed, (b) a `poll_<provider>_alerts(config, tenant_id) -> int` function that builds a client from the integration's decrypted config, calls the real API, maps results into the `security_events` shape, inserts them, and **returns 0 on any failure** (never raises to the caller — matches `saas_integration_service.py`'s Phase 14 "partial evidence, never raise" convention), and (c) an optional background polling loop function.

**When to use:** For OCI, Alibaba, and Cloudflare exactly as `cloud_integrations_endpoints.py`'s `test_integration()` and `trigger_cloud_discovery()` already dispatch to `azure_defender_ingest`/`gcp_scc_ingest` — add three more `elif provider == "..."` branches calling the three new modules.

```python
# Source: backend/azure_defender_ingest.py (verbatim structure to replicate for OCI/Alibaba/Cloudflare)
try:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.security import SecurityCenter
    _AZURE_SDK_AVAILABLE = True
except ImportError:
    _AZURE_SDK_AVAILABLE = False
    logger.warning("[AzureDefender] azure-mgmt-security not installed — Azure Defender ingest disabled")

async def poll_azure_defender_alerts(config: Dict[str, Any], omni_tenant_id: str) -> int:
    if not _AZURE_SDK_AVAILABLE:
        return 0
    # ... build client, call real API, map + insert into db.security_events, return len(events)
    # ... except Exception: logger.error(...); return 0
```

**Wiring point in `cloud_integrations_endpoints.py`** (both `test_integration()` and `trigger_cloud_discovery()` need the new branches — this is the same "widen every gate in lockstep" lesson Phase 25 already learned for `cloud_checks_service.py`'s 4 gates):
```python
# test_integration(): add alongside the existing azure_defender/gcp_scc branches
elif provider == "oci_cloud_guard":
    from oci_ingest import poll_oci_cloud_guard_problems
    count = await poll_oci_cloud_guard_problems(config, integ.get("tenant_id", ""))
elif provider == "alibaba_sas":
    from alibaba_ingest import poll_alibaba_sas_alerts
    count = await poll_alibaba_sas_alerts(config, integ.get("tenant_id", ""))
elif provider == "cloudflare_zero_trust":
    from cloudflare_ingest import poll_cloudflare_zero_trust_events
    count = await poll_cloudflare_zero_trust_events(config, integ.get("tenant_id", ""))
```

**Note on `aws_guardduty`/`aws_securityhub` (explicitly `count = 0` in the current code, not in PROV-01's scope but visible in the same dispatch block):** these are *not* named in PROV-01's requirement text — leave them as-is unless the planner deliberately expands scope; don't silently "fix" them as a drive-by.

### Pattern 2: New Provider Check-Catalog (PROV-02 — mirrors `cloud_checks_k8s.py`/DO_CHECKS exactly, per-Phase-25 4-gate widening)

**What:** `CLOUD_CHECKS` is a flat concatenation of per-provider lists (`AWS_CHECKS + AZURE_CHECKS + GCP_CHECKS + K8S_CHECKS + DO_CHECKS`), each entry a dict with `id`/`name`/`description`/`provider`/`service`/`severity`/`frameworks`/`remediation`. Adding M365 and MongoDB Atlas means two new files (`cloud_checks_m365.py`, `cloud_checks_mongodb_atlas.py`) with the same dict shape and `provider: "microsoft365"` / `provider: "mongodb_atlas"`, imported into `cloud_checks_service.py` and appended to `CLOUD_CHECKS`, then **all four gates from Phase 25's Pattern 1 widened again**: `RUNNABLE_PROVIDERS` tuple (execution), `cloud_checks_endpoints.py`'s inline tuple (direct-run), `cloud_account_endpoints.py`'s `_VALID_PROVIDERS` set (registration), `mcp_server_endpoints.py`'s tuple (MCP tool).

**Recommended M365 check topics** (based on Microsoft Graph Security API's `secureScoreControlProfiles` categories, `[ASSUMED — WebSearch-sourced control-name knowledge, not independently fetched from Graph API docs this session]`): MFA enforcement for admins, Conditional Access policy coverage, mailbox audit logging enabled, external sharing restrictions in SharePoint/OneDrive, legacy authentication protocols blocked, Secure Score baseline threshold.

**Recommended MongoDB Atlas check topics** (based on Atlas Admin API's project/cluster settings surface `[ASSUMED — WebSearch-sourced, not independently fetched from Atlas API docs this session]`): network access list has no `0.0.0.0/0` entry, cluster encryption-at-rest enabled, database auditing enabled, IP access list / VPC peering configured instead of public access, database user roles follow least-privilege (no built-in `atlasAdmin` on service accounts), backup/PITR enabled.

**Critical caveat carried over from the diagram above:** because `db.cloud_findings` is never populated by any writer in this codebase, these new checks — like every existing AWS/Azure/GCP/K8s/DO check — will evaluate to `PASS` for every account, always, until a real findings-ingestion pipeline exists. This is **consistent with existing behavior**, not a regression introduced by this phase, but the planner should decide whether to (a) ship the catalog-only extension consistent with the existing (pre-existing-gap) pattern, matching the phrase "scanned providers" literally, or (b) flag this as something the phase should also partially address (e.g., have `test_integration()`/`trigger_cloud_discovery()`-style calls from Pattern 1, if M365/MongoDB Atlas *also* get a `cloud_integrations_endpoints.py` entry, actually populate `cloud_findings` for these two providers specifically as a small worked example). See Open Questions.

### Pattern 3: SaaS Posture-Check Layer Over Existing Real Pulls (PROV-03)

**What:** `saas_integration_service.py`'s `pull_*_evidence()` functions already return a list of dicts shaped `{"control_id", "source", "tenant_id", "collected_at", "content", "status": "pass"|"fail"|"no-data"}` from **real** API calls. A new `saas_posture_checks_service.py` should define a small check catalog per provider (mirroring `CLOUD_CHECKS`'s dict shape: `id`, `name`, `severity`, `remediation`, `frameworks`) and a `run_posture_checks(connection, db)` function that calls the *same* `pull_*_evidence()` functions (no duplicate API calls — reuse, don't re-fetch), and maps each evidence item's existing `status` field onto the matching catalog check's `PASS`/`FAIL`, writing to a new `saas_check_results` collection shaped like `cloud_check_results` (`id`, `tenantId`, `connectionId`, `provider`, `checkId`, `checkName`, `service`, `severity`, `result`, `frameworks`, `remediation`, `detail`, `checked_at`).

**Example mapping (GitHub, using data already fetched by `pull_github_evidence`):**
```python
# Source: derived from backend/saas_integration_service.py's existing pull_github_evidence() shape
GITHUB_POSTURE_CHECKS = [
    {"id": "gh-branch-protection", "name": "Main Branch Protection Enabled", "severity": "high",
     "service": "repository", "frameworks": ["SOC2-CC8.1"], "remediation": "Enable required status checks and enforce_admins on the main branch.",
     "_evidence_control_id": "Access to Source Code Simulation"},  # maps to the control_id pull_github_evidence already emits
    {"id": "gh-code-scanning-clean", "name": "No Open Critical Code Scanning Alerts", "severity": "critical",
     "service": "repository", "frameworks": ["OWASP-ASVS-V14"], "remediation": "Triage and remediate open critical GitHub code scanning alerts.",
     "_evidence_control_id": "Security Patch Status"},
]

async def run_posture_checks(connection: dict, db) -> dict:
    evidence = await saas_integration_service.pull_all_evidence(connection, db)  # reuse — real API calls already made
    ev_by_control = {e["control_id"]: e for e in evidence}
    results = []
    for check in GITHUB_POSTURE_CHECKS:  # dispatch by connection["provider"] to the right catalog
        ev = ev_by_control.get(check["_evidence_control_id"])
        result = "PASS" if ev and ev.get("status") == "pass" else ("FAIL" if ev else "NO-DATA")
        results.append({...})  # id/severity/remediation/result/checked_at, upsert into db.saas_check_results
    return {"ran": len(results), "connectionId": connection["id"]}
```

**Why this is not hand-rolling a new integration:** every HTTP call PROV-03 needs already exists and already runs in production (Phase 14, shipped, 10/10 tests passing). This pattern only adds a re-shaping/labeling layer, following the exact same "catalog of named checks with severity+remediation" contract as `CLOUD_CHECKS`.

### Pattern 4: Wire Dead-Code `AttackPathService` Into the Registered Endpoint (PROV-04)

**What:** `attack_path_endpoints.py`'s `get_attack_paths()` handler must call `attack_path_service.get_attack_path_service(db).get_attack_paths(tenant_id)` instead of its own inline seed-first logic. `AttackPathService.get_attack_paths()` already implements the "prefer real findings" behavior PROV-04 asks for (checks `attack_paths` collection, then correlates `db.assets` × `db.vulnerabilities`/`db.cspm_findings`, and *only* falls back to `_seed_demo_paths()` when genuinely no asset/vuln data exists).

```python
# Source: backend/attack_path_endpoints.py — CURRENT (buggy) handler, to be replaced
@router.get("/attack-paths")
async def get_attack_paths(current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    db = get_database()
    stored = await db.attack_paths.find({"tenantId": tenant_id}, {"_id": 0}).sort("timestamp", -1).to_list(length=50)
    if stored:
        return stored
    paths = _seed_paths(tenant_id)   # <-- never tries real correlation; delete this whole duplicate function
    ...
    return paths

# RECOMMENDED replacement:
from attack_path_service import get_attack_path_service
@router.get("/attack-paths")
async def get_attack_paths(current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    db = get_database()
    service = get_attack_path_service(db)
    paths = await service.get_attack_paths(tenant_id)
    return paths
```

**The `simulated` flag (matching Phase 25's CHK-03 precedent exactly):** `AttackPathService._seed_demo_paths()` and the real-correlation branch both need an explicit `"simulated": True`/`"simulated": False` field added to each path dict, so the frontend can render the same kind of prominent badge Phase 25 added for container scans.

**The edge-field mismatch (found independently while reading this code — must be fixed for PROV-04 to be meaningfully "real", otherwise the label is invisible either way):**
```typescript
// Source: types.ts:1273-1277 — frontend expects:
export interface AttackPathEdge { from: string; to: string; label: string; }
```
```python
# Source: backend/attack_path_service.py:112-115 and attack_path_endpoints.py:54-57 — backend emits:
"edges": [{"source": node_e["id"], "target": node_h["id"], "vulnerability": entry_cve}, ...]
```
`AttackPathDashboard.tsx:82` does `(displayPath.edges || []).find(e => e.from === node.id)?.label` — this **always** returns `undefined` today because the field names never match on either side. Pick one contract and make both sides match it (recommend keeping the backend's `source`/`target`/`vulnerability` naming, since it's more semantically precise for a graph edge, and updating both `types.ts` and `AttackPathDashboard.tsx` to match — changing the backend risks missing a caller; changing the frontend is a two-file, well-contained fix).

### Anti-Patterns to Avoid
- **Building live SDK polling for M365/MongoDB Atlas as "scanned providers" (PROV-02) when the existing AWS/Azure/GCP precedent is catalog-matching against an empty collection:** this would make M365/MongoDB Atlas *more* real than every existing "runnable" provider, an inconsistency, not a fix — unless the planner explicitly decides (per Open Questions) to also seed `cloud_findings` for these two as a worked example.
- **Adding PROV-03 posture-check logic inline to `saas_integration_service.py`:** the file is already at exactly 500 lines — this will silently violate CLAUDE.md's 500-line rule.
- **Re-fetching from GitHub/Okta/GWS/Slack/Jira APIs a second time for posture checks instead of reusing `pull_*_evidence()`'s already-fetched data:** doubles API call volume/rate-limit risk for zero benefit — the evidence-pull functions already compute pass/fail per item.
- **Confusing `cloud_integrations_endpoints.py` (PROV-01's target) with `cloud_account_endpoints.py`/`cloud_checks_service.py` (PROV-02's target) or `connectors_hub_endpoints.py` (an entirely separate, fully-mocked SIEM-connector catalog not in scope for any PROV-* requirement — its `sync_connector()` uses `random.randint()` for a fake record count and its "Microsoft 365" catalog entry is unrelated to PROV-02):** three different "provider list" surfaces exist in this codebase; grep for the literal file name before editing, per the Phase 25 four-gate lesson.
- **Fixing only one side of the `AttackPathEdge` field-name mismatch:** changing only the backend or only the frontend still leaves edge labels broken.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OCI API request signing (RSA-SHA256 canonical-string signing) | A custom OCI request-signer | The official `oci` SDK | OCI's signing scheme is genuinely intricate (canonical header ordering, body-hash inclusion rules) — this is exactly the kind of "deceptively complex" problem a vendor SDK exists to solve |
| MongoDB Atlas HTTP Digest authentication | A hand-rolled RFC 7616 digest-auth implementation | `requests.auth.HTTPDigestAuth` (already-pinned `requests` dependency) | Digest auth's nonce/cnonce/qop handshake is easy to get subtly wrong (replay/nonce-reuse bugs); `requests` has shipped a battle-tested implementation for over a decade — zero reason to reimplement it |
| Re-deriving pass/fail security posture from raw GitHub/Okta/GWS/Slack API responses | A parallel, duplicate set of API-parsing logic in the new posture-checks file | The `status` field `saas_integration_service.py`'s `pull_*_evidence()` functions already compute | The parsing/pass-fail logic already exists, is already tested (10/10 in `test_saas_integration.py`), and duplicating it creates two sources of truth for "is this GitHub repo's branch protection on" |
| Attack-path exploit-chain correlation (assets × vulnerabilities → paths) | A new correlation algorithm | `AttackPathService.get_attack_paths()` — already written, just disconnected | This is the single clearest "don't hand-roll, don't even re-plan, just wire it up" finding in this research — the code exists and has never been called |

**Key insight:** Two of this phase's four requirements (PROV-03, PROV-04) are substantially "reuse code that already does the real work but isn't wired up or isn't structured as a checks-catalog" rather than "build new integrations." Only PROV-01 (OCI/Alibaba/Cloudflare) is genuinely new external-API integration work, and PROV-02 (M365/MongoDB Atlas) is a catalog extension inheriting a pre-existing (not-this-phase's-fault) data gap.

## Common Pitfalls

### Pitfall 1: Believing PROV-02 requires live SDK polling because PROV-01 does
**What goes wrong:** A planner sees "OCI/Alibaba/Cloudflare need real polling" (PROV-01) right next to "M365/MongoDB Atlas need to be scanned providers" (PROV-02) and assumes both need the same live-SDK-polling treatment, ballooning PROV-02 into 2 more full SDK integrations plus a new `cloud_findings`-writing pipeline that doesn't exist for *any* existing provider today.
**Why it happens:** The two requirements sit next to each other in the roadmap and both use provider-integration language, but they target two architecturally different subsystems (see Summary).
**How to avoid:** Confirm which of the three provider surfaces (`cloud_integrations_endpoints.py` vs. `cloud_checks_service.py` vs. `connectors_hub_endpoints.py`) each requirement's language matches before scoping tasks — "polls for findings"/"store connection config" = subsystem 1 (PROV-01); "scanned providers" = subsystem 2, following the Phase 25 `RUNNABLE_PROVIDERS` widening pattern (PROV-02).
**Warning signs:** A plan for PROV-02 includes new `requirements.txt` entries for a Graph/Atlas *ingest* SDK beyond what's needed for the check catalog itself, or proposes writing to `db.cloud_findings` for M365/MongoDB Atlas specifically while every other provider still doesn't.

### Pitfall 2: Adding PROV-03 logic inline and silently breaching the 500-line CLAUDE.md limit
**What goes wrong:** `saas_integration_service.py` is **exactly** 500 lines today (confirmed via `wc -l`). Any inline addition — even one line — breaches the constraint.
**Why it happens:** PROV-03 conceptually "belongs" in the SaaS integration file since it reuses that file's functions, making inline placement feel natural.
**How to avoid:** New file `saas_posture_checks_service.py`, importing `saas_integration_service` rather than extending it — same pattern `compliance_evidence_lifecycle_endpoints.py`/`compliance_bulk_evidence_endpoints.py` used historically in this codebase when a host file was at/near its limit (see STATE.md decisions for 07-02, 08-01).
**Warning signs:** `wc -l backend/saas_integration_service.py` returns >500 after a task claims to be complete.

### Pitfall 3: Fixing the dead-code wiring but not the edge-field mismatch (or vice versa)
**What goes wrong:** PROV-04 is verified "done" because `attack_path_endpoints.py` now calls the real service and a `simulated` badge appears — but the edge labels between nodes (the CVE/lateral-movement text) still never render, because `AttackPathDashboard.tsx`'s `e.from`/`e.label` lookup still doesn't match the backend's `source`/`vulnerability` field names. This bug pre-dates this phase and is independent of the demo-fallback issue, but a UAT reviewer will likely notice missing edge labels and (correctly) flag it as incomplete.
**Why it happens:** The two bugs live in different files and were introduced independently; PROV-04's requirement text only mentions "prefers real findings" and "labels the fallback," not edge rendering, so it's easy to miss during scoping.
**How to avoid:** Read `types.ts`'s `AttackPathEdge` interface and `AttackPathDashboard.tsx`'s edge-lookup line side-by-side with the backend's edge-dict construction before considering PROV-04 done; fix both.
**Warning signs:** Manually testing the Attack Path dashboard shows node cards but no text on the connecting lines between them.

### Pitfall 4: New provider credentials not following the existing encryption pattern for their target file
**What goes wrong:** This codebase has **three independent Fernet encryption setups** for provider credentials, each with a different env var name and different production-vs-dev fallback behavior: `cloud_accounts_service.py` (`CLOUD_CREDENTIALS_KEY`, hard-fails in production if unset), `saas_integration_service.py` (`ENCRYPTION_KEY`, warns + generates ephemeral key in dev), `cloud_integrations_endpoints.py` (`INTEGRATION_ENCRYPTION_KEY`, warns + stores unencrypted if unset in dev, hard-fails in production). Adding OCI/Alibaba/Cloudflare config to the wrong encryption scheme, or inventing a fourth, fragments credential-handling further.
**Why it happens:** Three legitimate historical reasons (Phase 14, Phase 20, and whenever `cloud_integrations_endpoints.py` was added) produced three parallel patterns; nothing currently unifies them.
**How to avoid:** OCI/Alibaba/Cloudflare integration config belongs in `cloud_integrations_endpoints.py`'s existing `SUPPORTED_PROVIDERS`/`_encrypt_secrets`/`_SECRET_FIELDS` machinery (just add the 3 providers' credential field names — e.g., `oci_private_key` — to `_SECRET_FIELDS` if not already covered by the existing `client_secret`/`service_account_json`/`aws_secret_key` set; check whether OCI's `oci_private_key` needs adding). Do not introduce a fourth encryption scheme.
**Warning signs:** A new `Fernet(...)` instantiation appears anywhere in a new file this phase adds.

### Pitfall 5: `azure-mgmt-security` is not actually installed — the "working" PROV-01 precedent is itself currently non-functional
**What goes wrong:** This research cites `azure_defender_ingest.py`'s real-SDK pattern as the model to replicate, but `azure-mgmt-security` (needed for `poll_azure_defender_alerts`) is **not present in `requirements.txt` and not importable in the current venv** (`ModuleNotFoundError` confirmed this session). So the "already working" precedent actually silently no-ops today too (`_AZURE_SDK_AVAILABLE = False` → every poll returns 0) — it just no-ops via the intentional graceful-fallback path rather than the unimplemented-stub path PROV-01 fixes for OCI/Alibaba/Cloudflare.
**Why it happens:** `azure-mgmt-security` was presumably intended to ship with this feature but never got added to `requirements.txt`.
**How to avoid:** Not a blocker for this phase's explicit scope (Azure Defender isn't a PROV-01 target), but worth a one-line flag in the PLAN — and if the planner wants a truly working demo/manual-test path for *any* of the polling providers, they may need to `pip install azure-mgmt-security` too, not just the 3 new SDKs.
**Warning signs:** Manually testing Azure Defender's "Test Connection" button after this phase still silently returns `events_ingested: 0` even with valid-looking credentials.

## Code Examples

### Existing "real poll, graceful degrade" pattern to replicate (verbatim reference)
```python
# Source: backend/azure_defender_ingest.py:91-131
async def poll_azure_defender_alerts(config: Dict[str, Any], omni_tenant_id: str) -> int:
    if not _AZURE_SDK_AVAILABLE:
        logger.debug("[AzureDefender] SDK unavailable, skipping poll")
        return 0
    az_tenant = config.get("azure_tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    subscription_id = config.get("subscription_id", "")
    if not all([az_tenant, client_id, client_secret, subscription_id]):
        logger.warning("[AzureDefender] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0
    try:
        client, sub_id = _make_azure_client(az_tenant, client_id, client_secret, subscription_id)
        if not client:
            return 0
        alerts = list(client.alerts.list())
        if not alerts:
            return 0
        set_tenant_id(omni_tenant_id)
        db = get_database()
        events = [_parse_defender_alert(a, omni_tenant_id) for a in alerts]
        if events:
            await db.security_events.insert_many(events)
        return len(events)
    except Exception as exc:
        logger.error("[AzureDefender] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0
```

### Existing "real API + pass/fail evidence" pattern to reuse for PROV-03 (verbatim reference)
```python
# Source: backend/saas_integration_service.py:189-220 (pull_github_evidence, excerpt)
bp_data = bp_resp.json()
bp_enabled = bool(bp_data.get("required_status_checks") or bp_data.get("enforce_admins"))
evidence.append({
    "control_id": _CTRL_SOURCE_CODE,
    "source": "saas-github",
    "tenant_id": tenant_id,
    "collected_at": collected_at,
    "content": f"GitHub: Branch protection on main: {bp_enabled}",
    "status": "pass" if bp_enabled else "fail",
})
```

### MongoDB Atlas digest-auth call pattern (no new dependency)
```python
# Illustrative — uses already-pinned `requests`, wrapped for the codebase's async convention
import asyncio
import requests
from requests.auth import HTTPDigestAuth

def _atlas_get_sync(url: str, public_key: str, private_key: str) -> dict:
    resp = requests.get(url, auth=HTTPDigestAuth(public_key, private_key), timeout=10)
    resp.raise_for_status()
    return resp.json()

async def poll_mongodb_atlas_findings(config: dict, tenant_id: str) -> int:
    public_key = config.get("atlas_public_key", "")
    private_key = config.get("atlas_private_key", "")
    project_id = config.get("atlas_project_id", "")
    if not all([public_key, private_key, project_id]):
        return 0
    try:
        data = await asyncio.to_thread(
            _atlas_get_sync,
            f"https://cloud.mongodb.com/api/atlas/v2/groups/{project_id}/clusters",
            public_key, private_key,
        )
        # ... map cluster settings to check results, upsert into db.cloud_check_results ...
        return len(data.get("results", []))
    except Exception:
        return 0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `cloud_integrations_endpoints.py`'s OCI/Alibaba/Cloudflare providers store config only, `test_integration()` returns `count=0` with no real call | Real ingest modules mirroring the existing Azure Defender/GCP SCC pattern | This phase (32) | Closes the specific gap the 2026-07-06 feature-parity audit flagged vs. Prowler's provider breadth |
| Attack path dashboard always shows the same 3 hardcoded demo scenarios (`_seed_paths()` runs first, unconditionally, on empty `attack_paths` collection) | Real asset×vulnerability correlation (`AttackPathService`) preferred, demo-seed only as genuine last resort, both paths labeled `simulated: true/false` | This phase (32) | Fixes a dead-code bug that has existed since `AttackPathService` was written but never wired to the registered route |
| SaaS OAuth providers (GitHub/Jira/Okta/GWS/Slack) support evidence-pull only — free-text `control_evidence` rows | Same real API calls also produce a discrete, severity-rated posture-check catalog result | This phase (32) | Brings SaaS providers to structural parity with the `CLOUD_CHECKS`/`IAC_CHECKS` catalog contract used everywhere else |

**Deprecated/outdated:** MongoDB's legacy API-key digest-auth method for the Atlas Admin API is not deprecated but MongoDB's own docs now steer new integrations toward Service Accounts (OAuth2 client-credentials) `[CITED via WebSearch summary]` — noted as a future hardening option, not required for this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `oci`, `aliyun-python-sdk-core-v3`, and `cloudflare` are the correct current official PyPI package names for OCI/Alibaba/Cloudflare Python access | Standard Stack, Package Legitimacy Audit | Low — cross-checked against live PyPI registry via `pip index versions` this session (all three resolve with long version histories); WebSearch-sourced package-name discovery still requires the `[ASSUMED]` tag per the package-name-provenance rule regardless of registry confirmation |
| A2 | `requests.auth.HTTPDigestAuth` correctly implements the digest scheme MongoDB Atlas Admin API requires, with no codebase-specific quirks | Standard Stack, Code Examples | Low-medium — this is training-knowledge, not independently verified against a live Atlas API call this session; if wrong, the fallback is the `httpx-auth` package (also viable, flagged SUS in the legitimacy audit) or a bespoke digest implementation |
| A3 | PROV-01's "real polling" and PROV-02's "scanned providers" target two different subsystems (`cloud_integrations_endpoints.py` vs. `cloud_checks_service.py`) rather than one unified system | Summary, Architecture Patterns 1 & 2 | **High impact if wrong** — this is the central scope-resolving claim of this research. It is backed by direct-read evidence (exact phrase matches, working real-poll precedent only existing in `cloud_integrations_endpoints.py`, "scanned providers" terminology matching Phase 20's naming for the other subsystem) but the requirement text itself doesn't name files, so it is ultimately an interpretation. Flagged explicitly in Open Questions for planner/user confirmation. |
| A4 | Recommended M365 and MongoDB Atlas check topics (MFA, Conditional Access, network access lists, encryption-at-rest, etc.) are representative of what "posture checks" for these providers should cover | Architecture Patterns — Pattern 2 | Low — these are illustrative starter checks based on general knowledge of each platform's security-configuration surface, not fetched from an authoritative source this session; the planner should treat the exact check list as a starting point, not a verified-complete set |
| A5 | Keeping the backend's `source`/`target`/`vulnerability` edge-field naming and updating the frontend (`types.ts` + `AttackPathDashboard.tsx`) to match is the lower-risk fix direction, vs. changing the backend to `from`/`to`/`label` | Architecture Patterns — Pattern 4 | Low — either direction fixes the bug; recommendation is based on "the backend has 2 call sites (real + demo) vs. the frontend's 1 render site," making the frontend the smaller edit, not a technical requirement |

**If this table is empty:** N/A — see rows above.

## Open Questions (RESOLVED)

1. **Is `cloud_integrations_endpoints.py` really PROV-01's sole intended target, or should `cloud_account_endpoints.py`'s `_VALID_PROVIDERS` (and the `AddCloudAccountModal.tsx` frontend, which already offers OCI/Alibaba/Cloudflare as options that 400 today) also be widened?** (RESOLVED)
   - What we know: The phase description's exact phrase "only store connection config with no real polling" matches `cloud_integrations_endpoints.py`'s behavior precisely (confirmed by direct read of `create_integration()`/`test_integration()`). Separately, `AddCloudAccountModal.tsx` (a *different* frontend surface, feeding `cloud_account_endpoints.py`) already lists OCI/Alibaba/Cloudflare as selectable providers, but that endpoint's `_VALID_PROVIDERS` set doesn't include them — so submitting that form for those three providers 400s today, an independent pre-existing bug.
   - **RESOLVED: PROV-01's primary target is `cloud_integrations_endpoints.py` (exact language match), AND the `cloud_account_endpoints.py` `_VALID_PROVIDERS` 400-on-submit bug is folded in as a small lockstep fix** — this follows Phase 25's recorded Key Decision (PROJECT.md: "provider-allowlist lockstep widening"), where exactly this class of allowlist mismatch was fixed across `cloud_account_endpoints.py`/`cloud_checks_endpoints.py`/`mcp_server_endpoints.py` in lockstep. Leaving a UI that 400s on submit for providers this same phase is making pollable would be an obvious inconsistency.

2. **Should PROV-02's M365/MongoDB Atlas check catalogs also get a `cloud_findings`-populating ingest path (breaking the "every check always PASSes" precedent), given this phase is already building real-poll ingest infrastructure for PROV-01 that could plausibly be reused?** (RESOLVED)
   - What we know: `cloud_findings` is never written by any code path today, for any provider. PROV-01 is, coincidentally, building exactly the kind of real-poll ingest machinery that *could* populate it for M365 (via Graph Security API's `secureScores`) and MongoDB Atlas (via the Admin API), if the planner wanted PROV-02 to be more than catalog-only.
   - **RESOLVED (user-confirmed via AskUserQuestion, 2026-07-08): Real findings ingestion.** M365 (Microsoft Graph secureScores, auth via the already-resolvable `msal`) and MongoDB Atlas (Admin API via `requests.auth.HTTPDigestAuth`, zero new dependencies) become the FIRST providers whose checks evaluate against real polled findings written to `cloud_findings`, reusing the real-poll ingest machinery PROV-01 builds. This deliberately breaks the "always PASS against an empty collection" precedent — the plan must ensure checks for providers WITHOUT ingested findings still behave sanely (i.e., the existing catalog-only providers keep their current behavior unchanged; no regression), and results sourced from real findings should be distinguishable from catalog-only evaluations (extend the Phase 25 `simulated`-flag labeling convention: catalog-only evaluations against an empty findings set are the "simulated"-equivalent case).

3. **For PROV-04's edge-field-name fix, is there any other frontend consumer of `AttackPathEdge` besides `AttackPathDashboard.tsx` that would need updating too?** (RESOLVED)
   - What we know: `AttackPathDashboard.tsx` is the only `.tsx` file (outside stale `.claude/worktrees/` snapshots, which are not live code) that references `AttackPath`/edge fields, per this session's grep.
   - **RESOLVED: adopting the recommendation** — proceed with the fix; include a final grep for `AttackPathEdge`/`\.edges\b` in the task's verify step as cheap insurance.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `oci` (Oracle SDK) | PROV-01 (OCI polling) | ✗ (not installed in venv) | — | None — must `pip install`; no viable httpx-only substitute given OCI's signing complexity (see Alternatives Considered) |
| `aliyun-python-sdk-core-v3` | PROV-01 (Alibaba polling) | ✗ | — | Raw httpx against Alibaba's REST API is a viable fallback if the planner prefers avoiding the dependency |
| `cloudflare` (official client) | PROV-01 (Cloudflare polling) | ✗ | — | Raw httpx against Cloudflare's REST API (simple bearer-token auth) is a fully viable, lower-dependency fallback |
| `msal` | PROV-02 (M365 Graph auth) | ✓ (transitively, via `azure-identity`) | 1.37.0 | None needed — already resolvable; just needs an explicit `requirements.txt` line |
| `azure-mgmt-security` | Pre-existing Azure Defender polling (not a PROV-* target, but the cited precedent pattern) | ✗ | — | Not this phase's responsibility to fix, but the planner should be aware the "working" precedent is itself currently silently degraded |

**Missing dependencies with no fallback:**
- `oci` — must be installed for PROV-01's OCI branch to do anything beyond the current no-op.

**Missing dependencies with fallback:**
- `aliyun-python-sdk-core-v3`, `cloudflare` — SDK or raw-httpx are both viable; planner's choice.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`pytest.ini` at repo root: `testpaths = . backend`, `asyncio_mode = auto`) |
| Config file | `/home/user/enterprise-omni-agent-ai-platform/pytest.ini` |
| Quick run command | `cd backend && python -m pytest tests/test_cloud_integrations.py tests/test_cloud_checks_expansion.py tests/test_saas_posture_checks.py tests/test_attack_path.py -v` |
| Full suite command | `cd backend && python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROV-01 | `test_integration()` for `oci_cloud_guard`/`alibaba_sas`/`cloudflare_zero_trust` calls a real (mocked-in-test) SDK client and returns a non-zero-when-mocked-successful count | unit | `pytest backend/tests/test_cloud_integrations.py::test_oci_poll_ingests_findings -x` | ❌ Wave 0 — **no test file exists at all today for `cloud_integrations_endpoints.py`**, a pre-existing coverage gap this phase should close |
| PROV-02 | `run_checks()` evaluates M365/MongoDB Atlas checks when `provider` is one of the two new values; all 4 gates accept the new providers | unit | `pytest backend/tests/test_cloud_checks_expansion.py::test_run_checks_evaluates_microsoft365 -x` | ❌ Wave 0 (extend existing file from Phase 25) |
| PROV-03 | `run_posture_checks()` for a GitHub connection reuses `pull_github_evidence`'s mocked HTTP response and writes correctly-shaped PASS/FAIL results to `saas_check_results` | unit | `pytest backend/tests/test_saas_posture_checks.py::test_github_posture_checks_from_evidence -x` | ❌ Wave 0 |
| PROV-04 | `GET /api/security/attack-paths` returns real correlated paths (not seed data) when `db.assets`/`db.vulnerabilities` have data, and returns `simulated: true` paths only when both are empty | integration | `pytest backend/tests/test_attack_path.py::test_attack_paths_prefers_real_correlation -x` | ❌ Wave 0 — **no test file exists at all today for either `attack_path_service.py` or `attack_path_endpoints.py`** |
| PROV-04 | Edge dicts returned by the API have fields matching whatever `AttackPathEdge` is updated to expect (source/target/vulnerability or from/to/label — whichever direction the planner picks) | unit | `pytest backend/tests/test_attack_path.py::test_edge_field_contract -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_cloud_integrations.py tests/test_cloud_checks_expansion.py tests/test_saas_posture_checks.py tests/test_attack_path.py tests/test_cloud_accounts.py -v`
- **Per wave merge:** `cd backend && python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_cloud_integrations.py` — does not exist; needed for PROV-01 (this is also a pre-existing Phase-unknown test-coverage gap — `cloud_integrations_endpoints.py` has zero dedicated tests today despite being a 481-line file with encryption, RBAC, and 11 providers)
- [ ] `backend/tests/test_attack_path.py` — does not exist; needed for PROV-04 (same gap for `attack_path_service.py`/`attack_path_endpoints.py`)
- [ ] `backend/tests/test_saas_posture_checks.py` — new file, needed for PROV-03
- [ ] Extend `backend/tests/test_cloud_checks_expansion.py` (exists from Phase 25) with PROV-02 cases
- [ ] Framework install: `pip install oci aliyun-python-sdk-core-v3 cloudflare msal` — required before PROV-01 unit tests can mock/import the new ingest modules' SDK-availability guards

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | Unchanged — all touched endpoints already require `get_current_user`/RBAC dependencies |
| V3 Session Management | no | Not touched by this phase |
| V4 Access Control | yes | `cloud_integrations_endpoints.py`'s existing tenant-scoping (`tenant_id`/role checks) must be preserved unchanged when adding 3 new providers; new `saas_check_results`/attack-path queries must tenant-scope identically to the collections they're modeled on (`cloud_check_results`, `control_evidence`) |
| V5 Input Validation | yes | New provider config fields (OCI OCID format, Alibaba access keys, Cloudflare tokens, MongoDB Atlas project ID) need the same `required_fields`-presence validation `cloud_integrations_endpoints.py` already applies to its other 9 providers — don't skip validation for the 3 new ones |
| V6 Cryptography | yes | New provider credentials (OCI private key, Alibaba access key secret, Cloudflare API token, MongoDB Atlas private key) MUST go through `cloud_integrations_endpoints.py`'s existing `_encrypt_secrets`/`_SECRET_FIELDS` Fernet pattern — add each new secret field name to `_SECRET_FIELDS` (currently `{"client_secret", "service_account_json", "aws_secret_key"}`), do not store any of them in plaintext, and do not introduce a 4th independent encryption scheme (see Common Pitfalls 4) |

### Known Threat Patterns for Multi-Provider Credential Storage & Polling

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| A new provider's secret field name (e.g., `oci_private_key`) is added to `required_fields` but forgotten from `_SECRET_FIELDS`, causing it to be stored plaintext in `db.cloud_integrations` and returned unmasked by `list_integrations()`'s `_mask_secrets()` | Information Disclosure | Cross-check every new required credential field against `_SECRET_FIELDS`/`_mask_secrets()`'s hardcoded key sets before considering a new provider "done" — this is an easy one-line omission with a real credential-leak consequence |
| A malformed/malicious OCI/Alibaba/Cloudflare API response (attacker-controlled if credentials are somehow scoped too broadly, or via a compromised upstream) is parsed and inserted into `db.security_events` without size/shape bounds | Tampering / Denial of Service | Mirror `azure_defender_ingest.py`'s existing pattern — wrap the whole parse-and-insert in `try/except Exception: return 0`, never let a malformed response propagate an exception past the poll function |
| Presenting attack-path demo-seed scenarios as real findings (compliance-integrity risk, same category as Phase 25's CHK-03 simulated-CVE finding) | Spoofing (of finding authenticity) | Explicit `simulated: true` field on every attack-path dict + prominent UI labeling, exactly mirroring the Phase 25 CHK-03 precedent |
| SaaS posture-check results (PROV-03) silently diverge from the evidence-pull `status` they're derived from (e.g., a bug maps a `"fail"` evidence item to a `"PASS"` check result) | Tampering (of compliance signal integrity) | `run_posture_checks()` should be pure re-shaping of `pull_*_evidence()`'s already-computed `status` field — add a unit test asserting `evidence.status == "fail"` always yields `check.result == "FAIL"` for every mapped check, not independent re-derivation logic |

## Sources

### Primary (HIGH confidence)
- Direct codebase reads: `backend/cloud_checks_service.py`, `backend/cloud_account_endpoints.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_accounts_service.py`, `backend/cloud_integrations_endpoints.py`, `backend/connectors_hub_endpoints.py`, `backend/azure_defender_ingest.py`, `backend/gcp_scc_ingest.py`, `backend/saas_integration_service.py`, `backend/attack_path_service.py`, `backend/attack_path_endpoints.py`, `backend/router_registry.py`, `backend/requirements.txt`, `components/AttackPathDashboard.tsx`, `components/AddCloudAccountModal.tsx`, `types.ts`, `backend/tests/test_cloud_checks_expansion.py`, `.planning/phases/25-cloud-checks-execution-gaps/25-RESEARCH.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md` — all read in full this session, `[VERIFIED: codebase grep + direct read]`
- `pip index versions oci/aliyun-python-sdk-core-v3/cloudflare/httpx-auth/pymongo` against the live PyPI registry — `[VERIFIED: package registry, this session]`
- `pip show msal` in the project venv — `[VERIFIED: local environment inspection, this session]`
- `python -c "import oci/cloudflare/aliyunsdkcore/msgraph/azure.mgmt.security"` import-availability checks in the project venv — `[VERIFIED: local environment inspection, this session]`
- `gsd-tools query package-legitimacy check` seam output for `oci`, `aliyun-python-sdk-core-v3`, `cloudflare`, `httpx-auth` — `[VERIFIED: tool output, this session]`

### Secondary (MEDIUM confidence)
- [oci · PyPI](https://pypi.org/project/oci/) `[ASSUMED — WebSearch, cross-checked against PyPI registry directly]`
- [Oracle Cloud Infrastructure SDK for Python — GitHub](https://github.com/oracle/oci-python-sdk) `[ASSUMED — WebSearch]`
- [aliyun-python-sdk-core-v3 · PyPI](https://pypi.org/project/aliyun-python-sdk-core-v3/) `[ASSUMED — WebSearch, cross-checked against PyPI registry directly]`
- [Cloudflare Python API library — PyPI](https://pypi.org/project/cloudflare/) `[ASSUMED — WebSearch, cross-checked against PyPI registry directly]`
- [Atlas Administration API Authentication Methods — MongoDB Docs](https://www.mongodb.com/docs/atlas/api/api-authentication/) `[ASSUMED — WebSearch summary, not independently fetched]`
- [Get secureScore — Microsoft Graph v1.0](https://learn.microsoft.com/en-us/graph/api/securescore-get?view=graph-rest-1.0) `[ASSUMED — WebSearch summary, not independently fetched]`
- [SecurityEvents.Read.All — Graph Permissions](https://graphpermissions.merill.net/permission/SecurityEvents.Read.All) `[ASSUMED — WebSearch summary, not independently fetched]`

### Tertiary (LOW confidence)
- Illustrative M365/MongoDB Atlas check-topic lists in Architecture Patterns — Pattern 2 (based on general platform-security knowledge, not fetched from an authoritative source this session; flagged in Assumptions Log as A4)

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — new-provider SDK package names are WebSearch-sourced (tagged `[ASSUMED]` per provenance rule) though cross-checked against the live PyPI registry; the codebase's existing dependency findings (`msal` transitive, `azure-mgmt-security` missing) are HIGH (directly verified in this session's venv)
- Architecture: HIGH — the three-subsystem mapping, the dead-`AttackPathService` finding, the always-empty-`cloud_findings` finding, the 500-line `saas_integration_service.py` constraint, and the `AttackPathEdge` field mismatch are all confirmed by direct grep/read this session, not inference
- Pitfalls: HIGH — every pitfall traces to a specific confirmed fact (file line count, grep result, import error, or field-name comparison)

**Research date:** 2026-07-08
**Valid until:** 2026-08-07 (30 days — codebase findings are stable; external SDK package facts should be re-verified with a fresh `pip index versions` check immediately before implementation since this is a fast-moving area of the dependency graph)
