"""Retention Tiers Endpoints — /api/retention-tiers/"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api/retention-tiers", tags=["Retention"])

VALID_TIERS = {"hot", "warm", "cold", "archive", "compliance"}


class PolicyCreate(BaseModel):
    name: str
    tier: str
    retention_days: int
    applies_to: str = "all"
    legal_hold: bool = False


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    tier: Optional[str] = None
    retention_days: Optional[int] = None
    applies_to: Optional[str] = None
    legal_hold: Optional[bool] = None


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("/stats")
async def retention_stats(current_user: TokenData = Depends(get_current_user)):
    """Aggregated stats per retention tier for the tenant."""
    db = get_database()
    pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {"_id": "$tier", "count": {"$sum": 1}}},
    ]
    tier_counts: dict = {t: 0 for t in VALID_TIERS}
    async for row in db.retention_policies.aggregate(pipeline):
        if row["_id"] in tier_counts:
            tier_counts[row["_id"]] = row["count"]
    legal_hold_count = await db.retention_policies.count_documents(
        {"tenantId": current_user.tenant_id, "legal_hold": True}
    )
    return {
        "tier_counts": tier_counts,
        "legal_hold_count": legal_hold_count,
        "total": sum(tier_counts.values()),
    }


@router.get("/")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    """List all retention policies for the tenant."""
    db = get_database()
    results = []
    async for doc in db.retention_policies.find({"tenantId": current_user.tenant_id}):
        _strip_id(doc)
        results.append(doc)
    return results


@router.post("/", status_code=201)
async def create_policy(
    body: PolicyCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new retention policy."""
    if body.tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"tier must be one of {sorted(VALID_TIERS)}")
    if body.retention_days < 1:
        raise HTTPException(status_code=400, detail="retention_days must be >= 1")
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "name": body.name,
        "tier": body.tier,
        "retention_days": body.retention_days,
        "applies_to": body.applies_to,
        "legal_hold": body.legal_hold,
        "created_at": now,
        "updated_at": now,
    }
    await db.retention_policies.insert_one(doc)
    _strip_id(doc)
    return doc


@router.put("/{policy_id}")
async def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update a retention policy."""
    db = get_database()
    existing = await db.retention_policies.find_one(
        {"id": policy_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Policy not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if "tier" in updates and updates["tier"] not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"tier must be one of {sorted(VALID_TIERS)}")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.retention_policies.update_one(
        {"id": policy_id, "tenantId": current_user.tenant_id},
        {"$set": updates},
    )
    doc = await db.retention_policies.find_one({"id": policy_id})
    _strip_id(doc)
    return doc


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(
    policy_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a retention policy (blocked if legal hold is active)."""
    db = get_database()
    existing = await db.retention_policies.find_one(
        {"id": policy_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Policy not found")
    if existing.get("legal_hold"):
        raise HTTPException(status_code=409, detail="Cannot delete a policy with legal hold active")
    await db.retention_policies.delete_one(
        {"id": policy_id, "tenantId": current_user.tenant_id}
    )
    return None


@router.post("/{policy_id}/legal-hold")
async def toggle_legal_hold(
    policy_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Toggle legal hold on a retention policy."""
    db = get_database()
    existing = await db.retention_policies.find_one(
        {"id": policy_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Policy not found")
    new_val = not existing.get("legal_hold", False)
    await db.retention_policies.update_one(
        {"id": policy_id, "tenantId": current_user.tenant_id},
        {"$set": {"legal_hold": new_val, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"policy_id": policy_id, "legal_hold": new_val}
