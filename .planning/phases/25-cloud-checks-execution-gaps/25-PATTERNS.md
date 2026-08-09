# Phase 25: Cloud Checks Execution Gaps - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 10 (7 source edits, 3 test files)
**Analogs found:** 10 / 10 (all files being edited already exist and contain the pattern to extend — this phase is 100% "extend existing pattern in place," no new analog search across the codebase was needed since every touched file already demonstrates its own pattern)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/cloud_checks_service.py` | service | CRUD (upsert check results) | itself — `RUNNABLE_PROVIDERS` tuple + `_RUNNABLE_CHECKS_COUNT` (lines 34-35) | exact (in-place edit) |
| `backend/cloud_checks_endpoints.py` | route/controller | request-response | itself — provider validation at line 73 | exact (in-place edit) |
| `backend/cloud_account_endpoints.py` | route/controller | request-response | itself — `_VALID_PROVIDERS` at line 13 | exact (in-place edit) |
| `backend/mcp_server_endpoints.py` | route/controller (tool-calling) | request-response | itself — provider validation at line 78 | exact (in-place edit) |
| `backend/iac_scanner_service.py` | service (rule engine) | transform (regex scan) | itself — existing Terraform rule dicts (lines 12-28) + `_detect_provider()` (lines 94-107) | exact (in-place edit, additive rules + bugfix) |
| `backend/container_scanner_service.py` | service | transform / file-I/O (subprocess) | itself — `_simulated_results()` (lines 75-89) and `_parse_trivy_output()` (lines 49-72) | exact (in-place edit) |
| `components/IacContainerDashboard.tsx` | component | request-response (fetch + render) | itself — existing `note` banner (lines 337-341) and `ContainerScanResponse` interface (lines 33-45) | exact (in-place edit) |
| `backend/tests/test_cloud_checks_expansion.py` | test | — | `backend/tests/test_iac_scanner.py` (full file, `_mkdb`/`_mkuser`/`_build` helpers, lines 8-40) | role-match (empty stub to be filled using sibling test file's harness) |
| `backend/tests/test_iac_scanner.py` | test | — | itself — `test_iac_scan_terraform_s3_public_acl` (lines 42-47), `test_container_scan_image` (lines 69-76) | exact (extend in place) |
| `backend/tests/test_cloud_accounts.py` | test | — | `backend/tests/test_iac_scanner.py::test_iac_scan_config` (lines 62-67, `_build`/`_mkdb` pattern applied to an endpoints router) | role-match |

## Pattern Assignments

### `backend/cloud_checks_service.py` (service, CRUD) — CHK-01, Gate 4

**Analog:** itself, lines 31-35 and 62-65

**Current code to widen** (`backend/cloud_checks_service.py:31-35`):
```python
# Providers actually reachable via POST /api/cloud-checks/run (cloud_checks_endpoints.py).
# K8s and DigitalOcean checks are defined but never evaluated by run_checks(), so they must
# be excluded from the coverage denominator or coverage could never reach 100%.
RUNNABLE_PROVIDERS = ("aws", "azure", "gcp")
_RUNNABLE_CHECKS_COUNT = len([c for c in CLOUD_CHECKS if c["provider"] in RUNNABLE_PROVIDERS])
```

**Execution gate to widen** (`backend/cloud_checks_service.py:62-65`):
```python
async def run_checks(self, account_id: str, provider: str, tenant_id: str, credentials_hint: Optional[str] = None) -> Dict:
    """Evaluate checks against the account's imported findings from native scanners."""
    if provider not in RUNNABLE_PROVIDERS:
        return {"error": f"provider must be one of {RUNNABLE_PROVIDERS}", "ran": 0}
