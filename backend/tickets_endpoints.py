import os
import pathlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from authentication_service import TokenData
from rbac_service import rbac_service
from tickets_models import (
    AddCommentRequest, ApproveRequest, BulkUpdateRequest, CreateTicketRequest,
    EscalateRequest, LinkTicketRequest, LogWorkRequest, RejectRequest,
    UpdateTicketRequest, _actor, _effective_tenant,
)
from tickets_service import LINK_TYPES, tickets_service
from database import mongodb, get_database

router = APIRouter(prefix="/api/tickets", tags=["Internal Tickets"])

_UPLOAD_DIR = os.getenv("TICKET_ATTACHMENT_DIR", "/tmp/ticket_attachments")
os.makedirs(_UPLOAD_DIR, exist_ok=True)

_VALID_TRANSITIONS: dict[str, set] = {
    "open":             {"in_progress", "on_hold", "pending_customer", "resolved", "closed"},
    "in_progress":      {"open", "on_hold", "pending_customer", "resolved"},
    "on_hold":          {"open", "in_progress", "pending_customer"},
    "pending_customer": {"open", "in_progress", "resolved"},
    "resolved":         {"closed", "open"},
    "closed":           {"open"},
}


# ── Ticket CRUD ───────────────────────────────────────────────────────────────

