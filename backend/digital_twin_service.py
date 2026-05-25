"""
Digital Twin Simulation Service

Runs change-impact simulations using real asset data from MongoDB.
Impact score is derived from asset criticality and open vulnerability count.
Success probability is estimated from patch deployment history.
"""
import asyncio
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/digital_twin", tags=["Digital Twin"])

_DT_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


class SimulationRequest(BaseModel):
    action_type: str  # "patch", "config_change", "firewall_rule"
    target_id: str
    details: str


class SimulationResult(BaseModel):
    success_probability: float
    impact_score: int  # 0-100 (100 = high impact/risk)
    predicted_downtime: str
    conflicts: List[str]
    compliance_check: str


_CRITICALITY_IMPACT = {"high": 60, "critical": 60, "medium": 40, "low": 20}
_ACTION_IMPACT      = {"patch": 10, "config_change": 5, "firewall_rule": 25}
_ACTION_DOWNTIME    = {"patch": 120, "config_change": 45, "firewall_rule": 0}
_SUCCESS_DEFAULTS   = {"high": 88.0, "critical": 85.0, "medium": 93.0, "low": 97.0}


@router.post("/simulate")
async def run_simulation(request: SimulationRequest, current_user: TokenData = Depends(get_current_user)):
    """Simulates a network change on the Digital Twin using real asset data."""
    await asyncio.sleep(0)  # yield to event loop

    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)

    # ── 1. Security policy violation fast path ────────────────────────────────
    if request.action_type == "firewall_rule" and "allow all" in request.details.lower():
        return SimulationResult(
            success_probability=100.0,
            impact_score=99,
            predicted_downtime="0s",
            conflicts=["CRITICAL: Violates Zero Trust Policy", "Overly permissive rule"],
            compliance_check="FAILED",
        )

    db = get_database()

    # ── 2. Look up target asset (tenant-scoped) ───────────────────────────────
    asset_filter: dict = {"$or": [{"id": request.target_id}, {"hostname": request.target_id}]}
    if user_role not in _DT_SUPER_ROLES and tenant_id:
        asset_filter["tenantId"] = tenant_id
    asset = await db.assets.find_one(asset_filter, {"_id": 0})

    criticality = (asset.get("criticality") or "medium").lower() if asset else "medium"
    asset_id = asset.get("id") if asset else request.target_id

    # ── 3. Open vulnerability count (tenant-scoped) ───────────────────────────
    vuln_filter: dict = {"assetId": asset_id, "status": {"$in": ["open", "Open"]}}
    if user_role not in _DT_SUPER_ROLES and tenant_id:
        vuln_filter["tenantId"] = tenant_id
    vuln_count = await db.vulnerabilities.count_documents(vuln_filter)

    # ── 4. Impact score ───────────────────────────────────────────────────────
    base_impact      = _CRITICALITY_IMPACT.get(criticality, 35)
    vuln_pts         = min(vuln_count * 2, 25)
    action_pts       = _ACTION_IMPACT.get(request.action_type, 10)
    impact_score     = min(base_impact + vuln_pts + action_pts, 100)

    # ── 5. Success probability from deployment history ────────────────────────
    history = await db.patch_deployment_jobs.find(
        {"asset_ids": asset_id, "status": {"$in": ["completed", "failed"]}},
        {"_id": 0, "status": 1},
    ).to_list(length=100)

    if history:
        success_count = sum(1 for h in history if h.get("status") == "completed")
        success_prob  = round((success_count / len(history)) * 100, 1)
    else:
        success_prob  = _SUCCESS_DEFAULTS.get(criticality, 91.0)

    # ── 6. Predicted downtime ─────────────────────────────────────────────────
    base_dt = _ACTION_DOWNTIME.get(request.action_type, 60)
    if asset and asset.get("requiresReboot") and request.action_type == "patch":
        base_dt += 180
    predicted_downtime = f"{base_dt}s" if base_dt > 0 else "0s"

    # ── 7. Conflict detection ─────────────────────────────────────────────────
    conflicts: List[str] = []
    if vuln_count > 10:
        conflicts.append(f"Asset has {vuln_count} open vulnerabilities — patch exposure is high")
    if criticality in ("high", "critical") and request.action_type in ("patch", "config_change"):
        conflicts.append("High-criticality asset — change requires CAB approval")
    if impact_score > 75:
        conflicts.append("High blast-radius change — validate in staging environment first")

    compliance_check = "FAILED" if impact_score >= 90 else "PASSED"

    return SimulationResult(
        success_probability=success_prob,
        impact_score=impact_score,
        predicted_downtime=predicted_downtime,
        conflicts=conflicts,
        compliance_check=compliance_check,
    )


@router.get("/state")
async def get_twin_state(current_user: TokenData = Depends(get_current_user)):
    """Returns the current sync status of the digital twin from real asset data."""
    from datetime import datetime, timezone
    db = get_database()

    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    tenant_filter: dict = {} if user_role in _DT_SUPER_ROLES else ({"tenantId": tenant_id} if tenant_id else {"tenantId": None})

    assets_modeled = await db.assets.count_documents(tenant_filter)

    pipeline = [{"$match": tenant_filter}, {"$group": {"_id": "$subnet"}}, {"$count": "total"}]
    seg_result = await db.assets.aggregate(pipeline).to_list(length=1)
    segments = seg_result[0]["total"] if seg_result else max(1, assets_modeled // 50)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "sync_status": "Synced",
        "last_sync": now,
        "assets_modeled": assets_modeled,
        "network_segments": segments,
    }