```

**Pattern to copy:** Widen the `RUNNABLE_PROVIDERS` tuple literal to include `"kubernetes"` and `"digitalocean"`. `_RUNNABLE_CHECKS_COUNT` recomputes automatically since it's derived from the same tuple at import time (Pitfall 2) — do not touch that line's shape, only the tuple it reads from.

---

### `backend/cloud_checks_endpoints.py` (route, request-response) — CHK-01, Gate 2

**Analog:** itself, line 73

**Current code:**
```python
# Source: backend/cloud_checks_endpoints.py:73
if payload.provider not in ("aws", "azure", "gcp"):
    raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")
```

**Pattern to copy:** Same literal-tuple-widening pattern as Gate 4 — change the tuple and the error message string in lockstep so client-facing errors stay accurate.

---

### `backend/cloud_account_endpoints.py` (route, request-response) — CHK-01, Gate 1

**Analog:** itself, lines 13, 40-41

**Current code:**
```python
# Source: backend/cloud_account_endpoints.py:13
_VALID_PROVIDERS = {"aws", "azure", "gcp"}
...
# lines 40-41
if payload.get("provider") not in _VALID_PROVIDERS:
    raise HTTPException(status_code=400, detail=f"provider must be one of {sorted(_VALID_PROVIDERS)}")
```

**Pattern to copy:** Widen the `_VALID_PROVIDERS` set literal. This is the registration gate — per research Pattern 1, this must move in lockstep with Gate 4 or `POST /api/cloud-accounts` will still reject `provider=kubernetes`/`digitalocean` even after `run_checks()` accepts them, leaving the multi-account UI flow broken.

---

### `backend/mcp_server_endpoints.py` (route/tool, request-response) — CHK-01, Gate 3

**Analog:** itself, lines 24, 78-79

**Current code:**
```python
# Source: backend/mcp_server_endpoints.py:78-79
if provider not in ("aws", "azure", "gcp"):
    raise HTTPException(status_code=400, detail="provider must be aws, azure, or gcp")
# line 24 — stale tool-schema description string, update for consistency:
# "params": {"provider": "string (aws/azure/gcp)", ...}
```

**Pattern to copy:** Same tuple-widening pattern as Gate 2, plus update the cosmetic tool-schema description string at line 24 to reflect the widened provider set.

---

### `backend/iac_scanner_service.py` (service, transform) — CHK-02

**Analog:** itself — existing Terraform rule-dict shape (lines 12-28) and `scan_code()` dispatch (lines 45-91, provider-agnostic already)

**Rule-dict shape to replicate exactly** (`backend/iac_scanner_service.py:12`):
```python
{"id": "tf-s3-public-acl", "name": "S3 Bucket Public ACL", "description": "S3 bucket should not have public ACL", "provider": "terraform", "severity": "critical", "pattern": r'resource\s+"aws_s3_bucket"\s+"([^"]+)"', "negative_pattern": r'acl\s*=\s*"public-read"|acl\s*=\s*"public-read-write"', "vulnerable_marker": True},
```

**Scope-bounded rule shape** to replicate for any CFN rule with a greedy/DOTALL negative_pattern (`backend/iac_scanner_service.py:24-25`, ReDoS guard per Pitfall 5):
```python
{"id": "tf-hardcoded-key", ..., "negative_pattern": r'variable\s+"aws_access_key|var\.', "scope_lines": 2},
{"id": "tf-plaintext-secret", ..., "negative_pattern": r'sensitive\s*=\s*true', "scope_lines": 5},
```

**Where to add the 18 CFN rules:** Append a new `# ─── CloudFormation checks ──` section immediately after the Kubernetes block (after line 38, before the closing `]` at line 39), using `"provider": "cloudformation"`. Use the full `CFN_CHECKS` list already drafted in RESEARCH.md (Pattern 2, 18 rules) verbatim — do not invent a new shape.

**`scan_code()` early-return to delete** (`backend/iac_scanner_service.py:50-54`) — this special-case branch becomes dead code once CFN rules exist in `IAC_CHECKS` and must be removed so CFN templates flow through the same `relevant = [c for c in IAC_CHECKS if c["provider"] == provider]` dispatch (line 58) as Terraform/K8s:
```python
if provider == "cloudformation":
    return {"scan_id": scan_id, "provider": provider, "total": 0, "fail": 0, "findings": [],
            "scanned_at": _now(), "warning": "CloudFormation checks are not yet implemented"}
```

