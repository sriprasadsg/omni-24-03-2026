# Phase 41: CSPM Provider Expansion (OCI, Alibaba, Cloudflare) - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 11
**Analogs found:** 11 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/cloud_checks_oci.py` (new) | model/config (check-definition data module) | batch | `backend/cloud_checks_aws.py` | exact |
| `backend/cloud_checks_alibaba.py` (new) | model/config | batch | `backend/cloud_checks_aws.py` | exact |
| `backend/cloud_checks_cloudflare.py` (new) | model/config | batch | `backend/cloud_checks_aws.py` | exact |
| `backend/cloud_checks_service.py` (modified) | service | CRUD/batch | itself (existing import + `RUNNABLE_PROVIDERS`/`CLOUD_CHECKS` composition block) | exact |
| `backend/oci_ingest.py` (modified — add `poll_oci_cspm_findings`) | service | request-response (external API poll → DB write) | `backend/mongodb_atlas_ingest.py` | exact |
| `backend/alibaba_ingest.py` (modified — add `poll_alibaba_cspm_findings`, V2 SDK) | service | request-response | `backend/mongodb_atlas_ingest.py` | exact |
| `backend/cloudflare_ingest.py` (modified — add `poll_cloudflare_cspm_findings`) | service | request-response | `backend/mongodb_atlas_ingest.py` | exact |
| `backend/cloud_accounts_service.py` (modified — `scan_account()` if/elif ladder) | service | request-response/CRUD | itself, `microsoft365`/`mongodb_atlas` branches (lines 111-122) | exact |
| `backend/requirements.txt` (modified) | config | — | existing `oci`/`cloudflare` pins | exact |
| `components/AddCloudAccountModal.tsx` (modified) | component | request-response (form submit) | itself + `services/apiService.ts::addCloudAccount` | exact (bug-fix + extend) |
| `services/apiService.ts::addCloudAccount` (modified) | service (API client) | request-response | `backend/cloud_account_endpoints.py::register_account` (payload contract) | exact |
| `components/CloudChecksScanner.tsx` (modified — provider maps + SIMULATED badge) | component | request-response | `components/IacContainerDashboard.tsx` (simulated badge pattern) | role-match |

## Pattern Assignments

### `backend/cloud_checks_oci.py`, `backend/cloud_checks_alibaba.py`, `backend/cloud_checks_cloudflare.py` (model/config, batch)

**Analog:** `backend/cloud_checks_aws.py` (verbatim shape confirmed live)

**Module pattern** (`backend/cloud_checks_aws.py:1-3`):
```python
"""AWS cloud security check definitions. Used by cloud_checks_service.py."""
AWS_CHECKS = [
    # ─── IAM ────────────────────────────────────────────────────────────────
    {"id": "aws-iam-001", "name": "Root account MFA enabled", "description": "AWS root account must have MFA enabled", "provider": "aws", "service": "iam", "severity": "critical", "frameworks": ["CIS-1.1", "NIST-IA-2", "PCI-8.3", "SOC2-CC6.1"], "remediation": "Enable MFA for the root account via IAM console."},
    ...
]
```

**Required dict keys per entry:** `id` (kebab-case, `<provider>-<service>-NNN`), `name`, `description`, `provider` (must exactly match the `RUNNABLE_PROVIDERS`/scan_account provider string: `"oci"`, `"alibaba"`, `"cloudflare"`), `service` (category tag — use the D-03-mandated shared categories: `iam`, `storage`, `encryption`, `logging`), `severity` (`critical`/`high`/`medium`/`low`), `frameworks` (list of strings — use `CIS-OCI-*` for OCI, Alibaba Config/SAS baseline IDs for Alibaba, Cloudflare Security Center taxonomy tags for Cloudflare per D-03), `remediation` (imperative sentence).

Target ~8-10 entries per file per D-03, grouped by the same `# ─── CATEGORY ─── ` comment-banner convention AWS uses.

