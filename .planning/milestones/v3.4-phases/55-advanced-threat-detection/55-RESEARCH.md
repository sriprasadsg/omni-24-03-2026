# Phase 55: Advanced Threat Detection & Response - Research

**Researched:** 2026-08-03
**Domain:** Native security correlation (SIEM), UEBA-driven predictive containment, outbound SOC/OCSF integration — all as extensions of existing Phase 51/53/54 backend infrastructure
**Confidence:** HIGH (this phase is 95% "extend traced, working code," not new-framework research)

## Summary

Phase 55 does not introduce new frameworks, ML libraries, or external services. Every one of its three requirements (INT-04, AUT-03, COMM-01) is explicitly locked (CONTEXT.md D-01..D-04) to extending code that already exists and is already tested: `siem_engine.py`'s rule-evaluation/case-creation loop, `autonomous_remediation_service.remediate()`'s deterministic YAML-playbook dispatch engine (built in Phase 53, currently **dead code in production** — see Pitfall 1), and `webhook_service.py`'s HTTP delivery + `ocsf_endpoints.py`'s OCSF-1.0 formatting convention. No new pip/npm packages are required.

The single genuinely open design question CONTEXT.md flagged — "which UEBA anomaly type maps to which Phase 53 playbook" — has a concrete, code-grounded answer traced below (see Architecture Pattern 2): the fixed `ACTION_MAP` allowlist (`patch_package`, `kill_process`, `restore_file`, `block_ip`, `unblock_ip`, `disable_service`, `enable_service`) only contains **agent-dispatched, endpoint-scoped** actions, but most UEBA anomaly rules (`brute_force`, `impossible_travel`, `known_malicious_ip`, `mass_download`, `lateral_movement`, `dormant_account`, `off_hours_login`, `new_country`, `after_hours_data_access`) are **user/IP-scoped with no `agent_id`** — there is no user→agent mapping anywhere in the codebase (agents are hostname-keyed, not user-keyed). Only the Shadow AI rule (`ShadowAIEvent` carries a real `agent_id`) has a clean existing-playbook fit (`kill_process`). This is not a gap to paper over — it is the actual shape of the codebase, and the plan should scope predictive containment accordingly rather than inventing a fictitious user-to-agent resolution mechanism.

