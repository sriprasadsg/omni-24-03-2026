"""Advanced Threat Hunting Endpoints — /api/advanced-hunting/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import re
import uuid

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
        "name": "Password Spray Detection",
        "description": "Detect multiple failed login attempts across many accounts from a single source",
        "query": "SecurityEvent | where EventID == 4625 | summarize FailedAttempts=count() by SourceIP | where FailedAttempts > 10",
        "category": "Identity",
        "mitre_technique": "T1110.003",
    },
    {
        "name": "Impossible Travel",
        "description": "Detect logins from geographically distant locations in a short time window",
        "query": "SigninLogs | where ResultType != 0 | project UserPrincipalName, Location, TimeGenerated | order by TimeGenerated desc",
        "category": "Identity",
        "mitre_technique": "T1078",
    },
    {
        "name": "Privilege Escalation",
        "description": "Detect addition of users to privileged groups",
        "query": "SecurityEvent | where EventID in (4728, 4732, 4756) | project TimeGenerated, SubjectUserName, MemberName, TargetUserName",
        "category": "Privilege Escalation",
        "mitre_technique": "T1078.002",
    },
    {
        "name": "Lateral Movement via SMB",
        "description": "Detect suspicious SMB connections indicative of lateral movement",
        "query": "NetworkTraffic | where DestinationPort == 445 | where network contains 'SMB' | summarize count() by SourceIP, DestinationIP",
        "category": "Lateral Movement",
        "mitre_technique": "T1021.002",
    },
    {
        "name": "DNS Anomaly Detection",
        "description": "Detect unusual DNS query volumes that may indicate C2 communication",
        "query": "NetworkTraffic | where network contains 'DNS' | summarize QueryCount=count() by SourceIP, domain | where QueryCount > 1000",
        "category": "Command and Control",
        "mitre_technique": "T1071.004",
    },
    {
        "name": "Data Exfiltration by Volume",
        "description": "Detect large outbound data transfers that may indicate exfiltration",
        "query": "NetworkTraffic | where network contains 'network' | summarize TotalBytes=sum(BytesSent) by SourceIP | where TotalBytes > 100000000",
        "category": "Exfiltration",
        "mitre_technique": "T1048",
    },
    {
        "name": "Suspicious Process Execution",
        "description": "Detect execution of known LOLBin processes used in attacks",
        "query": "Process | where ProcessName in ('powershell.exe','cmd.exe','wscript.exe','cscript.exe','mshta.exe') | where Process contains 'encoded'",
        "category": "Execution",
        "mitre_technique": "T1059.001",
    },
    {
        "name": "Ransomware Indicators",
        "description": "Detect mass file rename/delete activity indicative of ransomware",
        "query": "SecurityEvent | where EventID in (4663, 4656) | where Process contains 'ransomware' | summarize FileOps=count() by SubjectUserName | where FileOps > 500",
        "category": "Impact",
        "mitre_technique": "T1486",
    },
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _detect_query_type(query: str) -> str:
    q = query.lower()
    if "eventid" in q:
        return "security_events"
    if "signinlogs" in q or "login" in q:
        return "audit_logs_login"
    if "process" in q:
        return "security_events_process"
    if "networktraffic" in q or "network" in q:
        return "network_events"
    return "security_events_text"


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
    current_user: TokenData = Depends(get_current_user),
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
    current_user: TokenData = Depends(get_current_user),
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
    current_user: TokenData = Depends(get_current_user),
):
    """Execute a KQL-like hunt query against the appropriate collection."""
    db = get_database()
    query_type = _detect_query_type(body.query)
    since = datetime.now(timezone.utc) - timedelta(hours=body.time_range_hours)
    since_iso = since.isoformat()
    limit = max(1, min(body.limit, 1000))

    base_filter: dict = {"tenantId": current_user.tenant_id}

    if query_type == "security_events":
        base_filter["created_at"] = {"$gte": since_iso}
        # Extract EventID values from query if present
        event_ids = re.findall(r"\b(\d{4,5})\b", body.query)
        if event_ids:
            base_filter["event_id"] = {"$in": [int(e) for e in event_ids]}
        collection = db.security_events

    elif query_type == "audit_logs_login":
        base_filter["created_at"] = {"$gte": since_iso}
        base_filter["action"] = "login"
        collection = db.audit_logs

    elif query_type == "security_events_process":
        base_filter["created_at"] = {"$gte": since_iso}
        base_filter["event_type"] = "process"
        collection = db.security_events

    elif query_type == "network_events":
        base_filter["created_at"] = {"$gte": since_iso}
        collection = db.network_events

    else:
        # Text search on description
        base_filter["created_at"] = {"$gte": since_iso}
        collection = db.security_events

    cursor = collection.find(base_filter).limit(limit)
    results = []
    async for doc in cursor:
        _strip_id(doc)
        results.append(doc)

    # Optionally increment run_count if query text matches a saved query
    await db.hunting_queries.update_one(
        {"query": body.query, "tenantId": current_user.tenant_id},
        {"$inc": {"run_count": 1}, "$set": {"last_run": datetime.now(timezone.utc).isoformat()}},
    )

    return {
        "results": results,
        "total": len(results),
        "query_type": query_type,
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

_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}
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