**`_detect_provider()` bugfix** (`backend/iac_scanner_service.py:94-107`) — replace with the YAML-tolerant version from RESEARCH.md Pattern 3 (adds `_CFN_TYPE_RE = re.compile(r'"?Type"?\s*:\s*"?AWS::')` module-level constant and checks it in the `yaml`/`yml` branch plus an extension-less fallback before returning `"unknown"`).

---

### `backend/container_scanner_service.py` (service, transform) — CHK-03

**Analog:** itself, `_simulated_results()` (lines 75-89) and `_parse_trivy_output()` (lines 49-72)

**Current simulated-results dict to extend** (`backend/container_scanner_service.py:88`):
```python
result = {"scan_id": scan_id, "image": image_name, "trivy": False, "note": note or "Trivy not installed — simulated results", "vulns": vulns, "total": len(vulns), "critical": c, "high": h, "medium": m, "low": l, "scanned_at": _now()}
```

**Pattern to copy:** Add `"simulated": True` alongside the existing `"trivy": False` key (same dict literal, one new key). Symmetrically add `"simulated": False` to the real-Trivy return in `_parse_trivy_output()` (`backend/container_scanner_service.py:69`):
```python
return {"scan_id": scan_id, "image": image_name, "trivy": True, "vulns": vulns, "total": len(vulns), "critical": critical, "high": high, "medium": medium, "low": low, "scanned_at": _now()}
```
→ add `"simulated": False` to this dict too, for a consistent contract shape across both paths.

**Do not touch:** `scan_image()`'s control flow (lines 12-36) — CHK-03 is purely an additive field, not a fail-closed behavior change (Anti-Pattern / Pitfall 4).

---

### `components/IacContainerDashboard.tsx` (component, request-response) — CHK-03

**Analog:** itself — `ContainerScanResponse` interface (lines 33-45) and existing `note` banner (lines 337-341)

**Interface to extend** (`components/IacContainerDashboard.tsx:33-45`):
```typescript
interface ContainerScanResponse {
  scan_id: string;
  image: string;
  trivy: boolean;
  vulns: ContainerVuln[];
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  scanned_at: string;
  note?: string;
}
```
→ add `simulated?: boolean;` to this interface.

**Existing banner pattern to replicate for the two new badge locations** (`components/IacContainerDashboard.tsx:337-341`):
```tsx
{containerResult?.note && (
  <div className="px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded-lg text-xs flex items-center gap-2">
    <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {containerResult.note}
  </div>
)}
```

