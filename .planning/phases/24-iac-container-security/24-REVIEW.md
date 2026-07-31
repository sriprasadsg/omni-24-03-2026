---
phase: 24-iac-container-security
reviewed: 2026-07-04T14:52:53Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - backend/iac_scanner_service.py
  - backend/iac_scanner_endpoints.py
  - backend/container_scanner_service.py
  - backend/container_scanner_endpoints.py
  - backend/tests/test_iac_scanner.py
  - components/IacContainerDashboard.tsx
findings:
  critical: 5
  warning: 8
  info: 3
  total: 16
status: issues_found
---

# Phase 24: Code Review Report

**Reviewed:** 2026-07-04T14:52:53Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the IaC scanner, container scanner, their FastAPI endpoints, the phase's test suite, and the combined dashboard component. This phase has multiple severity-critical defects, confirmed by direct execution, not just inspection:

- `iac_scanner_service.scan_code()` inverts PASS/FAIL for the majority of Terraform checks (12 of 17), so vulnerable infrastructure reports as passing and clean infrastructure reports as failing.
- A second, previously-unreported inversion bug affects 5 of the 9 Kubernetes checks: a hard-coded override forces `has_negative = False` for every Kubernetes check, which discards the actual mitigation-detection logic and makes those 5 checks always report FAIL — even for a fully hardened manifest (verified experimentally below).
- CloudFormation, despite being advertised in the module docstring and in the dashboard's file-type dropdown, has zero implemented checks; every CloudFormation template — however vulnerable — scans clean (`total: 0`, `fail: 0`).
- The test suite's dependency-override pattern for `rbac_service.has_permission(...)` doesn't work (factory returns a fresh closure per call, so the override key never matches the route's baked-in dependency), causing real 401s in 3 tests. Running the suite confirms **5 of 8 tests fail** (2 from the status inversion, 3 from the auth override bug) — this exact bug class, and its correct fix, is already documented in `test_notification_service.py` in this same repo (override `get_current_user` instead), so it should not have recurred here.
- The dashboard component's TypeScript interfaces (`IaCScanResponse`, `IaCResult`) don't match the actual `/api/iac/scan` response shape at all (`results`/`total_checks`/`pass_count`/`fail_count`/`filename`/`type`/`name`/`line_ref` vs. actual `findings`/`total`/`fail`/`provider`/`check_name`/`line`). This crashes the results table (`iacResult.results.map(...)` on `undefined`) immediately after every successful scan.

All five are BLOCKER-severity and were each independently reproduced (test run output and standalone repro scripts included below per finding).

## Critical Issues

### CR-01: Terraform/CloudFormation PASS/FAIL logic inverted for vulnerability-marker checks

**File:** `backend/iac_scanner_service.py:59`
**Issue:** `status = "PASS" if has_negative else "FAIL"` is backwards for every Terraform check whose `negative_pattern` encodes the **vulnerable** condition (as opposed to a few checks — see note — whose `negative_pattern` encodes a *mitigation*). Confirmed by running the check against known-bad and known-clean Terraform:

```
$ pytest backend/tests/test_iac_scanner.py -v
tests/test_iac_scanner.py::test_iac_scan_terraform_s3_public_acl FAILED
    AssertionError: assert 'PASS' == 'FAIL'   # public-read ACL reported as PASS
tests/test_iac_scanner.py::test_iac_scan_clean_tf FAILED
    AssertionError: assert (1 == 0 or 'FAIL' == 'PASS')  # clean bucket reported as FAIL
```

Affected checks (12 of 17 Terraform checks — verified by reading each `negative_pattern` and confirming it encodes the vulnerable condition, not a mitigation): `tf-s3-public-acl`, `tf-iam-wildcard`, `tf-sg-open-ssh`, `tf-sg-open-rdp`, `tf-ebs-encrypted`, `tf-rds-encrypted`, `tf-eks-public`, `tf-ec2-public-ip`, `tf-alb-http`, `tf-kms-rotation`, `tf-ec2-admin`, `tf-rds-deletion-protection`.

(Note: `tf-s3-logging`, `tf-vpc-flow-logs`, `tf-hardcoded-key`, `tf-plaintext-secret`, `tf-s3-versioning` use `negative_pattern` to encode the *mitigation* being present, so the current formula happens to be correctly oriented for those 5 — do not blanket-flip all 17, only the 12 listed above, or you will introduce the same bug in the opposite direction for those 5.)

Net effect: this scanner currently reports the exact opposite of ground truth for the majority of its Terraform checks — a public-read S3 bucket, wide-open SSH/RDP security groups, unencrypted EBS/RDS volumes, a publicly-exposed EKS endpoint, etc. all show as "PASS", while correctly configured resources show as "FAIL".

**Fix:** For the 12 vulnerability-marker checks, invert the formula (or, cleaner, add an explicit `"vulnerable_marker": True` flag per check and branch on it):
```python
# checks where negative_pattern encodes the VULNERABLE condition
status = "FAIL" if has_negative else "PASS"
```
Recommend restructuring `IAC_CHECKS` so each entry explicitly states whether its second pattern is a `vulnerable_pattern` or a `mitigation_pattern`, and have `scan_code()` branch on that instead of overloading a single ambiguous `negative_pattern` key with opposite meanings across checks — the current design is what caused this bug and will cause the next one too.

---

### CR-02: Kubernetes mitigation checks always report FAIL regardless of manifest content

**File:** `backend/iac_scanner_service.py:57-58`
**Issue:**
```python
if provider == "kubernetes":
    has_negative = False  # K8s checks fire when pattern IS found
```
This unconditionally discards the `has_negative` value that was just computed from `negative_pattern` for **every** Kubernetes check, not only the ones where that's correct (`k8s-privileged`, `k8s-host-network`, `k8s-host-pid`, `k8s-secrets-env` — these have `negative_pattern: None` so the override is a no-op for them). For the 5 checks that *do* use `negative_pattern` as a mitigation marker (`k8s-run-as-root`, `k8s-no-resource-limits`, `k8s-no-network-policy`, `k8s-ro-not-set`, `k8s-no-probes`), this override means the mitigation is never detected — these 5 checks always report FAIL, even for a fully hardened pod. Reproduced directly:

```python
>>> import iac_scanner_service as iac
>>> code = '''apiVersion: v1
... kind: Pod
... spec:
...   containers:
...   - name: app
...     securityContext:
...       runAsNonRoot: true
...       readOnlyRootFilesystem: true
...     resources:
...       limits: {cpu: "1"}
...     livenessProbe: {httpGet: {path: /healthz}}
... '''
>>> r = iac.scan_code(code, "pod.yaml")
>>> [(f["check_id"], f["status"]) for f in r["findings"]]
[('k8s-run-as-root', 'FAIL'), ('k8s-no-resource-limits', 'FAIL'),
 ('k8s-ro-not-set', 'FAIL'), ('k8s-no-probes', 'FAIL')]
```
Every mitigation was correctly applied in the manifest above (`runAsNonRoot: true`, resource `limits`, `readOnlyRootFilesystem: true`, `livenessProbe`) yet all four testable checks still report FAIL. This makes ~55% of the Kubernetes rule set permanently non-functional — it can never pass no matter how the manifest is hardened, which will train users to ignore the scanner's findings for these checks.

**Fix:** Remove the blanket override; only force `has_negative = False` for the subset of Kubernetes checks whose `negative_pattern` is `None` (which already default to `False` naturally, since `if negative:` guards the computation) — i.e. delete lines 57-58 entirely:
```python
found = re.search(check["pattern"], code, re.MULTILINE | re.DOTALL)
if not found:
    continue
negative = check.get("negative_pattern")
has_negative = bool(re.search(negative, code, re.MULTILINE | re.DOTALL)) if negative else False
status = "PASS" if has_negative else "FAIL"
```
This makes the (already-correct) `if negative:` guard do the right thing for both providers without a provider-specific special case, and combined with the fix in CR-01, both providers use one consistent formula once the vulnerable-vs-mitigation flag from CR-01 is added per check.

---

### CR-03: CloudFormation provider has zero implemented checks — silently vacuous scan

**File:** `backend/iac_scanner_service.py:8-37` (checks list), `:70-83` (`_detect_provider`)
**Issue:** `_detect_provider()` correctly identifies CloudFormation templates (`ext in ("json", "template")` + `"Type" : "AWS::"` substring), but `IAC_CHECKS` contains zero entries with `"provider": "cloudformation"` (verified: `grep -c '"provider": "cloudformation"' iac_scanner_service.py` → `0`). Since `relevant = [c for c in IAC_CHECKS if c["provider"] == provider or provider == "unknown"]` only matches on exact provider string, any CloudFormation template gets an empty `relevant` list and thus zero findings — a total pass with no checks run at all:
```python
>>> cfn = '{"Resources": {"MyBucket": {"Type" : "AWS::S3::Bucket", "Properties": {"AccessControl": "PublicRead"}}}}'
>>> iac.scan_code(cfn, "template.json")
{'provider': 'cloudformation', 'total': 0, 'fail': 0, 'findings': [], ...}
```
A public-ACL S3 bucket defined via CloudFormation scans as `0 total / 0 fail` — indistinguishable in the UI from "nothing to check" — while the module docstring ("27 security checks for Terraform, K8s, CloudFormation manifests") and the dashboard's file-type dropdown ("template.yaml (CloudFormation)") both actively advertise CloudFormation support that does not exist. This is a silent, total feature gap for an entire declared IaC provider, not merely a missing edge case.

**Fix:** Either implement CloudFormation-equivalent checks (mirroring the Terraform set against CFN JSON `"Type": "AWS::..."` resources / `Properties`), or — at minimum, until implemented — surface this honestly instead of silently returning a clean scan, e.g.:
```python
if provider == "cloudformation" and not any(c["provider"] == "cloudformation" for c in IAC_CHECKS):
    return {"scan_id": scan_id, "provider": provider, "total": 0, "fail": 0, "findings": [],
            "scanned_at": _now(), "warning": "CloudFormation checks are not yet implemented"}
```
and remove the CloudFormation option from the dashboard until real checks exist.

---

### CR-04: Test dependency-override never engages — `rbac_service.has_permission(...)` returns a fresh closure per call

**File:** `backend/tests/test_iac_scanner.py:28-29`
**Issue:**
```python
app.dependency_overrides[rbac_service.has_permission("view:dashboard")] = lambda: t
app.dependency_overrides[rbac_service.has_permission("manage:settings")] = lambda: t
```
`rbac_service.has_permission()` (`backend/rbac_service.py:115-129`) is a factory that returns a brand-new `async def dependency(...)` closure object on every invocation — there is no caching/memoization keyed on `required_permission`. FastAPI's `dependency_overrides` dict is keyed by object identity, so the closure object created here in the test (by calling `has_permission("view:dashboard")` a second time) is never the same object as the one baked into the router when the endpoint module was imported and decorated. The override silently never matches, and the real `has_permission(...)` → `get_current_user` → `oauth2_scheme` dependency chain runs for real, with no `Authorization` header supplied by the `TestClient`, producing a 401.

Confirmed by running the suite:
```
$ pytest backend/tests/test_iac_scanner.py -v
tests/test_iac_scanner.py::test_iac_scan_config          FAILED  assert 401 == 200
tests/test_iac_scanner.py::test_container_list_results    FAILED  assert 401 == 200
tests/test_iac_scanner.py::test_iac_tenant_isolation       FAILED  assert 401 == 200
5 failed, 3 passed in 0.94s
```
(The other 2 failures are CR-01.) This is the exact same bug class as the documented fix in this repo's own `test_notification_service.py:34-39`, which explicitly comments:
> "has_permission(...) is a factory — every route decorator call produces a distinct closure, so overriding by re-calling it here never matches the object actually bound into the router. get_current_user is the stable, singleton dependency every has_permission(...) closure wraps, so override that instead."

That comment/fix already exists elsewhere in this codebase and was not applied here.

**Fix:** Override the stable singleton `get_current_user` dependency instead, as `test_notification_service.py` already does:
```python
from authentication_service import get_current_user
app.dependency_overrides[get_current_user] = lambda: t
```
and drop the two `rbac_service.has_permission(...)` override lines entirely (they don't work and give false confidence that RBAC paths are exercised).

---

### CR-05: Dashboard component's TypeScript interfaces don't match the actual API response — crashes on every successful IaC scan

**File:** `components/IacContainerDashboard.tsx:4-22, 230-233, 254-261, 281-285`
**Issue:** `IaCScanResponse`/`IaCResult` declare fields that the backend never sends. Actual `/api/iac/scan` response (from `iac_scanner_service.scan_code()`, returned unmodified by `iac_scanner_endpoints.py:22-25`) is:
```json
{"scan_id": "...", "provider": "terraform", "total": 3, "fail": 2,
 "findings": [{"check_id": "...", "check_name": "...", "severity": "...", "status": "FAIL", "message": "...", "line": 4}],
 "scanned_at": "..."}
```
but the component expects:
```ts
{ scan_id, filename, type, scanned_at, total_checks, pass_count, fail_count,
  results: [{ check_id, name, severity, status, message, line_ref }] }
```
None of `filename`, `type`, `total_checks`, `pass_count`, `fail_count`, or `results` exist on the real response (the real keys are `provider`, `total`, `fail`, `findings`). Line 254 does `iacResult.results.map(...)` — since `results` is `undefined`, this throws `TypeError: Cannot read properties of undefined (reading 'map')` and crashes the results panel immediately after every successful scan submission. The scan-history panel (`iacHistory.map(...)`, lines 278-287) reads `h.filename`, `h.type`, `h.pass_count`, `h.fail_count`, none of which exist either — this doesn't crash (React renders `undefined` as blank) but silently produces a history list with blank filenames, blank type badges, and no pass/fail counts.

By contrast, `ContainerScanResponse`/`ContainerVuln` are correctly aligned with the actual container-scanner response shape — this mismatch is specific to the IaC scanner integration.

**Fix:** Align the interfaces (and JSX field accesses) to the real backend shape, e.g.:
```ts
interface IaCResult {
  check_id: string;
  check_name: string;
  severity: string;
  status: string;
  message: string;
  line: number;
}
interface IaCScanResponse {
  scan_id: string;
  provider: string;
  total: number;
  fail: number;
  findings: IaCResult[];
  scanned_at: string;
}
```
and update usages accordingly (`iacResult.findings.map(...)`, `iacResult.total - iacResult.fail` for a pass count, `r.check_name`, `r.line`, `h.provider`, etc.) — or, if the intended contract really is `results`/`total_checks`/`pass_count`/`fail_count`/`filename`/`type`, change the backend to emit that shape instead. Either direction works; right now neither side agrees with the other, and this needs to be exercised with a live scan (not just eyeballed) before merging, since neither the Python nor the TS test suites currently catch this.

## Warnings

### WR-01: Simulated container-scan fallback mislabels genuine scan failures as "Trivy not installed"

**File:** `backend/container_scanner_service.py:22-32, 71-86`
**Issue:** `scan_image()` falls through to `_simulated_results(scan_id, image_name)` (no `note` argument) in every failure branch: non-zero Trivy exit code, `FileNotFoundError`, `TimeoutExpired`, or any other `Exception`. `_simulated_results` then defaults `note` to `"Trivy not installed — simulated results"` regardless of which branch triggered it. If Trivy **is** installed but the scan fails for an unrelated reason (bad image reference, registry auth failure, network timeout, transient crash), the caller is told Trivy isn't installed and is handed a fixed set of 6 hardcoded fake CVEs (`CVE-2024-0001`..`0006`) as if they reflected the requested image. This risks operators believing a specific, real vulnerability set applies to an image it was never actually scanned, or dismissing a real infrastructure problem (Trivy misconfigured/network broken) as "just not installed."
**Fix:** Pass a distinct, accurate note per failure branch, e.g. `_simulated_results(scan_id, image_name, note=f"Trivy scan failed (rc={result.returncode}) — simulated results")`, and only use the "not installed" wording when `trivy_path` was actually `None`.

### WR-02: Unused `import random` (dead code)

**File:** `backend/container_scanner_service.py:72`
**Issue:** `_simulated_results()` imports `random` but never uses it — the vulnerability list is a fixed literal.
**Fix:** Remove the unused import.

### WR-03: Confusing/inconsistent image-tag defaulting logic

**File:** `backend/container_scanner_endpoints.py:19`
**Issue:**
```python
if not image_name or ":" not in image_name and "/" in image_name:
    image_name = f"{image_name}:latest" if image_name else "nginx:latest"
```
Due to `and` binding tighter than `or`, this only appends `:latest` when the image name contains `/` but no `:` (e.g. `myorg/myimage` → `myorg/myimage:latest`). A bare, unqualified name with neither a slash nor a colon (e.g. `myimage`) is left untouched, so tag-defaulting is applied inconsistently depending on whether the name happens to include a registry/namespace path. This is easy to misread (and easy to break further) without added parentheses.
**Fix:** Make the intent explicit:
```python
if not image_name:
    image_name = "nginx:latest"
elif ":" not in image_name:
    image_name = f"{image_name}:latest"
```

### WR-04: "unknown" provider runs the full combined Terraform + Kubernetes rule set

**File:** `backend/iac_scanner_service.py:47`
**Issue:** `relevant = [c for c in IAC_CHECKS if c["provider"] == provider or provider == "unknown"]` — when `_detect_provider()` can't classify the input, every check from both providers is run against it, including regexes tuned for a completely different syntax. Arbitrary/unrecognized text can incidentally match unrelated patterns (e.g. any text containing the literal substring `containers:`), producing confusing, provider-mismatched findings for content that isn't IaC at all.
**Fix:** For `provider == "unknown"`, either run no checks (return `findings: []` with a `provider: "unknown"` marker) or make the ambiguity explicit in the response instead of silently applying both rule sets.

### WR-05: Failing-row highlight never triggers (case mismatch)

**File:** `components/IacContainerDashboard.tsx:255`
**Issue:** `style={{ background: r.status === 'fail' ? 'rgba(239,68,68,.03)' : 'transparent' }}` compares against lowercase `'fail'`, but the backend always returns uppercase `"FAIL"`/`"PASS"` (see `iac_scanner_service.py:59`). The `BADGE()` helper two lines below correctly handles both cases (`status === 'fail' || status === 'FAIL'`), showing this was a known concern that wasn't applied consistently. As a result, failing rows never get the red row background.
**Fix:** `background: r.status.toUpperCase() === 'FAIL' ? 'rgba(239,68,68,.03)' : 'transparent'`.

### WR-06: Fetch calls have no error handling — unhandled promise rejections

**File:** `components/IacContainerDashboard.tsx:82-95`
**Issue:** `fetchIacHistory`, `fetchContainerHistory`, and `fetchIacConfig` call `fetch(...).then(...)` with no `.catch()`. A network failure (offline, CORS, DNS) throws inside the promise chain with nothing to observe it — an unhandled promise rejection with no user-facing feedback, unlike `runIacScan`/`runContainerScan` which do wrap their fetches in `try/catch` and set `error`.
**Fix:** Wrap in `try/catch` (or `.catch(() => {})` at minimum) consistent with the pattern already used elsewhere in the same file.

### WR-07: No validation/allow-list on `image_name`; unrestricted registry pulls from the scanning host

**File:** `backend/container_scanner_endpoints.py:14-24`
**Issue:** `image_name` is accepted as an arbitrary string (bounded only by FastAPI's default body-size limits) and passed straight through to `trivy image <image_name>`, which will attempt to pull from whatever registry the reference resolves to. Any authenticated user holding only `view:dashboard` can direct the scanning host to attempt pulls against arbitrary registries (including internal/private ones reachable from that host), with no format validation, no allow-list, and no per-user rate limiting on a call that can block for up to 300s (`subprocess.run(..., timeout=300)`). This is not command injection (the subprocess call uses list-form args, not shell), but it is an unauthenticated-to-the-registry pull primitive plus a resource-exhaustion vector.
**Fix:** Validate `image_name` against an expected reference pattern (registry/namespace/name:tag), consider restricting to an allow-list of registries in production, and add basic per-tenant rate limiting around the subprocess call.

### WR-08: Container-scan tests are not hermetic — they exercise the real Trivy-detection subprocess path

**File:** `backend/tests/test_iac_scanner.py:60-66, 78-81`
**Issue:** `test_container_scan_image` and `test_container_vuln_severity_counts` call `cs.scan_image(...)` directly without mocking `_find_trivy`/`subprocess.run`. This means the test's actual code path (real-Trivy vs. simulated) — and its runtime (`_find_trivy` alone issues up to 3 subprocess calls with 5s timeouts each) — depends on whatever happens to be installed on the machine running the suite, rather than being deterministic and fast.
**Fix:** `patch("container_scanner_service._find_trivy", return_value=None)` (or mock `subprocess.run` directly) so the test always exercises a known, fast, deterministic code path.

## Info

### IN-01: `test_iac_tenant_isolation` doesn't test tenant isolation

**File:** `backend/tests/test_iac_scanner.py:73-76`
**Issue:** The test only asserts `r.status_code == 200` for a `tenant-a`/`user`-role request to `/api/iac/results`; it never creates data under a different tenant or asserts that cross-tenant results are excluded. The name promises isolation coverage that the body doesn't provide.
**Fix:** Seed results for two distinct tenant IDs in the mock DB and assert the response for tenant A excludes tenant B's records (or at minimum assert the `find` mock was called with the expected `{"tenantId": ...}` filter).

### IN-02: Docstring overstates check count and CloudFormation coverage

**File:** `backend/iac_scanner_service.py:1`
**Issue:** `"""IaC Scanner — 27 security checks for Terraform, K8s, CloudFormation manifests."""` — the actual count is 26 (17 Terraform + 9 Kubernetes; verified by grep), and 0 are CloudFormation-specific (see CR-03).
**Fix:** Update the docstring once CR-03 is resolved (or immediately, to stop overstating current coverage).

### IN-03: Weak/unscoped heuristics for secret-related Terraform checks

**File:** `backend/iac_scanner_service.py:22-23`
**Issue:** `tf-hardcoded-key` and `tf-plaintext-secret` search `negative_pattern` (`var\.` / `sensitive = true`) anywhere in the whole file rather than scoped to the same resource/variable block as the matching `pattern`. A file with multiple resources — one genuinely hardcoding a secret and another correctly using `sensitive = true` elsewhere — can cause the hardcoded one to be marked as mitigated by an unrelated declaration.
**Fix:** Scope the negative-pattern search to the same block (e.g., match within N lines of the `pattern` match, or parse per-resource blocks) rather than the entire file.

---

_Reviewed: 2026-07-04T14:52:53Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
