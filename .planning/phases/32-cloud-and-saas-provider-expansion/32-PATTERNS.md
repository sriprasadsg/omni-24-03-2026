# Phase 32: Cloud and SaaS Provider Expansion - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 12 (3 modified endpoints/services, 5 new ingest modules, 1 new posture service, 1 modified frontend component, 3 test files + 1 extended)
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/oci_ingest.py` (NEW) | service (ingest module) | event-driven / batch poll | `backend/azure_defender_ingest.py` | exact |
| `backend/alibaba_ingest.py` (NEW) | service (ingest module) | event-driven / batch poll | `backend/gcp_scc_ingest.py` | exact |
| `backend/cloudflare_ingest.py` (NEW) | service (ingest module) | event-driven / batch poll | `backend/azure_defender_ingest.py` | exact |
| `backend/m365_ingest.py` (NEW, optional worked-example) | service (ingest module) | event-driven / batch poll | `backend/gcp_scc_ingest.py` (auth-then-poll shape) | role-match |
| `backend/mongodb_atlas_ingest.py` (NEW, optional worked-example) | service (ingest module) | event-driven / batch poll | `backend/azure_defender_ingest.py` (poll+insert shape) | role-match |
| `backend/cloud_integrations_endpoints.py` (MODIFIED) | controller/route (FastAPI router) | request-response, dispatch-to-ingest | itself (existing `test_integration`/`trigger_cloud_discovery` dispatch block) | exact — extend in place |
| `backend/cloud_checks_service.py` (MODIFIED) | service (catalog + evaluation engine) | CRUD (catalog match against Mongo) | itself (`RUNNABLE_PROVIDERS`, `CLOUD_CHECKS` concatenation, `run_checks()`) | exact — extend in place |
| `backend/cloud_checks_m365.py` (NEW) | model/config (check catalog) | N/A (static data) | `backend/cloud_checks_service.py`'s inline `DO_CHECKS` list (same dict shape) — real per-provider files: `cloud_checks_aws.py`/`cloud_checks_k8s.py` | exact |
| `backend/cloud_checks_mongodb_atlas.py` (NEW) | model/config (check catalog) | N/A (static data) | same as above | exact |
| `backend/cloud_account_endpoints.py` (MODIFIED) | controller/route | request-response, validation gate | itself (`_VALID_PROVIDERS` set, line 13) | exact — widen in place |
| `backend/saas_posture_checks_service.py` (NEW) | service (reshape/evaluation layer) | transform (evidence → check result) | `backend/saas_integration_service.py` (`pull_*_evidence`, `pull_all_evidence`) + `cloud_checks_service.py` (catalog/result shape) | role-match (hybrid of both) |
| `backend/saas_posture_checks_endpoints.py` (NEW) | controller/route | request-response | `backend/cloud_account_endpoints.py` (thin router calling a service module) | role-match |
| `backend/attack_path_endpoints.py` (MODIFIED — delete duplicate logic) | controller/route | request-response | `backend/attack_path_service.py` (the real logic to call instead) | exact (self-referential fix) |
| `backend/attack_path_service.py` (MODIFIED — add `simulated` flag) | service (correlation engine) | transform / CRUD | itself | exact |
| `components/AttackPathDashboard.tsx` (MODIFIED) | component | request-response (renders API payload) | `components/IacContainerDashboard.tsx` (SIMULATED badge convention) | role-match |
| `backend/tests/test_cloud_integrations.py` (NEW) | test | N/A | `backend/tests/test_automation_and_baa.py` (mock-db helper convention) | exact |
| `backend/tests/test_attack_path.py` (NEW) | test | N/A | `backend/tests/test_automation_and_baa.py` | exact |
| `backend/tests/test_saas_posture_checks.py` (NEW) | test | N/A | `backend/tests/test_cloud_checks_expansion.py` (`_chain`/`_mkdb` helper convention, more directly applicable since it's async-service-level, not HTTP-level) | exact |
| `backend/tests/test_cloud_checks_expansion.py` (EXTENDED) | test | N/A | itself | exact |

## Pattern Assignments

### `backend/oci_ingest.py`, `backend/alibaba_ingest.py`, `backend/cloudflare_ingest.py` (service, event-driven poll)

**Analog:** `backend/azure_defender_ingest.py` (230 lines) — read in full. Secondary analog: `backend/gcp_scc_ingest.py` (253 lines) for the "auth via decoded service-account/API-key JSON, then list, then parse" variant (closer to Cloudflare's bearer-token REST shape and Alibaba's access-key shape).

**Imports / SDK-availability guard pattern** (`azure_defender_ingest.py` lines 1-24):
```python
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

try:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.security import SecurityCenter
    _AZURE_SDK_AVAILABLE = True
except ImportError:
    _AZURE_SDK_AVAILABLE = False
    logger.warning("[AzureDefender] azure-mgmt-security not installed — Azure Defender ingest disabled")
