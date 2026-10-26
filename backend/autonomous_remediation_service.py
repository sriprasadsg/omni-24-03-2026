"""
Autonomous Remediation Service (deterministic playbooks through Autonomous Ops)

Turns a finding into a vendored/operator YAML playbook (remediation_playbook_service, no LLM),
asks the autonomy gate (autonomous_ops.gate, GATE-03) what to do, and then either records a
simulation, parks an approval card, or dispatches the playbook's steps. Every step, verify
re-scan and compensation is written by ``gate.execute`` as a stamped registry command; this
module writes no agent instruction itself (GATE-05). Approvals and denials go through the
ledger (autonomous_ops.approvals) and the "remediation" dispatcher registered at the foot of
this module. The earlier LLM path (plan generation, scripts, scheduled cycle) no longer exists.
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from autonomous_ops import approvals
from autonomous_ops.scope import raw, tenant_scope
from database import get_database
from tenant_context import set_tenant_id, reset_tenant_id

logger = logging.getLogger(__name__)

# Configuration
AUTONOMOUS_REMEDIATION_DRY_RUN = os.getenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "true").lower() in ("1", "true", "yes")
MAX_AUTO_SEVERITY = os.getenv("MAX_AUTO_SEVERITY", "medium").lower()

# Bounded polling for the 53-03 playbook loop: how long to wait for the
# agent to report a dispatched step's result, and for a re-check to prove
# a finding is actually cleared. A timeout on either NEVER counts as
# resolved — it counts as unverified (AUTO-01: verify is grounded).
STEP_POLL_TIMEOUT_SEC = int(os.getenv("REMEDIATION_STEP_POLL_TIMEOUT_SEC", "60"))
STEP_POLL_INTERVAL_SEC = int(os.getenv("REMEDIATION_STEP_POLL_INTERVAL_SEC", "2"))
VERIFY_TIMEOUT_SEC = int(os.getenv("REMEDIATION_VERIFY_TIMEOUT_SEC", "60"))
VERIFY_POLL_INTERVAL_SEC = int(os.getenv("REMEDIATION_VERIFY_POLL_INTERVAL_SEC", "3"))

# Per-agent concurrency cap (AUTO-03) — a DB lease (remediation_inflight),
# never a process-memory counter, so it holds across uvicorn workers.
MAX_CONCURRENT_PER_AGENT = int(os.getenv("REMEDIATION_MAX_CONCURRENT_PER_AGENT", "2"))
REMEDIATION_LEASE_TTL_SEC = int(os.getenv("REMEDIATION_LEASE_TTL_SEC", "300"))

# Severity order for ceiling check
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class RemediationFinding:
    """Unified representation of a remediable finding."""
    finding_id: str
    finding_type: str  # "vulnerability", "cspm", "alert", "compliance"
    severity: str
    tenant_id: str
    agent_id: Optional[str]
    resource_id: Optional[str]
    details: Dict[str, Any]
    matched_policy: Optional[Dict] = None
    raw_doc: Optional[Dict] = None


def _render_step_params(params: Dict[str, Any], finding: RemediationFinding) -> Dict[str, Any]:
    """Resolves a playbook step's `{{finding.X}}` / `{{finding.details.Y}}`
    templated params against the actual RemediationFinding. Non-template
    values pass through unchanged."""
    rendered: Dict[str, Any] = {}
    for key, template in (params or {}).items():
        if not (isinstance(template, str) and template.startswith("{{") and template.endswith("}}")):
            rendered[key] = template
            continue
        parts = template[2:-2].strip().split(".")
        if not parts or parts[0] != "finding":
            rendered[key] = None
            continue
        value: Any = finding
        for part in parts[1:]:
            value = value.get(part) if isinstance(value, dict) else getattr(value, part, None)
            if value is None:
                break
        rendered[key] = value
    return rendered


# Parameter keys that may never reach an agent: the registry carries actions, not scripts
# (GATE-05 / PROH-81-01), whatever a playbook step contains.
_FORBIDDEN_PARAM_KEYS = ("script",)


def _safe_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """The rendered step parameters without any key that would carry a script."""
    return {k: v for k, v in (params or {}).items() if k not in _FORBIDDEN_PARAM_KEYS}


class _Unregistered:
    """An action name the registry does not know: kept as given so the gate refuses it."""

    def __init__(self, name):
        self.name = name if isinstance(name, str) else str(name)


def _gate_steps(items, finding: "RemediationFinding") -> list:
    """The steps as the gate sees them: [{action: registry name, params: rendered}], in order."""
    from autonomous_ops import registry
    steps = [i if isinstance(i, dict) else {} for i in (items if isinstance(items, list) else [])]
    return [{"action": (registry.resolve(i.get("action")) or _Unregistered(i.get("action"))).name,
             "params": _safe_params(_render_step_params(i.get("params", {}), finding))} for i in steps]


def _finding_from_request_doc(doc: Dict[str, Any]) -> "RemediationFinding":
    """Reconstructs the RemediationFinding a pending remediation_requests
    row was created from, so approve_remediation() can resume dispatch
    without re-scanning."""
    return RemediationFinding(
        finding_id=doc.get("findingId"),
        finding_type=doc.get("findingType"),
        severity=doc.get("findingSeverity"),
        tenant_id=doc.get("tenantId"),
        agent_id=doc.get("agentId"),
        resource_id=doc.get("findingResourceId"),
        details=doc.get("findingDetails") or {},
    )


class AutonomousRemediationService:
    """Deterministic playbook remediation decided by the autonomy gate."""

    def _severity_within_ceiling(self, severity: str) -> bool:
        """Check if finding severity is within the auto-execute ceiling."""
        finding_level = SEVERITY_ORDER.get(severity.lower(), 4)
        ceiling_level = SEVERITY_ORDER.get(MAX_AUTO_SEVERITY.lower(), 2)
        return finding_level <= ceiling_level

    async def scan_for_remediable_findings(self, tenant_id: str) -> List[RemediationFinding]:
        """
        Scan all remediable finding types for this tenant.
        Returns list of findings that match enabled auto-execute policies.
        """
        from response_orchestrator import ResponseOrchestrator

        db = get_database()
        orchestrator = ResponseOrchestrator()
        findings: List[RemediationFinding] = []

        # 1. Vulnerabilities (open, severity within ceiling)
        try:
            _tctx = set_tenant_id(tenant_id)
            vulns = await db.vulnerabilities.find({
                "status": {"$in": ["open", "detected", "confirmed"]},
                "severity": {"$in": list(SEVERITY_ORDER.keys())}
            }).to_list(length=200)

            for vuln in vulns:
                sev = (vuln.get("severity") or "").lower()
                if not self._severity_within_ceiling(sev):
                    continue
                # Check if there's an auto-execute policy for this vuln type
                alert_like = {
                    "alert_id": vuln.get("id"),
                    "type": "VULNERABILITY",
                    "severity": sev,
                    "cve_id": vuln.get("cveId"),
                    "asset_id": vuln.get("assetId"),
                }
                policies = await db.response_policies.find({
                    "enabled": True, "tenantId": tenant_id, "auto_execute": True
                }).to_list(length=50)
                matched = None
                for policy in policies:
                    if orchestrator._matches(alert_like, policy.get("conditions", [])):
                        matched = policy
                        break
                if matched:
                    findings.append(RemediationFinding(
                        finding_id=vuln.get("id"),
                        finding_type="vulnerability",
                        severity=sev,
                        tenant_id=tenant_id,
                        agent_id=vuln.get("agentId"),
                        resource_id=vuln.get("assetId"),
                        details=vuln,
                        matched_policy=matched,
                        raw_doc=vuln,
                    ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] Vuln scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        # 2. CSPM Findings (cloud security posture)
        try:
            _tctx = set_tenant_id(tenant_id)
            cspm_findings = await db.cspm_findings.find({
                "status": "open",
                "auto_remediable": True,
                "severity": {"$in": list(SEVERITY_ORDER.keys())}
            }).to_list(length=200)

            for finding in cspm_findings:
                sev = (finding.get("severity") or "").lower()
                if not self._severity_within_ceiling(sev):
                    continue
                alert_like = {
                    "alert_id": finding.get("id"),
                    "type": "CSPM_FINDING",
                    "severity": sev,
                    "provider": finding.get("provider"),
                    "resource_id": finding.get("resourceId"),
                    "check_id": finding.get("checkId"),
                }
                policies = await db.response_policies.find({
                    "enabled": True, "tenantId": tenant_id, "auto_execute": True
                }).to_list(length=50)
                matched = None
                for policy in policies:
                    if orchestrator._matches(alert_like, policy.get("conditions", [])):
                        matched = policy
                        break
                if matched:
                    findings.append(RemediationFinding(
                        finding_id=finding.get("id"),
                        finding_type="cspm",
                        severity=sev,
                        tenant_id=tenant_id,
                        agent_id=None,
                        resource_id=finding.get("resourceId"),
                        details=finding,
                        matched_policy=matched,
                        raw_doc=finding,
                    ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] CSPM scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        # 3. XDR Alerts (matched by response policies with auto_execute)
        try:
            _tctx = set_tenant_id(tenant_id)
            alerts = await db.alerts.find({
                "status": "open",
                "severity": {"$in": list(SEVERITY_ORDER.keys())}
            }).to_list(length=200)

            for alert in alerts:
                sev = (alert.get("severity") or "").lower()
                if not self._severity_within_ceiling(sev):
                    continue
                policies = await db.response_policies.find({
                    "enabled": True, "tenantId": tenant_id, "auto_execute": True
                }).to_list(length=50)
                matched = None
                for policy in policies:
                    if orchestrator._matches(alert, policy.get("conditions", [])):
                        matched = policy
                        break
                if matched:
                    findings.append(RemediationFinding(
                        finding_id=alert.get("alert_id") or alert.get("id"),
                        finding_type="alert",
                        severity=sev,
                        tenant_id=tenant_id,
                        agent_id=alert.get("agent_id"),
                        resource_id=alert.get("resource_id"),
                        details=alert,
                        matched_policy=matched,
                        raw_doc=alert,
                    ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] Alert scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        # 4. Compliance Control Failures (where AI remediation exists)
        try:
            _tctx = set_tenant_id(tenant_id)
            failed_controls = await db.asset_compliance.find({
                "status": "fail",
                "controlId": {"$exists": True}
            }).to_list(length=200)

            for control in failed_controls:
                sev = (control.get("severity") or "medium").lower()
                if not self._severity_within_ceiling(sev):
                    continue
                # Check for auto-execute compliance remediation policy
                alert_like = {
                    "alert_id": control.get("id"),
                    "type": "COMPLIANCE_FAILURE",
                    "severity": sev,
                    "control_id": control.get("controlId"),
                    "framework": control.get("frameworkId"),
                }
                policies = await db.response_policies.find({
                    "enabled": True, "tenantId": tenant_id, "auto_execute": True
                }).to_list(length=50)
                matched = None
                for policy in policies:
                    if orchestrator._matches(alert_like, policy.get("conditions", [])):
                        matched = policy
                        break
                if matched:
                    findings.append(RemediationFinding(
                        finding_id=control.get("id"),
                        finding_type="compliance",
                        severity=sev,
                        tenant_id=tenant_id,
                        agent_id=control.get("agentId"),
                        resource_id=control.get("assetId"),
                        details=control,
                        matched_policy=matched,
                        raw_doc=control,
                    ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] Compliance scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        # 5. Native NSCAN (malicious scan verdicts) — deterministic playbook
        # selection, no response_policies gate (Phase 53, AUTO-01).
        try:
            _tctx = set_tenant_id(tenant_id)
            scans = await db.security_scan_results.find({
                "tenantId": tenant_id, "verdict": "Malicious",
            }).to_list(length=100)
            for s in scans:
                findings.append(RemediationFinding(
                    finding_id=str(s.get("id") or s.get("_id") or ""),
                    finding_type="nscan",
                    severity="critical",
                    tenant_id=tenant_id,
                    agent_id=s.get("agentId"),
                    resource_id=s.get("target"),
                    details={"type": s.get("type"), "verdict": s.get("verdict"), "ts": s.get("created_at")},
                    raw_doc=s,
                ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] NSCAN scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        # 6. Native VULN (agent-sourced open vulnerabilities/misconfigs) —
        # deterministic playbook selection (Phase 53, AUTO-01).
        try:
            _tctx = set_tenant_id(tenant_id)
            native_vulns = await db.vulnerabilities.find({
                "tenantId": tenant_id, "status": "Open", "source": "agent",
            }).to_list(length=100)
            for v in native_vulns:
                findings.append(RemediationFinding(
                    finding_id=v.get("id") or str(v.get("_id", "")),
                    finding_type="vuln",
                    severity=(v.get("severity") or "Medium").lower(),
                    tenant_id=tenant_id,
                    agent_id=v.get("agentId"),
                    resource_id=v.get("assetId") or v.get("agentId"),
                    details=v,
                    raw_doc=v,
                ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] Native VULN scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        # 7. FIM drift (Changed paths — Added/Removed have no diffable
        # before-state to restore) — deterministic playbook selection.
        try:
            _tctx = set_tenant_id(tenant_id)
            fim_drift = await db.fim_events.find({
                "tenantId": tenant_id, "change_type": "Changed",
            }).to_list(length=100)
            for f in fim_drift:
                findings.append(RemediationFinding(
                    finding_id=str(f.get("id") or f.get("_id", "")),
                    finding_type="fim",
                    severity="high",
                    tenant_id=tenant_id,
                    agent_id=f.get("agent_id"),
                    resource_id=f.get("path"),
                    details=f,
                    raw_doc=f,
                ))
        except Exception as e:
            logger.warning("[AutonomousRemediation] FIM scan error for tenant %s: %s", tenant_id, e)
        finally:
            reset_tenant_id(_tctx)

        logger.info("[AutonomousRemediation] Tenant %s: found %d remediable findings", tenant_id, len(findings))
        return findings

    async def _poll_task_status(self, db, task_id: str, timeout_sec: int, interval_sec: int,
                                tenant_id: Optional[str] = None) -> str:
        """Polls agent_instructions.status (written by POST .../instructions/result)
        for a terminal state. Returns SUCCESS/FAILURE, or TIMEOUT if the bound
        is exceeded — a timeout is never treated as success. With ``tenant_id`` the
        read is on the raw handle and filtered by tenant explicitly."""
        flt: Dict[str, Any] = {"id": task_id}
        coll = raw(db).agent_instructions if tenant_id else db.agent_instructions
        if tenant_id:
            flt["tenantId"] = tenant_id
        elapsed = 0
        while elapsed <= timeout_sec:
            doc = await coll.find_one(flt)
            status = (doc or {}).get("status")
            if status in ("SUCCESS", "FAILURE"):
                return status
            await asyncio.sleep(max(interval_sec, 0) or 0.01)
            elapsed += interval_sec if interval_sec > 0 else 1
        return "TIMEOUT"

    async def remediate(self, finding: RemediationFinding) -> Dict[str, Any]:
        """Deterministic playbook remediation (Phase 53-03/53-04, AUTO-01/03) decided by the
        autonomy gate (Phase 81, GATE-03): select a YAML playbook (53-01) for the finding,
        build one ActionRequest from it and let ``gate.decide`` choose. Nothing else is
        written before that decision.

        refuse -> {status: refused, reason}; shadow -> {status: shadow, autonomy_action_id};
        needs_approval / suggest -> a ``pending_approval`` remediation_requests row linked to
        the ledger card (approve/deny go through the ledger); allow_auto -> the row is
        ``dispatching`` and the playbook runs at once. Every transition writes an immutable
        remediation_audit record (AUTO-04)."""
        with tenant_scope(finding.tenant_id):
            return await self._remediate(finding)

    async def _remediate(self, finding: RemediationFinding) -> Dict[str, Any]:
        from autonomous_ops import gate, ledger, registry
        from remediation_playbook_service import load_playbooks, select_playbook
        from remediation_audit_service import write_audit

        db = get_database()
        tenant_id = finding.tenant_id

        playbooks = await load_playbooks(db, tenant_id)
        playbook = select_playbook(finding, playbooks)
        if not playbook:
            return {"status": "no_playbook", "finding_id": finding.finding_id}

        remediation_id = f"REM-{finding.finding_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        base_record = {
            "remediation_id": remediation_id,
            "agentId": finding.agent_id,
            "finding": {"id": finding.finding_id, "type": finding.finding_type, "severity": finding.severity},
            "playbook": playbook["name"],
            "tenantId": tenant_id, # Add tenantId to base_record
        }
        await write_audit(db, tenant_id, {**base_record, "stage": "selected"})

        steps = playbook.get("steps") or []
        gate_steps = _gate_steps(steps, finding)
        gate_rollback = _gate_steps(playbook.get("rollback") or [], finding)
        request = gate.ActionRequest(
            tenant_id=tenant_id,
            kind="security",
            origin="ueba" if finding.finding_type == "anomaly" else "remediation",
            actions=[step["action"] for step in gate_steps],
            targets=[finding.agent_id] if finding.agent_id else [],
            params=gate_steps[0]["params"] if gate_steps else {},
            steps=gate_steps, rollback=gate_rollback,       # the gate checks every step (GATE-03/08)
            dedupe_key=f"{tenant_id}|{playbook['name']}|{finding.finding_type}|{finding.finding_id}",
            playbook=playbook["name"],
            # Only an explicit gate_class step key raises the class; the steps' destructive
            # flags never decide it (GATE-04 locked split).
            playbook_raise=registry.playbook_raises(steps),
            reason={"ruleId": f"playbook:{playbook['name']}",
                    "inputs": {"findingId": finding.finding_id, "findingType": finding.finding_type,
                               "severity": finding.severity}},
            reason_text=f"Playbook {playbook['name']} applied to {finding.finding_type} finding {finding.finding_id}.",
            dispatcher="remediation",
            remediation_id=remediation_id,
        )
        decision = await gate.decide(db, request, master_shadow=AUTONOMOUS_REMEDIATION_DRY_RUN)

        if decision.outcome == "refuse":
            await write_audit(db, tenant_id, {**base_record, "stage": "refused", "reason": decision.reason})
            return {"status": "refused", "reason": decision.reason, "remediation_id": remediation_id}
        if decision.state == "shadow":
            await write_audit(db, tenant_id, {**base_record, "stage": "shadow",
                                              "autonomy_action_id": decision.action_id,
                                              "would_have": decision.would_have})
            return {"status": "shadow", "autonomy_action_id": decision.action_id, "remediation_id": remediation_id}

        awaiting = decision.outcome != "allow_auto"       # needs_approval or suggest: a card
        status = "pending_approval" if awaiting else "dispatching"
        request_doc = {
            "id": remediation_id,
            "tenantId": tenant_id,
            "agentId": finding.agent_id,
            "findingId": finding.finding_id,
            "findingType": finding.finding_type,
            "findingSeverity": finding.severity,
            "findingResourceId": finding.resource_id,
            "findingDetails": finding.details,
            "playbookName": playbook["name"],
            "playbook": playbook,
            "status": status,
            "autonomyActionId": decision.action_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await db.remediation_requests.insert_one(dict(request_doc))
        except Exception as exc:
            logger.error("[AutonomousRemediation] request for %s not recorded: %s", remediation_id, exc)
            await ledger.transition(db, tenant_id, decision.action_id,
                                    ("awaiting_approval", "suggested", "dispatching"), "failed",
                                    reasonCode="dispatch_failed")
            return {"status": "failed", "reason": "request_not_recorded", "remediation_id": remediation_id}

        # Store the current state of remediation in the remediation_audit collection
        await write_audit(db, tenant_id, {
            **base_record,
            "stage": "requested",
            "status": status,
            "request_doc": request_doc,
        })

        if awaiting:
            await write_audit(db, tenant_id, {**base_record, "stage": "pending_approval"})
            return {"status": "pending_approval", "remediation_id": remediation_id,
                    "autonomy_action_id": decision.action_id}

        return await self._dispatch_and_verify(remediation_id, finding, playbook, action_id=decision.action_id)

    async def approve_remediation(self, remediation_id: str, tenant_id: str, approver) -> Dict[str, Any]:
        """Operator approval of a pending remediation card (AUTO-03, GATE-10). Delegates to
        ``approvals.approve`` through the ledger row the request is linked to
        (``autonomyActionId``): one compare-and-set decides the winner, a second click gets
        ``already_handled``. The dispatch itself is ``dispatch_approved_remediation``."""
        from autonomous_ops import approvals

        db = get_database()
        with tenant_scope(tenant_id):
            req = await db.remediation_requests.find_one({"id": remediation_id, "tenantId": tenant_id})
            if not req:
                return {"status": "not_found", "remediation_id": remediation_id}
            action_id = req.get("autonomyActionId")
            if not action_id:
                return {"status": "refused", "reason": "legacy_request", "remediation_id": remediation_id}
            out = await approvals.approve(db, tenant_id, action_id, approver=_actor(approver))
        if out.get("status") == "dispatched" and isinstance(out.get("dispatch"), dict):
            return {"remediation_id": remediation_id, **out["dispatch"]}
        return {**{k: v for k, v in out.items() if k != "dispatch"}, "remediation_id": remediation_id}

    async def deny_remediation(self, remediation_id: str, tenant_id: str, approver, reason: str = "") -> Dict[str, Any]:
        """Operator denial of a pending remediation card — cancels it without ever
        dispatching (``approvals.deny`` on the linked ledger row) and records the denial as a
        new (append-only) audit override record."""
        from autonomous_ops import approvals
        from remediation_audit_service import write_audit

        db = get_database()
        with tenant_scope(tenant_id):
            req = await db.remediation_requests.find_one({"id": remediation_id, "tenantId": tenant_id})
            if not req:
                return {"status": "not_found", "remediation_id": remediation_id}
            action_id = req.get("autonomyActionId")
            if not action_id:
                return {"status": "refused", "reason": "legacy_request", "remediation_id": remediation_id}
            out = await approvals.deny(db, tenant_id, action_id, approver=_actor(approver), reason=reason or "")
            if out.get("status") != "denied":
                return {**out, "remediation_id": remediation_id}
            await db.remediation_requests.update_one(
                {"id": remediation_id, "tenantId": tenant_id, "status": "pending_approval"},
                {"$set": {"status": "denied"}})
            await write_audit(db, tenant_id, {
                "remediation_id": remediation_id, "stage": "override_denied",
                "approver": _actor(approver)["username"], "reason": reason,
            })
        return {"status": "denied", "remediation_id": remediation_id}

    async def dispatch_approved_remediation(self, db, row: Dict[str, Any], approver: Dict[str, Any]) -> Dict[str, Any]:
        """The "remediation" dispatcher registered with ``approvals.register_dispatcher``.
        Called with the ledger row already ``approved``. Compare-and-sets the request from
        ``pending_approval`` to ``dispatching`` (a double click, or a request already denied,
        dispatches nothing) and then runs the same ``_dispatch_and_verify`` as an automatic
        playbook: approval only removes the gate, never the lease, compensation or audit."""
        from remediation_audit_service import write_audit
        from pymongo import ReturnDocument

        tenant_id = row["tenantId"]
        remediation_id = row.get("remediationId")
        with tenant_scope(tenant_id):
            req = await db.remediation_requests.find_one_and_update(
                {"id": remediation_id, "tenantId": tenant_id, "status": "pending_approval"},
                {"$set": {"status": "dispatching"}}, return_document=ReturnDocument.AFTER)
            if not req:
                return {"status": "refused", "reason": "request_not_pending"}
            await write_audit(db, tenant_id, {
                "remediation_id": remediation_id, "stage": "override_approved",
                "approver": (approver or {}).get("username"),
            })
            finding = _finding_from_request_doc(req)
            return await self._dispatch_and_verify(remediation_id, finding, req["playbook"], action_id=row["id"])

    async def _acquire_agent_lease(self, db, agent_id: str, remediation_id: str) -> bool:
        """DB-backed concurrency lease (AUTO-03) — a `remediation_inflight`
        row per active remediation, keyed by agent, with a TTL. Counting via
        a live Mongo query (never process memory) means the cap holds
        across uvicorn workers and a crashed lease self-expires rather than
        deadlocking the agent."""
        now = datetime.now(timezone.utc)
        active = await db.remediation_inflight.count_documents({
            "agentId": agent_id, "expiresAt": {"$gt": now.isoformat()},
        })
        if active >= MAX_CONCURRENT_PER_AGENT:
            return False
        await db.remediation_inflight.insert_one({
            "agentId": agent_id, "remediationId": remediation_id,
            "acquiredAt": now.isoformat(),
            "expiresAt": (now + timedelta(seconds=REMEDIATION_LEASE_TTL_SEC)).isoformat(),
        })
        return True

    async def _release_agent_lease(self, db, agent_id: str, remediation_id: str) -> None:
        await db.remediation_inflight.delete_one({"agentId": agent_id, "remediationId": remediation_id})

    async def _mark(self, db, tenant_id: str, action_id: Optional[str], from_states, to_state: str, **fields) -> None:
        """Move the ledger row (GATE-07). Never raises into the remediation, and a lost
        compare-and-set (the reconciler got there first) is not an error."""
        if not action_id:
            return
        from autonomous_ops import ledger
        try:
            await ledger.transition(db, tenant_id, action_id, from_states, to_state, **fields)
        except Exception as exc:
            logger.error("[AutonomousRemediation] ledger row %s not moved to %s: %s", action_id, to_state, exc)

    async def _dispatch_and_verify(self, remediation_id: str, finding: RemediationFinding, playbook: Dict[str, Any],
                                   action_id: Optional[str] = None) -> Dict[str, Any]:
        """The actual dispatch → poll → verify → (compensate|escalate) body, shared by an
        immediately-allowed remediate() call and an approved card. ``action_id`` is the
        ledger row (gate.decide); every step is written by gate.execute against it and the
        row moves to executed, verified, failed or rolled_back at the audit points below.
        Acquires a per-agent DB lease before dispatching and always releases it."""
        from remediation_audit_service import write_audit

        db = get_database()
        tenant_id = finding.tenant_id
        agent_id = finding.agent_id or "auto"
        base_record = {
            "remediation_id": remediation_id,
            "agentId": finding.agent_id,
            "finding": {"id": finding.finding_id, "type": finding.finding_type, "severity": finding.severity},
            "playbook": playbook["name"],
            "tenantId": tenant_id, # Add tenantId to base_record
        }

        if not await self._acquire_agent_lease(db, agent_id, remediation_id):
            await write_audit(db, tenant_id, {**base_record, "stage": "deferred"})
            await db.remediation_requests.update_one(
                {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "deferred"}}
            )
            await self._mark(db, tenant_id, action_id, ("approved", "dispatching"), "refused",
                             reasonCode="agent_busy",
                             reasonText="The host is busy with another remediation, so nothing was run.")
            return {"status": "deferred", "remediation_id": remediation_id}

        try:
            steps_dispatched: List[Dict[str, Any]] = []
            for step in playbook.get("steps", []):
                dispatch_status = await self._dispatch_step(finding, step, action_id, "action")
                steps_dispatched.append(dispatch_status)
                if dispatch_status["status"] != "SUCCESS":
                    await write_audit(db, tenant_id, {
                        **base_record, "stage": "dispatch_incomplete", "steps_dispatched": steps_dispatched,
                    })
                    await db.remediation_requests.update_one(
                        {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "unverified"}}
                    )
                    await self._mark(db, tenant_id, action_id, ("approved", "dispatching", "executed"), "failed",
                                     reasonCode="dispatch_failed",
                                     reasonText="The action was not confirmed by the host, so it is treated as failed.")
                    return {"status": "unverified", "remediation_id": remediation_id, "steps_dispatched": steps_dispatched}

            await write_audit(db, tenant_id, {**base_record, "stage": "dispatched", "steps_dispatched": steps_dispatched})
            await self._mark(db, tenant_id, action_id, ("dispatching",), "executed",
                             result={"stepsDispatched": len(steps_dispatched)})

            verification_result = await self._verify_finding_resolved(finding, action_id)
            await write_audit(db, tenant_id, {
                **base_record, "stage": "verified", "steps_dispatched": steps_dispatched,
                "verification_result": verification_result,
            })

            result: Dict[str, Any] = {
                "status": verification_result, "remediation_id": remediation_id, "steps_dispatched": steps_dispatched,
            }

            if verification_result == "resolved":
                await self._mark(db, tenant_id, action_id, ("executed",), "verified")
            elif verification_result == "failed":
                await self._mark(db, tenant_id, action_id, ("executed", "dispatching"), "failed",
                                 reasonCode="verify_failed",
                                 reasonText="The check afterwards still found the problem.")
                rollback_steps = playbook.get("rollback") or []
                if rollback_steps:
                    rollback_dispatched = []
                    for step in rollback_steps:
                        rollback_dispatched.append(await self._dispatch_step(finding, step, action_id, "compensate"))
                    await write_audit(db, tenant_id, {
                        **base_record, "stage": "rollback_dispatched", "rollback_steps": rollback_dispatched,
                    })
                    await self._mark(db, tenant_id, action_id, ("failed",), "rolled_back")
                    result["rollback_dispatched"] = True
                else:
                    await db.alerts.insert_one({
                        "alert_id": f"ESC-{remediation_id}",
                        "type": "REMEDIATION_ESCALATION",
                        "severity": "critical",
                        "status": "open",
                        "agent_id": finding.agent_id,
                        "tenantId": tenant_id,
                        "message": (
                            f"Irreversible remediation '{playbook['name']}' for finding {finding.finding_id} "
                            "failed verification and has no rollback — human review required."
                        ),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    await write_audit(db, tenant_id, {**base_record, "stage": "escalated"})
                    result["escalated"] = True

            await db.remediation_requests.update_one(
                {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": verification_result}}
            )
            return result
        finally:
            await self._release_agent_lease(db, agent_id, remediation_id)

    async def _dispatch_step(self, finding: RemediationFinding, step: Dict[str, Any],
                             action_id: Optional[str] = None, kind: str = "action") -> Dict[str, Any]:
        """Dispatches one playbook step through ``gate.execute`` (kind action, or compensate
        for a verify-failure undo step) and polls it to a grounded terminal state. The gate
        is the only writer: it refuses unless the ledger row allows this kind of instruction
        (and, for an action, no stop is on)."""
        from autonomous_ops import gate
        from remediation_playbook_service import ACTION_MAP

        action = step["action"]
        if not action_id:
            return {"action": action, "status": "refused", "reason": "no_ledger_row"}
        command = ACTION_MAP[action]
        params = _safe_params(_render_step_params(step.get("params", {}), finding))
        db = get_database()
        dispatch = await gate.execute(db, finding.tenant_id, action_id, command=command,
                                      agent_id=finding.agent_id or "auto", params=params, kind=kind)
        task_id = dispatch.get("task_id")
        if dispatch.get("status") != "queued" or not task_id:
            return {"action": action, "status": "refused", "reason": dispatch.get("reason")}

        status = await self._poll_task_status(db, task_id, STEP_POLL_TIMEOUT_SEC, STEP_POLL_INTERVAL_SEC,
                                              tenant_id=finding.tenant_id)
        return {"action": action, "task_id": task_id, "status": status}

    async def _verify_finding_resolved(self, finding: RemediationFinding, action_id: Optional[str] = None) -> str:
        """Grounded, bounded re-check of the finding's own current state.
        Returns 'resolved' ONLY on a definite clear; a timeout, an
        unrecognized finding type, or an ambiguous result returns
        'unverified' — never silently 'resolved'. A confirmed still-bad
        state returns 'failed'."""
        db = get_database()
        _tctx = set_tenant_id(finding.tenant_id)
        try:
            if finding.finding_type == "vuln":
                return await self._verify_vuln_resolved(db, finding)
            if finding.finding_type == "fim":
                return await self._verify_fim_resolved(db, finding)
            if finding.finding_type == "nscan":
                return await self._check_nscan_resolved(db, finding, action_id)
            return "unverified"
        except Exception as e:
            logger.warning("[AutonomousRemediation] Verify failed for %s: %s", finding.finding_id, e)
            return "unverified"
        finally:
            reset_tenant_id(_tctx)

    async def _verify_vuln_resolved(self, db, finding: RemediationFinding) -> str:
        """Polls db.vulnerabilities up to VERIFY_TIMEOUT_SEC — the record
        only flips off 'open' on the next ingest cycle, so an immediate
        still-open read is expected, not a failure. Only a still-explicitly-
        open status AT the timeout bound is a definite negative ('failed');
        a missing/unrecognized status at timeout is genuinely ambiguous
        ('unverified')."""
        from bson import ObjectId
        elapsed = 0
        last_status = None
        query = None
        # finding_id is set from v.get("id") or str(v.get("_id", "")) in scan_for_remediable_findings
        # The document in DB has _id (ObjectId), not an "id" field.
        # Try to parse as ObjectId for _id lookup.
        try:
            query = {"_id": ObjectId(finding.finding_id)}
        except Exception:
            # Fallback: use details to construct unique match (tenantId, agentId, cve_id, affected_path, detail)
            details = finding.details or {}
            query = {
                "tenantId": finding.tenant_id,
                "agentId": details.get("agentId"),
                "cve_id": details.get("cve_id") or details.get("cveId"),
                "affected_path": details.get("affected_path"),
            }
            detail = details.get("detail")
            if detail:
                query["detail"] = detail
        while elapsed <= VERIFY_TIMEOUT_SEC:
            vuln = await db.vulnerabilities.find_one(query)
            if vuln is None:
                return "resolved"
            last_status = (vuln.get("status") or "").lower()
            if last_status in ("patched", "resolved", "closed"):
                return "resolved"
            await asyncio.sleep(max(VERIFY_POLL_INTERVAL_SEC, 0) or 0.01)
            elapsed += VERIFY_POLL_INTERVAL_SEC if VERIFY_POLL_INTERVAL_SEC > 0 else 1
        return "failed" if last_status in ("open", "detected", "confirmed") else "unverified"

    async def _verify_fim_resolved(self, db, finding: RemediationFinding) -> str:
        """Polls the path's latest fim_events row up to VERIFY_TIMEOUT_SEC.
        A still-'Changed' row at the timeout bound is a definite negative
        ('failed'); no row / an unrecognized change_type is ambiguous
        ('unverified')."""
        elapsed = 0
        last_change_type = None
        while elapsed <= VERIFY_TIMEOUT_SEC:
            latest = await db.fim_events.find_one(
                {"tenantId": finding.tenant_id, "path": finding.resource_id},
                sort=[("timestamp", -1)],
            )
            if latest is None:
                return "resolved"
            last_change_type = latest.get("change_type")
            if last_change_type != "Changed":
                return "resolved"
            await asyncio.sleep(max(VERIFY_POLL_INTERVAL_SEC, 0) or 0.01)
            elapsed += VERIFY_POLL_INTERVAL_SEC if VERIFY_POLL_INTERVAL_SEC > 0 else 1
        return "failed" if last_change_type == "Changed" else "unverified"

    async def _check_nscan_resolved(self, db, finding: RemediationFinding, action_id: Optional[str] = None) -> str:
        """A killed process/blocked IP has no periodic re-check like
        vuln/fim do — the only grounded re-check available is to dispatch a
        fresh scan against the same target and read its verdict. The re-scan is a
        ``probe`` written by gate.execute (never a second dispatch channel); with no
        ledger row there is nothing to probe against and the result is unverified."""
        from autonomous_ops import gate

        if not action_id:
            return "unverified"
        scan_type = (finding.details or {}).get("type") or "file"
        param_key = "path" if scan_type == "file" else "target"
        dispatch_ts = datetime.now(timezone.utc).isoformat()
        dispatch = await gate.execute(get_database(), finding.tenant_id, action_id, command=f"scan_{scan_type}",
                                      agent_id=finding.agent_id or "auto",
                                      params={param_key: finding.resource_id}, kind="probe")
        task_id = dispatch.get("task_id")
        if dispatch.get("status") != "queued" or not task_id:
            return "unverified"

        status = await self._poll_task_status(db, task_id, VERIFY_TIMEOUT_SEC, VERIFY_POLL_INTERVAL_SEC,
                                              tenant_id=finding.tenant_id)
        if status != "SUCCESS":
            return "unverified"

        fresh = await db.security_scan_results.find_one(
            {"tenantId": finding.tenant_id, "target": finding.resource_id, "created_at": {"$gt": dispatch_ts}},
            sort=[("created_at", -1)],
        )
        if fresh is None:
            return "unverified"
        return "failed" if fresh.get("verdict") == "Malicious" else "resolved"


def _actor(approver) -> Dict[str, Any]:
    """The approver as the ledger records it: a dict already, or a bare user id/email."""
    if isinstance(approver, dict):
        return approver
    name = str(approver or "unknown")
    return {"username": name, "display": name, "tier": "tenant"}


async def _remediation_dispatcher(db, row: Dict[str, Any], approver: Dict[str, Any]) -> Dict[str, Any]:
    return await AutonomousRemediationService().dispatch_approved_remediation(db, row, approver)


# The ledger dispatches an approved "remediation" card through this module (GATE-10).
approvals.register_dispatcher("remediation", _remediation_dispatcher)
