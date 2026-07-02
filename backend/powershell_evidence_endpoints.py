"""POST /api/powershell-evidence/submit — accepts PowerShell compliance evidence batches.

Authenticated via X-Registration-Key header (agent headless mode) or JWT bearer.
Feeds into process_automated_evidence() so results appear in existing evidence pages.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from authentication_service import get_optional_user
from compliance_evidence_processor import process_automated_evidence
from database import get_database

logger = logging.getLogger(__name__)
router = APIRouter()

# Roles that bypass cross-tenant tenant-mismatch guard
_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class PSCheck(BaseModel):
    check: str = Field(..., min_length=1, max_length=200)
    status: str = Field(..., pattern=r"^(Pass|Fail|Warning|Error|N/A)$")
    details: str = Field("", max_length=2000)
    evidence_content: Optional[str] = Field(None, max_length=50000)
    content_hash: Optional[str] = Field(None, max_length=64)


class PSEvidencePayload(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=253)
    checks: List[PSCheck] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/api/powershell-evidence/submit")
async def submit_powershell_evidence(
    payload: PSEvidencePayload,
    x_registration_key: Optional[str] = Header(None, alias="X-Registration-Key"),
    current_user=Depends(get_optional_user),
):
    """Accept batch PowerShell compliance evidence and write to control_evidence."""
    db = get_database()
    tenant_id: Optional[str] = None

    # Auth resolution: registration key takes priority over JWT
    if x_registration_key:
        tenant = await db._db.tenants.find_one({"registrationKey": x_registration_key})
        if not tenant:
            raise HTTPException(status_code=401, detail="Invalid registration key")
        resolved_tenant_id = tenant.get("id", "")
        if not resolved_tenant_id:
            # A tenant document missing its "id" field must fail loudly here rather than
            # silently propagating tenant_id="" -> falsy fallback_tenant_id, which would
            # let evidence end up written with tenant_id=None (WR-08).
            logger.error("Tenant record for registration key is missing 'id' field")
            raise HTTPException(status_code=500, detail="Tenant record missing id")

        # Cross-tenant check: if JWT is also present, they must agree (unless super admin)
        if current_user:
            jwt_tenant = getattr(current_user, "tenant_id", None) or ""
            jwt_role = getattr(current_user, "role", "")
            if jwt_role not in _SUPER_ROLES and jwt_tenant and jwt_tenant != resolved_tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail="Token tenant does not match registration key tenant",
                )
        tenant_id = resolved_tenant_id

    elif current_user:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        if not tenant_id:
            raise HTTPException(status_code=401, detail="No tenant context in token")

    else:
        raise HTTPException(
            status_code=401,
            detail="Authentication required: provide X-Registration-Key or Authorization header",
        )

    compliance_data = {"compliance_checks": [c.model_dump() for c in payload.checks]}
    try:
        await process_automated_evidence(
            payload.hostname,
            compliance_data,
            db,
            agent_type="powershell",
            fallback_tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.error("PowerShell evidence processing error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Evidence processing failed")

    return {
        "accepted": len(payload.checks),
        "hostname": payload.hostname,
        "tenant_id": tenant_id,
    }
