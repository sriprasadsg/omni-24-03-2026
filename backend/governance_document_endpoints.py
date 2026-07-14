"""Governance Document Endpoints — /api/governance/documents CRUD + approval + e-sign + PDF export."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Body, Request, Query
from database import get_database
from rbac_utils import require_permission
from auth_utils import get_current_user
from typing import Optional, List
import governance_document_service as svc

router = APIRouter(prefix="/api/governance", tags=["Governance Documents"])
_log = logging.getLogger(__name__)


def _tenant(current_user) -> Optional[str]:
    """Extract tenant_id from current_user, return None if absent."""
    return getattr(current_user, "tenant_id", None)


def _sub(current_user) -> str:
    """Extract requester identity (email) from JWT user object."""
    return getattr(current_user, "username", "unknown")


@router.post("/documents")
async def create_document(
    data: dict = Body(...),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    try:
        doc = await svc.create_document(db, tenant_id, _sub(current_user), data)
    except Exception as e:
        _log.error("Failed to create document: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    return doc


@router.get("/documents")
async def list_documents(
    status: Optional[str] = Query(None),
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
    data: dict = Body(...),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    content = data.get("content", "")
    doc = await svc.add_version(db, tenant_id, doc_id, content, _sub(current_user))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/documents/{doc_id}/submit-for-approval")
async def submit_for_approval(
    doc_id: str,
    data: dict = Body(...),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    approvers = data.get("approvers", [])
    request = await svc.submit_for_approval(db, tenant_id, doc_id, _sub(current_user), approvers)
    if not request:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"approval_request_id": request["id"]}


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
    return doc


@router.post("/documents/{doc_id}/sign")
async def sign_document(
    doc_id: str,
    request: Request,
    data: dict = Body(...),
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    typed_name = data.get("typed_name", "").strip()
    consent = data.get("consent")

    if not consent:
        raise HTTPException(status_code=400, detail="Consent checkbox required")
    if not typed_name:
        raise HTTPException(status_code=400, detail="Typed name required")

    # Derive all authoritative metadata server-side (Pitfall 3)
    signer_email = _sub(current_user)
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")[:512]

    try:
        doc = await svc.sign_document(
            db, tenant_id, doc_id, signer_email, typed_name, ip_address, user_agent
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return doc


@router.get("/documents/{doc_id}/export-signed-pdf")
async def export_signed_pdf(
    doc_id: str,
    current_user=Depends(require_permission("manage:compliance")),
    db=Depends(get_database),
):
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    doc = await svc.get_document(db, tenant_id, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.get("signatures"):
        raise HTTPException(status_code=400, detail="Document has no signatures to export")

    import os
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "reports")
    os.makedirs(reports_dir, exist_ok=True)

    try:
        pdf_meta = await svc.export_signed_pdf(doc, reports_dir)
    except Exception as e:
        _log.error("Failed to export signed PDF for document %s: %s", doc_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    return pdf_meta