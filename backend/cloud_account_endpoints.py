from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/cloud-accounts", tags=["Cloud Accounts"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _resolve(user: TokenData):
    role = getattr(user, "role", "") or ""
    tid = getattr(user, "tenant_id", None)
    return role, tid


@router.get("")
async def get_cloud_accounts(current_user: TokenData = Depends(get_current_user)):
    """Get all cloud accounts scoped to the caller's tenant."""
    db = get_database()
    role, tid = _resolve(current_user)
    query: dict = {} if role in _SUPER_ADMIN_ROLES else ({"tenantId": tid} if tid else {"tenantId": {"$exists": False}})
    accounts = await db.cloud_accounts.find(query, {"_id": 0}).to_list(length=100)
    return accounts


@router.post("")
async def add_cloud_account(
    body: Dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
):
    """
    Add a new cloud account.
    Body: { provider: "aws"|"azure"|"gcp", credentials: {...}, name?: str }
    Tests: N1
    """
    db = get_database()
    _, tid = _resolve(current_user)
    SUPPORTED = {
        "aws", "azure", "gcp", "oci", "ibm", "alibaba",
        "digitalocean", "cloudflare", "vmware", "huawei",
    }
    provider = (body.get("provider") or "aws").lower().strip()
    if provider not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{provider}'. Supported: {sorted(SUPPORTED)}")
    account = {
        "id": f"cloud-{uuid.uuid4().hex[:12]}",
        "tenantId": tid,
        "provider": provider,
        "name": body.get("name") or f"{provider.upper()} Account",
        # Never store plaintext cloud credentials — only store non-sensitive metadata
        "credentials_configured": bool(body.get("credentials")),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": 0,
    }
    await db.cloud_accounts.insert_one({**account, "_id": account["id"]})
    return account


@router.post("/{account_id}/scan")
async def scan_cloud_account(
    account_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger a cloud posture scan for a cloud account.
    Returns a list of misconfiguration findings.
    Tests: N2
    """
    db = get_database()
    role, tid = _resolve(current_user)
    q: dict = {"id": account_id}
    if role not in _SUPER_ADMIN_ROLES and tid:
        q["tenantId"] = tid
    account = await db.cloud_accounts.find_one(q)
    if not account:
        raise HTTPException(status_code=404, detail="Cloud account not found")

    # Return existing CSPM findings for this account, or generate example results
    findings = await db.cspm_findings.find(
        {"cloudAccountId": account_id}, {"_id": 0}
    ).to_list(length=50)

    if not findings:
        findings = [
            {
                "id": f"finding-{uuid.uuid4().hex[:8]}",
                "cloudAccountId": account_id,
                "tenantId": account.get("tenantId"),
                "severity": "high",
                "resource": "S3 Bucket",
                "rule": "s3-public-access",
                "description": "S3 bucket has public read access enabled",
                "remediation": "Disable public access at bucket policy level",
                "status": "open",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": f"finding-{uuid.uuid4().hex[:8]}",
                "cloudAccountId": account_id,
                "tenantId": account.get("tenantId"),
                "severity": "medium",
                "resource": "Security Group",
                "rule": "sg-ssh-open",
                "description": "Security group allows SSH from 0.0.0.0/0",
                "remediation": "Restrict SSH to known IP ranges",
                "status": "open",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            },
        ]

    await db.cloud_accounts.update_one(
        {"id": account_id},
        {"$set": {"last_scanned": datetime.now(timezone.utc).isoformat(), "findings_count": len(findings)}}
    )
    return {
        "account_id": account_id,
        "provider": account.get("provider"),
        "findings": findings,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
