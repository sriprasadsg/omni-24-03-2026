"""
Certificate/TLS expiry tracking.
Manually-managed certificate records with expiry monitoring and alert generation.
"""
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from typing import Any, Dict, List, Optional

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database

router = APIRouter(prefix="/api/certificates", tags=["Certificates"])

_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


def _tenant(user: TokenData) -> Optional[str]:
    return getattr(user, "tenant_id", None)


def _tq(user: TokenData) -> Dict[str, Any]:
    role = getattr(user, "role", "") or ""
    if role in _SUPER_ROLES:
        return {}
    tid = _tenant(user)
    return {"tenantId": tid} if tid else {"tenantId": None}


@router.get("")
async def list_certificates(
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    certs = await db.certificates.find(_tq(current_user), {"_id": 0}).sort("expires_at", 1).to_list(length=500)
    # Compute days_until_expiry at query time
    now = datetime.now(timezone.utc).isoformat()
    for cert in certs:
        exp = cert.get("expires_at")
        if exp:
            diff = (datetime.fromisoformat(exp.replace("Z", "+00:00")) -
                    datetime.now(timezone.utc)).days
            cert["days_until_expiry"] = diff
        else:
            cert["days_until_expiry"] = None
    return certs


@router.post("")
async def create_certificate(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    cert = {
        "id": str(uuid.uuid4()),
        "tenantId": _tenant(current_user),
        "name": (payload.get("name") or "").strip()[:120],
        "domain": (payload.get("domain") or "").strip()[:253],
        "issuer": (payload.get("issuer") or "").strip()[:120],
        "subject": (payload.get("subject") or "").strip()[:120],
        "expires_at": payload.get("expires_at") or "",
        "issued_at": payload.get("issued_at") or "",
        "asset_id": payload.get("asset_id") or "",
        "environment": (payload.get("environment") or "production").strip()[:50],
        "notes": (payload.get("notes") or "")[:500],
        "created_at": now,
        "created_by": getattr(current_user, "username", ""),
    }
    if not cert["name"] or not cert["expires_at"]:
        raise HTTPException(status_code=422, detail="name and expires_at are required")
    await db.certificates.insert_one({**cert})
    cert.pop("_id", None)

    # Generate alert if expiring within 30 days
    if cert["expires_at"]:
        try:
            exp_dt = datetime.fromisoformat(cert["expires_at"].replace("Z", "+00:00"))
            days_left = (exp_dt - datetime.now(timezone.utc)).days
            if days_left <= 30:
                sev = "Critical" if days_left <= 7 else "High"
                await db.alerts.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenantId": cert["tenantId"],
                    "severity": sev,
                    "type": "cert_expiry",
                    "source": f"certificates:{cert['domain'] or cert['name']}",
                    "message": (
                        f"TLS certificate '{cert['name']}' for {cert['domain'] or '(no domain)'} "
                        f"expires in {days_left} day(s) on {cert['expires_at'][:10]}"
                    ),
                    "status": "Open",
                    "acknowledged": False,
                    "timestamp": now,
                })
        except Exception:
            pass

    return cert


@router.put("/{cert_id}")
async def update_certificate(
    cert_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    filt = {"id": cert_id, **_tq(current_user)}
    allowed = {"name", "domain", "issuer", "subject", "expires_at", "issued_at",
               "asset_id", "environment", "notes"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.certificates.update_one(filt, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Certificate not found")
    doc = await db.certificates.find_one(filt, {"_id": 0})
    return doc


@router.delete("/{cert_id}")
async def delete_certificate(
    cert_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    db = get_database()
    await db.certificates.delete_one({"id": cert_id, **_tq(current_user)})
    return {"success": True}


@router.get("/summary")
async def get_certificate_summary(
    current_user: TokenData = Depends(get_current_user),
):
    """Return counts by expiry bracket for dashboard cards."""
    db = get_database()
    certs = await db.certificates.find(_tq(current_user), {"_id": 0, "expires_at": 1}).to_list(length=1000)
    now = datetime.now(timezone.utc)
    buckets = {"expired": 0, "critical": 0, "warning": 0, "ok": 0, "unknown": 0}
    for cert in certs:
        exp = cert.get("expires_at")
        if not exp:
            buckets["unknown"] += 1
            continue
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            days = (exp_dt - now).days
            if days < 0:
                buckets["expired"] += 1
            elif days <= 7:
                buckets["critical"] += 1
            elif days <= 30:
                buckets["warning"] += 1
            else:
                buckets["ok"] += 1
        except Exception:
            buckets["unknown"] += 1
    buckets["total"] = len(certs)
    return buckets