**Three surfaces needing the badge** (per RESEARCH.md Pattern 4):
1. **Vulnerability Summary panel header** — near line 361 (`<p className="text-sm text-gray-500 ... font-mono">{containerResult.image}</p>`), add a badge conditioned on `containerResult.simulated` using the same yellow/AlertTriangle visual language as the existing banner.
2. **Vulnerabilities table** — the table header block starts at line 384 (`<span className="text-sm font-semibold ...">Vulnerabilities</span>`) with columns defined at line 391 (`['CVE', 'Package', 'Severity', 'Installed', 'Fixed', 'Title']`); add a "SIMULATED" chip in this header area when `containerResult.simulated` is true — do not tag individual rows (all vulns share one scan's flag).
3. **Scan History list** — mirror the IaC history-row pattern already present at lines 303-313 (`iacHistory.map((h, i) => ...)` with inline badges like `<span className="px-1.5 py-0.5 bg-blue-100 ...">{h.provider}</span>`); apply the same small-tag pattern to `containerHistory.map(...)` rows, showing a "sim" tag when `entry.simulated` is true.

---

### `backend/tests/test_cloud_checks_expansion.py` (test) — CHK-01

**Analog:** `backend/tests/test_iac_scanner.py` (full file, especially `_mkdb`/`_mkuser`/`_build` helpers at lines 8-40)

**Harness pattern to copy verbatim** (`backend/tests/test_iac_scanner.py:1-40`):
```python
import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from starlette.testclient import TestClient

def _mkuser(t="tenant-a", r="admin"):
    u = MagicMock(); u.tenant_id = t; u.role = r; return u

def _mkdb(collections=(...)):
    db = MagicMock()
    for col in collections:
        c = MagicMock()
        c.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
        c.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))
        c.find_one = AsyncMock(return_value=None)
        c.update_one = AsyncMock()
        setattr(db._db, col, c)
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=None)
    return db

def _build(module_name, mock_db, user):
    import importlib
    mod = importlib.import_module(module_name)
    from authentication_service import get_current_user
    app = FastAPI(); app.include_router(mod.router)
    t = MagicMock(); t.tenant_id = user.tenant_id; t.role = user.role
    app.dependency_overrides[get_current_user] = lambda: t
    patcher = patch(f"{module_name}.get_database", return_value=mock_db); patcher.start()
    rbac_patcher = patch("rbac_service.get_database", return_value=mock_db); rbac_patcher.start()
    return TestClient(app, raise_server_exceptions=False)
```

**Note:** For `cloud_checks_service.py` this uses `db.<collection>` directly (not `db._db.<collection>` as in `iac_scanner_service.py`) — confirm the collection attribute path against `cloud_checks_service.py`'s actual `self._db()` usage (`db.cloud_accounts`, `db.cloud_findings`, `db.cloud_check_results` — no `_db` prefix) before reusing `_mkdb`; adjust the mock's attribute-setting target accordingly (`setattr(db, col, c)` not `setattr(db._db, col, c)`).

**Test functions required** (from RESEARCH.md's Test Map): `test_run_checks_evaluates_kubernetes`, `test_run_checks_evaluates_digitalocean`, `test_coverage_denominator_includes_new_providers`.

---

### `backend/tests/test_iac_scanner.py` (test) — CHK-02, CHK-03

**Analog:** itself — `test_iac_scan_terraform_s3_public_acl` (lines 42-47) for CFN tests; `test_container_scan_image` (lines 69-76) for the `simulated` field assertion

**Pattern to copy for each new CFN rule test** (`backend/tests/test_iac_scanner.py:42-47`):
```python
def test_iac_scan_terraform_s3_public_acl():
    code = 'resource "aws_s3_bucket" "bad" { bucket = "public-bucket"; acl = "public-read" }'
    r = iac.scan_code(code, "main.tf")
    s3 = [f for f in r["findings"] if f["check_id"] == "tf-s3-public-acl"]
    assert len(s3) > 0, f"No S3 findings in {r['findings']}"
    assert s3[0]["status"] == "FAIL"
```
Apply identically for `cfn-s3-public-acl` etc. using YAML-format CFN code strings (per RESEARCH.md Code Examples section, already drafted `test_iac_scan_cfn_s3_public_acl`) plus a `test_detect_provider_yaml_cloudformation` test.

**Pattern to extend for CHK-03** (`backend/tests/test_iac_scanner.py:69-76`) — **must not be broken, only extended with a new assertion**:
```python
def test_container_scan_image():
    import container_scanner_service as cs
    with patch("container_scanner_service._find_trivy", return_value=None):
        r = cs.scan_image("nginx:latest")
    assert "scan_id" in r
    assert r["image"] == "nginx:latest"
    assert r["total"] > 0
    assert "vulns" in r
    # NEW: assert r["simulated"] is True
```

---

### `backend/tests/test_cloud_accounts.py` (test) — CHK-01, Gate 1

**Analog:** `backend/tests/test_iac_scanner.py::test_iac_scan_config` (lines 62-67) — same `_build`/`_mkdb` + `TestClient` pattern applied to a different endpoints router

```python
# Source: backend/tests/test_iac_scanner.py:62-67
def test_iac_scan_config():
    db = _mkdb(); u = _mkuser(); c = _build("iac_scanner_endpoints", db, u)
    r = c.get("/api/iac/scan-config")
    assert r.status_code == 200
    r2 = c.post("/api/iac/scan-config", json={"severity_threshold": "high", "auto_scan_enabled": True})
    assert r2.status_code == 200
```
**Pattern to copy:** Use `_build("cloud_account_endpoints", db, u)` and POST to the account-registration route with `{"provider": "kubernetes", ...}` to assert 200/201 once `_VALID_PROVIDERS` is widened (`test_register_kubernetes_account`). Read `test_cloud_accounts.py`'s existing tests first for the exact endpoint path and payload shape used for aws/gcp registration, then mirror it for kubernetes/digitalocean.

## Shared Patterns

### Provider-Allowlist Literal Widening (CHK-01)
**Source:** Four independent literals — `cloud_checks_service.py:34`, `cloud_checks_endpoints.py:73`, `cloud_account_endpoints.py:13`, `mcp_server_endpoints.py:78` (plus cosmetic string at `mcp_server_endpoints.py:24`)
**Apply to:** All four gate files, in lockstep, in the same commit/plan step — do not treat any one as "the fix." No shared constants module is to be introduced (see RESEARCH.md Don't Hand-Roll) — edit each literal directly.

### IaC Rule-Dict Shape (CHK-02)
**Source:** `backend/iac_scanner_service.py:12-28` (Terraform rules), `scan_code()` at lines 45-91 (provider-agnostic dispatch, unchanged)
**Apply to:** All 18 new CFN rules — same keys (`id`, `name`, `description`, `provider`, `severity`, `pattern`, `negative_pattern`, optional `vulnerable_marker`, optional `scope_lines`). Never invent a parallel `scan_cloudformation()` function.

### Simulated-Data Labeling (CHK-03)
**Source:** `backend/container_scanner_service.py:88` (`_simulated_results()`), mirrors the existing codebase precedent in `finops_service.py`'s `_generate_simulated_spend()` (same "logs a warning + returns a differently-sourced-but-same-shaped dict" pattern, per RESEARCH.md Don't Hand-Roll)
**Apply to:** Both the simulated-path and real-Trivy-path return dicts in `container_scanner_service.py`, and the `ContainerScanResponse` TS interface + 3 render sites in `IacContainerDashboard.tsx`.

### Test Harness (`_mkdb`/`_mkuser`/`_build`)
**Source:** `backend/tests/test_iac_scanner.py:8-40`
**Apply to:** `test_cloud_checks_expansion.py` (new tests) and `test_cloud_accounts.py` (new registration test) — reuse verbatim, adjusting only the collection-attribute path (`db.<col>` vs `db._db.<col>`) to match each service module's actual `self._db()` access pattern.

## No Analog Found

None — every file in scope for this phase already exists and contains the exact pattern it needs to be extended with (this is a pure wiring/extension phase per RESEARCH.md's own framing: "not a new-technology phase").

## Metadata

**Analog search scope:** `backend/cloud_checks_service.py`, `backend/cloud_checks_endpoints.py`, `backend/cloud_account_endpoints.py`, `backend/mcp_server_endpoints.py`, `backend/iac_scanner_service.py`, `backend/container_scanner_service.py`, `components/IacContainerDashboard.tsx`, `backend/tests/test_iac_scanner.py`, `backend/tests/test_cloud_checks_expansion.py` — all read directly this session (line numbers verified live, not solely inherited from RESEARCH.md)
**Files scanned:** 9 source/test files read in full or targeted ranges; `backend/tests/test_cloud_accounts.py` referenced but not re-read in full (planner/implementer should read it before writing new tests, per CLAUDE.md "always read before editing")
**Pattern extraction date:** 2026-07-06
