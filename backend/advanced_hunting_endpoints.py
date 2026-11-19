"""Advanced Threat Hunting Endpoints — /api/advanced-hunting/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from rbac_utils import require_permission
from database import get_database
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import re
import uuid
from auth_roles import platform_scope_roles
import kql_engine
from kql_parser import KqlError
from soc_endpoints import soc_scope

router = APIRouter(prefix="/api/advanced-hunting", tags=["Advanced Hunting"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SaveQueryRequest(BaseModel):
    name: str
    description: str
    query: str
    category: str


class RunQueryRequest(BaseModel):
    query: str
    time_range_hours: int = 24
    limit: int = 100


# ---------------------------------------------------------------------------
# Built-in query templates
# ---------------------------------------------------------------------------

QUERY_TEMPLATES = [
    {
        "name": "Password Spray / Brute Force",
        "description": "Sources with many failed sign-ins, and how many accounts each one tried",
        "query": "SigninLogs | where Outcome == 'failure' | summarize FailedAttempts=count(), Accounts=dcount(Account) by SourceIP | where FailedAttempts > 10 | order by FailedAttempts desc",
        "category": "Identity",
        "mitre_technique": "T1110.003",
    },
    {
        "name": "Failed Windows Logons",
        "description": "Failed Windows logons (4625) per account and computer",
        "query": "SecurityEvent | where EventID == 4625 | summarize Failures=count() by Account, Computer | order by Failures desc",
        "category": "Identity",
        "mitre_technique": "T1110",
    },
    {
        "name": "Privilege Escalation",
        "description": "Users added to privileged groups (4728, 4732, 4756)",
        "query": "SecurityEvent | where EventID in (4728, 4732, 4756) | project TimeGenerated, Computer, Account, Group, Message",
        "category": "Privilege Escalation",
        "mitre_technique": "T1078.002",
    },
    {
        "name": "New Service Installed",
        "description": "Services installed on Windows (7045), a common persistence and ransomware step",
        "query": "SecurityEvent | where EventID == 7045 | project TimeGenerated, Computer, Message",
        "category": "Persistence",
        "mitre_technique": "T1543.003",
    },
    {
        "name": "Security Log Cleared",
        "description": "The Windows Security log was cleared (1102)",
        "query": "SecurityEvent | where EventID == 1102 | project TimeGenerated, Computer, Account",
        "category": "Defense Evasion",
        "mitre_technique": "T1070.001",
    },
    {
        "name": "Sudo Activity on Linux",
        "description": "sudo commands per account and host",
        "query": "Syslog | where Action == 'sudo_command' | summarize Commands=count(), Examples=make_set(CommandLine) by Account, Computer | order by Commands desc",
        "category": "Privilege Escalation",
        "mitre_technique": "T1548.003",
    },
    {
        "name": "Lateral Movement Ports",
        "description": "IDS alerts towards SMB, RDP and WinRM ports",
        "query": "IdsAlerts | where DestinationPort in (445, 139, 3389, 5985, 5986) | summarize Hits=count() by SourceIP, DestinationIP, DestinationPort | order by Hits desc",
        "category": "Lateral Movement",
        "mitre_technique": "T1021",
    },
    {
        "name": "Top IDS Signatures",
        "description": "The network signatures that fired most, and from how many sources",
        "query": "IdsAlerts | summarize Hits=count(), Sources=dcount(SourceIP) by Signature, Category | top 20 by Hits",
        "category": "Command and Control",
        "mitre_technique": "T1071",
    },
    {
        "name": "Ransomware Indicators",
        "description": "SOC alerts that point at ransomware: encryption, shadow copy deletion, ransom notes",
        "query": "SecurityAlert | where Title contains 'ransom' or Type contains 'ransom' or Description contains 'shadow' or Description contains 'vssadmin' | project TimeGenerated, Title, Severity, Status, AgentId, Process",
        "category": "Impact",
        "mitre_technique": "T1486",
    },
    {
        "name": "Alert Volume by Hour",
        "description": "SOC alerts per hour and severity",
        "query": "SecurityAlert | summarize Alerts=count() by bin(TimeGenerated, 1h), Severity | order by TimeGenerated asc",
        "category": "Overview",
        "mitre_technique": "",
    },
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/queries")
async def list_saved_queries(
    current_user: TokenData = Depends(get_current_user),
):
    """List all saved hunt queries for the tenant."""
    db = get_database()
    cursor = db.hunting_queries.find({"tenantId": current_user.tenant_id})
    results = []
    async for doc in cursor:
        results.append({
            "id": doc.get("id"),
            "name": doc.get("name"),
            "description": doc.get("description"),
            "query": doc.get("query"),
            "category": doc.get("category"),
            "created_at": doc.get("created_at"),
            "run_count": doc.get("run_count", 0),
            "last_run": doc.get("last_run"),
        })
    return results


@router.post("/queries", status_code=201)
async def save_query(
    body: SaveQueryRequest,
    current_user: TokenData = Depends(require_permission("investigate:security")),
):
    """Save a new hunt query."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "name": body.name,
        "description": body.description,
        "query": body.query,
        "category": body.category,
        "created_at": now,
        "run_count": 0,
        "last_run": None,
    }
    await db.hunting_queries.insert_one(doc)
    _strip_id(doc)
    return doc


