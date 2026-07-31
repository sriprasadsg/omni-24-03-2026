---
phase: 25-cloud-checks-execution-gaps
reviewed: 2026-07-06T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - backend/cloud_account_endpoints.py
  - backend/cloud_checks_endpoints.py
  - backend/cloud_checks_service.py
  - backend/container_scanner_service.py
  - backend/iac_scanner_service.py
  - backend/mcp_server_endpoints.py
  - backend/tests/test_cloud_accounts.py
  - backend/tests/test_cloud_checks_expansion.py
  - backend/tests/test_iac_scanner.py
  - components/IacContainerDashboard.tsx
findings:
  critical: 2
  warning: 6
  info: 2
  total: 10
status: issues_found
---

# Phase 25: Code Review Report

**Reviewed:** 2026-07-06T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the three plans that make up Phase 25 (CHK-01 provider-allowlist widening, CHK-02 CloudFormation rule expansion + YAML-detection fix, CHK-03 `simulated` flag on container scans).

The provider-allowlist widening (CHK-01) is genuinely consistent: `cloud_account_endpoints.py`, `cloud_checks_endpoints.py`, `cloud_checks_service.py`, and `mcp_server_endpoints.py` all now gate on the identical five-provider tuple `("aws", "azure", "gcp", "kubernetes", "digitalocean")` — no gate was left narrower than another. The `simulated` flag (CHK-03) is additive and optional on the TypeScript interfaces, and both success/failure code paths in `container_scanner_service.py` set it consistently, so it is genuinely non-breaking for existing consumers.

However, the new CloudFormation rule set (CHK-02) has two logic defects that undermine the actual security value of the new checks — one is a straight PASS/FAIL inversion on a security-relevant check, and the other is a regex ordering bug that misses the most common real-world property layout for security-group rules. Both slipped past the added tests because the tests assert on scan behavior (provider detection, ReDoS timing) without asserting the correct `status` for the specific new checks they exercise. See Critical section below.

## Critical Issues

### CR-01: `cfn-ec2-admin-userdata` check has inverted PASS/FAIL logic

**File:** `backend/iac_scanner_service.py:55`
**Issue:** This check is missing `"vulnerable_marker": True`, which its Terraform analog (`tf-ec2-admin`, line 26) has:

```python
# line 26 — Terraform version, correct
{"id": "tf-ec2-admin", ..., "negative_pattern": r'user_data.*admin|user_data.*root', "vulnerable_marker": True},

# line 55 — CloudFormation version, BUG: no vulnerable_marker
{"id": "cfn-ec2-admin-userdata", ..., "negative_pattern": r'UserData.*(admin|root)', "scope_lines": 15},
```

In `scan_code()` (lines 91-98), a check without `vulnerable_marker` is treated as a "mitigation-present" check: `status = "PASS" if has_negative else "FAIL"`. Since `has_negative` here means "UserData references admin/root was found", the effect is exactly backwards — an EC2 instance whose `UserData` **does** reference admin/root elevation is reported `PASS` (safe), and an instance whose `UserData` does **not** mention admin/root is reported `FAIL` (vulnerable). This is a genuine PASS/FAIL inversion on a security scanner's own output. `backend/tests/test_iac_scanner.py:165-182` (`test_iac_scan_cfn_redos_bounded`) constructs a CloudFormation block containing an admin-referencing comment and a base64 `UserData` payload, but only asserts on scan timing — it never asserts `status` for `cfn-ec2-admin-userdata`, so this inversion ships untested.

**Fix:**
```python
{"id": "cfn-ec2-admin-userdata", "name": "EC2 UserData References Admin/Root", "description": "EC2 instance UserData should not reference admin/root elevation", "provider": "cloudformation", "severity": "high", "pattern": r'Type"?\s*:?\s*"?AWS::EC2::Instance', "negative_pattern": r'UserData.*(admin|root)', "vulnerable_marker": True, "scope_lines": 15},
```

### CR-02: `cfn-sg-open-ssh` / `cfn-sg-open-rdp` only match one CidrIp/FromPort ordering, missing the common real-world layout