@router.get("")
async def list_tickets(
    status:         Optional[str]  = Query(None),
    priority:       Optional[str]  = Query(None),
    type:           Optional[str]  = Query(None),
    assignee:       Optional[str]  = Query(None),
    assignee_group: Optional[str]  = Query(None),
    reporter:       Optional[str]  = Query(None),
    search:         Optional[str]  = Query(None),
    sla_status:     Optional[str]  = Query(None),
    overdue_only:   bool           = Query(False),
    page:           int            = Query(1, ge=1),
    page_size:      int            = Query(50, ge=1, le=200),
    sort_by:        str            = Query("created_at"),
    sort_dir:       int            = Query(-1),
    current_user:   TokenData      = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    import logging as _log
    tenant_id = _effective_tenant(current_user)
    _is_super = (current_user.role or "") in {"Super Admin", "superadmin", "super_admin", "platform-admin"}
    if not tenant_id and not _is_super:
        raise HTTPException(status_code=400, detail="No tenant context — please log out and back in to refresh your session.")
    try:
        return await tickets_service.list_tickets(
            tenant_id=tenant_id,
            status=status, priority=priority, ticket_type=type,
            assignee=assignee, assignee_group=assignee_group, reporter=reporter,
            search=search, sla_status=sla_status, overdue_only=overdue_only,
            page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir,
        )
    except Exception as exc:
        _log.getLogger(__name__).error("[tickets] list_tickets failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list tickets: {type(exc).__name__}")


@router.get("/stats")
async def get_stats(
    reporter:     Optional[str] = Query(None),
    current_user: TokenData     = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    return await tickets_service.get_stats(
        reporter=reporter,
        tenant_id=_effective_tenant(current_user),
    )


@router.post("/bulk")
async def bulk_update(
    body:         BulkUpdateRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    return await tickets_service.bulk_update(
        ticket_ids=body.ticket_ids,
        updates=body.updates,
        actor=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    ticket = await tickets_service.get_ticket(ticket_id, tenant_id=_effective_tenant(current_user))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("")
async def create_ticket(
    request:      Request,
    body:         CreateTicketRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    data = body.model_dump(exclude_none=False)

    if body.template_id:
        tmpl = await tickets_service.list_templates(tenant_id=_effective_tenant(current_user))
        tmpl = next((t for t in tmpl if t["id"] == body.template_id), None)
        if tmpl:
            defaults = tmpl.get("defaults", {})
            for k, v in defaults.items():
                if not data.get(k):
                    data[k] = v

    # ── Auto-enrich from agent document when agent_id is supplied ────────────
    if body.agent_id:
        try:
            caller_tenant = _effective_tenant(current_user)
            agent_query: dict = {"$or": [{"id": body.agent_id}, {"hostname": body.agent_id}]}
            if caller_tenant:
                agent_query["tenantId"] = caller_tenant
            agent_doc = await mongodb.db.agents.find_one(agent_query)
            if agent_doc:
                data["agent_hostname"] = agent_doc.get("hostname") or body.agent_id
                data["agent_id"]       = agent_doc.get("id", body.agent_id)
                tid = agent_doc.get("tenantId", caller_tenant)
                tenant_doc = await mongodb.db.tenants.find_one({"id": tid}, {"name": 1})
                data["tenant_name"] = (tenant_doc or {}).get("name", tid)
                data.setdefault("tags", [])
                if "agent-raised" not in data["tags"]:
                    data["tags"].append("agent-linked")
        except Exception:
            pass  # enrichment is best-effort; ticket is still created

    if not data.get("endpoint_info"):
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        data["endpoint_info"] = {
            "ip_address": client_ip,
            "user_agent": request.headers.get("User-Agent", "unknown"),
        }

    ticket = await tickets_service.create_ticket(
        data=data,
        reporter=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )

    if not ticket.get("assignee"):
        assigned = await tickets_service.auto_assign(ticket)
        if assigned:
            await tickets_service.update_ticket(
                ticket["id"], {"assignee": assigned},
                actor="system", tenant_id=_effective_tenant(current_user),
            )
            ticket["assignee"] = assigned

    try:
        from ticket_webhook_service import dispatch_event
        import asyncio
        tenant_id = _effective_tenant(current_user)
        asyncio.create_task(dispatch_event(tenant_id, "ticket.created", ticket))
    except Exception:
        pass

    return ticket


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id:    str,
    body:         UpdateTicketRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "status" in data:
        current_ticket = await tickets_service.get_ticket(
            ticket_id, tenant_id=_effective_tenant(current_user)
        )
        if not current_ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        current_status = current_ticket.get("status", "open")
        allowed = _VALID_TRANSITIONS.get(current_status, set())
        if data["status"] not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current_status}' to '{data['status']}'",
            )
    updated = await tickets_service.update_ticket(
        ticket_id,
        data,
        actor=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated


@router.delete("/{ticket_id}")
async def delete_ticket(
    ticket_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    deleted = await tickets_service.delete_ticket(
        ticket_id, tenant_id=_effective_tenant(current_user)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"success": True}


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/{ticket_id}/history")
async def get_history(
    ticket_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> List[Dict[str, Any]]:
    history = await tickets_service.get_history(
        ticket_id, tenant_id=_effective_tenant(current_user)
    )
    if history is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return history


# ── Comments ──────────────────────────────────────────────────────────────────

@router.post("/{ticket_id}/comments")
async def add_comment(
    ticket_id:    str,
    body:         AddCommentRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    try:
        updated = await tickets_service.add_comment(
            ticket_id,
            author=_actor(current_user),
            text=body.text,
            tenant_id=_effective_tenant(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Detect @mentions in comment text and notify mentioned users
    mentions = re.findall(r'@([\w.+-]+@[\w.+-]+\.[a-z]+)', body.text, re.IGNORECASE)
    if mentions:
        try:
            from ticket_notifications import _send
            import asyncio
            for email in set(mentions):
                asyncio.create_task(_send(
                    title=f"[{updated.get('ticket_number')}] You were mentioned",
                    message=(
                        f"{_actor(current_user)} mentioned you in a comment: "
                        f"\"{body.text[:120]}\""
                    ),
                    severity="info",
                    recipients=[email],
                    metadata={"ticket_id": ticket_id, "event": "mention"},
                ))
        except Exception:
            pass

    return updated


# ── Ticket linking ────────────────────────────────────────────────────────────

@router.post("/{ticket_id}/links")
async def add_link(
    ticket_id:    str,
    body:         LinkTicketRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    if body.link_type not in LINK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid link_type. Allowed: {LINK_TYPES}")
    updated = await tickets_service.add_link(
        ticket_id, body.linked_id, body.link_type,
        actor=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated


@router.delete("/{ticket_id}/links/{linked_id}")
async def remove_link(
    ticket_id:    str,
    linked_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    updated = await tickets_service.remove_link(
        ticket_id, linked_id,
        actor=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated


# ── Work log / time tracking ──────────────────────────────────────────────────

@router.post("/{ticket_id}/work-log")
async def log_work(
    ticket_id:    str,
    body:         LogWorkRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    updated = await tickets_service.log_work(
        ticket_id,
        author=_actor(current_user),
        hours=body.hours,
        description=body.description,
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated


# ── Attachments ───────────────────────────────────────────────────────────────

# Allowlist of safe MIME types for ticket attachments.
# Magic-bytes are checked in addition to the Content-Type header to prevent
# MIME-spoofing attacks (attacker sends PE binary as "image/png").
_ALLOWED_MIME_TYPES: set[str] = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    # Archives (read-only — cannot execute server-side)
    "application/zip", "application/x-zip-compressed",
    "application/gzip", "application/x-tar",
    # Data
    "application/json", "application/xml", "text/xml",
    "text/html",  # allowed for evidence exports, served with Content-Disposition: attachment
}

# Map leading magic bytes → expected MIME prefix (defence-in-depth)
_MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"%PDF",         "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG",      "image/png"),
    (b"GIF8",         "image/gif"),
    (b"PK\x03\x04",   "application/zip"),    # also covers OOXML (.docx/.xlsx)
    (b"\x1f\x8b",     "application/gzip"),
]

_BLOCKED_EXTENSIONS: set[str] = {
    ".exe", ".dll", ".bat", ".cmd", ".sh", ".ps1", ".py", ".rb",
    ".php", ".asp", ".aspx", ".jsp", ".jar", ".com", ".msi", ".vbs", ".js",
}


def _validate_attachment(filename: str, contents: bytes, content_type: str | None) -> str:
    """
    Validate a ticket attachment and return the safe MIME type to store.
    Raises HTTPException(415) for disallowed types.
    """
    # Block by file extension regardless of MIME
    ext = os.path.splitext(filename)[1].lower()
    if ext in _BLOCKED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File extension '{ext}' is not allowed for security reasons",
        )

    # Normalise the declared MIME (strip params like "; charset=utf-8")
    declared = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if declared not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Content type '{declared}' is not permitted. Allowed: documents, images, archives, text/data.",
        )

    # Magic-bytes check: declared MIME must match leading bytes
    for magic, expected_prefix in _MAGIC_BYTES:
        if contents[:len(magic)] == magic:
            if not declared.startswith(expected_prefix.split("/")[0]):
                raise HTTPException(
                    status_code=415,
                    detail="File content does not match declared content type (MIME mismatch)",
                )
            break

    return declared


@router.post("/{ticket_id}/attachments")
async def upload_attachment(
    ticket_id:    str,
    file:         UploadFile = File(...),
    current_user: TokenData  = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    ticket = await tickets_service.get_ticket(
        ticket_id, tenant_id=_effective_tenant(current_user)
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    max_bytes = 20 * 1024 * 1024
    contents  = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds 20 MB limit")

    safe_mime = _validate_attachment(file.filename or "attachment", contents, file.content_type)

    raw_name    = os.path.basename(file.filename or "attachment")
    safe_name   = re.sub(r"[^A-Za-z0-9._\-]", "_", raw_name) or "attachment"
    stored_name = f"{ticket_id}_{uuid.uuid4()}_{safe_name}"

    upload_root = pathlib.Path(_UPLOAD_DIR).resolve()
    stored_path = (upload_root / stored_name).resolve()
    if not str(stored_path).startswith(str(upload_root) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid filename")

    with open(stored_path, "wb") as fh:
        fh.write(contents)

    att = await tickets_service.add_attachment(
        ticket_id,
        filename=file.filename or "attachment",
        size=len(contents),
        mimetype=safe_mime,
        stored_as=stored_name,
        uploaded_by=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )
    return att or {}


@router.delete("/{ticket_id}/attachments/{attachment_id}")
async def delete_attachment(
    ticket_id:     str,
    attachment_id: str,
    current_user:  TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    ticket = await tickets_service.get_ticket(
        ticket_id, tenant_id=_effective_tenant(current_user)
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    att = next((a for a in ticket.get("attachments", []) if a["id"] == attachment_id), None)

    ok = await tickets_service.remove_attachment(
        ticket_id, attachment_id,
        actor=_actor(current_user),
        tenant_id=_effective_tenant(current_user),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if att:
        upload_root = pathlib.Path(_UPLOAD_DIR).resolve()
        fpath       = (upload_root / att.get("stored_as", "")).resolve()
        if str(fpath).startswith(str(upload_root) + os.sep) and fpath.exists():
            fpath.unlink()

    return {"success": True}


# ── Approval workflow ─────────────────────────────────────────────────────────

@router.post("/{ticket_id}/approve")
async def approve_ticket(
    ticket_id:    str,
    body:         ApproveRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    updated = await tickets_service.approve_ticket(
        ticket_id,
        approver=_actor(current_user),
        comment=body.comment or "",
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated


@router.post("/{ticket_id}/reject")
async def reject_ticket(
    ticket_id:    str,
    body:         RejectRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    updated = await tickets_service.reject_ticket(
        ticket_id,
        rejector=_actor(current_user),
        reason=body.reason,
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated


# ── Escalation ────────────────────────────────────────────────────────────────

@router.post("/{ticket_id}/escalate")
async def escalate_ticket(
    ticket_id:    str,
    body:         EscalateRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    updated = await tickets_service.escalate_ticket(
        ticket_id,
        actor=_actor(current_user),
        reason=body.reason or "",
        tenant_id=_effective_tenant(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return updated
