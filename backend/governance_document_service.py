"""Governance Document Service — versioned policies/procedures with approval delegation."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

_log = logging.getLogger(__name__)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_document(
    db,
    tenant_id: str,
    requester: str,
    data: dict
) -> dict:
    """Create a new governance document in draft state with initial version."""
    doc_id = _gen_id("doc")
    version = 1
    doc = {
        "id": doc_id,
        "tenantId": tenant_id,
        "title": data.get("title", ""),
        "doc_type": data.get("doc_type", "policy"),
        "status": "draft",
        "current_version": version,
        "approval_request_id": None,
        "versions": [{
            "version": version,
            "content": data.get("content", ""),
            "status": "draft",
            "author": requester,
            "created_at": _now_iso(),
        }],
        "signatures": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.governance_documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def add_version(
    db,
    tenant_id: str,
    doc_id: str,
    content: str,
    author: str
) -> dict:
    """Append a new version to an existing document, resetting status to draft."""
    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        return None

    new_version = doc["current_version"] + 1
    version_entry = {
        "version": new_version,
        "content": content,
        "status": "draft",
        "author": author,
        "created_at": _now_iso(),
    }
    doc["versions"].append(version_entry)
    doc["current_version"] = new_version
    doc["status"] = "draft"
    doc["updated_at"] = _now_iso()

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"versions": doc["versions"], "current_version": new_version, "status": "draft", "updated_at": doc["updated_at"]}}
    )
    return doc


async def get_document(db, tenant_id: str, doc_id: str) -> Optional[dict]:
    """Fetch a single document by ID, scoped to tenant."""
    doc = await db.governance_documents.find_one({"id": doc_id, "tenantId": tenant_id}, {"_id": 0})
    return doc


async def list_documents(db, tenant_id: str, status: Optional[str] = None) -> List[dict]:
    """List documents for a tenant, optionally filtered by status."""
    query = {"tenantId": tenant_id}
    if status:
        query["status"] = status
    cursor = db.governance_documents.find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def submit_for_approval(
    db,
    tenant_id: str,
    doc_id: str,
    requester: str,
    approvers: List[str]
) -> Dict[str, Any]:
    """Submit a document for approval, delegating to the generic ApprovalService."""
    from approval_service import get_approval_service

    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        return None

    service = get_approval_service(db)
    request = await service.create_approval_request(
        tenant_id=tenant_id,
        requester=requester,
        action_type="governance_document_approval",
        description=f"Approve governance document {doc_id}",
        details={"document_id": doc_id},
        workflow_steps=[{"role": "ComplianceOfficer", "approvers": approvers}],
    )

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"status": "pending_approval", "approval_request_id": request["id"], "updated_at": _now_iso()}}
    )
    return request


async def publish_document(
    db,
    tenant_id: str,
    doc_id: str
) -> dict:
    """Publish a document only if its approval request is live-status approved."""
    from approval_service import get_approval_service

    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        raise ValueError("Document not found")

    approval_request_id = doc.get("approval_request_id")
    if not approval_request_id:
        raise ValueError("Document has no approval request — cannot publish")

    service = get_approval_service(db)
    approval = await service.get_request(approval_request_id, tenant_id)
    if not approval or approval.get("status") != "approved":
        raise ValueError(f"Approval request {approval_request_id} is not approved (status: {approval.get('status') if approval else 'not found'})")

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"status": "published", "published_at": _now_iso(), "updated_at": _now_iso()}}
    )
    doc["status"] = "published"
    doc["published_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    return doc


import logging
import uuid
import html # Added for PDF export
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

_log = logging.getLogger(__name__)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_document(
    db,
    tenant_id: str,
    requester: str,
    data: dict
) -> dict:
    """Create a new governance document in draft state with initial version."""
    doc_id = _gen_id("doc")
    version = 1
    doc = {
        "id": doc_id,
        "tenantId": tenant_id,
        "title": data.get("title", ""),
        "doc_type": data.get("doc_type", "policy"),
        "status": "draft",
        "current_version": version,
        "approval_request_id": None,
        "versions": [{
            "version": version,
            "content": data.get("content", ""),
            "status": "draft",
            "author": requester,
            "created_at": _now_iso(),
        }],
        "signatures": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.governance_documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def add_version(
    db,
    tenant_id: str,
    doc_id: str,
    content: str,
    author: str
) -> dict:
    """Append a new version to an existing document, resetting status to draft."""
    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        return None

    new_version = doc["current_version"] + 1
    version_entry = {
        "version": new_version,
        "content": content,
        "status": "draft",
        "author": author,
        "created_at": _now_iso(),
    }
    doc["versions"].append(version_entry)
    doc["current_version"] = new_version
    doc["status"] = "draft"
    doc["updated_at"] = _now_iso()

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"versions": doc["versions"], "current_version": new_version, "status": "draft", "updated_at": doc["updated_at"]}}
    )
    return doc


async def get_document(db, tenant_id: str, doc_id: str) -> Optional[dict]:
    """Fetch a single document by ID, scoped to tenant."""
    doc = await db.governance_documents.find_one({"id": doc_id, "tenantId": tenant_id}, {"_id": 0})
    return doc


async def list_documents(db, tenant_id: str, status: Optional[str] = None) -> List[dict]:
    """List documents for a tenant, optionally filtered by status."""
    query = {"tenantId": tenant_id}
    if status:
        query["status"] = status
    cursor = db.governance_documents.find(query, {"_id": 0}).sort("created_at", -1)
    return await cursor.to_list(length=100)


async def submit_for_approval(
    db,
    tenant_id: str,
    doc_id: str,
    requester: str,
    approvers: List[str]
) -> Dict[str, Any]:
    """Submit a document for approval, delegating to the generic ApprovalService."""
    from approval_service import get_approval_service

    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        return None

    service = get_approval_service(db)
    request = await service.create_approval_request(
        tenant_id=tenant_id,
        requester=requester,
        action_type="governance_document_approval",
        description=f"Approve governance document {doc_id}",
        details={"document_id": doc_id},
        workflow_steps=[{"role": "ComplianceOfficer", "approvers": approvers}],
    )

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"status": "pending_approval", "approval_request_id": request["id"], "updated_at": _now_iso()}}
    )
    return request


async def publish_document(
    db,
    tenant_id: str,
    doc_id: str
) -> dict:
    """Publish a document only if its approval request is live-status approved."""
    from approval_service import get_approval_service

    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        raise ValueError("Document not found")

    approval_request_id = doc.get("approval_request_id")
    if not approval_request_id:
        raise ValueError("Document has no approval request — cannot publish")

    service = get_approval_service(db)
    approval = await service.get_request(approval_request_id, tenant_id)
    if not approval or approval.get("status") != "approved":
        raise ValueError(f"Approval request {approval_request_id} is not approved (status: {approval.get('status') if approval else 'not found'})")

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$set": {"status": "published", "published_at": _now_iso(), "updated_at": _now_iso()}}
    )
    doc["status"] = "published"
    doc["published_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    return doc


async def sign_document(
    db,
    tenant_id: str,
    doc_id: str,
    signer_email: str,
    typed_name: str,
    ip_address: str,
    user_agent: str
) -> dict:
    """Append a signature to a document after re-checking live approval status."""
    from approval_service import get_approval_service

    doc = await get_document(db, tenant_id, doc_id)
    if not doc:
        raise ValueError("Document not found")

    approval_request_id = doc.get("approval_request_id")
    if not approval_request_id:
        raise ValueError("Document has no approval request — cannot sign")

    service = get_approval_service(db)
    approval = await service.get_request(approval_request_id, tenant_id)
    if not approval or approval.get("status") != "approved":
        raise ValueError(f"Approval request {approval_request_id} is not approved (status: {approval.get('status') if approval else 'not found'})")

    signature_record = {
        "signer_email": signer_email,
        "typed_name": typed_name,
        "consented": True,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "signed_at": _now_iso(),
    }

    await db.governance_documents.update_one(
        {"id": doc_id, "tenantId": tenant_id},
        {"$push": {"signatures": signature_record}, "$set": {"updated_at": _now_iso()}}
    )
    doc["signatures"].append(signature_record)
    doc["updated_at"] = _now_iso()
    return doc


async def export_signed_pdf(doc: dict, reports_dir: str) -> dict:
    """Build a reportlab PDF of the signed document."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.pagesizes import letter
    import os

    os.makedirs(reports_dir, exist_ok=True)

    doc_id = doc.get("id", "unknown")
    current_version = doc.get("current_version", 1)
    filename = f"{doc_id}_v{current_version}_signed.pdf"
    filepath = os.path.join(reports_dir, filename)

    styles = getSampleStyleSheet()
    # Add a paragraph style for content to handle newlines
    styles.add(ParagraphStyle(name='Content', parent=styles['Normal'], leading=14))

    elements = [
        Paragraph(html.escape(doc.get("title", "Untitled Document"), quote=False), styles["Title"]),
        Paragraph(html.escape(f"Version {doc.get('current_version', 'N/A')} — Status: {doc.get('status', 'N/A')}", quote=False), styles["Normal"]),
        Spacer(1, 12),
        Paragraph("Signatures:", styles["h2"]),
    ]

    if not doc.get("signatures"):
        elements.append(Paragraph("No signatures yet.", styles["Italic"]))
    else:
        for sig in doc.get("signatures", []):
            elements.append(Paragraph(
                html.escape(
                    f"Signed by: {sig.get('typed_name', 'N/A')} ({sig.get('signer_email', 'N/A')}) "
                    f"at {sig.get('signed_at', 'N/A')} from {sig.get('ip_address', 'N/A')}",
                    quote=False,
                ),
                styles["Normal"],
            ))
            elements.append(Spacer(1, 6))

    # Add document content
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Document Content:", styles["h2"]))
    current_version_content = next(
        (v["content"] for v in doc["versions"] if v["version"] == doc["current_version"]),
        "No content available for this version."
    )
    elements.append(Paragraph(html.escape(current_version_content, quote=False), styles["Content"]))

    doc_template = SimpleDocTemplate(filepath, pagesize=letter,
                                     rightMargin=inch/2, leftMargin=inch/2,
                                     topMargin=inch/2, bottomMargin=inch/2)
    doc_template.build(elements)

    return {"filename": filename, "url": f"/static/reports/{filename}", "generatedAt": _now_iso()}


# Export get_approval_service for test patching
from approval_service import get_approval_service as _get_approval_service
get_approval_service = _get_approval_service