"""
Backend Safety Guardrails
Server-side counterpart to agent/agentic_core/safety.py.
Centralises the action-risk model so the playbook engine, orchestrator,
and autonomous decision service all share one source of truth.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Actions blocked in every code path — no override possible
FORBIDDEN_ACTIONS = frozenset([
    "delete_critical_files",
    "shutdown_production",
    "modify_firewall_allow_all",
    "disable_antivirus",
    "wipe_disk",
    "uninstall_agent",
])

# Actions that always need a human approval token *unless*
# the caller supplies an explicit override context (e.g. auto-triggered by
# the correlation engine with confidence >= AUTO_APPROVE_THRESHOLD).
APPROVAL_REQUIRED_ACTIONS = frozenset([
    "isolate_host",
    "restart_service",
    "modify_configuration",
    "deploy_patch",
    "update_application",
    "rollback_ransomware",
])

# Actions that are safe to execute immediately without review
SAFE_ACTIONS = frozenset([
    "scan_system",
    "collect_logs",
    "check_status",
    "kill_process_low_priority",
    "block_ip",
    "quarantine_file",
    "send_notification",
    "kill_process",
])

# Confidence threshold above which the system can auto-approve
# an action that would otherwise require a human gate
AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.90

# Asset criticality levels that always require human approval regardless
# of confidence or context
HIGH_CRITICALITY_LEVELS = frozenset(["critical", "high"])


class ActionRiskResult:
    __slots__ = ("allowed", "requires_approval", "reason", "risk_level")

    def __init__(
        self,
        allowed: bool,
        requires_approval: bool,
        reason: str,
        risk_level: str = "low",
    ):
        self.allowed = allowed
        self.requires_approval = requires_approval
        self.reason = reason
        self.risk_level = risk_level

    def __repr__(self):  # pragma: no cover
        return (
            f"ActionRiskResult(allowed={self.allowed}, "
            f"requires_approval={self.requires_approval}, "
            f"risk_level={self.risk_level!r}, reason={self.reason!r})"
        )


def evaluate_action(
    action: str,
    *,
    confidence: float = 1.0,
    asset_criticality: Optional[str] = None,
    blast_radius: int = 0,
    auto_approved: bool = False,
) -> ActionRiskResult:
    """
    Evaluate whether an action may proceed autonomously.

    Parameters
    ----------
    action:             The action name (e.g. "isolate_host", "kill_process")
    confidence:         0-1 confidence score from the decision engine
    asset_criticality:  "critical" | "high" | "medium" | "low" | None
    blast_radius:       Number of additional assets/services affected
    auto_approved:      True when the caller holds an explicit approval token
                        (e.g. the correlation engine confirmed at >= 0.9 confidence)

    Returns
    -------
    ActionRiskResult
    """
    action_lc = action.lower().strip()

    # 1. Hard block — never allowed
    for forbidden in FORBIDDEN_ACTIONS:
        if forbidden in action_lc:
            logger.warning("SAFETY: blocked forbidden action '%s'", action_lc)
            return ActionRiskResult(
                allowed=False,
                requires_approval=False,
                reason=f"Action '{action}' is permanently forbidden",
                risk_level="critical",
            )

    # 2. Confidence guard
    if confidence < 0.8:
        return ActionRiskResult(
            allowed=False,
            requires_approval=True,
            reason=f"Confidence too low ({confidence:.2f} < 0.8) — human review required",
            risk_level="medium",
        )

    # 3. Blast radius guard
    if blast_radius > 5:
        return ActionRiskResult(
            allowed=False,
            requires_approval=True,
            reason=f"Blast radius {blast_radius} exceeds limit of 5 entities",
            risk_level="high",
        )

    # 4. Approval-required actions
    needs_approval = any(req in action_lc for req in APPROVAL_REQUIRED_ACTIONS)
    if needs_approval:
        # Allow auto-approval only when confidence is very high AND asset is not critical
        is_critical_asset = asset_criticality in HIGH_CRITICALITY_LEVELS
        high_confidence = confidence >= AUTO_APPROVE_CONFIDENCE_THRESHOLD

        if auto_approved and high_confidence and not is_critical_asset:
            logger.info(
                "SAFETY: auto-approving '%s' (conf=%.2f, criticality=%s)",
                action_lc, confidence, asset_criticality,
            )
            return ActionRiskResult(
                allowed=True,
                requires_approval=False,
                reason="Auto-approved: high confidence, non-critical asset",
                risk_level="medium",
            )

        # Otherwise gate on human approval
        risk = "high" if is_critical_asset else "medium"
        return ActionRiskResult(
            allowed=True,
            requires_approval=True,
            reason=f"Action '{action}' requires human approval"
            + (" (critical asset)" if is_critical_asset else ""),
            risk_level=risk,
        )

    # 5. Passes all checks — proceed
    return ActionRiskResult(
        allowed=True,
        requires_approval=False,
        reason="Action is safe and within autonomy limits",
        risk_level="low",
    )


def log_safety_decision(
    action: str,
    result: ActionRiskResult,
    context: dict,
) -> None:
    """Emit a structured safety audit log entry."""
    logger.info(
        "SAFETY_AUDIT action=%s allowed=%s requires_approval=%s risk=%s reason=%r "
        "execution_id=%s",
        action,
        result.allowed,
        result.requires_approval,
        result.risk_level,
        result.reason,
        context.get("execution_id", "n/a"),
    )