**File:** `backend/iac_scanner_service.py:43-44`
**Issue:**
```python
{"id": "cfn-sg-open-ssh", ..., "negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*22|ToPort"?\s*:\s*22)', "vulnerable_marker": True, "scope_lines": 15},
{"id": "cfn-sg-open-rdp", ..., "negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*22|ToPort"?\s*:\s*3389)', "vulnerable_marker": True, "scope_lines": 15},
```
(pattern text abbreviated for RDP to show shape; actual RDP regex uses 3389). Both patterns require `CidrIp` to appear **textually before** `FromPort`/`ToPort` (the `.*` only matches forward). But the single most common `SecurityGroupIngress` property order in AWS's own documentation and generated templates is:
```yaml
SecurityGroupIngress:
  - IpProtocol: tcp
    FromPort: 22
    ToPort: 22
    CidrIp: 0.0.0.0/0
```
i.e. `FromPort`/`ToPort` **before** `CidrIp`. In that (very common) ordering, the regex never matches, `has_negative` is `False`, and with `vulnerable_marker: True` the check reports `status = "PASS"` for an actually wide-open security group. This is a false negative in the flagship new-checks set. Contrast with the pre-existing Terraform sibling (`tf-sg-open-ssh`, line 14), which correctly ORs both orderings:
```python
r'cidr_blocks\s*=\s*\[?\s*"0\.0\.0\.0/0".*from_port\s*=\s*22|from_port\s*=\s*22.*cidr_blocks\s*=\s*\[?\s*"0\.0\.0\.0/0"'
```
`backend/tests/test_iac_scanner.py:124-140` (`test_iac_scan_cfn_sg_open_ssh`) only exercises the `CidrIp`-first ordering, so this gap is untested.

**Fix:** OR both orderings, matching the Terraform pattern's shape:
```python
"negative_pattern": r'CidrIp"?\s*:\s*"?0\.0\.0\.0/0.*(FromPort"?\s*:\s*22|ToPort"?\s*:\s*22)|(FromPort"?\s*:\s*22|ToPort"?\s*:\s*22).*CidrIp"?\s*:\s*"?0\.0\.0\.0/0',
```
(and the equivalent for port 3389 in `cfn-sg-open-rdp`).

## Warnings

### WR-01: `POST /api/cloud-checks/run` doesn't translate `run_checks()` error results into HTTP error statuses

**File:** `backend/cloud_checks_endpoints.py:70-77`
**Issue:** `cloud_checks_service.run_checks()` can return `{"error": "Cloud account not found", "ran": 0}` (see `backend/cloud_checks_service.py:69-70`) or `{"error": f"provider must be one of {RUNNABLE_PROVIDERS}", "ran": 0}`. This endpoint returns that dict verbatim with a 200 status — the caller has to inspect the body to discover a failure. Compare with `cloud_account_endpoints.py:50-57` (`scan_account`), which correctly inspects `result.get("error")` and maps to 404/502. The same request path reachable via `mcp_server_endpoints.py:73-82` (`run_cloud_check`) has the identical gap.
**Fix:**
```python
result = await cloud_checks_service.run_checks(
    payload.accountId, payload.provider, _tenant(current_user), payload.credentialsHint
)
if result.get("error"):
    status_code = 404 if result["error"] == "Cloud account not found" else 400
    raise HTTPException(status_code=status_code, detail=result["error"])
return result
```

### WR-02: `cfn-eks-public-endpoint` doesn't flag the omitted-property case its own description calls out as vulnerable

**File:** `backend/iac_scanner_service.py:47`
**Issue:** Description reads "EndpointPublicAccess should be false (defaults to true if omitted)", but the check only fires (`vulnerable_marker: True`) when `EndpointPublicAccess: true` is explicitly present. A template that simply omits the property — the described unsafe default — is reported `PASS`. Compare with `cfn-kms-rotation-disabled` (line 50) and `cfn-rds-deletion-protection-disabled` (line 57), which correctly use the mitigation-style pattern (search for the *safe* value, default to FAIL when absent) for the exact same "unsafe default when omitted" scenario.
**Fix:** Invert to mitigation-style, mirroring the KMS/RDS-deletion-protection checks — search for `EndpointPublicAccess"?\s*:\s*false` as the mitigation and drop `vulnerable_marker`, so an omitted property (no match) correctly yields `FAIL`.

### WR-03: Fixed `scope_lines` windows risk false-positive FAILs on legitimately-configured, larger resource blocks

