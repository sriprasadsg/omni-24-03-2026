"""
Conditional Access Policy Service
Defines and evaluates access control policies based on device trust,
session risk, location, and time context.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

ACTIONS = ("allow", "deny", "require_mfa", "require_compliant_device")


async def list_policies(tenant_id: str) -> List[Dict]:
    db = get_database()
    cursor = db._db.ca_policies.find({"tenantId": tenant_id}).sort("priority", 1)
    docs = await cursor.to_list(length=200)
    for d in docs:
        d.pop("_id", None)
    return docs


async def create_policy(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    name = data.get("name", "").strip()
    if not name:
        raise ValueError("Policy name is required")
    action = data.get("action", "deny")
    if action not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": name,
        "description": data.get("description", ""),
        "enabled": bool(data.get("enabled", True)),
        "priority": int(data.get("priority", 100)),
        "action": action,
        "conditions": {
            "device_trust_below": data.get("conditions", {}).get("device_trust_below"),
            "session_risk_above": data.get("conditions", {}).get("session_risk_above"),
            "require_location_known": bool(data.get("conditions", {}).get("require_location_known", False)),
            "allowed_hours_start": data.get("conditions", {}).get("allowed_hours_start"),
            "allowed_hours_end": data.get("conditions", {}).get("allowed_hours_end"),
            "user_groups": data.get("conditions", {}).get("user_groups", []),
            "platforms": data.get("conditions", {}).get("platforms", []),
        },
        "created_at": now,
        "updated_at": now,
        "created_by": data.get("created_by", ""),
        "hit_count": 0,
        "last_triggered": None,
    }
    await db._db.ca_policies.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_policy(policy_id: str, tenant_id: str) -> Optional[Dict]:
    db = get_database()
    doc = await db._db.ca_policies.find_one({"id": policy_id, "tenantId": tenant_id})
    if doc:
        doc.pop("_id", None)
    return doc


async def update_policy(policy_id: str, tenant_id: str, data: Dict[str, Any]) -> Optional[Dict]:
    db = get_database()
    allowed = {"name", "description", "enabled", "priority", "action", "conditions"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        raise ValueError("No updatable fields provided")
    if "action" in update and update["action"] not in ACTIONS:
        raise ValueError(f"action must be one of {ACTIONS}")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db._db.ca_policies.update_one(
        {"id": policy_id, "tenantId": tenant_id},
        {"$set": update},
    )
    return await get_policy(policy_id, tenant_id)


async def delete_policy(policy_id: str, tenant_id: str) -> bool:
    db = get_database()
    result = await db._db.ca_policies.delete_one({"id": policy_id, "tenantId": tenant_id})
    return result.deleted_count > 0


async def evaluate(tenant_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate all enabled policies against the provided context.
    context keys: device_trust_score, session_risk_score, location_known,
                  user_group, platform, current_hour (0-23)
    Returns: { decision, matched_policy, reason }
    """
    db = get_database()
    policies = await list_policies(tenant_id)
    device_trust = float(context.get("device_trust_score", 100))
    session_risk = float(context.get("session_risk_score", 0))
    location_known = bool(context.get("location_known", True))
    user_group = context.get("user_group", "")
    platform = context.get("platform", "")
    current_hour = int(context.get("current_hour", datetime.now(timezone.utc).hour))

    for policy in policies:
        if not policy.get("enabled"):
            continue
        cond = policy.get("conditions", {})

        # Check device trust threshold
        dt_below = cond.get("device_trust_below")
        if dt_below is not None and device_trust >= float(dt_below):
            continue

        # Check session risk threshold
        sr_above = cond.get("session_risk_above")
        if sr_above is not None and session_risk <= float(sr_above):
            continue

        # Check location requirement
        if cond.get("require_location_known") and not location_known:
            pass  # condition matches (unknown location triggers the policy)
        elif cond.get("require_location_known") and location_known:
            continue  # known location, policy doesn't apply

        # Check time window
        h_start = cond.get("allowed_hours_start")
        h_end = cond.get("allowed_hours_end")
        if h_start is not None and h_end is not None:
            if h_start <= current_hour <= h_end:
                continue  # within allowed window

        # Check user groups
        groups = cond.get("user_groups", [])
        if groups and user_group not in groups:
            continue

        # Check platforms
        platforms = cond.get("platforms", [])
        if platforms and platform not in platforms:
            continue

        # Policy matched — record hit and return decision
        await db._db.ca_policies.update_one(
            {"id": policy["id"], "tenantId": tenant_id},
            {"$inc": {"hit_count": 1}, "$set": {"last_triggered": datetime.now(timezone.utc).isoformat()}},
        )
        return {
            "decision": policy["action"],
            "matched_policy": policy["name"],
            "policy_id": policy["id"],
            "reason": f"Policy '{policy['name']}' matched",
        }

    return {"decision": "allow", "matched_policy": None, "policy_id": None, "reason": "No policy matched — default allow"}


async def get_summary(tenant_id: str) -> Dict[str, Any]:
    db = get_database()
    total = await db._db.ca_policies.count_documents({"tenantId": tenant_id})
    enabled = await db._db.ca_policies.count_documents({"tenantId": tenant_id, "enabled": True})
    deny = await db._db.ca_policies.count_documents({"tenantId": tenant_id, "action": "deny"})
    mfa = await db._db.ca_policies.count_documents({"tenantId": tenant_id, "action": "require_mfa"})
    return {"total": total, "enabled": enabled, "deny_policies": deny, "mfa_policies": mfa}
