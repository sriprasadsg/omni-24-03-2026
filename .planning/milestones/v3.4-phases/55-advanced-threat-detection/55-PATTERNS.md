# Phase 55: Advanced Threat Detection & Response - Pattern Map

**Mapped:** 2026-08-03
**Files analyzed:** 8 (all extensions of existing files; 0 confirmed net-new files, 1 conditional new test file, 1 conditional new small helper module)
**Analogs found:** 8 / 8 (this phase is self-referential — every target file's own current content IS the pattern to extend; RESEARCH.md already traced exact line numbers)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/siem_engine.py` (extend: new `correlate_native_findings()` method) | service (correlation engine) | batch/transform → event-driven alert | `backend/native_security_ops_endpoints.py` (`get_findings`) for the bounded-read/normalize/merge shape; `siem_engine.py` itself (`_evaluate_rules`/`_match_rule`/`_trigger_alert`) for the rule-eval loop to reuse | exact (self) |
| `backend/threat_intel_endpoints.py` (extend enrichment path) | service/route | request-response | `backend/threat_intel_endpoints.py` itself (`enrich_security_event`) | exact (self) |
| `backend/remediation_playbook_service.py` (extend `select_playbook()` with `elif finding_type == "anomaly":`) | service (pure dispatcher) | transform | `remediation_playbook_service.py` itself — existing `fim`/`nscan`/`vuln` branches | exact (self) |
| `backend/ueba_service.py` (new call site: after `analyze_login`/`analyze_data_access`/`report_shadow_ai` produce `is_anomalous=True`, build `RemediationFinding` + call `.remediate()`) | service (event-driven trigger) | event-driven | `ueba_service.py`'s own `report_shadow_ai` → `background_tasks.add_task(_persist_alert, ...)` pattern (line 314-320) | exact (self) |
| `backend/autonomous_remediation_service.py` | UNCHANGED (only a new `finding_type` value flows through it) | — | n/a — no edit | n/a |
| `backend/webhook_service.py` | UNCHANGED (`trigger_webhook()` consumed as-is) | — | n/a — no edit | n/a |
| `backend/ocsf_endpoints.py` (or new small `soc_integration_service.py` if 500-line cap would be breached) — new OCSF payload builder + 3 outbound push call sites | service (event-driven, fire-and-forget) | event-driven / request-response (outbound) | `backend/ocsf_endpoints.py` itself (`ocsf_findings` OCSF-shape builder) + `backend/notification_manager.py` (`send_notification`'s `asyncio.create_task(self.webhook_service.trigger_webhook(...))` fire-and-forget wrap) | exact (2 analogs combined) |
| `backend/tests/test_siem_engine.py` (new file — no test file exists today) | test | — | `backend/tests/test_remediation_guards.py` (fixture/mocking style) | role-match |
| `backend/tests/test_ueba_remediation_trigger.py` (new file) | test | — | `backend/tests/test_remediation_guards.py` | role-match |
| `backend/tests/test_remediation_playbook.py` (extend, add `anomaly` cases) | test | — | itself | exact (self) |
| `backend/tests/test_webhook_signing.py` (extend, add OCSF/fire-and-forget cases) or new `test_soc_integration.py` | test | — | itself | exact (self) |

## Pattern Assignments

### `backend/siem_engine.py` — new `correlate_native_findings(self, tenant_id)` method (INT-04)

**Analog 1 (bounded-read/normalize/merge shape):** `backend/native_security_ops_endpoints.py` lines 20-41

```python
# Source: backend/native_security_ops_endpoints.py:28-41
scans = await db.security_scan_results.find({"tenantId": tenant_id}).to_list(length=200)
vulns = await db.vulnerabilities.find({"tenantId": tenant_id}).to_list(length=200)
fim = await db.fim_events.find({"tenantId": tenant_id}).to_list(length=200)

findings = []
for s in scans:
    findings.append({"source": "scan", "severity": s.get("severity", "medium"), "hostname": s.get("agentId"), ...})
for v in vulns:
    findings.append({"source": "vulnerability", ...})
for f in fim:
    findings.append({"source": "fim", ...})

findings.sort(key=lambda x: x["ts"], reverse=True)
return {"findings": findings[offset:offset + limit]}
```
Copy this exact bounded-read (`to_list(length=200)`) + normalize + merge shape for the 4th collection this phase adds:
```python
remediation_events = await db.remediation_audit.find({"tenantId": tenant_id}).to_list(length=200)
```

**Analog 2 (rule-eval loop to REUSE, not duplicate):** `backend/siem_engine.py` lines 74-90
```python
# Source: backend/siem_engine.py:74-90 (existing — call this from the new method, don't rebuild it)
async def _evaluate_rules(self, events, tenant_id):
    rules = await self.db.siem_rules.find({"tenantId": tenant_id, "enabled": True}).to_list(length=1000)
    for rule in rules:
        for event in events:
            if self._match_rule(event, rule):
                await self._trigger_alert(event, rule, tenant_id)

def _match_rule(self, event, rule) -> bool:
    conditions = rule.get("conditions", {})
    for key, expected_value in conditions.items():
        if event.get(key) != expected_value:
            return False
    return True
```
The new `correlate_native_findings()` method should normalize the 4 native collections into the SAME `event` dict shape `_normalize_log` produces (`id`, `tenant_id`, `agent_id`, `timestamp`, `source`, `raw`, `category`, `action`, `user`), then call `self._evaluate_rules(normalized_events, tenant_id)` — this makes existing `siem_rules` docs apply to native findings automatically (RESEARCH.md Open Question 2, Option (a), the strongest reading of D-01).

**Alert/case creation to extend for a new SIEM push (COMM-01 hook point):** `backend/siem_engine.py` lines 92-131 (`_trigger_alert`) — this is where a new fire-and-forget `asyncio.create_task(webhook_service.trigger_webhook("threat.correlation", ocsf_payload))` call site belongs, matching the existing email-dispatch try/except-non-fatal pattern already there (lines 113-131).

---

### `backend/remediation_playbook_service.py` — new `anomaly` branch in `select_playbook()` (AUT-03)

**Analog:** the function's own existing branches, `backend/remediation_playbook_service.py` lines 91-123
```python
# Source: backend/remediation_playbook_service.py:108-121 (existing branches — pattern to clone)
if finding_type == "fim":
    return by_name.get("restore_file")

if finding_type == "nscan":
    scan_type = details.get("type") or details.get("scan_type")
    if scan_type == "ip":
        return by_name.get("block_ip")
    return by_name.get("kill_process")

if finding_type == "vuln":
    cve_id = details.get("cveId") or details.get("cve_id")
    if cve_id:
        return by_name.get("patch_package")
    return by_name.get("disable_service")

return None
```
New branch to add (per RESEARCH.md Architecture Pattern 2 — do not invent a new ACTION_MAP entry):
```python
if finding_type == "anomaly":
    if details.get("anomaly_rule") == "shadow_ai_detected" and _finding_attr(finding, "agent_id"):
        return by_name.get("kill_process")
    return None  # honest no_playbook outcome for user/IP-scoped anomalies without an agent
```
`_finding_attr(finding, name, default)` (lines 85-88) is the existing dict-or-dataclass accessor helper — reuse it, don't reimplement.

---

### `backend/ueba_service.py` — new post-analysis call site feeding `remediate()` (AUT-03)

**Analog (fire-and-forget background dispatch convention already used 4x in this same file):** `backend/ueba_service.py` lines 314-320 (`report_shadow_ai`)
```python
# Source: backend/ueba_service.py:314-320
async def report_shadow_ai(event: ShadowAIEvent, background_tasks: BackgroundTasks, db=Depends(get_database)):
    ...
    background_tasks.add_task(
        _persist_alert, db, "shadow_ai", "medium",
        ...
    )
```
Also see the endpoint-level pattern at lines 421-431 (`analyze_login_behavior`) — `background_tasks.add_task(_persist_alert, db, "ueba_anomaly", ...)`. The new containment call site should follow the SAME `background_tasks.add_task(...)` (or `asyncio.create_task(...)` if not in a request-scoped endpoint) convention — never `await remediate(...)` inline (RESEARCH.md Anti-Pattern: `_dispatch_and_verify()` can block up to 120s).

**Dataclass shape to construct (existing, unchanged):** `backend/autonomous_remediation_service.py` lines 42-53
```python
# Source: backend/autonomous_remediation_service.py:42-53
@dataclass
class RemediationFinding:
    finding_id: str
    finding_type: str
    severity: str
    tenant_id: str
    agent_id: Optional[str]
    resource_id: Optional[str]
    details: Dict[str, Any]
    matched_policy: Optional[Dict] = None
    raw_doc: Optional[Dict] = None
```
New call site constructs: `RemediationFinding(finding_id=..., finding_type="anomaly", severity=..., tenant_id=..., agent_id=event.agent_id if shadow_ai else None, resource_id=event.process or event.remote_host, details={"anomaly_rule": "shadow_ai_detected", ...})`.

**Dedup guard to call BEFORE `.remediate()` (mandatory per Pitfall 2/threat pattern table):** `backend/response_orchestrator.py` lines 231-244 (`is_duplicate_task`) — call `await orchestrator.is_duplicate_task(agent_id=..., action="remediate_anomaly", tenant_id=..., alert_type="anomaly")` exactly like `scan_for_remediable_findings`/`run_cycle` already do (`autonomous_remediation_service.py` lines 508, 958) before invoking `.remediate()`.

**Existing shape NOT to touch (Pitfall 4 — pre-existing, out of scope):** `backend/ueba_service.py` lines 228-247, the `_AUTO_BAN_RULES` block that already calls `ip_ban_service.ban_ip(..., auto=True)` with zero approval gate for `brute_force`/`known_malicious_ip` at score≥80. Leave this exactly as-is; do not extend or gate it this phase.

---

### `backend/ocsf_endpoints.py` (or new `soc_integration_service.py`) — OCSF payload builder + outbound push call sites (COMM-01)

**Analog 1 (OCSF shape to replicate exactly):** `backend/ocsf_endpoints.py` lines 34-44
```python
# Source: backend/ocsf_endpoints.py:34-44
ocsf_items.append({
    "class_uid": 2004,
    "category_uid": 2,
    "type_uid": 200401,
    "severity_id": sev_id,
    "severity": f.get("severity", "medium"),
    "finding": {"uid": f.get("id", ""), "title": f.get("title", "")},
    "time": _to_epoch(f.get("created_at", "")),
    "metadata": {"version": "1.0.0", "product": {"name": "OmniAgent Platform"}},
})
```
Reuse the `_to_epoch` helper (lines 14-19) and the `severity_map` dict (line 30) verbatim for the new outbound builder — do not invent a second epoch-parsing or severity-mapping function.

**Analog 2 (fire-and-forget dispatch — mandatory per Pitfall 3):** `backend/notification_manager.py` lines 11-21
```python
# Source: backend/notification_manager.py:11-21
async def send_notification(self, event_type: str, payload: Dict[str, Any], tenant_id: str):
    print(f"[NotificationManager] Dispatching {event_type} for tenant {tenant_id}")
    asyncio.create_task(self.webhook_service.trigger_webhook(event_type, payload))
```
Every new call site (SIEM correlation case creation in `_trigger_alert`, UEBA anomaly persistence in `_persist_alert`, remediation stage transitions in `write_audit` call sites) MUST wrap `webhook_service.trigger_webhook(event_type, ocsf_payload)` in `asyncio.create_task(...)` exactly like this — never `await` it directly in a hot path.

**Webhook delivery itself — UNCHANGED, consume as-is:** `backend/webhook_service.py` lines 56-85 (`trigger_webhook`) already does the `db.webhooks.find({"status": "Active", "events": event_type})` subscription lookup, SSRF-safe `_is_safe_webhook_url` check (lines 29-52), and HMAC signing (lines 98-103). No changes needed here — just call it with new `event_type` strings (`"threat.correlation"`, `"ueba.anomaly"`, `"remediation.event"`).

---

### Tests

**Analog for new `test_siem_engine.py` / `test_ueba_remediation_trigger.py`:** `backend/tests/test_remediation_guards.py` — fixture/finding-construction pattern:
```python
# Source: backend/tests/test_remediation_guards.py (verified pattern to clone)
def _finding(finding_type="nscan", **overrides):
    base = dict(
        finding_id="f-1", finding_type=finding_type, severity="critical",
        tenant_id="t1", agent_id="agent-1", resource_id="1.2.3.4",
        details={"type": "ip", "verdict": "Malicious", "ts": "2026-08-01T00:00:00Z"},
    )
    base.update(overrides)
    return RemediationFinding(**base)
# New test: _finding(finding_type="anomaly", details={"anomaly_rule": "shadow_ai_detected"})
```
Run scope for per-task commits: `backend/venv/bin/python -m pytest backend/tests/test_remediation_guards.py backend/tests/test_remediation_playbook.py backend/tests/test_webhook_signing.py -q`.

## Shared Patterns

### Tenant isolation (applies to every new correlation read and every new call site)
**Source:** `backend/autonomous_remediation_service.py` lines 144-148 (`scan_for_remediable_findings`)
```python
_tctx = set_tenant_id(tenant_id)
vulns = await db.vulnerabilities.find({...}).to_list(length=200)
# ... reset_tenant_id(_tctx) on the way out (matching finally-block usage elsewhere in the file)
```
Every new correlation read (`siem_engine.py`) and the new UEBA→remediate() call site MUST wrap DB access in `set_tenant_id(tenant_id)`/`reset_tenant_id(_tctx)` — never `db._db` directly (explicit scope fence in CONTEXT.md).

### Fire-and-forget async dispatch (applies to all 3 new webhook push points + the UEBA containment trigger)
**Source:** `backend/notification_manager.py` line 21 and `backend/ueba_service.py` lines 314-320/421-431
```python
asyncio.create_task(self.webhook_service.trigger_webhook(event_type, payload))
# or, inside a FastAPI request handler:
background_tasks.add_task(_persist_alert, db, alert_type, severity, title, description, metadata)
```
Apply to: all 3 OCSF push call sites (COMM-01) and the new UEBA→`remediate()` call site (AUT-03) — nothing in this phase may `await` a >100ms-risk call inline in a request/response cycle.

### Deterministic, no-LLM dispatcher pattern (applies to `select_playbook()` extension only)
**Source:** `backend/remediation_playbook_service.py` lines 91-123 — pure `if/elif` on `finding_type`/`details`, no LLM call anywhere in the module (per its own module docstring, lines 1-11). The new `anomaly` branch must stay within this same pure-function, deterministic-lookup shape (inherits Phase 53's D-02 constraint, reiterated in this phase's CONTEXT.md scope fences).

### Dedup-before-dispatch (applies to the new UEBA containment call site only)
**Source:** `backend/response_orchestrator.py` lines 231-244 (`is_duplicate_task`), used the same way at `backend/autonomous_remediation_service.py` lines 508 and 958. Must be called with a non-`"auto"`-colliding key where possible (Pitfall 2) — since only `shadow_ai_detected` reaches `remediate()` with a real `agent_id`, the existing per-agent dedup key is safe to use as-is for this phase's scope.

## No Analog Found

None — every file in this phase's scope is an extension of an existing, already-read file; RESEARCH.md's Sources section confirms full-file reads of all 8 target files this session.

## Metadata

**Analog search scope:** `backend/siem_engine.py`, `backend/threat_intel_endpoints.py`, `backend/remediation_playbook_service.py`, `backend/ueba_service.py`, `backend/autonomous_remediation_service.py`, `backend/webhook_service.py`, `backend/ocsf_endpoints.py`, `backend/notification_manager.py`, `backend/native_security_ops_endpoints.py`, `backend/response_orchestrator.py`, `backend/tests/*.py`
**Files scanned:** 11 (all read in full this session; largest was `autonomous_remediation_service.py` at 1018 lines, read via 2 targeted non-overlapping ranges: 1-170 and 548-687)
**Pattern extraction date:** 2026-08-03
