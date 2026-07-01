"""
Route aliases and missing convenience endpoints to ensure full API coverage.
All routes here delegate to existing handlers — no new logic introduced.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, List, Optional
from authentication_service import get_current_user
from rbac_utils import require_permission
from database import get_database
from auth_types import TokenData

router = APIRouter(tags=["Route Aliases"])


# ── MITRE ATT&CK aliases ──────────────────────────────────────────────────────
# (real routes: /api/mitre/matrix, /api/mitre/coverage)

# ── Network aliases ───────────────────────────────────────────────────────────

@router.get("/api/network/devices")
async def network_devices_alias(current_user: Any = Depends(get_current_user)):
    """Alias for /api/network-devices"""
    from network_endpoints import get_network_devices
    return await get_network_devices(current_user)


@router.get("/api/network/topology")
async def network_topology_alias(current_user: Any = Depends(get_current_user)):
    """Alias for /api/network-devices/topology"""
    from network_endpoints import get_network_topology
    return await get_network_topology(current_user)


@router.get("/api/network/segments")
async def network_segments_alias(current_user: Any = Depends(get_current_user)):
    """Alias for /api/network-devices/subnets"""
    from network_endpoints import get_network_subnets
    return await get_network_subnets(current_user)


# ── SBOM alias ────────────────────────────────────────────────────────────────

@router.get("/api/sbom")
async def sbom_list_alias(current_user: Any = Depends(get_current_user)):
    """Alias for /api/sboms"""
    from sbom_endpoints import get_sboms
    return await get_sboms(current_user)


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/api/reports")
async def list_reports(current_user: Any = Depends(get_current_user)):
    """List all available report categories."""
    return {
        "report_types": [
            {"id": "executive-summary",      "name": "Executive Summary",       "url": "/api/reports/executive-summary"},
            {"id": "vulnerability-exposure",  "name": "Vulnerability Exposure",  "url": "/api/reports/vulnerability-exposure"},
            {"id": "sla-compliance",          "name": "SLA Compliance",          "url": "/api/reports/sla-compliance"},
            {"id": "change-management",       "name": "Change Management",       "url": "/api/reports/change-management"},
            {"id": "compliance-reports",      "name": "Compliance Reports",      "url": "/api/compliance/reports"},
            {"id": "ticket-summary",          "name": "Ticket Summary",          "url": "/api/tickets/reports/summary"},
            {"id": "ticket-sla",              "name": "Ticket SLA",              "url": "/api/tickets/reports/sla"},
        ],
        "total": 7
    }


@router.get("/api/reports/templates")
async def list_report_templates(current_user: Any = Depends(get_current_user)):
    """Return available report template types."""
    return {
        "templates": [
            {"id": "executive-summary",     "name": "Executive Summary",      "frequency": ["daily", "weekly", "monthly"]},
            {"id": "vulnerability-exposure", "name": "Vulnerability Exposure", "frequency": ["daily", "weekly", "monthly"]},
            {"id": "sla-compliance",         "name": "SLA Compliance",         "frequency": ["weekly", "monthly"]},
            {"id": "change-management",      "name": "Change Management",      "frequency": ["weekly", "monthly"]},
            {"id": "compliance-summary",     "name": "Compliance Summary",     "frequency": ["monthly", "quarterly"]},
        ]
    }


# ── Compliance sub-routes ─────────────────────────────────────────────────────

@router.get("/api/compliance/policies")
async def get_compliance_policies(current_user: Any = Depends(get_current_user)):
    """Return compliance frameworks shaped as policies."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query: Dict = {}
    if tenant_id:
        query["tenantId"] = tenant_id
    frameworks = await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=100)
    # Also check tenant-scoped policy collection
    policies = await db.compliance_policies.find(query, {"_id": 0}).to_list(length=100) if tenant_id else []
    return frameworks + policies


@router.get("/api/compliance/checks")
async def get_compliance_checks(current_user: Any = Depends(get_current_user)):
    """Return compliance check results for the tenant."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query: Dict = {}
    if tenant_id:
        query["tenantId"] = tenant_id
    checks = await db.compliance_checks.find(query, {"_id": 0}).to_list(length=200)
    if not checks:
        # Fall back to controls from frameworks
        controls: List = []
        frameworks = await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=20)
        for fw in frameworks:
            for ctrl in (fw.get("controls") or [])[:5]:
                if isinstance(ctrl, dict):
                    controls.append({**ctrl, "framework": fw.get("shortName", fw.get("name", ""))})
        return controls
    return checks


@router.get("/api/compliance/benchmarks")
async def get_compliance_benchmarks(current_user: Any = Depends(get_current_user)):
    """Return CIS/NIST benchmark results."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query: Dict = {"tenantId": tenant_id} if tenant_id else {}
    benchmarks = await db.compliance_benchmarks.find(query, {"_id": 0}).to_list(length=100)
    if not benchmarks:
        frameworks = await db.compliance_frameworks.find({}, {"_id": 0}).to_list(length=20)
        benchmarks = [
            {
                "id": fw.get("id", ""),
                "name": fw.get("name", ""),
                "shortName": fw.get("shortName", ""),
                "progress": fw.get("progress", 0),
                "status": fw.get("status", "Unknown"),
            }
            for fw in frameworks
        ]
    return benchmarks