---

### `backend/cloud_checks_service.py` (modified)

**Analog:** itself — existing composition block

**Current state** (`backend/cloud_checks_service.py:9-14, 31, 37-38`):
```python
from cloud_checks_aws import AWS_CHECKS
from cloud_checks_azure import AZURE_CHECKS
from cloud_checks_gcp import GCP_CHECKS
from cloud_checks_k8s import K8S_CHECKS
from cloud_checks_m365 import M365_CHECKS
from cloud_checks_mongodb_atlas import MONGODB_ATLAS_CHECKS
...
CLOUD_CHECKS: List[Dict[str, Any]] = AWS_CHECKS + AZURE_CHECKS + GCP_CHECKS + K8S_CHECKS + DO_CHECKS + M365_CHECKS + MONGODB_ATLAS_CHECKS
...
RUNNABLE_PROVIDERS = ("aws", "azure", "gcp", "kubernetes", "digitalocean", "microsoft365", "mongodb_atlas")
_RUNNABLE_CHECKS_COUNT = len([c for c in CLOUD_CHECKS if c["provider"] in RUNNABLE_PROVIDERS])
```

**Required change:** add 3 imports (`from cloud_checks_oci import OCI_CHECKS`, etc.), append `+ OCI_CHECKS + ALIBABA_CHECKS + CLOUDFLARE_CHECKS` to the `CLOUD_CHECKS` sum, and append `"oci", "alibaba", "cloudflare"` to the `RUNNABLE_PROVIDERS` tuple. This is the single load-bearing gate per PITFALLS.md/RESEARCH.md — do not touch `cloud_checks_endpoints.py` or `cloud_account_endpoints.py`, both already list all 3 providers (verified lines below).

`cloud_account_endpoints.py:13` (already correct, no change needed):
```python
_VALID_PROVIDERS = {"aws", "azure", "gcp", "kubernetes", "digitalocean", "microsoft365", "mongodb_atlas", "oci", "alibaba", "cloudflare"}
```

---

### `backend/oci_ingest.py`, `backend/alibaba_ingest.py`, `backend/cloudflare_ingest.py` (modified — add CSPM `poll_*_cspm_findings`)

**Analog:** `backend/mongodb_atlas_ingest.py` (full file, 85 lines — the only existing 3-arg `(config, account_id, tenant_id) -> int` real-ingest-to-`cloud_findings` pattern in the codebase)

**Full reference pattern** (`backend/mongodb_atlas_ingest.py:1-85`):
```python
import asyncio, logging, uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

def _parse_atlas_finding(finding: Dict[str, Any], account_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()), "tenantId": tenant_id, "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "mongodb_atlas", "service": "cluster",
        "checkId": f"ATLAS-{cluster_name.upper().replace(' ', '-')}",
        "title": f"Atlas Cluster Setting: {cluster_name}",
        "description": f"...",
        "severity": severity, "status": "FAIL",
        "remediation": "Review cluster security configuration settings.",
        "raw_message": finding,
    }

async def poll_mongodb_atlas_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    public_key = config.get("atlas_public_key", "")
    ...
    if not all([public_key, private_key, project_id]):
        logger.warning("[Atlas] Incomplete credentials for tenant %s", tenant_id)
        return 0
    try:
        data = await asyncio.to_thread(_atlas_get_sync, url, public_key, private_key)
        findings = [_parse_atlas_finding(c, account_id, tenant_id) for c in data.get("results", [])]
        if not findings:
            return 0
        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        logger.info("[Atlas] Ingested %d findings for tenant %s", len(findings), tenant_id)
        return len(findings)
    except Exception as exc:
        logger.error("[Atlas] Poll failed for tenant %s: %s", tenant_id, exc)
        return 0
```

