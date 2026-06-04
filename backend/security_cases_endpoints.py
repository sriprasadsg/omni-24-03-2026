from fastapi import APIRouter, HTTPException, Depends
import logging
import uuid
from datetime import datetime, timezone
from database import get_database
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


@router.get("/security-cases")
async def list_security_cases(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List security cases"""
    db = get_database()
    is_admin = is_super_admin(getattr(current_user, "role", ""))
    query: dict = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = _sec_caller_tenant(current_user)
    cases = await db.security_cases.find(query, {"_id": 0}).to_list(length=100)
    return cases


@router.post("/security-cases")
async def create_security_case(
    case: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new security case from a security event."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    case.setdefault("id", f"case-{uuid.uuid4()}")
    case.setdefault("tenantId", _sec_caller_tenant(current_user))
    case.setdefault("createdAt", now)
    case["updatedAt"] = now
    await db.security_cases.insert_one({**case, "_id": case["id"]})
    case.pop("_id", None)
    return case


@router.put("/security-cases/{case_id}")
async def update_security_case(
    case_id: str,
    case: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Update an existing security case."""
    db = get_database()
    is_admin = is_super_admin(getattr(current_user, "role", ""))
    query: dict = {"id": case_id}
    if not is_admin:
        query["tenantId"] = _sec_caller_tenant(current_user)
    case["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result = await db.security_cases.update_one(query, {"$set": case}, upsert=False)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Security case not found")
    return case


@router.get("/security-events")
async def list_security_events(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List security events"""
    db = get_database()
    is_admin = is_super_admin(getattr(current_user, "role", ""))
    query: dict = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = _sec_caller_tenant(current_user)
    events = await db.security_events.find(query, {"_id": 0}).to_list(length=100)
    return events


@router.post("/security-events")
async def create_security_event(
    event: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new security event."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    event.setdefault("id", f"evt-{uuid.uuid4()}")
    event.setdefault("tenantId", _sec_caller_tenant(current_user))
    event.setdefault("createdAt", now)
    await db.security_events.insert_one({**event, "_id": event["id"]})
    event.pop("_id", None)
    return event


@router.get("/vulnerability-scans")
async def list_vulnerability_scans(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List vulnerability scans"""
    db = get_database()
    is_admin = is_super_admin(getattr(current_user, "role", ""))
    query: dict = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = _sec_caller_tenant(current_user)
    scans = await db.vulnerability_scans.find(query, {"_id": 0}).to_list(length=100)
    return scans


@router.get("/security/incident-impact/{incident_id}")
async def get_incident_impact(
    incident_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get incident impact graph — returns nodes/edges for an incident the caller can access."""
    db = get_database()
    is_admin = is_super_admin(getattr(current_user, "role", ""))

    incident_query: dict = {"id": incident_id}
    if not is_admin:
        incident_query["tenantId"] = _sec_caller_tenant(current_user)

    incident = await db.security_cases.find_one(incident_query, {"_id": 0})
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    affected_asset_ids = incident.get("affectedAssets", [])
    nodes = [{"id": "root", "label": f"Incident {incident_id}", "type": "Incident"}]
    edges = []

    if affected_asset_ids:
        assets = await db.assets.find(
            {"id": {"$in": affected_asset_ids}}, {"_id": 0, "id": 1, "hostname": 1, "type": 1}
        ).to_list(length=50)
        for asset in assets:
            nodes.append({
                "id": asset["id"],
                "label": asset.get("hostname", asset["id"]),
                "type": asset.get("type", "Asset"),
            })
            edges.append({"from": "root", "to": asset["id"], "label": "Affected"})
    else:
        nodes.append({"id": "no-assets", "label": "No affected assets linked", "type": "Info"})
        edges.append({"from": "root", "to": "no-assets", "label": "Status"})

    return {"nodes": nodes, "edges": edges}