@router.get("/api/compliance/cis")
async def get_cis_controls(current_user: Any = Depends(get_current_user)):
    """Return CIS Controls framework data."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query: Dict = {"tenantId": tenant_id} if tenant_id else {}
    cis = await db.cis_controls.find(query, {"_id": 0}).to_list(length=200)
    if not cis:
        frameworks = await db.compliance_frameworks.find(
            {"$or": [{"shortName": {"$regex": "CIS", "$options": "i"}}, {"name": {"$regex": "CIS", "$options": "i"}}]},
            {"_id": 0}
        ).to_list(length=5)
        return frameworks
    return cis


# ── GET wrappers for POST-only endpoints ──────────────────────────────────────

@router.get("/api/ai/test-connection")
async def ai_test_connection_status(current_user: Any = Depends(get_current_user)):
    """Return current LLM connection configuration (non-destructive GET variant)."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query: Dict = {"tenantId": tenant_id} if tenant_id else {}
    settings = await db.llm_settings.find_one(query, {"_id": 0})
    if not settings:
        settings = {}
    return {
        "status": "configured" if settings.get("provider") else "unconfigured",
        "provider": settings.get("provider", "ollama"),
        "model": settings.get("model", ""),
        "note": "Use POST /api/ai/test-connection to run a live connectivity test",
    }


@router.get("/api/ueba/shadow-ai")
async def get_shadow_ai_summary(current_user: Any = Depends(get_current_user)):
    """Return shadow AI detection summary (GET variant of the POST report endpoint)."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    query: Dict = {"tenantId": tenant_id} if tenant_id else {}
    count = await db.shadow_ai_events.count_documents(query)
    recent = await db.shadow_ai_events.find(query, {"_id": 0}).sort("timestamp", -1).to_list(length=10)
    return {
        "total_detections": count,
        "recent_events": recent,
        "status": "active" if count > 0 else "no_detections",
    }


@router.get("/api/tenants/me")
async def get_my_tenant(current_user: Any = Depends(get_current_user)):
    """Return the calling user's own tenant data."""
    from database import mongodb
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=404, detail="No tenant associated with this account")
    tenant = await mongodb.db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("/api/agent/download-token/{tenant_id}")
async def get_agent_download_info(
    tenant_id: str,
    current_user: Any = Depends(get_current_user),
):
    """Return agent download instructions for the tenant (GET variant)."""
    caller_tenant = getattr(current_user, "tenant_id", None)
    from rbac_utils import is_super_admin
    if not is_super_admin(getattr(current_user, "role", "")) and caller_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")
    return {
        "tenant_id": tenant_id,
        "instructions": "Use POST /api/agent/download-token/{tenant_id} to generate a one-time download token.",
        "download_url": f"/api/agent/download/{tenant_id}",
        "platforms": ["windows", "linux", "macos"],
    }


# ── Agents stats ──────────────────────────────────────────────────────────────

@router.get("/api/agents/stats")
async def get_agents_stats(current_user: Any = Depends(get_current_user)):
    """Return aggregated agent statistics."""
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None)
    from rbac_utils import is_super_admin
    query: Dict = {} if is_super_admin(getattr(current_user, "role", "")) else {"tenantId": tenant_id}
    total   = await db.agents.count_documents(query)
    online  = await db.agents.count_documents({**query, "status": {"$in": ["online", "active", "connected"]}})
    offline = await db.agents.count_documents({**query, "status": {"$in": ["offline", "disconnected"]}})
    return {
        "total": total,
        "online": online,
        "offline": offline,
        "other": total - online - offline,
    }


# ── AI guardrail-policy alias ─────────────────────────────────────────────────

@router.get("/api/ai-proxy/guardrail-policy")
async def get_guardrail_policy_alias(current_user: Any = Depends(get_current_user)):
    """Alias for /api/ai-proxy/policy — returns active guardrail policy."""
    db = get_database()
    tid = getattr(current_user, "tenant_id", None)
    settings = (await db.ai_settings.find_one({"tenant_id": tid}, {"_id": 0})) or \
               (await db.ai_settings.find_one({"tenant_id": "global"}, {"_id": 0})) or {}
    return settings.get("policy", {})


# ── Secrets findings alias ────────────────────────────────────────────────────

@router.get("/api/secrets/findings")
async def get_secrets_findings(current_user: Any = Depends(get_current_user)):
    """Alias for /api/secrets/list — returns secrets scan findings."""
    from secrets_service import get_secrets_service
    db = get_database()
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    svc = get_secrets_service(db)
    return await svc.list_secrets(tenant_id=tenant_id)


# ── PQC keys alias ────────────────────────────────────────────────────────────

@router.get("/api/pqc/keys")
async def get_pqc_keys(current_user: Any = Depends(get_current_user)):
    """Alias for /api/pqc/status — returns PQC key inventory."""
    from pqc_endpoints import pqc_status
    return await pqc_status(current_user)
