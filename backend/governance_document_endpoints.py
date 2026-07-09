

@router.get("/documents/{doc_id}/export-signed-pdf")
async def export_signed_pdf_endpoint(
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

    # Resolve reports_dir from compliance_reporting_service
    from compliance_reporting_service import REPORTS_DIR as reports_dir
    # Ensure directory exists
    import os
    os.makedirs(reports_dir, exist_ok=True)

    try:
        pdf_meta = await svc.export_signed_pdf(doc, reports_dir)
    except Exception as e:
        _log.error("Failed to export signed PDF for document %s: %s", doc_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    return pdf_meta