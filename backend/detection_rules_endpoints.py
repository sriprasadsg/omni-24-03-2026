"""Detection Rules Endpoints — /api/detection-rules/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/detection-rules", tags=["Detection Rules"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RuleCondition(BaseModel):
    field: str
    operator: str  # eq, ne, gt, lt, contains, regex
    value: str


class DetectionRuleCreate(BaseModel):
    name: str
    description: str
    severity: str  # critical|high|medium|low|informational
    rule_type: str  # query|threshold|anomaly
    conditions: List[RuleCondition] = []
    time_window_minutes: int = 60
    threshold_count: int = 1
    tags: List[str] = []
    mitre_tactics: List[str] = []
    mitre_techniques: List[str] = []


class DetectionRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    rule_type: Optional[str] = None
    conditions: Optional[List[RuleCondition]] = None
    time_window_minutes: Optional[int] = None
    threshold_count: Optional[int] = None
    tags: Optional[List[str]] = None
    mitre_tactics: Optional[List[str]] = None
    mitre_techniques: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"critical", "high", "medium", "low", "informational"}
VALID_RULE_TYPES = {"query", "threshold", "anomaly"}

BUILTIN_RULES = [
    {
        "name": "Password Spray",
        "description": "Detect 5 or more failed login attempts within 5 minutes",
        "severity": "high",
        "rule_type": "threshold",
        "conditions": [{"field": "action", "operator": "eq", "value": "login_failed"}],
        "time_window_minutes": 5,
        "threshold_count": 5,
        "tags": ["identity", "brute-force"],
        "mitre_tactics": ["Credential Access"],
        "mitre_techniques": ["T1110.003"],
    },
    {
        "name": "Impossible Travel",
        "description": "Detect logins from geographically distant locations in a short window",
        "severity": "high",
        "rule_type": "anomaly",
        "conditions": [{"field": "action", "operator": "eq", "value": "login"}],
        "time_window_minutes": 60,
        "threshold_count": 1,
        "tags": ["identity", "travel"],
        "mitre_tactics": ["Initial Access"],
        "mitre_techniques": ["T1078"],
    },
    {
        "name": "Privilege Escalation — Group Add",
        "description": "Detect users being added to privileged security groups (EventID 4728/4732)",
        "severity": "critical",
        "rule_type": "query",
        "conditions": [
            {"field": "event_id", "operator": "eq", "value": "4728"},
            {"field": "event_id", "operator": "eq", "value": "4732"},
        ],
        "time_window_minutes": 60,
        "threshold_count": 1,
        "tags": ["privilege-escalation"],
        "mitre_tactics": ["Privilege Escalation"],
        "mitre_techniques": ["T1078.002"],
    },
    {
        "name": "Lateral Movement via SMB",
        "description": "Detect suspicious SMB activity indicative of lateral movement",
        "severity": "high",
        "rule_type": "query",
        "conditions": [{"field": "description", "operator": "contains", "value": "smb"}],
        "time_window_minutes": 30,
        "threshold_count": 3,
        "tags": ["lateral-movement", "smb"],
        "mitre_tactics": ["Lateral Movement"],
        "mitre_techniques": ["T1021.002"],
    },
    {
        "name": "Data Exfiltration by Volume",
        "description": "Detect anomalously large outbound byte transfers",
        "severity": "critical",
        "rule_type": "threshold",
        "conditions": [{"field": "bytes_out", "operator": "gt", "value": "100000000"}],
        "time_window_minutes": 60,
        "threshold_count": 1,
        "tags": ["exfiltration", "data-loss"],
        "mitre_tactics": ["Exfiltration"],
        "mitre_techniques": ["T1048"],
    },
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _build_rule_doc(body: DetectionRuleCreate, tenant_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "name": body.name,
        "description": body.description,
        "severity": body.severity,
        "rule_type": body.rule_type,
        "conditions": [c.model_dump() for c in body.conditions],
        "time_window_minutes": body.time_window_minutes,
        "threshold_count": body.threshold_count,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
        "last_triggered": None,
        "trigger_count": 0,
        "tags": body.tags,
        "mitre_tactics": body.mitre_tactics,
        "mitre_techniques": body.mitre_techniques,
    }


async def _seed_builtin_rules(db, tenant_id: str) -> None:
    """Insert the 5 built-in rules for a tenant that has none yet."""
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for template in BUILTIN_RULES:
        doc = {
            "id": str(uuid.uuid4()),
            "tenantId": tenant_id,
            "enabled": True,
            "created_at": now,
            "updated_at": now,
            "last_triggered": None,
            "trigger_count": 0,
            **template,
        }
        docs.append(doc)
    await db.detection_rules.insert_many(docs)


def _event_matches_conditions(event: dict, conditions: list) -> bool:
    """Check if a single event document satisfies ANY condition in the list."""
    for cond in conditions:
        field = cond.get("field", "")
        operator = cond.get("operator", "eq")
        value = str(cond.get("value", ""))
        event_val = str(event.get(field, ""))

        if operator == "eq" and event_val == value:
            return True
        elif operator == "ne" and event_val != value:
            return True
        elif operator == "gt":
            try:
                if float(event_val) > float(value):
                    return True
            except (ValueError, TypeError):
                pass
        elif operator == "lt":
            try:
                if float(event_val) < float(value):
                    return True
            except (ValueError, TypeError):
                pass
        elif operator == "contains" and value.lower() in event_val.lower():
            return True
        elif operator == "regex":
            import re
            try:
                if re.search(value, event_val, re.IGNORECASE):
                    return True
            except Exception:
                pass
    return False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_rules(
    severity: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    rule_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    """List detection rules with optional filters."""
    db = get_database()

    # Seed built-in rules if none exist for this tenant
    count = await db.detection_rules.count_documents({"tenantId": current_user.tenant_id})
    if count == 0:
        await _seed_builtin_rules(db, current_user.tenant_id)

    filt: dict = {"tenantId": current_user.tenant_id}
    if severity is not None:
        if severity not in VALID_SEVERITIES:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        filt["severity"] = severity
    if enabled is not None:
        filt["enabled"] = enabled
    if rule_type is not None:
        if rule_type not in VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid rule_type: {rule_type}")
        filt["rule_type"] = rule_type

    cursor = db.detection_rules.find(filt).skip(skip).limit(limit)
    rules = []
    async for doc in cursor:
        rules.append(_strip_id(doc))
    return rules


@router.post("/", status_code=201)
async def create_rule(
    body: DetectionRuleCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new detection rule."""
    if body.severity not in VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {body.severity}")
    if body.rule_type not in VALID_RULE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid rule_type: {body.rule_type}")

    db = get_database()
    doc = _build_rule_doc(body, current_user.tenant_id)
    await db.detection_rules.insert_one(doc)
    _strip_id(doc)
    return doc


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    body: DetectionRuleUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update an existing detection rule."""
    db = get_database()
    existing = await db.detection_rules.find_one(
        {"id": rule_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field, val in body.model_dump(exclude_none=True).items():
        if field == "severity" and val not in VALID_SEVERITIES:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {val}")
        if field == "rule_type" and val not in VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid rule_type: {val}")
        if field == "conditions":
            updates[field] = [c if isinstance(c, dict) else c.model_dump() for c in val]
        else:
            updates[field] = val

    await db.detection_rules.update_one(
        {"id": rule_id, "tenantId": current_user.tenant_id},
        {"$set": updates},
    )
    updated = await db.detection_rules.find_one(
        {"id": rule_id, "tenantId": current_user.tenant_id}
    )
    return _strip_id(updated)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a detection rule."""
    db = get_database()
    result = await db.detection_rules.delete_one(
        {"id": rule_id, "tenantId": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return None


@router.post("/{rule_id}/enable")
async def enable_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Enable a detection rule."""
    db = get_database()
    result = await db.detection_rules.update_one(
        {"id": rule_id, "tenantId": current_user.tenant_id},
        {"$set": {"enabled": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"id": rule_id, "enabled": True}


@router.post("/{rule_id}/disable")
async def disable_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Disable a detection rule."""
    db = get_database()
    result = await db.detection_rules.update_one(
        {"id": rule_id, "tenantId": current_user.tenant_id},
        {"$set": {"enabled": False, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"id": rule_id, "enabled": False}


@router.post("/{rule_id}/test")
async def test_rule(
    rule_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Run the rule against the last 1 hour of security events."""
    db = get_database()
    rule = await db.detection_rules.find_one(
        {"id": rule_id, "tenantId": current_user.tenant_id}
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    cursor = db.security_events.find(
        {"tenantId": current_user.tenant_id, "created_at": {"$gte": since}}
    ).limit(500)

    conditions = rule.get("conditions", [])
    sample_matches = []
    match_count = 0

    async for event in cursor:
        _strip_id(event)
        if _event_matches_conditions(event, conditions):
            match_count += 1
            if len(sample_matches) < 5:
                sample_matches.append(event)

    return {
        "matched": match_count > 0,
        "match_count": match_count,
        "sample_matches": sample_matches,
        "rule_id": rule_id,
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def get_stats(current_user: TokenData = Depends(get_current_user)):
    """Return aggregated statistics for detection rules."""
    db = get_database()
    tenant_filter = {"tenantId": current_user.tenant_id}

    total = await db.detection_rules.count_documents(tenant_filter)
    enabled = await db.detection_rules.count_documents({**tenant_filter, "enabled": True})
    disabled = await db.detection_rules.count_documents({**tenant_filter, "enabled": False})

    by_severity: dict = {}
    for sev in VALID_SEVERITIES:
        by_severity[sev] = await db.detection_rules.count_documents(
            {**tenant_filter, "severity": sev}
        )

    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    triggers_last_24h = await db.detection_rules.count_documents(
        {**tenant_filter, "last_triggered": {"$gte": since_24h}}
    )

    return {
        "total": total,
        "enabled": enabled,
        "disabled": disabled,
        "by_severity": by_severity,
        "triggers_last_24h": triggers_last_24h,
    }