```
Clone this shape exactly for each new provider: `_OCI_SDK_AVAILABLE` guarding `import oci`, `_ALIBABA_SDK_AVAILABLE` guarding `import aliyunsdkcore`, `_CLOUDFLARE_SDK_AVAILABLE` guarding `import cloudflare` (or skip the try/except entirely for Cloudflare if the planner chooses raw httpx per RESEARCH.md's Alternatives-Considered guidance — in that case follow `gcp_scc_ingest.py`'s `poll_gcp_chronicle()` raw-REST-call shape at lines 155-222 instead).

**Client-builder helper pattern** (`azure_defender_ingest.py` lines 27-36, mirrored by `gcp_scc_ingest.py`'s `_make_scc_client` lines 28-40):
```python
def _make_azure_client(tenant_id: str, client_id: str, client_secret: str, subscription_id: str):
    if not _AZURE_SDK_AVAILABLE:
        return None, None
    credential = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
    client = SecurityCenter(credential, subscription_id)
    return client, subscription_id
```

**Severity-map helper pattern** (`azure_defender_ingest.py` lines 39-45 / `gcp_scc_ingest.py` lines 43-50) — every ingest module normalizes the vendor's severity vocabulary into this codebase's `Critical/High/Medium/Low` scale via a small dict `.get(vendor_value, "Medium")` lookup. Clone verbatim with OCI/Alibaba/Cloudflare's own severity strings as keys.

**Parse-one-alert-into-security_events-shape pattern** (`azure_defender_ingest.py` lines 48-88, `_parse_defender_alert`):
```python
return {
    "id": str(uuid.uuid4()),
    "tenant_id": tenant_id,
    "timestamp": time_generated,
    "log_type": "azure_defender",
    "alert_type": alert_type,
    "title": alert_name,
    "description": description,
    "severity": severity,
    "status": status,
    "compromised_entity": compromised_entity,
    "remote_address": remote_address,
    "resource_identifiers": resource_id,
    "raw_message": f"[Azure Defender] {alert_name}: {description[:200]}",
    "source": "azure_defender_for_cloud",
}
```
Every new ingest module needs a `_parse_<provider>_alert()` returning this exact document shape (`id`, `tenant_id`, `timestamp`, `log_type`, `title`, `description`, `severity`, `status`, `raw_message`, `source` are the required fields every consumer of `security_events` expects; provider-specific extra fields like `compromised_entity`/`finding_name` are additive, not required).

**THE core poll function — clone this control flow exactly** (`azure_defender_ingest.py` lines 91-131, `poll_azure_defender_alerts`):
```python
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
            logger.info("[AzureDefender] No alerts returned for subscription %s", subscription_id)
            return 0
        set_tenant_id(omni_tenant_id)
        db = get_database()
        events = [_parse_defender_alert(a, omni_tenant_id) for a in alerts]
        if events:
            await db.security_events.insert_many(events)
            logger.info("[AzureDefender] Ingested %d alerts for tenant %s", len(events), omni_tenant_id)
        return len(events)
    except Exception as exc:
        logger.error("[AzureDefender] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0
```
The `poll_<provider>_<thing>(config, omni_tenant_id) -> int` signature, the required-field `all([...])` gate before any API call, the `try/except Exception: log + return 0` never-raise contract, and `set_tenant_id()` + `db.security_events.insert_many()` are ALL mandatory — this is the exact shape the executor must clone for `poll_oci_cloud_guard_problems`, `poll_alibaba_sas_alerts`, `poll_cloudflare_zero_trust_events`.

**Background polling loop pattern (optional but present in both analogs)** (`azure_defender_ingest.py` lines 202-231):
```python
async def start_azure_polling():
    logger.info("[AzureDefender] Background polling loop started")
    while True:
        try:
            await asyncio.sleep(300)
            set_tenant_id("platform-admin")
            db = get_database()
            integrations = await db.cloud_integrations.find(
                {"provider": {"$in": ["azure_defender", "microsoft_sentinel"]}, "enabled": True}
            ).to_list(length=100)
            for integ in integrations:
                tenant_id = integ.get("tenant_id") or None
                if not tenant_id:
                    logger.warning("[AzureDefender] Skipping integration %s — no tenant_id configured", integ.get("id", "?"))
                    continue
                provider = integ.get("provider", "")
                cfg = integ.get("config", {})
                if provider == "azure_defender":
                    await poll_azure_defender_alerts(cfg, tenant_id)
                elif provider == "microsoft_sentinel":
                    await poll_sentinel_logs(cfg, tenant_id)
        except Exception as exc:
            logger.error("[AzureDefender] Polling loop error: %s", exc)
```
Not strictly required by PROV-01's requirement text (test/discover buttons already wire per-request polls) — include only if the planner wants full parity with the Azure/GCP precedent.

---

### `backend/cloud_integrations_endpoints.py` (MODIFIED — controller, request-response)

**Analog:** itself (481 lines, read in full).

**`_SECRET_FIELDS` widening point** (line 19):
```python
_SECRET_FIELDS = frozenset({"client_secret", "service_account_json", "aws_secret_key"})
```
Add the 3 new providers' credential field names actually declared in `SUPPORTED_PROVIDERS` (lines 132-166 already list `oci_private_key`, `access_key_secret` (Alibaba), `cf_api_token` (Cloudflare) as `required_fields` — cross-check each against this frozenset and add any missing ones). Same widening applies to `_mask_secrets()`'s inline `secret_keys` set at line 179 — **these two sets currently duplicate each other and both need editing in lockstep** (a third mini-instance of the Phase 25 "widen every gate" lesson).

**Dispatch-block widening point — `test_integration()`** (lines 329-343, the exact `elif` ladder to extend):
```python
try:
    if provider in ("azure_defender",):
        from azure_defender_ingest import poll_azure_defender_alerts
        count = await poll_azure_defender_alerts(config, integ.get("tenant_id", ""))
    elif provider == "microsoft_sentinel":
        from azure_defender_ingest import poll_sentinel_logs
        count = await poll_sentinel_logs(config, integ.get("tenant_id", ""))
    elif provider == "gcp_scc":
        from gcp_scc_ingest import poll_gcp_scc_findings
        count = await poll_gcp_scc_findings(config, integ.get("tenant_id", ""))
    elif provider == "gcp_chronicle":
        from gcp_scc_ingest import poll_gcp_chronicle
        count = await poll_gcp_chronicle(config, integ.get("tenant_id", ""))
    elif provider in ("aws_guardduty", "aws_securityhub"):
        count = 0
```
Add three new `elif` branches for `oci_cloud_guard`, `alibaba_sas`, `cloudflare_zero_trust` calling the new ingest modules' `poll_*` functions — same lazy `from x_ingest import y` inline-import style already used for every existing branch (avoids import cost/circular-import risk when the SDK isn't installed).

**Second dispatch site that must be widened in lockstep — `trigger_cloud_discovery()`** (lines 377-388):
```python
for integ in integrations:
    try:
        provider = integ.get("provider", "")
        config = integ.get("config", {})
        if provider in ("azure_defender", "microsoft_sentinel"):
            from azure_defender_ingest import poll_azure_defender_alerts
            real_count += await poll_azure_defender_alerts(config, tenant_id)
        elif provider in ("gcp_scc", "gcp_chronicle"):
            from gcp_scc_ingest import poll_gcp_scc_findings
            real_count += await poll_gcp_scc_findings(config, tenant_id)
    except Exception as e:
        logger.warning("Cloud provider poll failed for %s: %s", provider, e)
```
This is a **second, independent dispatch block** — `test_integration()` and `trigger_cloud_discovery()` both need the new `elif` branches; missing one is a silent gap (same class of bug Phase 25 flagged for `RUNNABLE_PROVIDERS`/`_VALID_PROVIDERS`/etc.).

---

### `backend/cloud_checks_m365.py`, `backend/cloud_checks_mongodb_atlas.py` (NEW — model/config, static catalog)

**Analog:** the inline `DO_CHECKS` list in `cloud_checks_service.py` lines 15-26 (the dict shape to clone) — real per-provider file precedent is `cloud_checks_aws.py`/`cloud_checks_k8s.py` (imported at lines 9-12), not read this session but same shape confirmed via the DO_CHECKS inline example and the `run_checks()` field access pattern below.

**Exact dict shape required per check entry** (`cloud_checks_service.py` line 16, one entry, annotated):
```python
{"id": "do-fw-001", "name": "DO Firewall Rules Restrict SSH", "description": "...", "provider": "digitalocean", "service": "firewall", "severity": "critical", "frameworks": ["NIST-SC-7", "PCI-1.2.1"], "remediation": "Restrict SSH inbound rules to trusted IPs in DO Cloud Firewall."}
```
`M365_CHECKS`/`MONGODB_ATLAS_CHECKS` must be `List[Dict[str, Any]]` with every entry containing `id`, `name`, `description`, `provider` (must be exactly `"microsoft365"` / `"mongodb_atlas"` — matches what `cloud_account_endpoints.py`'s `_VALID_PROVIDERS` and the endpoint payload's `provider` field will use), `service`, `severity`, `frameworks`, `remediation`. `run_checks()` (see below) reads `check["id"]`, `check["name"]`, `check["service"]`, `check["severity"]`, `check["frameworks"]`, `check["remediation"]`, `check["provider"]` — all six/seven keys are load-bearing, not optional.

---

### `backend/cloud_checks_service.py` (MODIFIED — service, CRUD/catalog-match)

**Analog:** itself.

**Import + concatenation widening point** (lines 9-29):
```python
from cloud_checks_aws import AWS_CHECKS
from cloud_checks_azure import AZURE_CHECKS
from cloud_checks_gcp import GCP_CHECKS
from cloud_checks_k8s import K8S_CHECKS
# ... DO_CHECKS inline ...
CLOUD_CHECKS: List[Dict[str, Any]] = AWS_CHECKS + AZURE_CHECKS + GCP_CHECKS + K8S_CHECKS + DO_CHECKS
```
Add `from cloud_checks_m365 import M365_CHECKS` and `from cloud_checks_mongodb_atlas import MONGODB_ATLAS_CHECKS`, append both to the `CLOUD_CHECKS` concatenation.

**`RUNNABLE_PROVIDERS` widening point** (lines 31-36):
```python
RUNNABLE_PROVIDERS = ("aws", "azure", "gcp", "kubernetes", "digitalocean")
_RUNNABLE_CHECKS_COUNT = len([c for c in CLOUD_CHECKS if c["provider"] in RUNNABLE_PROVIDERS])
```
Add `"microsoft365"` and `"mongodb_atlas"` to the tuple. `_RUNNABLE_CHECKS_COUNT` recomputes automatically from this — no separate edit needed there, but the `test_coverage_denominator_includes_new_providers` test pattern (see Test section) should assert this stays in sync.

**Exact evaluation code path that reads `cloud_findings` — critical for PROV-02 correctness** (`run_checks()`, lines 63-110):
```python
async def run_checks(self, account_id: str, provider: str, tenant_id: str, credentials_hint: Optional[str] = None) -> Dict:
    if provider not in RUNNABLE_PROVIDERS:
        return {"error": f"provider must be one of {RUNNABLE_PROVIDERS}", "ran": 0}
    db = self._db()
    account = await db.cloud_accounts.find_one({"id": account_id, "tenantId": tenant_id}, {"_id": 0})
    if not account:
        return {"error": "Cloud account not found", "ran": 0}

    findings_raw = await db.cloud_findings.find(
        {"accountId": account_id, "tenantId": tenant_id}, {"_id": 0}
    ).to_list(length=10000)
    significant_findings = [f for f in findings_raw if f.get("severity") in ("critical", "high", "medium")]
    failing_titles = {f.get("title", "").lower() for f in significant_findings}
    failing_ids = {f.get("checkId", "").lower() for f in significant_findings}

    now = datetime.now(timezone.utc).isoformat()
    upserted = 0
    provider_checks = [c for c in CLOUD_CHECKS if c["provider"] == provider]
    for check in provider_checks:
        cid = check["id"]
        name_lower = check["name"].lower()
        in_findings = cid.lower() in failing_ids or any(
            kw in title for title in failing_titles for kw in name_lower.split()[:3] if len(kw) > 3
        )
        result = "FAIL" if in_findings else "PASS"
        doc = {
            "id": f"ccr-{uuid.uuid4().hex}",
            "tenantId": tenant_id, "accountId": account_id, "provider": provider,
            "checkId": cid, "checkName": check["name"], "service": check["service"],
            "severity": check["severity"], "result": result,
            "frameworks": check["frameworks"], "remediation": check["remediation"],
            "detail": "Based on imported findings from native cloud scanner." if in_findings else "No matching findings found.",
            "checked_at": now,
        }
        await db.cloud_check_results.update_one(
            {"tenantId": tenant_id, "accountId": account_id, "checkId": cid}, {"$set": doc}, upsert=True,
        )
        upserted += 1
    return {"ran": upserted, "accountId": account_id, "provider": provider, "checked_at": now}
```
**No new logic needed here at all** for PROV-02 — `run_checks()` is provider-agnostic (filters `CLOUD_CHECKS` by `check["provider"] == provider`), so once `M365_CHECKS`/`MONGODB_ATLAS_CHECKS` exist and their `provider` field matches `"microsoft365"`/`"mongodb_atlas"`, this function works unmodified for the two new providers, inheriting the same "always PASS because `cloud_findings` is never written" behavior documented in RESEARCH.md — this is expected, not a bug to fix in this phase.

---

### `backend/cloud_account_endpoints.py` (MODIFIED — controller, gate-widening)

**Analog:** itself — this is the exact file+line Phase 25 widened for `kubernetes`/`digitalocean`; find the same diff shape (add tokens to a set literal).

**The widening point** (line 13):
```python
_VALID_PROVIDERS = {"aws", "azure", "gcp", "kubernetes", "digitalocean"}
```
Add `"microsoft365"`, `"mongodb_atlas"`. This is the same string value `register_account()`'s `payload.get("provider")` check compares against (line 42) — no other change to this file needed. Remember also to widen `mcp_server_endpoints.py`'s tuple (per RESEARCH.md's gate 3 — not read this session, but confirmed to exist as a fourth gate; the executor should grep for `_VALID_PROVIDERS`-equivalent tuples there before considering PROV-02 complete).

---

### `backend/saas_posture_checks_service.py` (NEW — service, transform/evaluation)

**Analog A (real data source to reuse, not duplicate):** `backend/saas_integration_service.py` (500 lines, read in full).

**Analog B (catalog + result-record shape to mirror):** `backend/cloud_checks_service.py`'s `run_checks()` (see excerpt above) — the `id`/`checkName`/`service`/`severity`/`result`/`frameworks`/`remediation`/`checked_at` document shape written to `cloud_check_results` is the shape `saas_check_results` should mirror.

**Evidence-pull signature to call (do not duplicate the HTTP calls)** — `pull_all_evidence()`, `saas_integration_service.py` lines 443-496:
```python
async def pull_all_evidence(self, connection: Dict, db) -> List[Dict]:
    """Pull evidence from a SaaS connection and write records to control_evidence.
    Uses _access_token_plain if present (test injection); otherwise decrypts
    access_token_enc from the connection document.
    """
    provider = connection.get("provider", "")
    tenant_id = connection.get("tenant_id", "")
    access_token = connection.get("_access_token_plain") or ""
    if not access_token:
        enc = connection.get("access_token_enc", "")
        if enc:
            try:
                access_token = _decrypt(enc)
            except Exception:
                logger.warning("Failed to decrypt access token for connection %s", connection.get("id"))
    domain = connection.get("domain", "")
    evidence: List[Dict] = []
    try:
        if provider == OAuthProvider.GITHUB:
            evidence = await self.pull_github_evidence(access_token, tenant_id, db)
        elif provider == OAuthProvider.JIRA:
            evidence = await self.pull_jira_evidence(access_token, tenant_id, db, domain=domain)
        elif provider == OAuthProvider.OKTA:
            evidence = await self.pull_okta_evidence(access_token, tenant_id, db, domain=domain)
        elif provider == OAuthProvider.GOOGLE_WORKSPACE:
            evidence = await self.pull_google_workspace_evidence(access_token, tenant_id, db)
        elif provider == OAuthProvider.SLACK:
            evidence = await self.pull_slack_evidence(access_token, tenant_id, db)
        else:
            logger.warning("Unknown provider: %s", provider)
    except Exception as exc:
        logger.warning("Evidence pull failed for provider %s: %s", provider, exc)
    ...
    return evidence
```
Call `saas_integration_service.saas_integration_service.pull_all_evidence(connection, db)` (or the more granular `pull_<provider>_evidence()` if a single provider's checks are being run) from the new file — **never** re-implement an httpx call against GitHub/Jira/Okta/GWS/Slack.

**Evidence item shape each `pull_*_evidence()` already returns** (e.g. `pull_github_evidence`, lines 174-181):
```python
evidence.append({
    "control_id": _CTRL_SECURE_DEV,
    "source": "saas-github",
    "tenant_id": tenant_id,
    "collected_at": collected_at,
    "content": f"GitHub: {pr_count} merged PRs to main branch found",
    "status": "pass" if pr_count > 0 else "no-data",
})
```
Every evidence item has `control_id` (a free-text control name, e.g. `"Access to Source Code Simulation"`, `"Security Patch Status"`, `"MFA for All Users"`, `"Account Security"` — these are the literal control-name strings the new check catalog's `_evidence_control_id` field must match against) and `status` (`"pass"`/`"fail"`/`"no-data"`).

**Full worked mapping-and-write function to clone (RESEARCH.md's own Pattern 3 code, verified consistent with the real source above)**:
```python
async def run_posture_checks(connection: dict, db) -> dict:
    evidence = await saas_integration_service.pull_all_evidence(connection, db)  # reuse — real API calls already made
    ev_by_control = {e["control_id"]: e for e in evidence}
    results = []
    for check in CHECKS_FOR[connection["provider"]]:  # dispatch by connection["provider"] to the right catalog
        ev = ev_by_control.get(check["_evidence_control_id"])
        result = "PASS" if ev and ev.get("status") == "pass" else ("FAIL" if ev else "NO-DATA")
        doc = {
            "id": f"scr-{uuid.uuid4().hex}", "tenantId": connection["tenant_id"], "connectionId": connection["id"],
            "provider": connection["provider"], "checkId": check["id"], "checkName": check["name"],
            "service": check["service"], "severity": check["severity"], "result": result,
            "frameworks": check["frameworks"], "remediation": check["remediation"],
            "detail": ev.get("content", "") if ev else "No evidence collected for this control.",
            "checked_at": _now_iso(),
        }
        await db.saas_check_results.update_one(
            {"tenantId": connection["tenant_id"], "connectionId": connection["id"], "checkId": check["id"]},
            {"$set": doc}, upsert=True,
        )
        results.append(doc)
    return {"ran": len(results), "connectionId": connection["id"]}
```

---

### `backend/saas_posture_checks_endpoints.py` (NEW — controller, request-response)

**Analog:** `backend/cloud_account_endpoints.py`'s thin-router-calling-a-service-module pattern (whole file, 87 lines).

**Router skeleton pattern** (`cloud_account_endpoints.py` lines 1-20):
```python
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict
from database import get_database
from auth_types import TokenData
from rbac_service import rbac_service
import cloud_accounts_service as svc
import logging

router = APIRouter(prefix="/api/cloud-accounts", tags=["Cloud Accounts"])
logger = logging.getLogger(__name__)

def _tid(user: TokenData) -> str:
    return getattr(user, "tenant_id", None) or ""

@router.post("/{account_id}/scan")
async def scan_account(account_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:cloud_security"))):
    db = get_database()
    result = await svc.scan_account(db, account_id, _tid(current_user))
    if result.get("error"):
        status_code = 404 if result["error"] == "Cloud account not found" else 502
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result
```
Use `prefix="/api/saas/posture-checks"`, RBAC-gated with `rbac_service.has_permission(...)` matching whatever permission SaaS/compliance endpoints already use (check `saas_integration_service.py`'s own endpoint file, not read this session — grep for its router before finalizing), and a `POST /{connection_id}/run` handler delegating to `saas_posture_checks_service.run_posture_checks()`.

---

### `backend/attack_path_endpoints.py` + `backend/attack_path_service.py` (MODIFIED — dead-code rewiring)

**Analog:** each other (self-referential fix; both read in full).

**Current (buggy) handler to replace — `attack_path_endpoints.py` lines 66-86:**
```python
@router.get("/attack-paths")
async def get_attack_paths(current_user=Depends(get_current_user)):
    """Get identified attack paths for the tenant."""
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")
    db = get_database()
    stored = await db.attack_paths.find({"tenantId": tenant_id}, {"_id": 0}).sort("timestamp", -1).to_list(length=50)
    if stored:
        return stored
    paths = _seed_paths(tenant_id)
    try:
        await db.attack_paths.insert_many([dict(p) for p in paths])
    except Exception:
        pass
    return paths
```
The whole `_seed_paths()` function (lines 18-63, duplicate demo logic) should be deleted; replace with:
```python
from attack_path_service import get_attack_path_service

@router.get("/attack-paths")
async def get_attack_paths(current_user=Depends(get_current_user)):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")
    db = get_database()
    service = get_attack_path_service(db)
    paths = await service.get_attack_paths(tenant_id)
    return paths
```

**`AttackPathService.get_attack_paths()` — the real correlation logic already exists** (`attack_path_service.py` lines 20-142, dead code, zero call sites today). Key excerpt — real-correlation branch and its fallback boundary (lines 38-73, 133-142):
```python
assets = await self.db.assets.find(query, {"_id": 0}).to_list(length=500)
vulns = await self.db.vulnerabilities.find({**query, "status": {"$ne": "Fixed"}}, {"_id": 0}).to_list(length=500)
if not assets and not vulns:
    vulns = await self.db.cspm_findings.find({**query, "status": {"$nin": ["Resolved", "Suppressed"]}}, {"_id": 0}).to_list(length=200)
...
# No real data available — seed representative demo paths so the dashboard is not blank
if not paths:
    paths = self._seed_demo_paths(tenant_id)
    for p in paths:
        try:
            await self.db.attack_paths.update_one({"id": p["id"]}, {"$set": p}, upsert=True)
        except Exception as e:
            logger.debug("Failed to persist demo attack path: %s", e)
return paths
```

**Add the `simulated` flag to BOTH the real-correlation path dict (line ~107-120) and `_seed_demo_paths()`'s path dict (line ~182-195):**
```python
path = {
    "id": path_id,
    "tenantId": tenant_id,
    "name": f"{entry_name} → {target_name}",
    "nodes": [...],
    "edges": [...],
    "probability": round(probability, 2),
    "impact": ...,
    "openVulnerabilities": len(entry_vulns),
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "simulated": False,   # ADD
}
```
```python
paths.append({
    "id": pid,
    "tenantId": tenant_id,
    "name": s["name"],
    "nodes": [...],
    "edges": [...],
    "probability": s["probability"],
    "impact": s["impact"],
    "openVulnerabilities": s["open_vulns"],
    "timestamp": now,
    "simulated": True,   # ADD
})
```

**Edge-field-name decision (RESEARCH.md's recommendation — keep backend's naming, fix frontend + types.ts):** backend emits `{"source": ..., "target": ..., "vulnerability": ...}` at both call sites (`attack_path_service.py` lines 112-115 and 187-190, `attack_path_endpoints.py`'s now-deleted `_seed_paths` lines 54-56). `types.ts` (lines 1273-1277) currently declares:
```typescript
export interface AttackPathEdge {
  from: string;
  to: string;
  label: string; // e.g., 'Exploits CVE-2023-1234'
}
```
Change to:
```typescript
export interface AttackPathEdge {
  source: string;
  target: string;
  vulnerability: string; // e.g., 'CVE-2023-1234'
}
export interface AttackPath {
  id: string;
  tenantId: string;
  name: string;
  nodes: AttackPathNode[];
  edges: AttackPathEdge[];
  simulated?: boolean;   // ADD
}
```

---

### `components/AttackPathDashboard.tsx` (MODIFIED — component)

**Analog for the SIMULATED badge:** `components/IacContainerDashboard.tsx` lines 367-371 (SIMULATED badge on scan card) and line 37 (`simulated?: boolean` on its own result type):
```tsx
{containerResult.simulated && (
  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 rounded-full text-xs font-semibold">
    <AlertTriangle className="w-3 h-3 shrink-0" /> SIMULATED — not a real Trivy scan
  </span>
)}
```
Adapt the copy to attack-path context, e.g. `SIMULATED — demo scenario, no real assets/vulnerabilities found`. Import `AlertTriangle` from the same icons module `IacContainerDashboard.tsx` uses (check its import line — likely `lucide-react` or local `./icons`; `AttackPathDashboard.tsx` currently imports `NetworkIcon, ShieldAlertIcon, BoxIcon` from `./icons`, line 3 — confirm `AlertTriangle`/equivalent exists there or import from the same source `IacContainerDashboard.tsx` uses).

**Broken edge-label lookup to fix** (`AttackPathDashboard.tsx` line 82, currently always returns `undefined`):
```tsx
{(displayPath.edges || []).find(e => e.from === node.id)?.label}
```
Change to match the backend/types.ts contract fixed above:
```tsx
{(displayPath.edges || []).find(e => e.source === node.id)?.vulnerability}
```

**Badge placement pattern** — add near the existing "High Priority Scenario" badge block (`AttackPathDashboard.tsx` lines 57-62):
```tsx
<div className="glass-premium rounded-3xl p-8 relative overflow-hidden">
    <div className="absolute top-0 right-0 p-8">
        <div className="px-4 py-1.5 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 rounded-full text-xs font-black uppercase tracking-widest animate-pulse border border-red-500/20">
            High Priority Scenario
        </div>
    </div>
```
Insert the simulated badge as a sibling here, conditioned on `displayPath.simulated`.

---

### `backend/tests/test_cloud_integrations.py`, `test_attack_path.py` (NEW — HTTP-route-level tests)

**Analog:** `backend/tests/test_automation_and_baa.py` (316 lines) — clone its full helper block verbatim (this is the codebase's standard FastAPI `TestClient` + mocked-Mongo convention):
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData

def _col(**overrides):
    col = MagicMock()
    col.find_one   = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find       = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.sort    = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col

def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db

def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)

def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app
```
Note: `cloud_integrations_endpoints.py` uses `auth_utils.get_current_user` (its own import, line 14) rather than `authentication_service.get_current_user` — check which module the router actually imports its dependency from and override that exact symbol via `app.dependency_overrides[...]`, per this file's own pattern (`from auth_utils import get_current_user`, not `authentication_service`). `attack_path_endpoints.py` imports from `authentication_service` (line 2) — matches the analog directly.

For `test_attack_path.py`, mock `db.attack_paths`, `db.assets`, `db.vulnerabilities`, `db.cspm_findings` and assert: (a) when `attack_paths` collection is empty and `assets`/`vulns` exist, the real-correlation branch runs and returns paths with `simulated: False`; (b) when everything is empty, `_seed_demo_paths()` runs and returns paths with `simulated: True`; (c) edges use `source`/`target`/`vulnerability` keys.

---

### `backend/tests/test_saas_posture_checks.py` (NEW — service-level async test)

**Analog:** `backend/tests/test_cloud_checks_expansion.py` (57 lines, read in full) — its `_chain`/`_mkdb` helper convention is the better fit here since `saas_posture_checks_service.run_posture_checks()` is called directly (async, no HTTP layer), same as `cloud_checks_service.run_checks()`:
```python
def _chain(result):
    c = MagicMock()
    c.to_list = AsyncMock(return_value=result)
    return c

def _mkdb(account):
    db = MagicMock()
    db.cloud_accounts = MagicMock()
    db.cloud_accounts.find_one = AsyncMock(return_value=account)
    db.cloud_findings = MagicMock()
    db.cloud_findings.find = MagicMock(return_value=_chain([]))
    db.cloud_check_results = MagicMock()
    db.cloud_check_results.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    return db
```
Adapt collection names to `saas_connections`/`saas_check_results`, and additionally mock `saas_integration_service.pull_all_evidence` (or the specific `pull_<provider>_evidence`) via `unittest.mock.patch` to return canned evidence lists with known `status` values, then assert the resulting `saas_check_results` docs have the expected `PASS`/`FAIL`/`NO-DATA` mapping — do not make real HTTP calls in tests (`saas_integration_service.py`'s own test file, `test_saas_integration.py`, referenced in RESEARCH.md as "10/10 tests passing," is the precedent for mocking httpx at the `pull_*_evidence` boundary rather than the raw `httpx.AsyncClient` level).

### `backend/tests/test_cloud_checks_expansion.py` (EXTENDED — existing file, read in full above)

Add `test_run_checks_evaluates_microsoft365` / `test_run_checks_evaluates_mongodb_atlas` following the exact shape of `test_run_checks_evaluates_kubernetes`/`test_run_checks_evaluates_digitalocean` (lines 33-48), and extend `test_coverage_denominator_includes_new_providers` (lines 51-57) to also assert `"microsoft365" in RUNNABLE_PROVIDERS` and `"mongodb_atlas" in RUNNABLE_PROVIDERS`.

## Shared Patterns

### Ingest-module "never raise, always return int count" contract
**Source:** `backend/azure_defender_ingest.py` lines 91-131, `backend/gcp_scc_ingest.py` lines 95-152
**Apply to:** `oci_ingest.py`, `alibaba_ingest.py`, `cloudflare_ingest.py`, and (if built) `m365_ingest.py`/`mongodb_atlas_ingest.py`
```python
try:
    ...
    return len(events)
except Exception as exc:
    logger.error("[<Provider>] Poll failed for tenant %s: %s", omni_tenant_id, exc)
    return 0
```

### Secret-field encryption via `_SECRET_FIELDS`/`_encrypt_secrets`/`_mask_secrets` (one of three parallel Fernet schemes in this codebase — RESEARCH.md Pitfall 4)
**Source:** `backend/cloud_integrations_endpoints.py` lines 16-72, 177-185
**Apply to:** any new provider credential field added to `SUPPORTED_PROVIDERS`' `required_fields`/`optional_fields` — must be added to both `_SECRET_FIELDS` (line 19) and the duplicate inline `secret_keys` set inside `_mask_secrets()` (line 179). Do not introduce a fourth encryption scheme (`saas_integration_service.py`'s `ENCRYPTION_KEY`/`_FERNET` scheme and `cloud_accounts_service.py`'s `CLOUD_CREDENTIALS_KEY` scheme are the other two — none of this phase's files should reach for either of those).

### Provider-registration gate widening ("widen every gate in lockstep" — Phase 25 lesson, reconfirmed this phase)
**Source:** `backend/cloud_account_endpoints.py` line 13 (`_VALID_PROVIDERS`), `backend/cloud_checks_service.py` line 35 (`RUNNABLE_PROVIDERS`)
**Apply to:** PROV-02's M365/MongoDB Atlas widening touches at minimum: `cloud_checks_service.py`'s `RUNNABLE_PROVIDERS`, `cloud_account_endpoints.py`'s `_VALID_PROVIDERS`, `cloud_checks_endpoints.py`'s inline tuple (not read this session — grep before considering done), and `mcp_server_endpoints.py`'s tuple (not read this session — grep before considering done). All four must contain the same provider string literals (`"microsoft365"`, `"mongodb_atlas"`) or the feature will be silently half-registered.

### FastAPI test harness (`TestClient` + mocked Motor collections)
**Source:** `backend/tests/test_automation_and_baa.py` lines 1-52 (`_col`, `_db`, `_user`, `_app` helpers)
**Apply to:** `test_cloud_integrations.py`, `test_attack_path.py` — clone verbatim, swap collection names and dependency-override target per router.

### Async-service-level test harness (mocked Mongo `find().to_list()` chains, no HTTP layer)
**Source:** `backend/tests/test_cloud_checks_expansion.py` lines 13-30 (`_chain`, `_mkdb`)
**Apply to:** `test_saas_posture_checks.py`, extended `test_cloud_checks_expansion.py` cases.

### "SIMULATED" badge convention for demo/fallback data
**Source:** `components/IacContainerDashboard.tsx` lines 367-371, 397-401 (and `simulated?: boolean` field at line 37 of that file's own result type)
**Apply to:** `components/AttackPathDashboard.tsx` (render when `displayPath.simulated === true`), and `backend/attack_path_service.py` (must set the boolean on both the real-correlation and demo-seed path dicts per the excerpt above).

## No Analog Found

None — all 12 target files have a direct or strong role-match analog in the existing codebase. The only file requiring cross-referencing two analogs rather than one is `saas_posture_checks_service.py` (data source from `saas_integration_service.py`, result-document shape from `cloud_checks_service.py`).

## Metadata

**Analog search scope:** `backend/*.py` (ingest/checks/endpoints/services), `backend/tests/*.py`, `components/*.tsx`, `types.ts` — all read in full via targeted `Read` calls guided by RESEARCH.md's file list; no `Glob`/`Grep` exploration needed since RESEARCH.md already named every analog precisely.
**Files scanned:** 12 (all fully read, no file exceeded 585 lines requiring chunked reads except RESEARCH.md itself)
**Pattern extraction date:** 2026-07-08