**cloud_findings document shape (must match exactly):** `id`, `tenantId`, `accountId`, `timestamp`, `provider`, `service`, `checkId`, `title`, `description` (optional), `severity`, `status` (`PASS`/`FAIL`), `remediation`, `raw_message`.

**Existing (mocked, 2-arg, SIEM-domain) code to NOT modify in place** — `backend/oci_ingest.py:1-105`, `backend/alibaba_ingest.py:1-94`, `backend/cloudflare_ingest.py:1-93` already define:
- `_make_oci_client(config)` / `_make_alibaba_client(config)` / `_make_cloudflare_client(config)` — currently return string `"mocked_*_client"`; the real work per RESEARCH.md Pattern 4 is un-mocking these (or a parallel real variant) to instantiate `oci.cloud_guard.CloudGuardClient(oci_config)`, the Alibaba V2 typed client, and the `cloudflare` SDK client respectively.
- `poll_oci_cloud_guard_problems(config, omni_tenant_id)` / `poll_alibaba_sas_alerts(config, omni_tenant_id)` / `poll_cloudflare_zero_trust_events(config, omni_tenant_id)` — 2-arg, writes `db.security_events`, still live call sites for `cloud_integrations_endpoints.py`'s SIEM `/test`/`/discover` routes. **Do not change their signature or write target** (Pitfall 3).
- Existing `_severity_map()` helpers in each file — reusable/cloneable for the new CSPM parse functions (OCI: `CRITICAL/HIGH/MEDIUM/LOW`; Cloudflare: same; Alibaba: int-keyed `1-4`).

**Required addition per file:** a new function `poll_oci_cspm_findings(config, account_id, tenant_id) -> int` / `poll_alibaba_cspm_findings(...)` / `poll_cloudflare_cspm_findings(...)`, cloned from the `mongodb_atlas_ingest.py` template above, sharing (or adding a real-variant of) each file's `_make_*_client()` helper, writing to `db.cloud_findings` (not `security_events`). Alibaba's new function must use the V2 typed SDK (`alibabacloud_config20200907`/`alibabacloud_sas20181203`), never the existing `aliyunsdkcore.client.AcsClient` import already in `alibaba_ingest.py:18`.

**Un-mocked real-call sketch** (from RESEARCH.md Pattern 3, OCI example):
```python
async def poll_oci_cspm_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    if not _OCI_SDK_AVAILABLE:
        return 0
    client = _make_oci_client(config)  # real: oci.cloud_guard.CloudGuardClient(oci_config)
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

---

### `backend/cloud_accounts_service.py` (modified — `scan_account()` ladder)

**Analog:** itself, existing `microsoft365`/`mongodb_atlas` branches

**Exact current pattern to clone** (`backend/cloud_accounts_service.py:99-124`):
```python
async def scan_account(db, account_id: str, tenant_id: str) -> dict:
    from cloud_checks_service import cloud_checks_service
    account = await db._db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id})
    if not account:
        return {"error": "Cloud account not found", "ran": 0}
    await db._db.cloud_accounts.update_one(
        {"id": account_id, "tenantId": tenant_id}, {"$set": {"scan_status": "scanning"}}
    )
    try:
        provider = account.get("provider", "aws")
        if provider == "microsoft365":
            from m365_ingest import poll_m365_secure_scores
            creds = _decrypt(account.get("credentials_ref", ""))
            try: config = json.loads(creds)
            except: config = {}
            await poll_m365_secure_scores(config, account_id, tenant_id)
        elif provider == "mongodb_atlas":
            from mongodb_atlas_ingest import poll_mongodb_atlas_findings
            creds = _decrypt(account.get("credentials_ref", ""))
            try: config = json.loads(creds)
            except: config = {}
            await poll_mongodb_atlas_findings(config, account_id, tenant_id)

        result = await cloud_checks_service.run_checks(account_id, provider, tenant_id)
        ...
