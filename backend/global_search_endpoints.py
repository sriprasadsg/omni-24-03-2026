"""
Global search — unified cross-resource search across assets, agents, alerts, and CVEs.
Returns grouped results per resource type, max 10 items each.
"""
import re
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Any, Dict, List

from authentication_service import get_current_user
from auth_types import TokenData
from database import get_database

router = APIRouter(prefix="/api/search", tags=["Global Search"])

_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
_MAX_PER_TYPE = 8


def _make_regex(q: str) -> Dict[str, Any]:
    return {"$regex": re.escape(q[:200]), "$options": "i"}


def _tenant_query(current_user: TokenData) -> Dict[str, Any]:
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ROLES:
        return {}
    tid = getattr(current_user, "tenant_id", None)
    return {"tenantId": tid} if tid else {"tenantId": None}


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Fan-out search across assets, agents, alerts, and vulnerabilities.
    Returns up to 8 results per category.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    db = get_database()
    regex = _make_regex(q)
    tq = _tenant_query(current_user)

    results: Dict[str, List[Dict[str, Any]]] = {}

    # ── Assets ────────────────────────────────────────────────────────────
    asset_filter = {
        "$or": [{"hostname": regex}, {"ipAddress": regex}, {"osName": regex}, {"name": regex}],
        **tq,
    }
    raw = await db.assets.find(asset_filter, {"_id": 0, "id": 1, "hostname": 1, "ipAddress": 1, "osName": 1, "status": 1}).to_list(length=_MAX_PER_TYPE)
    results["assets"] = [
        {"id": r.get("id"), "label": r.get("hostname") or r.get("name") or "—",
         "sub": r.get("ipAddress") or r.get("osName") or "—",
         "type": "asset", "view": "assetManagement"} for r in raw
    ]

    # ── Agents ────────────────────────────────────────────────────────────
    agent_filter = {
        "$or": [{"hostname": regex}, {"ipAddress": regex}, {"platform": regex}],
        **tq,
    }
    raw = await db.agents.find(agent_filter, {"_id": 0, "id": 1, "hostname": 1, "ipAddress": 1, "status": 1, "platform": 1}).to_list(length=_MAX_PER_TYPE)
    results["agents"] = [
        {"id": r.get("id"), "label": r.get("hostname") or "—",
         "sub": f"{r.get('platform', '—')} · {r.get('status', '—')}",
         "type": "agent", "view": "agents"} for r in raw
    ]

    # ── Alerts ────────────────────────────────────────────────────────────
    alert_filter = {
        "$or": [{"message": regex}, {"type": regex}, {"source": regex}],
        **tq,
    }
    raw = await db.alerts.find(alert_filter, {"_id": 0, "id": 1, "message": 1, "severity": 1, "status": 1, "timestamp": 1}).sort("timestamp", -1).to_list(length=_MAX_PER_TYPE)
    results["alerts"] = [
        {"id": r.get("id"), "label": (r.get("message") or "—")[:80],
         "sub": f"{r.get('severity', '—')} · {r.get('status', 'Open')}",
         "type": "alert", "view": "alertManagement"} for r in raw
    ]

    # ── Vulnerabilities ───────────────────────────────────────────────────
    vuln_filter = {
        "$or": [{"cveId": regex}, {"description": regex}, {"affectedSoftware": regex}, {"component": regex}],
        **tq,
    }
    raw = await db.vulnerabilities.find(vuln_filter, {"_id": 0, "id": 1, "cveId": 1, "severity": 1, "description": 1}).to_list(length=_MAX_PER_TYPE)
    results["vulnerabilities"] = [
        {"id": r.get("id"), "label": r.get("cveId") or "—",
         "sub": f"{r.get('severity', '—')} · {(r.get('description') or '')[:60]}",
         "type": "vulnerability", "view": "vulnerabilityManagement"} for r in raw
    ]

    # ── Patches ───────────────────────────────────────────────────────────
    patch_filter = {
        "$or": [{"title": regex}, {"name": regex}, {"kb_id": regex}, {"description": regex}],
        **tq,
    }
    raw = await db.patches.find(patch_filter, {"_id": 0, "id": 1, "title": 1, "name": 1, "status": 1, "severity": 1}).to_list(length=_MAX_PER_TYPE)
    results["patches"] = [
        {"id": r.get("id"), "label": r.get("title") or r.get("name") or "—",
         "sub": f"{r.get('severity', '—')} · {r.get('status', '—')}",
         "type": "patch", "view": "patchManagement"} for r in raw
    ]

    # ── Compliance Frameworks ─────────────────────────────────────────────
    cf_filter = {
        "$or": [{"name": regex}, {"title": regex}, {"framework": regex}, {"description": regex}],
        **tq,
    }
    raw = await db.compliance_frameworks.find(cf_filter, {"_id": 0, "id": 1, "name": 1, "title": 1, "status": 1, "framework": 1}).to_list(length=_MAX_PER_TYPE)
    results["compliance_frameworks"] = [
        {"id": r.get("id"), "label": r.get("name") or r.get("title") or "—",
         "sub": r.get("framework") or r.get("status") or "—",
         "type": "compliance_framework", "view": "compliance"} for r in raw
    ]

    total = sum(len(v) for v in results.values())
    return {"query": q, "total": total, "results": results}
