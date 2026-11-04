"""Operator approve/deny + immutable audit-read surface for the Phase 53
autonomous remediation engine (AUTO-03/04). Approve/deny resume or cancel
a `pending_approval` remediation created by
autonomous_remediation_service.remediate(); every action here is itself
recorded as a new (never-mutated) remediation_audit record.

Phase 81 (D-24 (c), D-10): approving or denying a card needs the approve tier,
control:autonomous_ops, on an interactive JWT session (get_current_user; API keys
use a different dependency and never reach these routes). Reading the audit trail
keeps manage:active_response. A denial's reason is validated like the reason of
/api/autonomous-ops/actions/{id}/deny (the same model): optional, stripped, at most 500 characters.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from autonomous_ops_endpoints import DecisionBody
from autonomous_remediation_service import AutonomousRemediationService
from authentication_service import get_current_user
from database import get_database
from rbac_utils import verify_permission
from remediation_audit_service import list_audit

logger = logging.getLogger("remediation_control_endpoints")
router = APIRouter(prefix="/api/remediation", tags=["Remediation Control"])


async def _require_ops_permission(current_user=Depends(get_current_user)):
    if not await verify_permission(current_user, "manage:active_response"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user


async def _require_approve_permission(current_user=Depends(get_current_user)):
    if not await verify_permission(current_user, "control:autonomous_ops"):
        raise HTTPException(status_code=403, detail="Permission denied")
    return current_user


def _approver(current_user) -> Dict[str, Any]:
    """Who approved, as the decision ledger records it."""
    name = (getattr(current_user, "username", None) or getattr(current_user, "email", None)
            or getattr(current_user, "id", None) or "unknown")
    return {"username": str(name), "display": str(name), "tier": "tenant"}


@router.get("/audit")
async def get_remediation_audit(
    limit: int = Query(100, ge=1, le=500),
    remediation_id: Optional[str] = Query(None),
    current_user=Depends(_require_ops_permission),
):
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    filters: Dict[str, Any] = {}
    if remediation_id:
        filters["remediation_id"] = remediation_id
    return await list_audit(db, tenant_id, filters=filters, limit=limit)


@router.post("/{remediation_id}/approve")
async def approve_remediation(remediation_id: str, current_user=Depends(_require_approve_permission)):
    tenant_id = getattr(current_user, "tenant_id", None)
    result = await AutonomousRemediationService().approve_remediation(
        remediation_id, tenant_id, _approver(current_user))
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Pending remediation not found")
    return result


@router.post("/{remediation_id}/deny")
async def deny_remediation(
    remediation_id: str,
    body: Optional[DecisionBody] = None,
    current_user=Depends(_require_approve_permission),
):
    tenant_id = getattr(current_user, "tenant_id", None)
    reason = (body.reason if body else None) or ""
    result = await AutonomousRemediationService().deny_remediation(
        remediation_id, tenant_id, _approver(current_user), reason)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Pending remediation not found")
    return result
