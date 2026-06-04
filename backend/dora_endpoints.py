"""
DORA Metrics Endpoint
Calculates the four DORA metrics from real deployment job data in MongoDB.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database
import logging


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dora", tags=["DORA Metrics"])

_DORA_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


def _parse_dt(val) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@router.get("/metrics")
async def get_dora_metrics(
    tenantId: Optional[str] = None,
    days: int = 30,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Calculate DORA metrics from patch_deployment_jobs and deployment_jobs collections.
    Returns one record per tenant (or the requested tenant) for the supplied time window.
    """
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    if tenantId and caller_role not in _DORA_SUPER_ROLES and tenantId != caller_tenant:
        raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
    effective_tenant = tenantId if (tenantId and caller_role in _DORA_SUPER_ROLES) else caller_tenant

    db = get_database()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=days)
    window_start_iso = window_start.isoformat()

    # Collect jobs from both collections
    query = {"createdAt": {"$gte": window_start_iso}}
    if effective_tenant:
        query["tenantId"] = effective_tenant  # type: ignore[assignment]

    jobs = await db.patch_deployment_jobs.find(query, {"_id": 0}).to_list(length=2000)
    jobs += await db.deployment_jobs.find(query, {"_id": 0}).to_list(length=2000)

    if not jobs:
        # Return zeroed metrics so the UI has something to render
        record = _zeroed_record(tenantId or "all", days, now)
        return [record]

    # Group by tenant
    tenant_jobs: dict = {}
    for job in jobs:
        tid = job.get("tenantId", "all")
        tenant_jobs.setdefault(tid, []).append(job)

    if tenantId and tenantId not in tenant_jobs:
        return [_zeroed_record(tenantId, days, now)]

    results = []
    for tid, tjobs in tenant_jobs.items():
        completed = [j for j in tjobs if j.get("status") in ("Completed", "completed", "Success", "success")]
        failed = [j for j in tjobs if j.get("status") in ("Failed", "failed", "Error", "error")]

        # 1. Deployment Frequency — deployments per day
        total = len(completed) + len(failed)
        deploy_freq = round(total / days, 2) if days else 0

        # 2. Lead Time for Changes — avg minutes from createdAt → updatedAt for completed
        lead_times = []
        for j in completed:
            start = _parse_dt(j.get("createdAt"))
            end = _parse_dt(j.get("updatedAt") or j.get("completedAt"))
            if start and end and end > start:
                lead_times.append((end - start).total_seconds() / 60)
        avg_lead_time = round(sum(lead_times) / len(lead_times), 1) if lead_times else 0

        # 3. Change Failure Rate — failed / (completed + failed)
        denominator = len(completed) + len(failed)
        change_failure_rate = round(len(failed) / denominator * 100, 1) if denominator else 0

        # 4. MTTR — mean time to restore: avg duration of failed jobs (proxy)
        mttr_minutes = []
        for j in failed:
            start = _parse_dt(j.get("createdAt"))
            end = _parse_dt(j.get("updatedAt") or j.get("completedAt"))
            if start and end and end > start:
                mttr_minutes.append((end - start).total_seconds() / 60)
        avg_mttr = round(sum(mttr_minutes) / len(mttr_minutes), 1) if mttr_minutes else 0

        results.append({
            "tenantId": tid,
            "period": f"Last {days} days",
            "calculatedAt": now.isoformat(),
            "deploymentFrequency": deploy_freq,
            "deploymentFrequencyLabel": _freq_label(deploy_freq),
            "leadTimeForChanges": avg_lead_time,
            "leadTimeLabel": _lead_label(avg_lead_time),
            "changeFailureRate": change_failure_rate,
            "changeFailureLabel": _cfr_label(change_failure_rate),
            "mttr": avg_mttr,
            "mttrLabel": _mttr_label(avg_mttr),
            "totalDeployments": total,
            "successfulDeployments": len(completed),
            "failedDeployments": len(failed),
        })

    return results


# ── DORA classification helpers ───────────────────────────────────────────────

def _freq_label(per_day: float) -> str:
    if per_day >= 1:
        return "Elite"
    if per_day >= 1 / 7:
        return "High"
    if per_day >= 1 / 30:
        return "Medium"
    return "Low"


def _lead_label(minutes: float) -> str:
    if minutes == 0:
        return "Unknown"
    if minutes < 60:
        return "Elite"
    if minutes < 60 * 24:
        return "High"
    if minutes < 60 * 24 * 7:
        return "Medium"
    return "Low"


def _cfr_label(pct: float) -> str:
    if pct <= 5:
        return "Elite"
    if pct <= 10:
        return "High"
    if pct <= 15:
        return "Medium"
    return "Low"


def _mttr_label(minutes: float) -> str:
    if minutes == 0:
        return "Unknown"
    if minutes < 60:
        return "Elite"
    if minutes < 60 * 24:
        return "High"
    if minutes < 60 * 24 * 7:
        return "Medium"
    return "Low"


def _zeroed_record(tenant_id: str, days: int, now: datetime) -> dict:
    return {
        "tenantId": tenant_id,
        "period": f"Last {days} days",
        "calculatedAt": now.isoformat(),
        "deploymentFrequency": 0,
        "deploymentFrequencyLabel": "Low",
        "leadTimeForChanges": 0,
        "leadTimeLabel": "Unknown",
        "changeFailureRate": 0,
        "changeFailureLabel": "Elite",
        "mttr": 0,
        "mttrLabel": "Unknown",
        "totalDeployments": 0,
        "successfulDeployments": 0,
        "failedDeployments": 0,
    }