@router.delete("/queries/{query_id}", status_code=204)
async def delete_query(
    query_id: str,
    current_user: TokenData = Depends(require_permission("investigate:security")),
):
    """Delete a saved hunt query."""
    db = get_database()
    result = await db.hunting_queries.delete_one(
        {"id": query_id, "tenantId": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Query not found")
    return None


@router.post("/run")
async def run_query(
    body: RunQueryRequest,
    current_user: TokenData = Depends(require_permission("investigate:security")),
):
    """Run a KQL query (kql_parser subset) over the caller's real SIEM events, SOC alerts and agent logs."""
    db = get_database()
    try:
        out = await kql_engine.run(db, soc_scope(current_user), body.query, body.time_range_hours, body.limit)
    except KqlError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Optionally increment run_count if query text matches a saved query
    await db.hunting_queries.update_one(
        {"query": body.query, "tenantId": current_user.tenant_id},
        {"$inc": {"run_count": 1}, "$set": {"last_run": datetime.now(timezone.utc).isoformat()}},
    )

    return {
        **out,
        "query_type": out["table"],
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "time_range_hours": body.time_range_hours,
    }


@router.get("/ioc-search")
async def ioc_search(
    indicator: str = Query(..., description="IOC value to search for"),
    ioc_type: str = Query(..., description="ip|domain|url|hash|email"),
    limit: int = Query(50, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    """Search for an IOC indicator across multiple collections."""
    valid_types = {"ip", "domain", "url", "hash", "email"}
    if ioc_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"ioc_type must be one of {sorted(valid_types)}",
        )

    db = get_database()
    tenant_filter = {"tenantId": current_user.tenant_id}
    matches = []

    # Security events — check remote_ip and domain fields
    se_filter = {
        **tenant_filter,
        "$or": [{"remote_ip": indicator}, {"domain": indicator}, {"description": {"$regex": re.escape(indicator), "$options": "i"}}],
    }
    cursor = db.security_events.find(se_filter).limit(limit)
    async for doc in cursor:
        _strip_id(doc)
        matches.append({
            "source": "security_events",
            "event_id": doc.get("id") or doc.get("event_id"),
            "timestamp": doc.get("created_at") or doc.get("timestamp"),
            "details": doc,
        })

    # Threat intel collection
    ti_filter = {
        **tenant_filter,
        "$or": [{"indicator": indicator}, {"value": indicator}],
    }
    cursor = db.threat_intel.find(ti_filter).limit(limit)
    async for doc in cursor:
        _strip_id(doc)
        matches.append({
            "source": "threat_intel",
            "event_id": doc.get("id"),
            "timestamp": doc.get("created_at") or doc.get("timestamp"),
            "details": doc,
        })

    # Audit logs
    al_filter = {
        **tenant_filter,
        "$or": [{"ip_address": indicator}, {"details": {"$regex": re.escape(indicator), "$options": "i"}}],
    }
    cursor = db.audit_logs.find(al_filter).limit(limit)
    async for doc in cursor:
        _strip_id(doc)
        matches.append({
            "source": "audit_logs",
            "event_id": doc.get("id"),
            "timestamp": doc.get("created_at") or doc.get("timestamp"),
            "details": doc,
        })

    return {
        "indicator": indicator,
        "ioc_type": ioc_type,
        "matches": matches[:limit],
        "match_count": len(matches),
    }


@router.get("/templates")
async def get_templates(current_user: TokenData = Depends(get_current_user)):
    """Return built-in KQL query templates."""
    return QUERY_TEMPLATES


# ---------------------------------------------------------------------------
# Geographic attack map + attack timeline (aggregations over security_events)
# ---------------------------------------------------------------------------

_SUPER_ROLES = platform_scope_roles()
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_GEO_FIELDS = ("country_code", "source_country", "countryCode", "geo_country")


def _range_to_hours(range_str: str) -> int:
    """Map a UI range token (24h/7d/30d) to hours; default 24h."""
    mapping = {"24h": 24, "7d": 168, "30d": 720, "1h": 1, "6h": 6}
    return mapping.get(range_str, 24)


def _event_scope(current_user: TokenData) -> dict:
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ROLES:
        return {}
    return {"tenantId": getattr(current_user, "tenant_id", None)}


def _worst_severity(sevs) -> str:
    best = "low"
    for s in sevs:
        s = (s or "low").lower()
        if _SEV_RANK.get(s, 0) > _SEV_RANK.get(best, 0):
            best = s
    return best


@router.get("/geo-sources")
async def geo_attack_sources(
    range: str = Query("24h"),
    current_user: TokenData = Depends(get_current_user),
):
    """Aggregate security events by source country for the attack map.

    Groups events in the time window by whichever geo field the event carries.
    Returns [] when events have no geo data (the UI keeps its own placeholder).
    """
    db = get_database()
    since = (datetime.now(timezone.utc) - timedelta(hours=_range_to_hours(range))).isoformat()
    query = {**_event_scope(current_user), "timestamp": {"$gte": since}}

    buckets: dict = {}
    async for ev in db.security_events.find(query, {"_id": 0}):
        cc = next((ev[f] for f in _GEO_FIELDS if ev.get(f)), None)
        if not cc:
            continue
        b = buckets.setdefault(cc, {"count": 0, "types": set(), "sevs": [], "last": ""})
        b["count"] += 1
        if ev.get("type"):
            b["types"].add(ev["type"])
        b["sevs"].append(ev.get("severity"))
        ts = ev.get("timestamp", "")
        if ts > b["last"]:
            b["last"] = ts

    results = [
        {
            "country": cc,
            "country_code": cc,
            "event_count": b["count"],
            "threat_types": sorted(b["types"]),
            "last_seen": b["last"],
            "severity": _worst_severity(b["sevs"]),
        }
        for cc, b in buckets.items()
    ]
    results.sort(key=lambda r: r["event_count"], reverse=True)
    return results


@router.get("/geo-sources/{country_code}/events")
async def geo_country_events(
    country_code: str,
    range: str = Query("24h"),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    """List recent security events originating from a given country."""
    db = get_database()
    since = (datetime.now(timezone.utc) - timedelta(hours=_range_to_hours(range))).isoformat()
    geo_or = [{f: country_code} for f in _GEO_FIELDS]
    query = {**_event_scope(current_user), "timestamp": {"$gte": since}, "$or": geo_or}

    events = []
    async for ev in db.security_events.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit):
        events.append({
            "id": ev.get("id", ""),
            "timestamp": ev.get("timestamp", ""),
            "source_ip": ev.get("source_ip") or ev.get("source") or "",
            "event_type": ev.get("type", "event"),
            "description": ev.get("description") or ev.get("message", ""),
        })
    return events


@router.get("/timeline")
async def attack_timeline(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(200, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    """Chronological security-event feed for the attack timeline view."""
    db = get_database()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {**_event_scope(current_user), "timestamp": {"$gte": since}}

    events = []
    async for ev in db.security_events.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit):
        events.append({
            "id": ev.get("id", ""),
            "timestamp": ev.get("timestamp", ""),
            "event_type": ev.get("type", "event"),
            "asset": ev.get("asset") or ev.get("source") or ev.get("hostname") or "",
            "user": ev.get("user"),
            "technique_id": ev.get("technique_id"),
            "technique_name": ev.get("technique_name"),
            "tactic": ev.get("tactic"),
            "severity": (ev.get("severity") or "low").lower(),
            "description": ev.get("description") or ev.get("message", ""),
            "details": ev.get("details"),
        })
    return events