**Primary recommendation:** Extend `siem_engine.py`, `select_playbook()`, and `webhook_service.py` call sites exactly as D-01/D-02/D-03 lock — do not build parallel systems. Feed `remediate()` from `ueba_service.py`'s per-event, rule-named `analyze_login`/`analyze_data_access` results (not `ueba_engine.py`'s periodic/manual batch ML score), because only the rule-based path fires at the moment of the triggering event and carries a specific `triggered_rules` name that a playbook-selection branch can key off. Fix the fact that `remediate()` has zero production call sites today by adding one directly in the UEBA anomaly path (event-driven), not by trying to retrofit the already-broken `run_cycle()` loop (out of this phase's scope fences).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Threat-intel/SIEM correlation (INT-04) | API/Backend (`siem_engine.py`, `threat_intel_endpoints.py`) | Database (new bounded reads of `security_scan_results`/`vulnerabilities`/`fim_events`/`remediation_audit`) | Correlation is pure server-side rule evaluation over Mongo-backed collections; no client tier involved |
| Predictive anomaly → containment (AUT-03) | API/Backend (`ueba_service.py` → `autonomous_remediation_service.remediate()`) | Database (`remediation_requests`/`remediation_inflight`/`remediation_audit` — the existing Phase 53 state machine) | Deterministic, backend-orchestrated dispatch; agent executes commands but never decides — consistent with D-02/Phase 53 D-01 |
| SOC/SIEM outbound push (COMM-01) | API/Backend (`webhook_service.py`) | External/Network (SIEM's HTTP ingest endpoint) | Fire-and-forget HTTP POST from backend; no new tier, no inbound surface (D-03) |
| Operator approval of predictive containment | Frontend (existing `RemediationControl`-style UI from Phase 54) → API/Backend (`remediation_control_endpoints.py`) | — | Reuses Phase 53/54's approve/deny UI+endpoint unchanged; this phase adds a new `finding_type`, not a new UI surface |

## User Constraints

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 — Extend existing correlation infra, don't rebuild (INT-04).** `siem_engine.py` / `threat_intel_endpoints.py` already have correlation logic (134 + 293 lines). Extend them to ingest `security_scan_results`, `vulnerabilities`, `fim_events`, and `remediation_audit` as correlation inputs, rather than building a parallel correlation path. Matches the established pattern from Phase 51/53 of extending real existing infra over building duplicate new systems.
- **D-02 — Predictive containment reuses Phase 53's remediation engine (AUT-03).** `ueba_engine.py`/`ueba_service.py`'s anomaly score becomes a new `finding_type` (e.g. `"anomaly"`) that `autonomous_remediation_service.remediate()` consumes — the SAME playbook selection / dispatch / poll / verify / audit machinery Phase 53 already built and tested. No new containment mechanism, no agent-local engine (consistent with Phase 53's own D-01: backend-orchestrated, agent executes commands).
- **D-03 — SOC integration is outbound OCSF push (COMM-01).** Reuse `webhook_service.py` to push OCSF-formatted (per `ocsf_endpoints.py` conventions) alerts/findings/remediation events to an external SIEM/syslog target. Outbound only — no inbound alert-ingestion endpoint this phase.
- **D-04 — Same approval gate as Phase 53, no autonomy exception (AUT-03).** Containment actions dispatched from a predictive/anomaly trigger go through the IDENTICAL default-on approval gate + dry-run + DB-lease concurrency cap + audit trail Phase 53 built. No faster/autonomous bypass for "real-time" urgency — consistency and safety over speed (explicit user choice over a confidence-threshold auto-dispatch alternative).

### Claude's Discretion
- Left to research/planning: the exact anomaly-to-playbook mapping (resolved concretely below — see Architecture Pattern 2).
- Left to planner: 4-plan breakdown internals (task-level sequencing within each of the 4 locked plan scopes).

### Deferred Ideas (OUT OF SCOPE)
(none raised during discussion — scope stayed within the phase boundary)

### Scope fences (MUST NOT — from CONTEXT.md)
- MUST NOT build a second/parallel remediation or dispatch engine — predictive containment routes through the existing `autonomous_remediation_service.remediate()` path (D-02).
- MUST NOT bypass Phase 53's approval gate for containment actions, regardless of anomaly confidence (D-04).
- MUST NOT put an LLM in the containment execution path (inherits Phase 53's D-02 deterministic-only constraint).
- MUST NOT build inbound SOC alert ingestion this phase (D-03, outbound only).
- MUST NOT duplicate existing SIEM/threat-intel/webhook/OCSF endpoints — extend them.
- MUST NOT access `db._db` in new/extended handlers.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INT-04 | Threat intel feeds, correlation engine | Architecture Pattern 1 (correlation input bounding), traced `siem_engine.py`/`threat_intel_endpoints.py` current shape, Don't-Hand-Roll table |
| AUT-03 | Predictive containment | Architecture Pattern 2 (anomaly-to-playbook mapping — the concrete resolution of CONTEXT.md's flagged open question), traced `remediate()`/`select_playbook()`/`ACTION_MAP`, Pitfall 1 (dead-code call site), Pitfall 2 (dedup collision) |
| COMM-01 | Syslog/SIEM webhook | Architecture Pattern 3 (OCSF push via `webhook_service.py`), traced `ocsf_endpoints.py`'s verified `class_uid=2004`/`category_uid=2` convention, Pitfall 3 (fire-and-forget) |

**Note on requirement-ID provenance:** `.planning/REQUIREMENTS.md` currently tracks a *different*, newer milestone (v4.0: SCALE-01/02, SEC-01/02, etc.) — it does NOT list INT-04/AUT-03/COMM-01. Those IDs live in `.planning/ROADMAP.md`'s Phase 55 section only (the v3.4 milestone this phase closes). This is expected — REQUIREMENTS.md has moved on to the next milestone while this phase finishes v3.4 — but the planner should cite ROADMAP.md, not REQUIREMENTS.md, as the requirement source for this phase's traceability.
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Prefer editing existing files over creating new ones; only create a new file when the existing target would breach the 500-line cap (established precedent throughout this codebase, e.g. 08-01, 30-05).
- Keep files under 500 lines. `autonomous_remediation_service.py` is already ~1050 lines — any addition to it (e.g., a new anomaly-finding-gathering block) should go in a focused helper module if it would push the file further past 500, following the `remediation_playbook_service.py`/`remediation_audit_service.py` extraction precedent Phase 53 already set.
- Validate input at system boundaries — new UEBA→remediation call site and new webhook event payloads must validate `finding.tenant_id`/`finding.agent_id` before use, matching the fail-closed `TenantIsolatedCollection` pattern.
- Never commit secrets/.env files — not directly relevant (no new credentials needed; SOC webhook auth reuses the existing per-webhook `secret`/HMAC signing already in `webhook_service.py`).
- No `Co-Authored-By` trailer on commits (repo-wide convention already reflected in recent commit history).

## Standard Stack

### Core
No new libraries. This phase is pure extension of already-installed, already-imported code:

| Library | Version | Purpose | Why Standard (for this phase) |
|---------|---------|---------|--------------------------------|
| motor (AsyncIOMotorClient) | already in use | Async Mongo reads for correlation inputs | Every collection touched (`security_scan_results`, `vulnerabilities`, `fim_events`, `remediation_audit`, `ueba_alerts`, `login_events`) is already Motor-backed |
| httpx | already in use (`webhook_service.py`) | Outbound OCSF/SIEM HTTP POST | `WebhookService._send_single_webhook` already does exactly this; D-03 requires reusing it unchanged |
| PyYAML | already in use (`remediation_playbook_service.py`) | Loading `backend/playbooks/*.yaml` | Playbook selection for the new `anomaly` finding_type reuses the same vendored-YAML mechanism; no new playbook format needed unless Architecture Pattern 2's Option B is chosen |
| scikit-learn / numpy (optional) | already in use (`ueba_engine.py`, guarded by `ML_AVAILABLE`) | Isolation Forest anomaly scoring | Already optional/degraded-gracefully; this phase does not need to touch this dependency at all if it uses `ueba_service.py`'s rule engine as the containment trigger (recommended) rather than `ueba_engine.py`'s ML score |

### Supporting
None — no new supporting libraries required.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Reusing `remediate()`'s agent-dispatch `ACTION_MAP` for IP/user-scoped anomalies | A new non-agent-dispatch action type calling `ip_ban_service.ban_ip()` synchronously from inside `_dispatch_step` | Bigger structural change to a function shared by every other finding type (vuln/fim/nscan); risks violating "no second dispatch engine" in spirit even if not in name. Not recommended for this phase — see Architecture Pattern 2 |
| `ueba_service.py`'s per-event rule engine as the containment trigger | `ueba_engine.py`'s periodic/manual Isolation Forest batch score | The ML engine only runs on-demand via a rate-limited (`2/hour`) `POST /api/ueba/calculate-all` endpoint — there is no "moment" to hook a real-time containment trigger off of. The rule engine fires per-event and is the only "predictive... real-time" fit per the phase goal |

**Installation:** None required — no `npm install` / `pip install` needed for this phase.

## Package Legitimacy Audit

Not applicable — this phase introduces zero new third-party packages. No `package-legitimacy check` run was needed.

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────────┐
                         │   Native v3.4 finding sources (existing)      │
                         │   security_scan_results / vulnerabilities /   │
                         │   fim_events / remediation_audit              │
                         └───────────────────┬───────────────────────────┘
                                              │ bounded per-collection reads
                                              │ (.find({tenantId}).to_list(length=N))
                                              ▼
┌───────────────┐   raw_logs topic   ┌──────────────────────────┐   security_cases  ┌──────────────┐
│ Agent / syslog │ ─────────────────▶│  siem_engine.SiemEngine    │ ───(existing)────▶│ SOC UI/queue │
│ ingest (exist.)│                   │  ._evaluate_rules() +      │                   └──────┬───────┘
└───────────────┘                   │  NEW: correlate native     │                          │
                                     │  findings (D-01 extension) │                          │
                                     └─────────────┬─────────────┘                          │
                                                    │                                        │
   UEBA login/data-access event ──▶ ueba_service.analyze_login()/analyze_data_access()      │
   (per-event, real-time rule engine, triggered_rules: brute_force, impossible_travel, ...)  │
                                                    │                                        │
                                                    │ is_anomalous + triggered_rules          │
                                                    ▼                                        │
                                     ┌──────────────────────────────┐                        │
                                     │ NEW call site (this phase):   │                        │
                                     │ build RemediationFinding(      │                       │
                                     │  finding_type="anomaly", ...) │                        │
                                     └─────────────┬──────────────────┘                       │
                                                    │ .remediate(finding)                     │
                                                    ▼                                         │
                        ┌───────────────────────────────────────────────────┐                │
                        │ autonomous_remediation_service.remediate()          │                │
                        │  → select_playbook() [NEW anomaly branch, D-02]     │                │
                        │  → destructive? pending_approval : dispatch          │                │
                        │  → _dispatch_and_verify() [UNCHANGED — lease/       │                │
                        │     rollback/escalate/audit, D-04]                  │                │
                        └───────────────────────┬─────────────────────────────┘               │
                                                 │ write_audit() → remediation_audit            │
                                                 ▼                                             │
                                     ┌──────────────────────────┐                              │
                                     │ remediation_control_      │◀── operator approve/deny ────┘
                                     │ endpoints.py (existing)   │    (Phase 54 UI, unchanged)
                                     └─────────────┬──────────────┘
                                                    │ (all of the above emit events)
                                                    ▼
                                     ┌──────────────────────────────┐     OCSF-formatted POST    ┌───────────────┐
                                     │ NEW call sites (this phase):  │ ─────────────────────────▶│ External SIEM │
                                     │ webhook_service.trigger_      │   (fire-and-forget,        │ / syslog HTTP │
                                     │ webhook(event_type, ocsf_doc) │   asyncio.create_task,      │  ingest       │
                                     │ [D-03, reuse unchanged]       │   never blocks pipeline)     └───────────────┘
                                     └────────────────────────────────┘
```

### Recommended Project Structure

No new top-level directories. Extensions land in existing files, with one likely new file to respect the 500-line cap:

```
backend/
├── siem_engine.py                        # D-01: add correlate_native_findings() (or similarly
│                                          #        named) method — bounded reads + normalize into
│                                          #        the same `event` shape _evaluate_rules() expects
├── threat_intel_endpoints.py             # D-01: extend enrich_security_event()-style pattern, or
│                                          #        add a companion enrichment path for native findings
├── remediation_playbook_service.py       # D-02: extend select_playbook() with a new
│                                          #        `elif finding_type == "anomaly":` branch
├── ueba_service.py                       # D-02: NEW call site — after analyze_login/
│                                          #        analyze_data_access produce is_anomalous=True,
│                                          #        build RemediationFinding + call .remediate()
├── autonomous_remediation_service.py     # UNCHANGED — remediate()/_dispatch_and_verify() consumed
│                                          #        as-is per D-02/D-04; only a new finding_type value
├── webhook_service.py                    # UNCHANGED — trigger_webhook() consumed as-is per D-03
├── ocsf_endpoints.py                     # D-03: reuse class_uid=2004/category_uid=2 convention for
│                                          #        the new outbound OCSF payload builder (may add a
│                                          #        shared _build_ocsf_finding() helper here or in a
│                                          #        new small module if this file would exceed 500 lines)
└── (possible new) soc_integration_service.py   # only if OCSF-payload-building + webhook dispatch
                                                 # logic doesn't fit cleanly in existing files without
                                                 # breaching the 500-line cap — mirrors the
                                                 # remediation_audit_service.py extraction precedent
```

### Pattern 1: Bounded, per-collection correlation input (INT-04) — precedent from Phase 54

**What:** Every native finding source is read with a fixed cap (`.to_list(length=N)`), never an unbounded scan, then merged/sorted in application code.
**When to use:** Any new correlation read against `security_scan_results`/`vulnerabilities`/`fim_events`/`remediation_audit` — directly addresses CONTEXT.md's "Correlation input volume" pitfall, which explicitly points at this exact precedent.
**Example (the actual precedent, verbatim from the codebase):**
```python
# Source: backend/native_security_ops_endpoints.py (Phase 54, GET /api/security-ops/findings)
scans = await db.security_scan_results.find({"tenantId": tenant_id}).to_list(length=200)
vulns = await db.vulnerabilities.find({"tenantId": tenant_id}).to_list(length=200)
fim = await db.fim_events.find({"tenantId": tenant_id}).to_list(length=200)
# ... normalize each into a common shape, merge, sort, THEN paginate in Python:
findings.sort(key=lambda x: x["ts"], reverse=True)
return {"findings": findings[offset:offset + limit]}
```
Apply the identical shape to the new correlation input for `remediation_audit` (4th collection) inside `siem_engine.py`'s extension.

### Pattern 2: Anomaly-to-playbook mapping (AUT-03) — the concrete resolution of CONTEXT.md's flagged open question

**What actually exists today**, traced directly from the code (all `[VERIFIED: backend/*.py]`):

`remediation_playbook_service.select_playbook(finding, playbooks)` is a pure `if/elif` dispatcher with **no branch for `finding_type == "anomaly"`** — it currently returns `None` for any unrecognized type, which `remediate()` turns into `{"status": "no_playbook", ...}` (a normal, already-handled terminal state, not an error).

The 5 vendored playbooks (`backend/playbooks/*.yaml`) and their fixed `ACTION_MAP` (`patch_package→upgrade_software`, `kill_process→kill_process`, `restore_file→restore_file`, `block_ip→block_ip`, `unblock_ip→unblock_ip`, `disable_service→disable_service`, `enable_service→enable_service`) are **all agent-dispatched, endpoint-scoped actions** — every one requires a real `finding.agent_id` because `_dispatch_and_verify()` acquires a per-agent DB lease (`remediation_inflight`, keyed by `agentId`) and `_dispatch_step()` inserts an `agent_instructions` doc addressed to that specific `agent_id` for the Rust agent to poll and execute.

Cross-referencing UEBA's actual event shapes:
- `ShadowAIEvent` (in `ueba_service.py`) carries a **real `agent_id`** (`agent_id: str, process: str, remote_ip: str, remote_host: str`) — an endpoint agent genuinely detected the shadow-AI connection. This is the ONE UEBA signal with a clean existing-playbook fit: `finding_type="anomaly"`, `resource_id=event.process` (or `remote_host`), `agent_id=event.agent_id` → maps to the existing `kill_process` playbook.
- `LoginEvent` / `DataAccessEvent` (also `ueba_service.py`) carry **no `agent_id`** — only `user_id`, `ip_address`, `resource`. There is no user→agent lookup anywhere in the codebase (`db.agents` documents are hostname-keyed via `agent_registry_endpoints.py`, never user-keyed). So `brute_force`, `impossible_travel`, `known_malicious_ip`, `mass_download`, `lateral_movement`, `dormant_account`, `off_hours_login`, `new_country`, `after_hours_data_access` — 9 of `ueba_service.py`'s 10 rules — have **no agent to dispatch a containment action to** using the existing `ACTION_MAP`.
- `ueba_engine.py`'s risk score (`calculate_risk_score`) is a periodic/manual (rate-limited `2/hour`, on-demand via `POST /api/ueba/calculate-all`) aggregate score over a rolling window — it has no single "triggering event" moment to hang a real-time containment call off of, unlike the per-event `ueba_service.py` path.

**Recommendation (grounded, not a guess):**
1. Use `ueba_service.py`'s `analyze_login`/`analyze_data_access` results — not `ueba_engine.py`'s batch score — as the containment trigger, because it fires per-event with a named `triggered_rules` list.
2. Add a new `elif finding_type == "anomaly":` branch to `select_playbook()` that inspects `finding.details.get("anomaly_rule")` (a new field the new call site should set): `"shadow_ai_detected"` → `kill_process`; anything else with no `agent_id` present → return `None` (honest `no_playbook` outcome — the finding is still recorded, correlated, and pushed to SIEM per INT-04/COMM-01, just not containment-actioned).
3. Do NOT invent a new `ACTION_MAP` entry (e.g., a synchronous `ip_ban_service.ban_ip()`-backed "action") this phase — it would require special-casing `_dispatch_step()`'s agent-instruction-and-poll contract for a non-agent-dispatched action, which risks becoming the "second dispatch mechanism" the scope fences explicitly forbid. If broader containment coverage for user/IP-scoped anomalies is wanted, that is a legitimate **follow-up phase**, not this one — flag it as a discuss-phase/user-confirmation point, not a silent scope expansion.
4. Existing behavior to be aware of (not to change): `ueba_service.py`'s `analyze_login` **already** auto-bans IPs via `ip_ban_service.ban_ip()` for `brute_force`/`known_malicious_ip` at score≥80, with NO approval gate (see Pitfall 4). This is pre-existing Phase-47-era functionality, out of this phase's file scope — but the plan should not assume this phase closes that inconsistency; it should be called out explicitly as a known, deliberately-unaddressed gap so nobody mistakes it for something this phase "should have" fixed.

**Example — the exact shape a new call site should produce (illustrative, matching the real dataclass):**
```python
# Source: backend/autonomous_remediation_service.py (existing dataclass, unchanged)
@dataclass
class RemediationFinding:
    finding_id: str
    finding_type: str  # NEW value this phase introduces: "anomaly"
    severity: str
    tenant_id: str
    agent_id: Optional[str]     # populated ONLY for shadow_ai_detected; None otherwise
    resource_id: Optional[str]
    details: Dict[str, Any]     # should include {"anomaly_rule": "shadow_ai_detected", ...}
```

### Pattern 3: Outbound OCSF push via `webhook_service.py` (COMM-01)

**What:** Reuse `WebhookService.trigger_webhook(event_type, payload)` unchanged. Register new `event_type` strings (e.g. `"threat.correlation"`, `"ueba.anomaly"`, `"remediation.event"`) that operators subscribe a webhook's `events: []` array to (existing `POST /api/webhooks` contract — no schema change needed).
**When to use:** At the 3 points D-03's success criterion identifies — SIEM correlation case creation (`_trigger_alert`), UEBA anomaly persistence (`_persist_alert`), and remediation stage transitions (`write_audit`'s call sites).
**Verified OCSF convention** `[VERIFIED: schema.ocsf.io — Detection Finding is class_uid=2004, category_uid=2, the class SIEM/EDR/XDR correlation-engine alerts belong to]` — this matches what `ocsf_endpoints.py` already emits for `/api/ocsf/findings`, so the new outbound payloads should reuse the identical `class_uid: 2004, category_uid: 2` shape for consistency across the codebase's two OCSF surfaces (existing pull-based `/api/ocsf/*` GET endpoints vs. this phase's new push-based webhook payloads).
**Example (the actual precedent, verbatim):**
```python
# Source: backend/ocsf_endpoints.py (existing, verified pattern to replicate)
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
```python
# Source: backend/notification_manager.py (existing fire-and-forget precedent to replicate)
asyncio.create_task(self.webhook_service.trigger_webhook(event_type, ocsf_payload))
```

### Anti-Patterns to Avoid
- **Building a second correlation loop:** Do not add a new `NativeFindingsCorrelator` class or similar — extend `SiemEngine` (D-01 is explicit: "extend, don't rebuild a parallel path").
- **Calling `remediate()` synchronously and awaiting completion inline in the UEBA request path:** `_dispatch_and_verify()` can poll for up to `STEP_POLL_TIMEOUT_SEC` (60s) + `VERIFY_TIMEOUT_SEC` (60s) per step — awaiting this inline in `POST /api/ueba/analyze-login`'s request/response cycle would make login-analysis calls hang for up to 2 minutes. Dispatch via `background_tasks.add_task` (the existing `ueba_service.py` convention already used for `_persist_alert`) or `asyncio.create_task`, matching the fire-and-forget pattern webhook delivery already uses.
- **Trusting `ueba_engine.py`'s `_generate_ueba_alert` recency dedup as sufficient for the new containment call site:** it only prevents duplicate *alerts* within 4 hours for `ueba_engine.py`'s own path — it says nothing about `ueba_service.py`'s separate alert stream, and does not prevent duplicate `remediate()` calls at all. Use `ResponseOrchestrator.is_duplicate_task` (already used by every other `remediate()`-adjacent call site) — see Pitfall 2 for its collision risk with `agent_id="auto"`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Approval/dry-run/concurrency-cap/audit gating for containment actions | A new gate specific to "predictive" containment | `autonomous_remediation_service._dispatch_and_verify()` (existing, tested — `test_remediation_guards.py`) | D-04 explicitly forbids any autonomy exception; the existing gate already does everything needed |
| OCSF formatting | A bespoke JSON shape for SIEM push | `ocsf_endpoints.py`'s verified `class_uid=2004/category_uid=2` shape | Keeps the codebase's two OCSF surfaces (pull GET + push webhook) consistent; avoids inventing a schema that later needs reconciling |
| Webhook delivery, retry/failure bookkeeping, SSRF guarding | A new HTTP client wrapper for SIEM push | `webhook_service.WebhookService.trigger_webhook()` | Already has `_is_safe_webhook_url` SSRF blocklist, HMAC signing, failure-count tracking, and `webhook_deliveries` history — reinventing any of this risks reintroducing the SSRF hole it already closes |
| YAML playbook loading/validation | A new playbook format for "anomaly" findings | `remediation_playbook_service.load_default_playbooks()`/`validate()` | Already validates every step's `action` against `ACTION_MAP`; a new playbook YAML for `shadow_ai_detected`-style containment (if the planner chooses to add one rather than reuse `kill_process` verbatim) still goes through this same loader unchanged |

**Key insight:** Every "Don't Hand-Roll" item here is not a hypothetical library recommendation — it's a specific, already-tested function in this repository that CONTEXT.md's locked decisions require reusing. The research risk in this phase is not "picking the wrong library," it's "silently building a parallel path because the mapping isn't 1:1 obvious" (exactly what Architecture Pattern 2 exists to prevent).

## Common Pitfalls

### Pitfall 1: `autonomous_remediation_service.remediate()` has zero production call sites today
**What goes wrong:** A plan that assumes "the Phase 53 deterministic engine already runs in production, I just need to feed it a new finding_type" will be wrong — `remediate()` is currently invoked ONLY from `backend/tests/test_remediation_guards.py` and `test_autonomous_remediation_loop.py`. The one production scheduler (`autonomous_remediation_loop()` in `app_background_tasks.py`, started at app startup) calls `run_cycle()`, which calls `generate_plan()`/`execute_plan()` — a DIFFERENT, older code path that only handles `finding_type in {"vulnerability", "cspm", "alert", "compliance"}`. The nscan/vuln/fim findings that `scan_for_remediable_findings()` already gathers (items 5-7) are never actually remediated by the running scheduler today, because `generate_plan()` returns `None` for those types (`"No plan for {finding.finding_id}"` failure, logged every cycle).
**Why it happens:** Phase 53 built `remediate()`/`select_playbook()` as a complete, tested subsystem but never wired a production trigger for it — likely deferred to whichever future phase would actually need real-time (rather than 300s-interval-polled) dispatch.
**How to avoid:** This phase's `ueba_service.py` call site is the FIRST real production caller of `remediate()`. Build it as a direct, event-driven call (background task off the UEBA analyze endpoints), not as a retrofit of the existing broken `run_cycle()` loop — fixing that loop's nscan/vuln/fim dead path is a pre-existing gap outside this phase's scope fences (CONTEXT.md doesn't mention it).
**Warning signs:** A plan task that says "wire the anomaly finding_type into `scan_for_remediable_findings()`" without also either (a) fixing `generate_plan()` to route to `remediate()` for playbook-eligible types, or (b) building the direct event-driven call site instead — option (b) is the smaller, locked-decision-consistent lift.

### Pitfall 2: Concurrency-lease/dedup collision when `agent_id` is absent
**What goes wrong:** `_acquire_agent_lease()`/`_release_agent_lease()` and `ResponseOrchestrator.is_duplicate_task`'s per-agent dedup key both fall back to `finding.agent_id or "auto"`. For the majority of UEBA anomaly types (no real `agent_id` — see Pattern 2), every anomaly-triggered remediation attempt across an ENTIRE tenant shares the single `"auto"` lease bucket (capped at `MAX_CONCURRENT_PER_AGENT=2`) and dedup key. A burst of distinct users' brute-force anomalies within the same tenant could silently `defer` or dedup-skip legitimate, unrelated containment attempts.
**Why it happens:** The lease/dedup mechanism was designed for genuinely agent-scoped findings (nscan/vuln/fim), where `agent_id` uniquely identifies the endpoint being acted on. Anomaly findings without a real agent_id break that assumption.
**How to avoid:** Given Architecture Pattern 2's recommendation (only `shadow_ai_detected` anomalies actually reach `remediate()` with a real `agent_id`), this collision risk is naturally minimized — non-dispatchable anomaly types never reach `_acquire_agent_lease()` at all (they resolve to `no_playbook` before dispatch). If the planner later expands containment coverage to user/IP-scoped anomalies, this pitfall becomes live and needs a dedicated non-`"auto"` keying strategy (e.g., a synthetic per-user lease key) — out of scope for now, but worth a one-line planner note.
**Warning signs:** Tests that assert 3+ concurrent anomaly remediations all succeed without checking the shared `"auto"` lease bucket cap.

### Pitfall 3: Webhook delivery failure must not block the correlation/finding pipeline
**What goes wrong:** If the new OCSF push calls are awaited inline inside `_trigger_alert()`/`_persist_alert()`/`write_audit()`'s call sites, a slow or down SIEM endpoint (10s httpx timeout, per `webhook_service.py`) stalls the correlation/anomaly/remediation pipeline for every tenant sharing that code path.
**Why it happens:** `WebhookService.trigger_webhook()` is `async def` and awaits every webhook POST sequentially inside `async with httpx.AsyncClient()`; nothing about the function itself is fire-and-forget — the fire-and-forget property comes entirely from the CALLER wrapping it in `asyncio.create_task(...)` (verified in `notification_manager.py`, the existing pattern).
**How to avoid:** Every new call site added by this phase MUST wrap `trigger_webhook(...)` (or a thin new OCSF-formatting wrapper around it) in `asyncio.create_task(...)`, exactly like `notification_manager.send_notification()` already does. Never `await webhook_service.trigger_webhook(...)` directly from a hot path.
**Warning signs:** A plan task phrased as "call `trigger_webhook` after creating the security case" without specifying the `asyncio.create_task` wrap.

### Pitfall 4: Pre-existing UEBA auto-ban already bypasses an approval gate — this phase does not touch it
**What goes wrong:** A reviewer or the planner might read D-04 ("no autonomy exception... regardless of anomaly confidence") and assume this phase must also gate `ueba_service.py`'s EXISTING `brute_force`/`known_malicious_ip` auto-ban-at-score≥80 behavior (`analyze_login`'s `_AUTO_BAN_RULES` block, which calls `ip_ban_service.ban_ip(..., auto=True)` with zero approval step).
**Why it happens:** That auto-ban is a different, pre-existing (`47-RESEARCH.md`-era) mechanism — a platform-level API-request IP ban via `ip_bans` collection, completely separate from the Phase 53 agent-dispatch playbook engine D-04 is scoped to. It predates this phase and is out of its file scope.
**How to avoid:** State explicitly in the plan/verification docs that this pre-existing auto-ban is a KNOWN, DELIBERATELY UNCHANGED behavior this phase does not modify — not a gap this phase silently left open. This avoids a reviewer flagging it as a missed D-04 violation.
**Warning signs:** UAT/verification criteria that test "no anomaly-triggered action bypasses approval" without carving out this pre-existing, out-of-file-scope exception explicitly.

## Runtime State Inventory

Not applicable — this is a greenfield-within-existing-files phase (extending running code with new finding types and call sites), not a rename/refactor/migration phase. No stored-data renames, no OS-registered state changes, no secret/env-var renames.

## Code Examples

### Example 1: Existing bounded-read + normalize + merge pattern to replicate for `remediation_audit` correlation input
```python
# Source: backend/native_security_ops_endpoints.py (Phase 54, verified in repo)
scans = await db.security_scan_results.find({"tenantId": tenant_id}).to_list(length=200)
vulns = await db.vulnerabilities.find({"tenantId": tenant_id}).to_list(length=200)
fim = await db.fim_events.find({"tenantId": tenant_id}).to_list(length=200)
# This phase adds a 4th bounded read the same way:
remediation_events = await db.remediation_audit.find({"tenantId": tenant_id}).to_list(length=200)
```

### Example 2: Existing deterministic playbook selection to extend (not replace)
```python
# Source: backend/remediation_playbook_service.py select_playbook() (verified in repo)
def select_playbook(finding, playbooks=None):
    ...
    finding_type = _finding_attr(finding, "finding_type")
    details = _finding_attr(finding, "details", {}) or {}

    if finding_type == "fim":
        return by_name.get("restore_file")
    if finding_type == "nscan":
        scan_type = details.get("type") or details.get("scan_type")
        return by_name.get("block_ip") if scan_type == "ip" else by_name.get("kill_process")
    if finding_type == "vuln":
        cve_id = details.get("cveId") or details.get("cve_id")
        return by_name.get("patch_package") if cve_id else by_name.get("disable_service")

    # NEW branch this phase adds:
    if finding_type == "anomaly":
        if details.get("anomaly_rule") == "shadow_ai_detected" and _finding_attr(finding, "agent_id"):
            return by_name.get("kill_process")
        return None  # honest no_playbook outcome for user/IP-scoped anomalies without an agent

    return None
```

### Example 3: Existing test pattern to replicate for the new `anomaly` finding_type
```python
# Source: backend/tests/test_remediation_guards.py (verified in repo — pattern to clone)
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

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `remediate()` deterministic playbook engine untriggered in production | `remediate()` gets its first real production call site (this phase) | This phase | The nscan/vuln/fim dead-call-site gap (Pitfall 1) predates this phase and is NOT fixed by it — only the new `anomaly` path gets a real caller |

**Deprecated/outdated:** Nothing in this phase's domain is deprecated — all referenced code (`siem_engine.py`, `remediation_playbook_service.py`, `webhook_service.py`, `ocsf_endpoints.py`) is current, actively-used-elsewhere code as of this research date.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | Recommending `ueba_service.py`'s per-event rule engine (not `ueba_engine.py`'s batch ML score) as the containment trigger is the best fit for "real-time predictive" per the phase goal | Architecture Pattern 2 | If the user actually wants the ML/Isolation-Forest score as the trigger, the plan would need a different (periodic, not event-driven) call-site design. This is a reasoned synthesis from the two engines' actual invocation shapes, not a locked CONTEXT.md decision — flag for confirmation if the planner wants extra certainty |
| A2 | Only `shadow_ai_detected` anomalies should reach `remediate()` with dispatch capability this phase; the other 9 UEBA rule types should resolve to a recorded-but-not-actioned `no_playbook` outcome | Architecture Pattern 2 | If the user expects ALL anomaly types to trigger SOME containment action, this scope is narrower than that expectation — but the alternative (inventing a new non-agent-dispatched action) risks violating the "no second dispatch engine" scope fence. This is the single most consequential judgment call in this research and should be confirmed with the user before planning locks it in |
| A3 | New webhook `event_type` string names (`"threat.correlation"`, `"ueba.anomaly"`, `"remediation.event"`) are illustrative, not an existing convention found in the codebase | Architecture Pattern 3 | Low risk — these are free-form strings operators subscribe to via `events: []`; any consistent naming works, no code depends on a specific string today |

**If this table needs resolution before planning:** A2 is the item most worth a quick user confirmation (or explicit planner call) since it changes AUT-03's effective containment coverage.

## Open Questions

1. **Should Plan 55-03 (automated containment/isolation) also add a NEW vendored playbook (e.g., a `shadow_ai_kill.yaml` distinct from the generic `kill_process.yaml`) rather than reusing `kill_process` verbatim?**
   - What we know: `kill_process.yaml`'s `match: {scan_type_not: ip}` and its single step (`action: kill_process, params: {target: "{{finding.resource_id}}"}`) already fits a shadow-AI process-kill use case structurally.
   - What's unclear: Whether reusing the SAME playbook for both `nscan` (malicious-process-scan) and `anomaly` (shadow-AI) findings could create confusing audit-trail entries (same `playbook: "kill_process"` name for two semantically different triggers).
   - Recommendation: Reuse `kill_process.yaml` as-is unless the planner decides the audit-trail clarity is worth a near-duplicate playbook file — this is a small, low-risk implementation detail, not an architectural one.

2. **Where exactly should the new `SiemEngine` correlation-extension method live — a new method on the existing `SiemEngine` class, or a new module-level function `siem_engine.py` calls into?**
   - What we know: `SiemEngine.__init__(self, db)` already takes `db`; `get_siem_engine(db)` is the existing factory. Both `_evaluate_rules`/`_match_rule` operate on the normalized `event` dict shape.
   - What's unclear: Whether the cleanest extension is (a) a new `async def correlate_native_findings(self, tenant_id)` method that normalizes the 4 native collections into the same `event` shape and re-runs `_evaluate_rules`, or (b) a standalone function outside the class that queries+correlates independently and writes directly to `security_cases`.
   - Recommendation: Option (a) — reusing `_evaluate_rules`/`_match_rule`/`_trigger_alert` means existing `siem_rules` documents automatically apply to native findings too (operators get correlation "for free" without redefining rules), which is the strongest reading of D-01's "extend, don't rebuild."

## Environment Availability

Not applicable — this phase has no new external tool/service/runtime dependencies. All required infrastructure (MongoDB via Motor, httpx for outbound webhooks, the existing Rust agent instruction-poll loop) is already running and exercised by Phase 51/53/54's test suites.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (via `asyncio_mode`/`pytestmark = pytest.mark.asyncio`), run through `backend/venv/bin/python -m pytest` |
| Config file | none dedicated — repo-wide convention, no `pytest.ini`/`pyproject.toml [tool.pytest]` section found; tests use `pytestmark = pytest.mark.asyncio` per-file |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/test_remediation_guards.py backend/tests/test_remediation_playbook.py -q` |
| Full suite command | `cd backend && venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| INT-04 | `SiemEngine` correlation extension ingests native findings and creates a `security_cases` doc when a `siem_rules` condition matches | unit | `pytest backend/tests/test_siem_engine.py -x` | ❌ Wave 0 (new file; no `test_siem_engine.py` exists today) |
| INT-04 | Correlation reads are bounded (never unbounded `.find({})` scans) | unit | same file as above, assert `.to_list(length=N)` cap via mock call args | ❌ Wave 0 |
| AUT-03 | `select_playbook()` new `anomaly` branch: `shadow_ai_detected` + real `agent_id` → `kill_process`; anything else → `None` | unit | `pytest backend/tests/test_remediation_playbook.py -k anomaly -x` | ❌ Wave 0 (extend existing file) |
| AUT-03 | New UEBA→`remediate()` call site fires exactly once per anomalous event, deduped via `ResponseOrchestrator.is_duplicate_task`, and NEVER bypasses the destructive-playbook approval gate | unit | `pytest backend/tests/test_ueba_remediation_trigger.py -x` | ❌ Wave 0 (new file) |
| AUT-03 | Same approval/dry-run/lease/audit path as Phase 53 (no bypass) | integration | `pytest backend/tests/test_remediation_guards.py -x` (existing, re-run to confirm no regression) | ✅ exists |
| COMM-01 | New OCSF-formatted webhook payloads use `class_uid=2004, category_uid=2` and are dispatched via `asyncio.create_task` (never awaited inline) | unit | `pytest backend/tests/test_webhook_signing.py -k ocsf -x` | ❌ Wave 0 (extend existing file, or new `test_soc_integration.py`) |
| COMM-01 | Webhook delivery failure does not raise/propagate into the calling correlation/anomaly/remediation code path | unit | same file as above, mock `httpx.AsyncClient.post` to raise, assert caller doesn't except | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `backend/venv/bin/python -m pytest backend/tests/test_remediation_guards.py backend/tests/test_remediation_playbook.py backend/tests/test_webhook_signing.py -q`
- **Per wave merge:** `cd backend && venv/bin/python -m pytest -q` (full suite — baseline per project memory is ~1343 passed / 3 pre-existing unrelated fails as of 2026-07-22; re-baseline at phase start since Phase 46-53 have landed since)
- **Phase gate:** Full suite green (modulo the same pre-existing, documented unrelated failures) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_siem_engine.py` — covers INT-04 (no test file for `siem_engine.py` exists today at all — the module has zero direct test coverage currently, only exercised indirectly via `stream_processing_endpoints.py`'s own tests if any)
- [ ] `backend/tests/test_ueba_remediation_trigger.py` — covers AUT-03's new call site (dedup, approval-gate-preserving, fire-and-forget dispatch)
- [ ] Extend `backend/tests/test_remediation_playbook.py` — covers the new `select_playbook()` anomaly branch
- [ ] Extend `backend/tests/test_webhook_signing.py` (or new `test_soc_integration.py`) — covers COMM-01's OCSF shape + fire-and-forget dispatch
- [ ] No framework install needed — pytest/pytest-asyncio already present and used throughout `backend/tests/`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | no | No new auth surface — all new endpoints/call-sites reuse existing `get_current_user`/`require_permission` deps |
| V3 Session Management | no | Not touched by this phase |
| V4 Access Control | yes | New/extended correlation and remediation-trigger code paths must preserve tenant scoping via `set_tenant_id`/`TenantIsolatedCollection` — never `db._db` (explicit scope fence) |
| V5 Input Validation | yes | New OCSF payload builder and UEBA→`RemediationFinding` construction must validate `tenant_id`/`agent_id`/`resource_id` presence before use (fail closed, matching `TenantIsolatedCollection`'s existing fail-closed design) |
| V6 Cryptography | yes (reuse only) | Outbound SIEM webhook signing reuses the EXISTING per-webhook HMAC-SHA256 (`X-Webhook-Signature`) in `webhook_service.py` — never hand-roll new crypto |
| V13 (SSRF, OCSF/API-adjacent) | yes (reuse only) | Outbound webhook URLs are validated by the EXISTING `_is_safe_webhook_url` SSRF blocklist in `webhook_service.py` (private/loopback/link-local/cloud-metadata CIDR ranges) — do not build a second URL validator |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| Cross-tenant correlation-input leakage (a correlation query missing a `tenantId` filter merges findings across tenants) | Information Disclosure | Every new correlation read MUST go through `set_tenant_id(tenant_id)` + the tenant-isolated `db` handle (never `db._db`) — exact pattern already used by `scan_for_remediable_findings()`'s per-tenant `_tctx = set_tenant_id(tenant_id)` / `reset_tenant_id(_tctx)` blocks |
| SSRF via attacker-controlled SIEM webhook URL | Tampering / Elevation of Privilege | Already mitigated by the existing `_is_safe_webhook_url` blocklist — no new code needed, just don't bypass it |
| Approval-gate bypass via a crafted high-confidence anomaly score | Elevation of Privilege | D-04 explicitly forbids any confidence-based bypass; `_dispatch_and_verify()`'s `is_destructive` check (based on the PLAYBOOK's steps, not the finding's confidence/severity) is what gates approval — the new anomaly branch must not introduce a severity/confidence shortcut around it |
| Replay/duplicate-dispatch of the same anomaly causing repeated destructive actions | Denial of Service (self-inflicted) | `ResponseOrchestrator.is_duplicate_task` dedup (5-10 min window) — MUST be called before `remediate()` at the new UEBA call site, exactly like every other `remediate()`-adjacent caller does |

## Sources

### Primary (HIGH confidence — direct codebase verification via Read/Grep this session)
- `backend/siem_engine.py` — full file read; correlation rule engine, `_normalize_log`/`_evaluate_rules`/`_match_rule`/`_trigger_alert` traced
- `backend/threat_intel_endpoints.py` — full file read; `scan_artifact`/`get_threat_feed`/`enrich_security_event` traced
- `backend/ueba_engine.py` — full file read; `calculate_risk_score`/`train_isolation_forest`/`_generate_ueba_alert` traced
- `backend/ueba_service.py` — full file read; `analyze_login`/`analyze_data_access`/`_RULES`/`_persist_alert`/auto-ban block traced
- `backend/ueba_endpoints.py` — full file read; confirmed `ueba_engine`'s only production trigger is the rate-limited manual `/calculate-all` endpoint
- `backend/autonomous_remediation_service.py` — read in full (multiple passes: 1-120, 300-600, 600-780, 780-980); `remediate()`, `select_playbook` call site, `_dispatch_and_verify`, `_acquire_agent_lease`, `run_cycle`, `generate_plan`/`execute_plan` all traced
- `backend/remediation_playbook_service.py` — full file read; `select_playbook`/`ACTION_MAP`/`validate`/`load_playbooks` traced
- `backend/playbooks/*.yaml` (5 files) — all read; confirmed exact agent-dispatch action shape
- `backend/remediation_audit_service.py` — full file read; `write_audit`/`list_audit` traced
- `backend/webhook_service.py` — full file read; `trigger_webhook`/`_send_single_webhook`/`_is_safe_webhook_url` traced
- `backend/webhook_endpoints.py` — full file read; webhook registration/`events`-array contract, HMAC signing, `test_webhook` traced
- `backend/ocsf_endpoints.py` — full file read; `class_uid=2004`/`category_uid=2` OCSF shape traced
- `backend/notification_manager.py` — full file read; fire-and-forget `asyncio.create_task` precedent confirmed
- `backend/stream_processing_endpoints.py` — full file read; confirmed `SiemEngine`'s only production caller (`raw_logs` topic)
- `backend/native_security_ops_endpoints.py` — full file read; Phase 54's bounded-read/normalize/merge/paginate pattern (the "correlation input volume" precedent CONTEXT.md points at) traced
- `backend/database.py` (lines 1-160) — `TenantIsolatedCollection`/`TenantIsolatedDatabase` exemption list traced; confirmed none of this phase's collections are exempted (so `set_tenant_id` context is mandatory)
- `backend/app_background_tasks.py` — full file read (relevant sections); confirmed `autonomous_remediation_loop()` calls `run_cycle()`, not `remediate()`
- `backend/remediation_control_endpoints.py` — full file read; approve/deny/audit-read endpoints traced
- `backend/response_orchestrator.py` (`is_duplicate_task`, lines 231-250+) — dedup key shape traced
- `backend/tests/test_remediation_guards.py` — read; exact mocking/test pattern precedent for the new `anomaly` finding_type tests
- `.planning/phases/54-integration-operator-ui/54-01-PLAN.md` — read; confirmed the "bound/paginate" precedent CONTEXT.md's pitfall references
- `.planning/ROADMAP.md` (grep) — confirmed INT-04/AUT-03/COMM-01 requirement-ID location (not in current REQUIREMENTS.md)
- `.planning/config.json` — confirmed `nyquist_validation: true`, `security_enforcement: true`, `security_asvs_level: 1`, all web-search providers `false`

### Secondary (MEDIUM confidence — external doc, verified against a real schema browser)
- [OCSF Schema — Detection Finding (schema.ocsf.io)](https://schema.ocsf.io/1.7.0/classes/detection_finding) — confirmed `class_uid=2004`, `category_uid=2` (Findings) is the correct class for SIEM/EDR/XDR correlation-engine alerts, matching what `ocsf_endpoints.py` already emits

### Tertiary (LOW confidence)
None — no findings in this research rest solely on unverified training-data recall; every architectural claim traces to a specific file/line read this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; every dependency already in active use and traced
- Architecture: HIGH for the extension points (all traced to real function signatures); MEDIUM for the two Open Questions (implementation-detail choices, not architectural risk)
- Pitfalls: HIGH — all 4 pitfalls are directly observed code facts (dead call site, shared lease key, awaited-vs-fire-and-forget, pre-existing auto-ban), not speculative

**Research date:** 2026-08-03
**Valid until:** 30 days (stable, internal-codebase-extension research — the only external-facing dependency, the OCSF schema convention, is a stable 1.x spec unlikely to change)
