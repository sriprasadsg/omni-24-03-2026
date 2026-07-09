"""Governance Document endpoints — versioned policies/procedures with approval delegation."""
import logging
from fastapi import APIRouter, HTTPException, Depends, Body, Query
from database import get_database
from auth_utils import get_current_user
from rbac_utils import require_permission
import governance_document_service as svc

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/governance", tags=["Governance Documents"])


def _tenant(user):
    return getattr(user, "tenant_id", None) or (user.get("tenant_id") if isinstance(user, dict) else None)


def _sub(user):
    if isinstance(user, dict):
        return user.get("sub") or user.get("email") or user.get("username")
    return getattr(user, "username", None) or getattr(user, "email", None)


@router.post("/documents")
async def create_document(
    payload: dict = Body(...),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    requester = _sub(current_user)
    doc = await svc.create_document(db, tenant_id, requester, payload)
    return doc


@router.get("/documents")
async def list_documents(
    status: str = Query(None),
    current_user=Depends(require_permission("view:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    docs = await svc.list_documents(db, tenant_id, status)
    return {"items": docs, "count": len(docs)}


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    current_user=Depends(require_permission("view:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    doc = await svc.get_document(db, tenant_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/documents/{doc_id}/new-version")
async def add_version(
    doc_id: str,
    payload: dict = Body(...),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    requester = _sub(current_user)
    content = payload.get("content", "")
    doc = await svc.add_version(db, tenant_id, doc_id, content, requester)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/documents/{doc_id}/submit-for-approval")
async def submit_for_approval(
    doc_id: str,
    payload: dict = Body(default={}),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    requester = _sub(current_user)
    approvers = payload.get("approvers", [])
    result = await svc.submit_for_approval(db, tenant_id, doc_id, requester, approvers)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.post("/documents/{doc_id}/publish")
async def publish_document(
    doc_id: str,
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    try:
        doc = await svc.publish_document(db, tenant_id, doc_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _log.error("Failed to publish document %s: %s", doc_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
    return doc