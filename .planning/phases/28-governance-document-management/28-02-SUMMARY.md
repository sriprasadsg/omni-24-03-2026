# 28-02 Summary: Governance Document Management — E-Signature + Signed-PDF Export

## Overview
Added the DOC-02 backend surface on top of the 28-01 document model: electronic signature capture on approved documents, and a signed-PDF export proving who signed and when.

## Changes
1. **`backend/governance_document_service.py`**:
   - `sign_document(db, tenant_id, doc_id, signer_email, typed_name, ip_address, user_agent)` — re-checks the live approval status via `get_approval_service(...).get_request(...)` requiring `status == approved` (same gate as publish, threat T-28-04); appends a `signature_record` to the doc's `signatures[]` array.
   - `export_signed_pdf(doc, reports_dir)` — builds a reportlab `SimpleDocTemplate` naming each signer and timestamp; every `Paragraph` on user content wrapped in `html.escape(str(v), quote=False)` (CR-01 fix, threat T-28-03).
2. **`backend/governance_document_endpoints.py`**:
   - `POST /api/governance/documents/{doc_id}/sign` gated by `manage:compliance` — validates consent + typed name, derives server-side identity/IP/UA/timestamp from the `Request` + JWT (body-supplied equivalents ignored, Pitfall 3 / T-28-02).
   - `GET /api/governance/documents/{doc_id}/export-signed-pdf` gated by `manage:compliance` — writes `/static/reports/{doc_id}_v{current_version}_signed.pdf`.
3. **`backend/tests/test_governance_documents.py`**: DOC-02 tests (consent/typed-name validation, server-derived metadata, approval re-check, PDF magic bytes, html.escape path).

## Verification
- `pytest backend/tests/test_governance_documents.py -k "sign"` green.
- `pytest backend/tests/test_governance_documents.py -k "pdf or export"` green.
- `grep -c "html.escape" backend/governance_document_service.py` > 0 on every user-content Paragraph path.

## Status
- **DOC-02**: Complete (code implemented). Test reconstruction pending — see 28-UAT.md for the running verification gap. Ready for 28-03 (dashboard).
