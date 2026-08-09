"""Operator approve/deny + immutable audit-read surface for the Phase 53
autonomous remediation engine (AUTO-03/04). Approve/deny resume or cancel
a `pending_approval` remediation created by
autonomous_remediation_service.remediate(); every action here is itself
recorded as a new (never-mutated) remediation_audit record.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

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
async def approve_remediation(remediation_id: str, current_user=Depends(_require_ops_permission)):
    tenant_id = getattr(current_user, "tenant_id", None)
    approver = getattr(current_user, "id", None) or getattr(current_user, "email", None)
    result = await AutonomousRemediationService().approve_remediation(remediation_id, tenant_id, approver)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Pending remediation not found")
    return result


@router.post("/{remediation_id}/deny")
async def deny_remediation(
    remediation_id: str,
    body: Dict[str, Any] = Body(default={}),
    current_user=Depends(_require_ops_permission),
):
    tenant_id = getattr(current_user, "tenant_id", None)
    approver = getattr(current_user, "id", None) or getattr(current_user, "email", None)
    reason = (body or {}).get("reason", "")
    result = await AutonomousRemediationService().deny_remediation(remediation_id, tenant_id, approver, reason)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Pending remediation not found")
    return result
