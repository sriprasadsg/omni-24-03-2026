"""
Just-In-Time (JIT) Privileged Access Service
Implements time-bounded privilege elevation with approval workflow,
audit logging, and automatic expiry enforcement.
"""

import uuid
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

JIT_STATES = ("pending", "approved", "active", "expired", "revoked", "denied")

DEFAULT_MAX_DURATION_HOURS = 8
PRIVILEGED_ROLES = ["admin", "super_admin", "security_analyst", "incident_responder"]

JIT_REQUEST_REASONS = [
    "incident_response",
    "scheduled_maintenance",
    "vulnerability_remediation",
    "audit_investigation",
    "compliance_review",
    "emergency_access",
    "other",
]


async def create_jit_request(
    requester_id: str,
    requester_email: str,
    tenant_id: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    db = get_database()

    duration_hours = min(int(data.get("duration_hours", 1)), DEFAULT_MAX_DURATION_HOURS)
    requested_role = data.get("requested_role", "admin")
    reason = data.get("reason", "other")
    justification = data.get("justification", "")
    target_resource = data.get("target_resource", "")

    if requested_role not in PRIVILEGED_ROLES:
        raise ValueError(f"Role '{requested_role}' is not a privileged role. Choose from: {PRIVILEGED_ROLES}")
    if reason not in JIT_REQUEST_REASONS:
        raise ValueError(f"Invalid reason. Choose from: {JIT_REQUEST_REASONS}")
    if not justification.strip():
        raise ValueError("Justification is required for JIT access requests")

    now = datetime.now(timezone.utc)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "requester_id": requester_id,
        "requester_email": requester_email,
        "requested_role": requested_role,
        "reason": reason,
        "justification": justification,
        "target_resource": target_resource,
        "duration_hours": duration_hours,
        "status": "pending",
        "requested_at": now.isoformat(),
        "approved_at": None,
        "approved_by": None,
        "approver_id": None,
        "activated_at": None,
        "expires_at": None,
        "revoked_at": None,
        "revoked_by": None,
        "deny_reason": None,
        "access_token": None,
        "session_id": str(uuid.uuid4()),
        "audit_trail": [
            {
                "event": "requested",
                "actor": requester_email,
                "timestamp": now.isoformat(),
                "detail": f"JIT access requested: {requested_role} for {duration_hours}h — {justification[:100]}",
            }
        ],
    }

    await db.jit_requests.insert_one(doc)
    logger.info("[JIT] New request %s from %s for role %s", doc["id"], requester_email, requested_role)

    # Auto-notify approvers via notification system
    try:
        from notification_manager import notification_manager
        await notification_manager.send_notification(
            "jit.access_requested",
            {
                "request_id": doc["id"],
                "requester": requester_email,
                "role": requested_role,
                "duration": duration_hours,
                "reason": reason,
                "justification": justification,
            },
            tenant_id,
        )
    except Exception as exc:
        logger.debug("[JIT] Could not send notification: %s", exc)

    return doc


async def approve_jit_request(
    request_id: str,
    approver_id: str,
    approver_email: str,
    tenant_id: str,
    role: str,
) -> Dict[str, Any]:
    db = get_database()
    query = {"id": request_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    req = await db.jit_requests.find_one(query)
    if not req:
        raise ValueError("JIT request not found")
    if req["status"] != "pending":
        raise ValueError(f"Request is not pending (current status: {req['status']})")
    if req["requester_id"] == approver_id:
        raise ValueError("Self-approval not permitted")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=req["duration_hours"])
    access_token = str(uuid.uuid4()).replace("-", "")  # Single-use session token

    update = {
        "status": "approved",
        "approved_at": now.isoformat(),
        "approved_by": approver_email,
        "approver_id": approver_id,
        "activated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "access_token": access_token,
    }
    await db.jit_requests.update_one(
        {"id": request_id},
        {
            "$set": update,
            "$push": {
                "audit_trail": {
                    "event": "approved",
                    "actor": approver_email,
                    "timestamp": now.isoformat(),
                    "detail": f"Access approved, expires at {expires_at.isoformat()}",
                }
            },
        },
    )

    logger.info("[JIT] Request %s approved by %s, expires %s", request_id, approver_email, expires_at.isoformat())
    return {**req, **update, "id": request_id}