```

**Required addition:** three more `elif` branches — `provider == "oci"` → `from oci_ingest import poll_oci_cspm_findings`, `provider == "alibaba"` → `from alibaba_ingest import poll_alibaba_cspm_findings`, `provider == "cloudflare"` → `from cloudflare_ingest import poll_cloudflare_cspm_findings` — each following the identical decrypt/`json.loads`/call shape shown above. Function-local imports (not top-of-file) is the established convention here — preserve it (test mocking in `test_cloud_findings_ingest.py` patches the flat module attribute, resolved at call time).

**Credential encryption (`_encrypt`/`_decrypt`, lines 186-191):** reuse as-is, `CLOUD_CREDENTIALS_KEY` Fernet — no new key management for OCI/Alibaba/Cloudflare credential blobs.

---

### `components/AddCloudAccountModal.tsx` + `services/apiService.ts::addCloudAccount` (modified)

**Analog:** itself + `backend/cloud_account_endpoints.py::register_account` (payload contract)

**Current broken payload** (`services/apiService.ts:2646-2656`):
```typescript
export const addCloudAccount = async (data: any, tenantId: string) => {
    try {
        const res = await authFetch(`${API_BASE}/cloud-accounts`, {
            method: 'POST',
            body: JSON.stringify({
                provider: (data.provider || 'aws').toLowerCase(),
                name: data.name,
                account_id: data.accountId,
                credentials: data.credentials || {},
            }),
        });
```

**Backend contract it must match** (`backend/cloud_account_endpoints.py:13,36-47`):
```python
_VALID_PROVIDERS = {"aws", "azure", "gcp", "kubernetes", "digitalocean", "microsoft365", "mongodb_atlas", "oci", "alibaba", "cloudflare"}
...
async def register_account(payload: Dict[str, Any] = Body(...), current_user=...):
    if payload.get("provider") not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, ...)
    ...
    if payload.get("credentials_ref") is not None and not isinstance(payload["credentials_ref"], str):
        raise HTTPException(status_code=400, detail="credentials_ref must be a string")
```

**Required fix:** `addCloudAccount()` must send `account_name` (not `name`) and `credentials_ref` as a **JSON string** (not a `credentials` object) — `JSON.stringify(data.credentials || {})` assigned to the `credentials_ref` key, matching `cloud_accounts_service.register_account()`'s `data.get("credentials_ref", "")` read (`backend/cloud_accounts_service.py:48`).

**Form field pattern to extend** (`components/AddCloudAccountModal.tsx:12-27,32-44`): `PROVIDER_META` record keyed by `CloudProvider` union (`OCI`, `Alibaba`, `Cloudflare` already present as options) plus generic `accessKey`/`secretKey` state (lines 32-33, 90-94). Add provider-conditional credential fields per D-04 by branching on `provider` inside the existing "Credentials" fieldset block (around line 90) — OCI needs 4 fields (tenancy OCID, user OCID, fingerprint, private key textarea), Alibaba needs 2 (access key ID + secret — reuse existing `accessKey`/`secretKey` state), Cloudflare needs 1 (API token). Build the `credentials_ref` JSON string from whichever field set is active before calling `onSave`.

---

### `components/CloudChecksScanner.tsx` (modified — provider maps + SIMULATED badge)

**Analog (provider maps):** itself, existing hardcoded arrays

**Current state** (`components/CloudChecksScanner.tsx:45,139,175`):
```typescript
const PROVIDER_ICONS: Record<string, string> = { aws: '☁️', azure: '🔵', gcp: '🟢' };
...
{['aws', 'azure', 'gcp'].map(prov => { ... })}
...
{['aws', 'azure', 'gcp'].map(p => <option key={p}>{p}</option>)}
```

**Required change:** add `oci`, `alibaba`, `cloudflare` entries/values to `PROVIDER_ICONS` and both `['aws','azure','gcp']` literal arrays (lines 139, 175). Consider also digitalocean/kubernetes/microsoft365/mongodb_atlas if time allows (pre-existing gap, flagged adjacent-but-optional in RESEARCH.md Pitfall 5).

**Analog (SIMULATED badge):** `components/IacContainerDashboard.tsx:380-412` — clone verbatim pattern:
```tsx
{containerResult.simulated && (
  <span className="flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400">
    <AlertTriangle className="w-3 h-3 shrink-0" /> SIMULATED — no findings imported yet
  </span>
)}
```
Compact table-cell variant also present at `components/IacContainerDashboard.tsx:465`:
```tsx
{h.simulated && <span className="px-1.5 py-0.5 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 rounded">sim</span>}
```
Add `simulated?: boolean` to `CloudChecksScanner.tsx`'s result/check TS interface (currently missing it — backend already returns the field from `run_checks()`) and render the badge in the results table row (near lines 225, 257 where `PROVIDER_ICONS[r.provider]` is already rendered).

---

## Shared Patterns

### Tenant isolation / `db._db` raw accessor
**Source:** `backend/cloud_accounts_service.py:1-13` (module docstring), all queries e.g. line 101, 104
**Apply to:** Any new query added to `cloud_accounts_service.py` — always manually include `"tenantId": tenant_id` in the filter; do NOT switch to the tenant-isolation-wrapped `db.cloud_accounts` accessor used elsewhere in this codebase without also removing the manual tenantId filters (explicitly flagged as unsafe to mix, see docstring lines 1-13).

### Credential encryption
**Source:** `backend/cloud_accounts_service.py:22-35,186-191` (`_FERNET`, `_encrypt`, `_decrypt`)
**Apply to:** All 3 new provider credential blobs — reuse `CLOUD_CREDENTIALS_KEY` Fernet encryption unchanged, no new key management.

### `cloud_findings` document shape
**Source:** `backend/mongodb_atlas_ingest.py:35-49` (`_parse_atlas_finding`)
**Apply to:** All 3 new `poll_*_cspm_findings` parse functions — exact field set: `id, tenantId, accountId, timestamp, provider, service, checkId, title, description, severity, status, remediation, raw_message`.

### Simulated flag computation (no client-side change needed)
**Source:** `backend/cloud_checks_service.py` `run_checks()` (`"simulated": not has_real_findings`, already generic per-provider)
**Apply to:** Nothing new needed backend-side once `cloud_findings` gets real documents for oci/alibaba/cloudflare — only the frontend badge rendering is missing (see `CloudChecksScanner.tsx` above).

### Function-local imports inside `scan_account()`
**Source:** `backend/cloud_accounts_service.py:112,118` (`from m365_ingest import poll_m365_secure_scores` inside the `if` branch, not at module top)
**Apply to:** The 3 new `elif` branches — keep imports function-local (deliberate pattern; test suite patches flat module attributes resolved at call time, per RESEARCH.md's test template note).

## No Analog Found

None — all 11 files/changes have a strong existing analog in the codebase (mongodb_atlas_ingest.py and cloud_checks_aws.py cover the bulk of backend patterns; IacContainerDashboard.tsx covers the one net-new frontend pattern).

## Metadata

**Analog search scope:** `backend/*.py` (cloud_checks_*, *_ingest.py, cloud_accounts_service.py, cloud_account_endpoints.py), `components/*.tsx` (AddCloudAccountModal, CloudChecksScanner, IacContainerDashboard), `services/apiService.ts`
**Files scanned:** cloud_checks_service.py, cloud_checks_aws.py, cloud_checks_service.py's DO_CHECKS block, mongodb_atlas_ingest.py, oci_ingest.py, alibaba_ingest.py, cloudflare_ingest.py, cloud_accounts_service.py, cloud_account_endpoints.py, AddCloudAccountModal.tsx, apiService.ts (addCloudAccount), CloudChecksScanner.tsx, IacContainerDashboard.tsx
**Pattern extraction date:** 2026-07-21
