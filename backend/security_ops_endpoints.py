import base64
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from security_service import get_security_service
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _sec_caller_tenant(current_user) -> str:
    tid = getattr(current_user, "tenant_id", None) or None
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


@router.post("/agents/{agent_id}/verify-integrity")
async def verify_agent_integrity(
    agent_id: str,
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Verify agent software integrity (detect tampering).
    Agents authenticate via their Bearer token; admins can verify any agent.
    """
    is_admin = is_super_admin(getattr(current_user, "role", ""))
    caller_id = getattr(current_user, "username", "")
    if not is_admin and caller_id != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized to verify this agent")

    try:
        security_service = get_security_service()
        db = get_database()

        expected_version_data = await db.agent_versions.find_one(
            {"version": data.get("version")},
            {"_id": 0},
        )
        if not expected_version_data:
            raise HTTPException(status_code=404, detail="Unknown agent version")

        expected_checksum = expected_version_data.get("checksum")
        result = security_service.validate_agent_integrity(
            agent_id=agent_id,
            reported_version=data.get("version"),
            reported_checksum=data.get("checksum"),
            expected_checksum=expected_checksum,
        )

        if result["threat_detected"]:
            await db.agents.update_one(
                {"id": agent_id},
                {"$set": {
                    "quarantined": True,
                    "quarantine_reason": "Agent integrity check failed - possible tampering",
                    "quarantined_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            await security_service.audit_security_event(
                db=db,
                event_type="agent_tampering_detected",
                details={
                    "agent_id": agent_id,
                    "version": data.get("version"),
                    "reported_checksum": data.get("checksum"),
                    "expected_checksum": expected_checksum,
                },
                severity="Critical",
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error verifying agent integrity: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/security/encrypt")
async def encrypt_data(
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Encrypt sensitive data using a server-managed AES-256-GCM key.
    The caller receives the ciphertext + nonce; the key is never returned.
    """
    try:
        security_service = get_security_service()
        key = security_service.generate_encryption_key()
        plaintext = data.get("plaintext", "").encode()
        encrypted, nonce = security_service.encrypt_payload(plaintext, key)
        return {
            "encrypted": base64.b64encode(encrypted).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "algorithm": "AES-256-GCM",
        }
    except Exception as e:
        logger.error("Error encrypting: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/security/audit-log")
async def get_security_audit_log(
    limit: int = 50,
    severity: str = None,
    event_type: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get security audit log entries — scoped to the caller's tenant."""
    try:
        db = get_database()
        is_admin = is_super_admin(getattr(current_user, "role", ""))

        query: dict = {}
        if not is_admin:
            query["tenantId"] = _sec_caller_tenant(current_user)
        if severity:
            query["severity"] = severity
        if event_type:
            query["type"] = event_type

        events = await db.security_audit_log.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.error("Error getting audit log: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
