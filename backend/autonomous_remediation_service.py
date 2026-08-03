"""
Autonomous Remediation Service
Orchestrates continuous detection → planning → execution → verification
for vulnerabilities, CSPM findings, XDR alerts, and compliance failures.
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_database
from tenant_context import set_tenant_id, reset_tenant_id

logger = logging.getLogger(__name__)

# Configuration
AUTONOMOUS_REMEDIATION_DRY_RUN = os.getenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "true").lower() in ("1", "true", "yes")
AUTONOMOUS_REMEDIATION_INTERVAL_SEC = int(os.getenv("AUTONOMOUS_REMEDIATION_INTERVAL_SEC", "300"))
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


@dataclass
class RemediationPlan:
    """Generated remediation plan for a finding."""
    finding: RemediationFinding
    action: str  # e.g., "run_patch_script", "kill_process", "update_security_group"
    script: str
    params: Dict[str, Any]
    requires_approval: bool
    source_service: str  # "remediation_service", "ai_remediation", "cloud_remediation", "agentic"
    model_provenance: Optional[str] = None


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
    """Main orchestrator for autonomous remediation loop."""

    def __init__(self):
        self._initialized = False

    async def _ensure_initialized(self):
        """Lazy-load heavy imports."""
        if not self._initialized:
            # These will be imported on first use to avoid circular imports
            self._initialized = True

    def _severity_within_ceiling(self, severity: str) -> bool:
        """Check if finding severity is within the auto-execute ceiling."""
        finding_level = SEVERITY_ORDER.get(severity.lower(), 4)
        ceiling_level = SEVERITY_ORDER.get(MAX_AUTO_SEVERITY.lower(), 2)
        return finding_level <= ceiling_level

    async def _is_tenant_enabled(self, tenant_id: str, db) -> bool:
        """Check if autonomous remediation is enabled for this tenant."""
        tenant = await db.tenants.find_one({"id": tenant_id}, {"enabledFeatures": 1})
        if not tenant:
            return False
        features = tenant.get("enabledFeatures", [])
        return "autonomousRemediation" in features or "autonomous_remediation" in features

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

    async def generate_plan(self, finding: RemediationFinding) -> Optional[RemediationPlan]:
        """Generate a remediation plan using the appropriate service."""
        try:
            await self._ensure_initialized()

            if finding.finding_type == "vulnerability":
                from remediation_service import RemediationService
                cve_id = finding.details.get("cveId") or finding.details.get("cve_id") or "UNKNOWN"
                asset_id = finding.resource_id or "unknown"
                request = await RemediationService.generate_fix_proposal(
                    tenant_id=finding.tenant_id,
                    asset_id=asset_id,
                    vulnerability_id=finding.finding_id,
                    cve_id=cve_id,
                )
                return RemediationPlan(
                    finding=finding,
                    action="run_remediation_script",
                    script=request.scriptContent,
                    params={"script_type": "powershell" if "powershell" in request.scriptContent.lower() else "bash"},
                    requires_approval=not AUTONOMOUS_REMEDIATION_DRY_RUN,
                    source_service="remediation_service",
                )

            elif finding.finding_type == "cspm":
                from ai_remediation_service import ai_remediation_service
                result = await ai_remediation_service.generate_cspm_remediation(finding.details)
                remediation_text = result.get("remediation", "")
                return RemediationPlan(
                    finding=finding,
                    action="apply_cloud_remediation",
                    script=remediation_text,
                    params={"provider": finding.details.get("provider")},
                    requires_approval=not AUTONOMOUS_REMEDIATION_DRY_RUN,
                    source_service="ai_remediation",
                    model_provenance="primary",
                )

            elif finding.finding_type == "alert":
                # Use AgenticService for autonomous tool selection
                from agentic_service import get_agentic_service
                try:
                    agentic = get_agentic_service()
                    security_context = {
                        "agent_id": finding.agent_id,
                        "alert": finding.details,
                        "findings": [finding.details],
                    }
                    decision = await agentic.run(finding.agent_id or "unknown", security_context)
                    return RemediationPlan(
                        finding=finding,
                        action=decision.get("tool_name", "unknown"),
                        script="",  # Agentic service queues instruction directly
                        params=decision.get("tool_input", {}),
                        requires_approval=not AUTONOMOUS_REMEDIATION_DRY_RUN,
                        source_service="agentic",
                        model_provenance=decision.get("source"),
                    )
                except Exception as e:
                    logger.warning("[AutonomousRemediation] Agentic decision failed: %s", e)
                    return None

            elif finding.finding_type == "compliance":
                from ai_remediation_service import ai_remediation_service
                result = await ai_remediation_service.generate_cspm_remediation(finding.details)
                remediation_text = result.get("remediation", "")
                return RemediationPlan(
                    finding=finding,
                    action="apply_compliance_remediation",
                    script=remediation_text,
                    params={"control_id": finding.details.get("controlId")},
                    requires_approval=not AUTONOMOUS_REMEDIATION_DRY_RUN,
                    source_service="ai_remediation",
                    model_provenance="primary",
                )

        except Exception as e:
            logger.error("[AutonomousRemediation] Plan generation failed for %s: %s", finding.finding_id, e)
            return None

        return None

    async def execute_plan(self, plan: RemediationPlan) -> Dict[str, Any]:
        """Execute the remediation plan. Returns execution result."""
        if AUTONOMOUS_REMEDIATION_DRY_RUN:
            logger.info("[AutonomousRemediation] DRY RUN - would execute: %s for %s",
                        plan.action, plan.finding.finding_id)
            return {"status": "dry_run", "action": plan.action, "finding_id": plan.finding.finding_id}

        try:
            # Dispatch via agent_instructions queue (existing pattern)
            db = get_database()

            task_id = f"AUTO-{plan.finding.finding_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

            # Build instruction for agent. "id" is what report_instruction_result
            # matches on to update status — without it, an inserted doc can never
            # be found again by task_id, so status/verify polling would hang
            # forever. "parameters" mirrors "payload" since agent dispatch arms
            # are split between reading one or the other.
            _step_payload = {
                **plan.params,
                "script": plan.script,
                "finding_id": plan.finding.finding_id,
                "finding_type": plan.finding.finding_type,
            }
            instruction = {
                "id": task_id,
                "type": plan.action,
                "agent_id": plan.finding.agent_id or "auto",
                "payload": _step_payload,
                "parameters": _step_payload,
                "status": "pending",
                "triggered_by": "autonomous_remediation",
                "triggered_by_finding": plan.finding.finding_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Check dedup using ResponseOrchestrator
            from response_orchestrator import ResponseOrchestrator
            orchestrator = ResponseOrchestrator()
            is_dup = await orchestrator.is_duplicate_task(
                agent_id=plan.finding.agent_id or "auto",
                action=plan.action,
                dedup_window_minutes=5,
                tenant_id=plan.finding.tenant_id,
                alert_type=plan.finding.finding_type,
            )
            if is_dup:
                logger.info("[AutonomousRemediation] Duplicate action skipped: %s", plan.action)
                return {"status": "skipped_duplicate", "action": plan.action}

            # Insert into agent_instructions
            await db.agent_instructions.insert_one(instruction)

            # Log decision to agent_ai_decisions
            await self._log_decision(plan, "executed", task_id)

            logger.info("[AutonomousRemediation] Executed %s for finding %s (task %s)",
                        plan.action, plan.finding.finding_id, task_id)
            return {"status": "queued", "task_id": task_id, "action": plan.action}

        except Exception as e:
            logger.error("[AutonomousRemediation] Execution failed: %s", e)
            await self._log_decision(plan, f"failed: {e}", None)
            return {"status": "failed", "error": str(e)}

    async def _poll_task_status(self, db, task_id: str, timeout_sec: int, interval_sec: int) -> str:
        """Polls agent_instructions.status (written by POST .../instructions/result)
        for a terminal state. Returns SUCCESS/FAILURE, or TIMEOUT if the bound
        is exceeded — a timeout is never treated as success."""
        elapsed = 0
        while elapsed <= timeout_sec:
            doc = await db.agent_instructions.find_one({"id": task_id})
            status = (doc or {}).get("status")
            if status in ("SUCCESS", "FAILURE"):
                return status
            await asyncio.sleep(max(interval_sec, 0) or 0.01)
            elapsed += interval_sec if interval_sec > 0 else 1
        return "TIMEOUT"

    async def remediate(self, finding: RemediationFinding) -> Dict[str, Any]:
        """Deterministic playbook remediation (Phase 53-03/53-04, AUTO-01/03):
        select a YAML playbook (53-01) for the finding and either dispatch it
        immediately (no destructive step) or park it `pending_approval`
        (AUTO-03) for an operator to approve/deny via
        approve_remediation()/deny_remediation(). Every transition writes an
        immutable remediation_audit record (AUTO-04)."""
        from remediation_playbook_service import load_playbooks, select_playbook
        from remediation_audit_service import write_audit

        db = get_database()
        tenant_id = finding.tenant_id

        playbooks = await load_playbooks(db)
        playbook = select_playbook(finding, playbooks)
        if not playbook:
            return {"status": "no_playbook", "finding_id": finding.finding_id}

        remediation_id = f"REM-{finding.finding_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        base_record = {
            "remediation_id": remediation_id,
            "agentId": finding.agent_id,
            "finding": {"id": finding.finding_id, "type": finding.finding_type, "severity": finding.severity},
            "playbook": playbook["name"],
        }
        await write_audit(db, tenant_id, {**base_record, "stage": "selected"})

        if AUTONOMOUS_REMEDIATION_DRY_RUN:
            await write_audit(db, tenant_id, {**base_record, "stage": "dry_run"})
            return {"status": "dry_run", "remediation_id": remediation_id}

        is_destructive = any(step.get("destructive") for step in playbook.get("steps", []))
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
            "status": "pending_approval" if is_destructive else "dispatching",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.remediation_requests.insert_one(dict(request_doc))

        if is_destructive:
            await write_audit(db, tenant_id, {**base_record, "stage": "pending_approval"})
            return {"status": "pending_approval", "remediation_id": remediation_id}

        return await self._dispatch_and_verify(remediation_id, finding, playbook)

    async def approve_remediation(self, remediation_id: str, tenant_id: str, approver: str) -> Dict[str, Any]:
        """Operator approval of a pending_approval remediation (AUTO-03).
        Resumes dispatch through the exact same _dispatch_and_verify path
        as a non-destructive playbook — approval only removes the gate, it
        never skips concurrency/rollback/audit."""
        from remediation_audit_service import write_audit

        db = get_database()
        req = await db.remediation_requests.find_one({"id": remediation_id, "tenantId": tenant_id})
        if not req or req.get("status") != "pending_approval":
            return {"status": "not_found", "remediation_id": remediation_id}

        await write_audit(db, tenant_id, {
            "remediation_id": remediation_id, "stage": "override_approved", "approver": approver,
        })
        await db.remediation_requests.update_one(
            {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "dispatching"}}
        )

        finding = _finding_from_request_doc(req)
        return await self._dispatch_and_verify(remediation_id, finding, req["playbook"])

    async def deny_remediation(self, remediation_id: str, tenant_id: str, approver: str, reason: str = "") -> Dict[str, Any]:
        """Operator denial of a pending_approval remediation — cancels it
        without ever dispatching, and records the denial as a new
        (append-only) audit override record."""
        from remediation_audit_service import write_audit

        db = get_database()
        req = await db.remediation_requests.find_one({"id": remediation_id, "tenantId": tenant_id})
        if not req or req.get("status") != "pending_approval":
            return {"status": "not_found", "remediation_id": remediation_id}

        await db.remediation_requests.update_one(
            {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "denied"}}
        )
        await write_audit(db, tenant_id, {
            "remediation_id": remediation_id, "stage": "override_denied", "approver": approver, "reason": reason,
        })
        return {"status": "denied", "remediation_id": remediation_id}

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

    async def _dispatch_and_verify(self, remediation_id: str, finding: RemediationFinding, playbook: Dict[str, Any]) -> Dict[str, Any]:
        """The actual dispatch → poll → verify → (rollback|escalate) body,
        shared by an immediately-eligible remediate() call and a later
        approve_remediation() resume. Acquires a per-agent DB lease before
        ever touching agent_instructions and always releases it, even on
        an early return."""
        from remediation_audit_service import write_audit

        db = get_database()
        tenant_id = finding.tenant_id
        agent_id = finding.agent_id or "auto"
        base_record = {
            "remediation_id": remediation_id,
            "agentId": finding.agent_id,
            "finding": {"id": finding.finding_id, "type": finding.finding_type, "severity": finding.severity},
            "playbook": playbook["name"],
        }

        if not await self._acquire_agent_lease(db, agent_id, remediation_id):
            await write_audit(db, tenant_id, {**base_record, "stage": "deferred"})
            await db.remediation_requests.update_one(
                {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "deferred"}}
            )
            return {"status": "deferred", "remediation_id": remediation_id}

        try:
            steps_dispatched: List[Dict[str, Any]] = []
            for step in playbook.get("steps", []):
                dispatch_status = await self._dispatch_step(finding, step)
                steps_dispatched.append(dispatch_status)
                if dispatch_status["status"] != "SUCCESS":
                    await write_audit(db, tenant_id, {
                        **base_record, "stage": "dispatch_incomplete", "steps_dispatched": steps_dispatched,
                    })
                    await db.remediation_requests.update_one(
                        {"id": remediation_id, "tenantId": tenant_id}, {"$set": {"status": "unverified"}}
                    )
                    return {"status": "unverified", "remediation_id": remediation_id, "steps_dispatched": steps_dispatched}

            await write_audit(db, tenant_id, {**base_record, "stage": "dispatched", "steps_dispatched": steps_dispatched})

            verification_result = await self._verify_finding_resolved(finding)
            await write_audit(db, tenant_id, {
                **base_record, "stage": "verified", "steps_dispatched": steps_dispatched,
                "verification_result": verification_result,
            })

            result: Dict[str, Any] = {
                "status": verification_result, "remediation_id": remediation_id, "steps_dispatched": steps_dispatched,
            }

            if verification_result == "failed":
                rollback_steps = playbook.get("rollback") or []
                if rollback_steps:
                    rollback_dispatched = []
                    for step in rollback_steps:
                        rollback_dispatched.append(await self._dispatch_step(finding, step))
                    await write_audit(db, tenant_id, {
                        **base_record, "stage": "rollback_dispatched", "rollback_steps": rollback_dispatched,
                    })
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

    async def _dispatch_step(self, finding: RemediationFinding, step: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches one playbook step via the shared execute_plan path and
        polls it to a grounded terminal state (never a second dispatch
        channel)."""
        from remediation_playbook_service import ACTION_MAP

        action = step["action"]
        command = ACTION_MAP[action]
        params = _render_step_params(step.get("params", {}), finding)
        step_plan = RemediationPlan(
            finding=finding, action=command, script="", params=params,
            requires_approval=False, source_service="remediation_playbook",
        )
        dispatch = await self.execute_plan(step_plan)
        task_id = dispatch.get("task_id")
        if dispatch.get("status") != "queued" or not task_id:
            return {"action": action, "status": dispatch.get("status") or "FAILURE"}

        db = get_database()
        status = await self._poll_task_status(db, task_id, STEP_POLL_TIMEOUT_SEC, STEP_POLL_INTERVAL_SEC)
        return {"action": action, "task_id": task_id, "status": status}

    async def _verify_finding_resolved(self, finding: RemediationFinding) -> str:
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
                return await self._check_nscan_resolved(db, finding)
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
        elapsed = 0
        last_status = None
        while elapsed <= VERIFY_TIMEOUT_SEC:
            vuln = await db.vulnerabilities.find_one({"id": finding.finding_id})
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

    async def _check_nscan_resolved(self, db, finding: RemediationFinding) -> str:
        """A killed process/blocked IP has no periodic re-check like
        vuln/fim do — the only grounded re-check available is to dispatch a
        fresh scan against the same target and read its verdict, reusing
        the existing scan dispatch path (never a second dispatch channel)."""
        scan_type = (finding.details or {}).get("type") or "file"
        param_key = "path" if scan_type == "file" else "target"
        rescan_plan = RemediationPlan(
            finding=finding, action=f"scan_{scan_type}", script="",
            params={param_key: finding.resource_id},
            requires_approval=False, source_service="remediation_playbook",
        )
        dispatch_ts = datetime.now(timezone.utc).isoformat()
        dispatch = await self.execute_plan(rescan_plan)
        task_id = dispatch.get("task_id")
        if dispatch.get("status") != "queued" or not task_id:
            return "unverified"

        status = await self._poll_task_status(db, task_id, VERIFY_TIMEOUT_SEC, VERIFY_POLL_INTERVAL_SEC)
        if status != "SUCCESS":
            return "unverified"

        fresh = await db.security_scan_results.find_one(
            {"tenantId": finding.tenant_id, "target": finding.resource_id, "created_at": {"$gt": dispatch_ts}},
            sort=[("created_at", -1)],
        )
        if fresh is None:
            return "unverified"
        return "failed" if fresh.get("verdict") == "Malicious" else "resolved"

    async def verify_remediation(self, finding: RemediationFinding, plan: RemediationPlan, result: Dict) -> bool:
        """Verify the remediation was effective. Returns True if fixed."""
        if AUTONOMOUS_REMEDIATION_DRY_RUN:
            return True  # In dry-run, assume success

        try:
            await asyncio.sleep(30)  # Wait for agent to execute

            db = get_database()
            _tctx = set_tenant_id(finding.tenant_id)

            if finding.finding_type == "vulnerability":
                # Re-scan: check if vulnerability status changed
                vuln = await db.vulnerabilities.find_one({"id": finding.finding_id})
                if vuln and vuln.get("status") in ("patched", "resolved", "closed"):
                    return True

            elif finding.finding_type == "cspm":
                # Re-run CSPM check or check finding status
                cspm = await db.cspm_findings.find_one({"id": finding.finding_id})
                if cspm and cspm.get("status") == "resolved":
                    return True

            elif finding.finding_type == "alert":
                # Check if alert was closed
                alert = await db.alerts.find_one({"alert_id": finding.finding_id})
                if alert and alert.get("status") in ("closed", "resolved"):
                    return True

            elif finding.finding_type == "compliance":
                # Re-evaluate control
                control = await db.asset_compliance.find_one({"id": finding.finding_id})
                if control and control.get("status") == "pass":
                    return True

            return False

        except Exception as e:
            logger.warning("[AutonomousRemediation] Verification failed: %s", e)
            return False
        finally:
            reset_tenant_id(_tctx)

    async def _log_decision(self, plan: RemediationPlan, outcome: str, task_id: Optional[str]) -> None:
        """Log autonomous decision to agent_ai_decisions for audit trail."""
        try:
            from ai_orchestration.decision_log import log_ai_decision

            db = get_database()
            await log_ai_decision(
                db,
                surface="autonomous_remediation",
                outcome=outcome,
                prompt_version="AUTO-REMEDIATION-v1",
                model_provenance=plan.model_provenance or "autonomous",
                citation_validation="n/a",
                ref={
                    "finding_id": plan.finding.finding_id,
                    "finding_type": plan.finding.finding_type,
                    "action": plan.action,
                    "task_id": task_id,
                    "dry_run": AUTONOMOUS_REMEDIATION_DRY_RUN,
                },
            )
        except Exception as e:
            logger.debug("[AutonomousRemediation] Decision log failed: %s", e)

    async def run_cycle(self, tenant_id: str) -> Dict[str, Any]:
        """Run one autonomous remediation cycle for a tenant."""
        start = datetime.now(timezone.utc)
        stats = {
            "tenant_id": tenant_id,
            "scanned": 0,
            "planned": 0,
            "executed": 0,
            "verified": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        try:
            db = get_database()
            if not await self._is_tenant_enabled(tenant_id, db):
                return {**stats, "status": "disabled"}

            findings = await self.scan_for_remediable_findings(tenant_id)
            stats["scanned"] = len(findings)

            for finding in findings:
                # Check dedup again before planning
                from response_orchestrator import ResponseOrchestrator
                orchestrator = ResponseOrchestrator()
                is_dup = await orchestrator.is_duplicate_task(
                    agent_id=finding.agent_id or "auto",
                    action="auto_remediate",
                    dedup_window_minutes=5,
                    tenant_id=tenant_id,
                    alert_type=finding.finding_type,
                )
                if is_dup:
                    stats["skipped"] += 1
                    continue

                plan = await self.generate_plan(finding)
                if not plan:
                    stats["failed"] += 1
                    stats["errors"].append(f"No plan for {finding.finding_id}")
                    continue

                stats["planned"] += 1

                result = await self.execute_plan(plan)
                if result.get("status") in ("queued", "dry_run"):
                    stats["executed"] += 1

                    # Verify
                    verified = await self.verify_remediation(finding, plan, result)
                    if verified:
                        stats["verified"] += 1
                    else:
                        # Create ticket for failed verification
                        await self._create_failure_ticket(finding, plan, result)
                else:
                    stats["failed"] += 1
                    stats["errors"].append(f"Execute failed: {result.get('error', 'unknown')}")

        except Exception as e:
            logger.error("[AutonomousRemediation] Cycle error for tenant %s: %s", tenant_id, e)
            stats["errors"].append(str(e))

        stats["duration_sec"] = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info("[AutonomousRemediation] Cycle complete: %s", stats)
        return stats

    async def _create_failure_ticket(self, finding: RemediationFinding, plan: RemediationPlan, result: Dict):
        """Create a remediation ticket when verification fails."""
        try:
            from ticketing_bridge import start_close_loop_scheduler

            db = get_database()
            await db.remediation_tickets.insert_one({
                "ticket_id": f"AUTO-FAIL-{finding.finding_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "tenantId": finding.tenant_id,
                "finding_id": finding.finding_id,
                "finding_type": finding.finding_type,
                "action_attempted": plan.action,
                "execution_result": result,
                "status": "open",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "autonomous_remediation",
            })
            logger.warning("[AutonomousRemediation] Created failure ticket for %s", finding.finding_id)
        except Exception as e:
            logger.error("[AutonomousRemediation] Failed to create ticket: %s", e)