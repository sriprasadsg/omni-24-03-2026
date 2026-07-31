---
phase: 32-cloud-and-saas-provider-expansion
reviewed: 2026-07-27T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - backend/oci_ingest.py
  - backend/alibaba_ingest.py
  - backend/cloudflare_ingest.py
  - backend/cloud_integrations_endpoints.py
  - backend/saas_posture_checks_service.py
  - backend/saas_posture_checks_endpoints.py
  - backend/attack_path_service.py
  - backend/attack_path_endpoints.py
  - backend/m365_ingest.py
  - backend/mongodb_atlas_ingest.py
  - backend/cloud_accounts_service.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 32: Code Review Report

**Reviewed:** 2026-07-27
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

New CSPM ingest paths (M365, Atlas, OCI/Alibaba/Cloudflare) and a SaaS posture-checks layer. The CSPM `poll_*_cspm_findings` functions call real SDKs, but the older 2-arg "SIEM" poll functions in the same three cloud modules **fabricate hardcoded events and insert them into `security_events`** — and per 32-01 they are wired into the integration test/discovery paths. Atlas and M365 findings mappings also emit false or mis-severitied findings.

## Critical Issues

### CR-01: SIEM ingest functions fabricate fake security events into production data

**File:** `backend/oci_ingest.py:88`, `backend/alibaba_ingest.py:90`, `backend/cloudflare_ingest.py:79`
**Issue:** `poll_oci_cloud_guard_problems`, `poll_alibaba_sas_alerts`, and `poll_cloudflare_zero_trust_events` do not call any SDK — they synthesize hardcoded objects (`type('Problem', (), {...})()`) and `insert_many` them into `db.security_events`. `_make_oci_client` returns the literal string `"mocked_oci_client"`. 32-01 states these are "wired into `cloud_integrations_endpoints.py` for both test and discovery paths," so any configured OCI/Alibaba/Cloudflare integration injects fabricated alerts, corrupting the SIEM and producing a false security posture.
**Fix:** Replace the mock bodies with real SDK calls, or gate them behind an explicit demo/simulated flag (as attack-path does) and never write them to `security_events` in a real integration path.

## Warnings

### WR-01: MongoDB Atlas ingest flags every cluster as a High/FAIL finding

**File:** `backend/mongodb_atlas_ingest.py:29-49` — `_parse_atlas_finding` hardcodes `severity="High"`, `status="FAIL"` for every cluster returned ("Assume failing for the POC finding"), regardless of actual configuration. This produces one false High finding per cluster.
**Fix:** Evaluate real cluster settings (IP access list `0.0.0.0/0`, TLS, auth) and only emit findings for actual misconfigurations.

### WR-02: M365 severity thresholds compare raw score to percentage bands

**File:** `backend/m365_ingest.py:27-46` — `_severity_map(current_score)` treats `score < 40 → Critical`, but `current_score` is a per-control absolute value (0..`maxScore`), not a percentage. A control with `maxScore=10, currentScore=5` is mislabeled Critical.
**Fix:** Normalize to a percentage: `pct = 100 * current_score / max_score` and map on `pct`.

### WR-03: Posture-check results list scoped to caller tenant, not connection tenant

**File:** `backend/saas_posture_checks_endpoints.py:49-52` — `list_posture_results` filters `saas_check_results` on `{"tenantId": user_tenant}`. When a super_admin/platform_admin runs checks against another tenant's connection (allowed by the `/run` bypass), the results are stored under the connection's tenant but listed under the admin's own tenant → the admin never sees what they ran, and a `None` `user_tenant` returns nothing.
**Fix:** For the super-admin path, scope the results query by `connection.get("tenant_id")` (matching how `/run` stores them).

## Info

### IN-01: Repeated bare `except:` blocks
**File:** `backend/cloud_accounts_service.py:114-140` — five `try: config = json.loads(creds) except: config = {}` bare excepts; use `except (json.JSONDecodeError, TypeError)`.

### IN-02: Attack-path heuristic slicing + non-simulated persistence
**File:** `backend/attack_path_service.py:84-89, 128` — `entry_assets[:5]`/`target_assets[:3]` silently drop paths as inventory grows, and heuristically-derived paths are persisted with `simulated=False` (presented as real). Consider a confidence field or documenting the cap.

### IN-03: Atlas v2 API version header
**File:** `backend/mongodb_atlas_ingest.py:66` — the Atlas Admin API v2 typically requires an `Accept: application/vnd.atlas.YYYY-MM-DD+json` header; a bare GET may 406. Verify against the live API.

---

_Reviewed: 2026-07-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
