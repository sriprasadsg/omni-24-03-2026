"""
Ticket configuration routes: watchers, templates, queue rules, and field schema.
Registered alongside tickets_endpoints under the same /api/tickets prefix.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from authentication_service import TokenData
from rbac_service import rbac_service
from tickets_models import (
    CreateTemplateRequest, FieldSchemaRequest, QueueRuleRequest, WatcherRequest,
    _actor, _effective_tenant,
)
from tickets_service import tickets_service

router = APIRouter(prefix="/api/tickets", tags=["Ticket Config"])


# ── Watchers ──────────────────────────────────────────────────────────────────

@router.post("/{ticket_id}/watchers")
async def add_watcher(
    ticket_id:    str,
    body:         WatcherRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    ok = await tickets_service.add_watcher(
        ticket_id, body.email, tenant_id=_effective_tenant(current_user)
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"success": True}


@router.delete("/{ticket_id}/watchers/{email}")
async def remove_watcher(
    ticket_id:    str,
    email:        str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    ok = await tickets_service.remove_watcher(
        ticket_id, email, tenant_id=_effective_tenant(current_user)
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"success": True}


# ── Templates ─────────────────────────────────────────────────────────────────

@router.get("/templates/list")
async def list_templates(
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> List[Dict[str, Any]]:
    return await tickets_service.list_templates(tenant_id=_effective_tenant(current_user))


@router.post("/templates")
async def create_template(
    body:         CreateTemplateRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    return await tickets_service.create_template(
        data=body.model_dump(),
        creator=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )


@router.patch("/templates/{template_id}")
async def update_template(
    template_id:  str,
    body:         CreateTemplateRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    updated = await tickets_service.update_template(
        template_id,
        data=body.model_dump(exclude_none=True),
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Template not found")
    return updated


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id:  str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    deleted = await tickets_service.delete_template(
        template_id, tenant_id=_effective_tenant(current_user)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


# ── Queue / auto-assign config ────────────────────────────────────────────────

@router.get("/queue/config")
async def get_queue_config(
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    return await tickets_service.get_queue_config(tenant_id=current_user.tenant_id or "")


@router.put("/queue/config")
async def save_queue_config(
    body:         QueueRuleRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    return await tickets_service.save_queue_config(
        tenant_id=current_user.tenant_id or "",
        rules=body.rules,
    )


# ── Custom field schema ───────────────────────────────────────────────────────

@router.get("/schema/fields")
async def get_field_schema(
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    return await tickets_service.get_field_schema(tenant_id=current_user.tenant_id or "")


@router.put("/schema/fields")
async def save_field_schema(
    body:         FieldSchemaRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    return await tickets_service.save_field_schema(
        tenant_id=current_user.tenant_id or "",
        fields=body.fields,
    )