async def deny_jit_request(
    request_id: str,
    approver_email: str,
    tenant_id: str,
    role: str,
    deny_reason: str = "",
) -> bool:
    db = get_database()
    query = {"id": request_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    req = await db.jit_requests.find_one(query)
    if not req or req["status"] != "pending":
        return False

    now = datetime.now(timezone.utc).isoformat()
    await db.jit_requests.update_one(
        {"id": request_id},
        {
            "$set": {"status": "denied", "deny_reason": deny_reason},
            "$push": {
                "audit_trail": {
                    "event": "denied",
                    "actor": approver_email,
                    "timestamp": now,
                    "detail": deny_reason or "Request denied",
                }
            },
        },
    )
    return True


async def revoke_jit_request(
    request_id: str,
    revoker_email: str,
    tenant_id: str,
    role: str,
    revoke_reason: str = "Manual revocation",
) -> bool:
    db = get_database()
    query = {"id": request_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id

    req = await db.jit_requests.find_one(query)
    if not req or req["status"] not in ("approved", "active"):
        return False

    now = datetime.now(timezone.utc).isoformat()
    await db.jit_requests.update_one(
        {"id": request_id},
        {
            "$set": {"status": "revoked", "revoked_at": now, "revoked_by": revoker_email, "access_token": None},
            "$push": {
                "audit_trail": {
                    "event": "revoked",
                    "actor": revoker_email,
                    "timestamp": now,
                    "detail": revoke_reason,
                }
            },
        },
    )
    logger.info("[JIT] Request %s revoked by %s", request_id, revoker_email)
    return True


async def list_jit_requests(
    tenant_id: str,
    role: str,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}
    if status:
        query["status"] = status

    requests = await db.jit_requests.find(query).sort("requested_at", -1).to_list(length=limit)
    for r in requests:
        r["_id"] = str(r["_id"])
        r.pop("access_token", None)  # Never expose access tokens in list
    return requests


async def get_jit_request(request_id: str, tenant_id: str, role: str) -> Optional[Dict[str, Any]]:
    db = get_database()
    query = {"id": request_id}
    if role != "super_admin":
        query["tenant_id"] = tenant_id
    req = await db.jit_requests.find_one(query)
    if req:
        req["_id"] = str(req["_id"])
        req.pop("access_token", None)
    return req


async def get_jit_summary(tenant_id: str, role: str) -> Dict[str, Any]:
    db = get_database()
    query = {} if role == "super_admin" else {"tenant_id": tenant_id}

    counts = {}
    for state in JIT_STATES:
        counts[state] = await db.jit_requests.count_documents({**query, "status": state})

    return {
        "counts_by_status": counts,
        "total": sum(counts.values()),
        "pending_approval": counts.get("pending", 0),
        "currently_active": counts.get("approved", 0) + counts.get("active", 0),
        "privileged_roles": PRIVILEGED_ROLES,
        "request_reasons": JIT_REQUEST_REASONS,
        "max_duration_hours": DEFAULT_MAX_DURATION_HOURS,
    }


# ── Background expiry enforcer ─────────────────────────────────────────────────

async def start_jit_expiry_loop():
    """Every 60 seconds, expire approved JIT requests past their expiry time."""
    logger.info("[JIT] Expiry enforcement loop started")
    while True:
        try:
            await asyncio.sleep(60)
            db = get_database()
            now = datetime.now(timezone.utc).isoformat()
            result = await db.jit_requests.update_many(
                {
                    "status": {"$in": ["approved", "active"]},
                    "expires_at": {"$lt": now},
                },
                {
                    "$set": {"status": "expired", "access_token": None},
                    "$push": {
                        "audit_trail": {
                            "event": "expired",
                            "actor": "system",
                            "timestamp": now,
                            "detail": "JIT access expired automatically",
                        }
                    },
                },
            )
            if result.modified_count > 0:
                logger.info("[JIT] Auto-expired %d JIT sessions", result.modified_count)
        except Exception as exc:
            logger.error("[JIT] Expiry loop error: %s", exc)