**File:** `backend/iac_scanner_service.py:40, 51, 56` (`cfn-s3-public-access`, `cfn-s3-logging-disabled`, `cfn-s3-versioning-disabled`)
**Issue:** All three S3 mitigation-style checks anchor their 15-line search window off the same `Type: AWS::S3::Bucket` match. A real bucket resource commonly has `BucketEncryption`, `PublicAccessBlockConfiguration`, `LifecycleConfiguration`, `Tags`, etc. before `LoggingConfiguration`/`VersioningConfiguration` appear — easily exceeding a 15-line window, especially when multi-line YAML block properties are involved. When that happens the mitigation is textually present but outside the window, so `has_negative` is `False` and the check reports `FAIL` on a bucket that is actually compliant.
**Fix:** Either widen `scope_lines` for these three checks (e.g. 25-30) or drop the windowing for these specific low-collision keywords (`LoggingConfiguration`, `VersioningConfiguration` are unlikely to belong to an unrelated resource) and search the whole file as the pre-existing Terraform `tf-s3-logging`/`tf-s3-versioning` checks already do (no `scope_lines` there).

### WR-04: `register_account` doesn't validate `account_id` type

**File:** `backend/cloud_account_endpoints.py:38-45`
**Issue:** `if not payload.get("provider") or not payload.get("account_id")` only checks truthiness, not type. A non-string `account_id` (e.g., an int, list, or dict) passes this guard and is persisted via `svc.register_account`, violating the project's "validate input at system boundaries" rule and risking downstream type errors wherever `account_id` is later treated as a string (e.g., `.lower()`/regex matching in `cloud_checks_service.run_checks`).
**Fix:**
```python
if not isinstance(payload.get("account_id"), str) or not payload.get("account_id"):
    raise HTTPException(status_code=400, detail="account_id must be a non-empty string")
```

### WR-05: `IacContainerDashboard.tsx` fetch callbacks close over a stale `headers`/`token` captured at mount

**File:** `components/IacContainerDashboard.tsx:94-116`
**Issue:**
```tsx
const token = sessionStorage.getItem('token') || sessionStorage.getItem('access_token');
const headers = token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };

const fetchIacHistory = useCallback(async () => { ... }, []);
const fetchContainerHistory = useCallback(async () => { ... }, []);
const fetchIacConfig = useCallback(async () => { ... }, []);
```
`token`/`headers` are recomputed every render, but the three `useCallback`s have empty dependency arrays, so they permanently close over whatever `headers` value existed on the render that first created them. If the auth token is written to `sessionStorage` after this component mounts (e.g., async auth restoration completing slightly later), the "Refresh" button (line 192) and every subsequent history/config fetch will keep sending requests without the `Authorization` header for the lifetime of the component.
**Fix:** Include `headers` (or `token`) in the dependency arrays, or read `sessionStorage` inside each callback body instead of closing over a render-scoped variable.

### WR-06: Single shared `loading` state couples the two independent tabs

**File:** `components/IacContainerDashboard.tsx:79, 124-154, 238, 256-257, 333, 352-353`
**Issue:** `loading` is one piece of state shared by both `runIacScan` and `runContainerScan`. Starting a scan on one tab (e.g., IaC Scanner) sets `loading = true`, which also renders the `Spinner` and disables the scan button on the *other* tab (Container Scanner) if the user switches tabs mid-scan, even though that tab's own request isn't running.
**Fix:** Use separate `iacLoading`/`containerLoading` state variables.

## Info

### IN-01: `credentialsHint`/`credentials_hint` is accepted end-to-end but never used

**File:** `backend/cloud_checks_endpoints.py:23-26`, `backend/cloud_checks_service.py:63`
**Issue:** `RunChecksPayload.credentialsHint` is parsed and forwarded to `cloud_checks_service.run_checks(..., credentials_hint=...)`, but the parameter is never read inside `run_checks()`'s body. This is either dead API surface or an unfinished feature; either way it's misleading to callers who assume passing it does something.
**Fix:** Either wire it into the check-evaluation logic or remove the parameter/field until it's implemented, with a `# TODO` noting the gap if intentionally deferred.

### IN-02: Duplicated CFN `Type` prefix pattern fragment repeated 18 times

**File:** `backend/iac_scanner_service.py:40-57`
**Issue:** Every CloudFormation check's `pattern` re-derives the same `Type"?\s*:?\s*"?AWS::` prefix inline (e.g. `Type"?\s*:?\s*"?AWS::S3::Bucket`) rather than reusing the already-defined `_CFN_TYPE_RE` fragment (line 108) or a shared constant, unlike the mitigation logic which is centralized. Purely a maintainability nit — any future fix to how `Type` is matched (e.g., handling `!Sub`/YAML anchors) needs 18 coordinated edits.
**Fix:** Factor the common prefix into a module-level string constant and interpolate the resource type suffix per check.

---

_Reviewed: 2026-07-06T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
