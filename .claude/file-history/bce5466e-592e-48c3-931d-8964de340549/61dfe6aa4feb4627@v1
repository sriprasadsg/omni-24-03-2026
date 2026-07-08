"""GET /api/compliance/score — severity-weighted compliance score with per-tenant Redis caching.

Delivers SCORE-01 (live per-tenant score), SCORE-02 (severity weighting), SCORE-03 (per-framework breakdown).

Cache key: compliance:score:{tenant_id}  (TTL 300s)
Super admin: compliance:score:__super__

compliance_frameworks: global collection — queried via db._db.compliance_frameworks (raw Motor, bypasses
TenantIsolatedCollection). Exempted in database.py lines 123-135, but the plan mandates db._db usage.
asset_compliance: tenant-scoped — queried via db.asset_compliance (TenantIsolatedCollection auto-injects tenantId).
"""
from fastapi import APIRouter, Depends, HTTPException
from database import get_database
from authentication_service import get_current_user
from cache_service import cache, invalidate_cache  # noqa: F401 (invalidate_cache imported for callers)
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()

_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

SEVERITY_WEIGHTS = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}

# Static category → severity mapping (Option A from RESEARCH.md — no DB schema change)
_CATEGORY_SEVERITY: dict[str, str] = {
    "Access Control":    "Critical",
    "Cryptography":      "Critical",
    "Incident Response": "Critical",
    "Audit":             "High",
    "Configuration":     "High",
    "Vulnerability":     "High",
    "Operations":        "Medium",
    "Risk Management":   "Medium",
}


def _score_status(status: str) -> str:
    """Normalise asset_compliance status to Compliant / Non-Compliant / Warning."""
    s = (status or "").strip()
    if s in ("Compliant", "Pass", "Passed", "Implemented", "pass", "passed"):
        return "Compliant"
    if s in ("Non-Compliant", "Fail", "Failed", "Not Implemented", "fail", "failed"):
        return "Non-Compliant"
    return "Warning"


def _weighted_score(controls_with_status: list[dict]) -> float:
    """Compute severity-weighted compliance score from a list of {severity, status_norm}."""
    total_weight = 0.0
    passing_weight = 0.0
    for c in controls_with_status:
        weight = SEVERITY_WEIGHTS.get(c.get("severity", "Low"), 1)
        total_weight += weight
        sn = c.get("status_norm", "Warning")
        if sn == "Compliant":
            passing_weight += weight
        elif sn == "Warning":
            passing_weight += weight * 0.5
    if total_weight == 0:
        return 0.0
    return round(passing_weight / total_weight * 100, 1)


@router.get("/api/compliance/score")
async def get_compliance_score(current_user=Depends(get_current_user)):
    """Return severity-weighted compliance score for the current tenant."""
    try:
        tenant_id = getattr(current_user, "tenant_id", None) or ""
        user_role = getattr(current_user, "role", "")
        is_super = user_role in _SUPER_ROLES

        cache_key = "compliance:score:__super__" if is_super else f"compliance:score:{tenant_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        db = get_database()

        # Fetch all frameworks (global collection — raw Motor)
        frameworks = [fw async for fw in db._db.compliance_frameworks.find({})]

        # Build control_meta: control_id → {severity, fw_id}
        control_meta: dict[str, dict] = {}
        for fw in frameworks:
            for c in fw.get("controls", []):
                cid = c.get("id", "")
                if cid:
                    control_meta[cid] = {
                        "severity": _CATEGORY_SEVERITY.get(c.get("category", ""), "Low"),
                        "fw_id": fw.get("id", ""),
                    }

        all_control_ids = list(control_meta.keys())

        # Fetch asset_compliance (TenantIsolatedCollection auto-injects tenantId)
        ac_by_control: dict[str, str] = {}  # controlId → last status
        query = {"controlId": {"$in": all_control_ids}} if all_control_ids else {}
        async for doc in db.asset_compliance.find(query):
            cid = doc.get("controlId", "")
            if cid:
                ac_by_control[cid] = doc.get("status", "")

        # Build per-framework scores
        fw_scores: list[dict] = []
        for fw in frameworks:
            fw_id = fw.get("id", "")
            fw_controls = fw.get("controls", [])
            evaluated = []
            passing = failing = partial = 0

            for c in fw_controls:
                cid = c.get("id", "")
                if cid not in ac_by_control:
                    continue  # No evidence — excluded from denominator (SCORE-01 resolution)
                severity = _CATEGORY_SEVERITY.get(c.get("category", ""), "Low")
                sn = _score_status(ac_by_control[cid])
                evaluated.append({"severity": severity, "status_norm": sn})
                if sn == "Compliant":
                    passing += 1
                elif sn == "Non-Compliant":
                    failing += 1
                else:
                    partial += 1

            fw_scores.append({
                "framework_id":   fw_id,
                "framework_name": fw.get("name", fw_id),
                "short_name":     fw.get("shortName", fw_id),
                "score":          _weighted_score(evaluated),
                "passing":        passing,
                "failing":        failing,
                "partial":        partial,
                "total_controls": len(evaluated),
            })

        # Overall score across all evaluated controls
        all_evaluated = []
        for cid, status in ac_by_control.items():
            meta = control_meta.get(cid)
            if meta:
                all_evaluated.append({
                    "severity":    meta["severity"],
                    "status_norm": _score_status(status),
                })

        payload = {
            "overall_score": _weighted_score(all_evaluated),
            "frameworks":    fw_scores,
            "computed_at":   datetime.now(timezone.utc).isoformat(),
            "tenant_id":     tenant_id,
        }
        cache.set(cache_key, payload, ttl=300)
        return payload

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("compliance score computation error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
