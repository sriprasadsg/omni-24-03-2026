"""
Workflow endpoints for the tickets API: CSAT, merge, and webhook CRUD.

This router shares the same prefix as tickets_endpoints (/api/tickets) and must
be included alongside it in router_registry.py:

    from tickets_workflow_endpoints import router as tickets_workflow_router
    app.include_router(tickets_workflow_router)
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from authentication_service import TokenData
from database import get_database
from rbac_service import rbac_service
from ticket_webhook_service import delete_webhook, get_webhooks, register_webhook
from tickets_models import (
    CSATRequest, MergeRequest, WebhookRequest, _actor, _effective_tenant,
)
from tickets_service import tickets_service

router = APIRouter(prefix="/api/tickets", tags=["Ticket Workflows"])


# ── CSAT ──────────────────────────────────────────────────────────────────────

@router.post("/{ticket_id}/csat")
async def submit_csat(
    ticket_id: str,
    body: CSATRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    """Customer satisfaction rating after ticket resolution."""
    db = get_database()
    tenant_id = _effective_tenant(current_user)
    ticket = await tickets_service.get_ticket(ticket_id, tenant_id=tenant_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.get("status") not in ("resolved", "closed"):
        raise HTTPException(
            status_code=400,
            detail="CSAT can only be submitted for resolved/closed tickets",
        )
    csat = {
        "rating": body.rating,
        "comment": body.comment,
        "submitted_by": _actor(current_user),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[tickets_service.COL].update_one(
        {"id": ticket_id, "tenantId": tenant_id},
        {"$set": {"csat": csat, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True, "csat": csat}


# ── Merge ─────────────────────────────────────────────────────────────────────

@router.post("/{ticket_id}/merge")
async def merge_ticket(
    ticket_id: str,
    body: MergeRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    """Merge this ticket into target_ticket_id. Source ticket is closed as duplicate."""
    db = get_database()
    tenant_id = _effective_tenant(current_user)
    source = await tickets_service.get_ticket(ticket_id, tenant_id=tenant_id)
    target = await tickets_service.get_ticket(body.target_ticket_id, tenant_id=tenant_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="One or both tickets not found")
    if ticket_id == body.target_ticket_id:
        raise HTTPException(status_code=400, detail="Cannot merge a ticket into itself")
    now = datetime.now(timezone.utc).isoformat()
    actor = _actor(current_user)
    # Copy comments from source to target
    for comment in source.get("comments", []):
        comment["merged_from"] = ticket_id
        await db[tickets_service.COL].update_one(
            {"id": body.target_ticket_id},
            {"$push": {"comments": comment}},
        )
    # Close source as duplicate
    await db[tickets_service.COL].update_one(
        {"id": ticket_id},
        {
            "$set": {
                "status": "closed",
                "merged_into": body.target_ticket_id,
                "updated_at": now,
            },
            "$push": {
                "history": {
                    "id": str(uuid.uuid4()),
                    "actor": actor,
                    "action": "merged",
                    "changes": {
                        "target": body.target_ticket_id,
                        "reason": body.reason,
                    },
                    "created_at": now,
                }
            },
        },
    )
    # Add merge note to target
    await db[tickets_service.COL].update_one(
        {"id": body.target_ticket_id},
        {
            "$push": {
                "history": {
                    "id": str(uuid.uuid4()),
                    "actor": actor,
                    "action": "merged_from",
                    "changes": {"source": ticket_id},
                    "created_at": now,
                }
            },
            "$set": {"updated_at": now},
        },
    )
    return {
        "success": True,
        "merged_from": ticket_id,
        "merged_into": body.target_ticket_id,
    }


# ── Webhook CRUD ──────────────────────────────────────────────────────────────

@router.get("/webhooks")
async def list_webhooks(
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    hooks = await get_webhooks(_effective_tenant(current_user))
    return {"webhooks": hooks}


@router.post("/webhooks")
async def create_webhook(
    body: WebhookRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    hook = await register_webhook(
        _effective_tenant(current_user),
        body.url,
        body.events,
        body.secret or "",
    )
    return hook


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook_endpoint(
    webhook_id: str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    deleted = await delete_webhook(_effective_tenant(current_user), webhook_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"success": True}
