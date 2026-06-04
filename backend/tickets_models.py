"""Pydantic request models and shared helpers for the tickets API."""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from authentication_service import TokenData

_SUPER_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _effective_tenant(user: TokenData) -> str:
    """Super admins see all tickets; everyone else is scoped to their tenant.
    Falls back to the TenantMiddleware context var when the JWT field is absent
    (e.g. token issued before tenant_id was indexed in the payload)."""
    if (user.role or "") in _SUPER_ROLES:
        return ""
    tenant = user.tenant_id or ""
    if not tenant:
        try:
            from tenant_context import get_tenant_id
            tenant = get_tenant_id() or ""
        except Exception:
            pass
    return tenant


def _actor(user: TokenData) -> str:
    return user.username or "unknown"


# ── Request models ────────────────────────────────────────────────────────────

class CreateTicketRequest(BaseModel):
    title:             str             = Field(..., max_length=500)
    description:       Optional[str]   = ""
    type:              Optional[str]   = "task"
    priority:          Optional[str]   = "medium"
    assignee:          Optional[str]   = ""
    assignee_group:    Optional[str]   = ""
    watchers:          Optional[List[str]] = []
    tags:              Optional[List[str]] = []
    due_date:          Optional[str]   = None
    sla_hours:         Optional[int]   = None
    linked_assets:     Optional[List[str]] = []
    linked_vulnerabilities: Optional[List[str]] = []
    endpoint_info:     Optional[dict]  = None
    approval_required: Optional[bool]  = False
    custom_fields:     Optional[dict]  = {}
    template_id:       Optional[str]   = None
    # Agent context — if supplied, backend auto-enriches hostname / tenant_name
    agent_id:          Optional[str]   = None


class UpdateTicketRequest(BaseModel):
    title:          Optional[str]        = None
    description:    Optional[str]        = None
    type:           Optional[str]        = None
    priority:       Optional[str]        = None
    status:         Optional[str]        = None
    assignee:       Optional[str]        = None
    assignee_group: Optional[str]        = None
    watchers:       Optional[List[str]]  = None
    tags:           Optional[List[str]]  = None
    due_date:       Optional[str]        = None
    sla_hours:      Optional[int]        = None
    linked_assets:  Optional[List[str]]  = None
    linked_vulnerabilities: Optional[List[str]] = None
    custom_fields:  Optional[dict]       = None


class BulkUpdateRequest(BaseModel):
    ticket_ids: List[str] = Field(..., min_length=1)
    updates:    Dict[str, Any]


class AddCommentRequest(BaseModel):
    text: str = Field(..., max_length=10_000)


class LinkTicketRequest(BaseModel):
    linked_id: str
    link_type: str = "relates_to"


class LogWorkRequest(BaseModel):
    hours:       float = Field(..., gt=0)
    description: str   = ""


class ApproveRequest(BaseModel):
    comment: Optional[str] = ""


class RejectRequest(BaseModel):
    reason: str


class EscalateRequest(BaseModel):
    reason: Optional[str] = ""


class WatcherRequest(BaseModel):
    email: str


class CreateTemplateRequest(BaseModel):
    name:           str
    description:    Optional[str]   = ""
    type:           Optional[str]   = "task"
    priority:       Optional[str]   = "medium"
    assignee:       Optional[str]   = ""
    assignee_group: Optional[str]   = ""
    tags:           Optional[List[str]] = []
    title_template: Optional[str]   = ""
    body_template:  Optional[str]   = ""
    custom_fields:  Optional[dict]  = {}
    sla_hours:      Optional[int]   = None


class QueueRuleRequest(BaseModel):
    rules: List[Dict[str, Any]]


class FieldSchemaRequest(BaseModel):
    fields: List[Dict[str, Any]]


class CSATRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = ""


class MergeRequest(BaseModel):
    target_ticket_id: str = Field(..., description="The ticket to merge INTO (will survive)")
    reason: Optional[str] = ""


class WebhookRequest(BaseModel):
    url: str
    events: List[str]
    secret: Optional[str] = ""
