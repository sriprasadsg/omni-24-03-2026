"""Go-live checks and the shadow observation period (Phase 86, GATE-09, D-14, D-15, D-16, D-20).

Five live checks are recorded once for the whole platform (``GOLIVE_CHECK_IDS``); each record is a new
document, so recording a check again keeps the earlier one and ``latest_checks`` shows the newest. An
organization may leave shadow mode only when all five checks have a record and seven whole days have
passed since its first shadow record (``lift_blockers``); anything that cannot be read blocks the lift.
The one organization a Super Admin has marked as the go-live test organization (D-23) is exempt from both
requirements; the mark is read fail closed, so an unreadable mark exempts nobody.

This module is the only code that touches the evidence collection, and only to insert into it, read it
and index it: it never updates, replaces or deletes a record (a structural test enforces that). Raw Mongo
handle and an explicit tenantId on every query; no model call.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from autonomous_ops import settings as ao_settings
from autonomous_ops.scope import raw

from . import GOLIVE_CHECK_IDS, GOLIVE_CHECKS, NOTE_MAX, NOTE_MIN, SHADOW_DAYS_REQUIRED, SHADOW_STATE, golive_test_org

_SECONDS_PER_DAY = 86400
_TOTAL = len(GOLIVE_CHECK_IDS)


def clock() -> datetime:
    """The current time; the one seam tests patch."""
    return datetime.now(timezone.utc)


def _checks(db):
    """The evidence collection. The only accessor: no other module may use it."""
    return raw(db)[GOLIVE_CHECKS]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def ensure_indexes(db) -> None:
    """Newest-first lookup per check, and one record per id."""
    coll = _checks(db)
    await coll.create_index([("checkId", 1), ("recordedAt", -1)], name="check_recorded")
    await coll.create_index("id", unique=True, name="id_unique")


async def record_check(db, check_id: str, note: str, actor: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Add one record for a check. ``ValueError`` for an unknown check id or a note outside 10 to 500
    characters after trimming. Earlier records stay."""
    text = note.strip() if isinstance(note, str) else ""
    if check_id not in GOLIVE_CHECK_IDS:
        raise ValueError("unknown go-live check")
    if not NOTE_MIN <= len(text) <= NOTE_MAX:
        raise ValueError(f"the note must be {NOTE_MIN} to {NOTE_MAX} characters")
    record = {
        "id": "GL-" + uuid.uuid4().hex, "checkId": check_id, "note": text,
        "recordedBy": {"username": str(actor.get("username") or "unknown"),
                       "display": str(actor.get("display") or actor.get("username") or "unknown")},
        "recordedAt": now,
    }
    await _checks(db).insert_one(dict(record))
    return record


async def latest_checks(db) -> List[Dict[str, Any]]:
    """One entry per check id, in ``GOLIVE_CHECK_IDS`` order: the newest record, or ``recorded`` False."""
    newest: Dict[str, Dict[str, Any]] = {}
    cursor = _checks(db).find({}, {"_id": 0}).sort([("recordedAt", -1), ("_id", -1)])
    async for doc in cursor:
        newest.setdefault(doc.get("checkId"), doc)
    out = []
    for check_id in GOLIVE_CHECK_IDS:
        doc = newest.get(check_id)
        out.append({"id": check_id, "recorded": doc is not None,
                    "recordedBy": doc.get("recordedBy") if doc else None,
                    "recordedAt": doc.get("recordedAt") if doc else None,
                    "note": doc.get("note") if doc else None})
    return out


async def _recorded_count(db) -> int:
    """How many of the five checks have at least one record."""
    ids = await _checks(db).distinct("checkId")
    return len({i for i in ids if i in GOLIVE_CHECK_IDS})


async def observation(db, tenant_id: str, now: datetime) -> Dict[str, Any]:
    """Shadow records of one organization: whole days since the first one (None when there is none),
    how many there are, and when the first was made."""
    actions = raw(db).autonomy_actions
    match = {"tenantId": tenant_id, "state": SHADOW_STATE}
    first_doc = await actions.find_one(match, {"_id": 0, "createdAt": 1}, sort=[("createdAt", 1)])
    would_have_done = await actions.count_documents(match)
    if first_doc is None:
        return {"daysObserved": None, "wouldHaveDone": would_have_done, "first": None}
    created = first_doc.get("createdAt")
    if not isinstance(created, datetime):
        raise ValueError("the first shadow record has no usable time")
    first = _aware(created)
    elapsed = (_aware(now) - first).total_seconds()
    return {"daysObserved": max(0, int(elapsed // _SECONDS_PER_DAY)), "wouldHaveDone": would_have_done, "first": first}


def _reasons(recorded: Optional[int], obs: Optional[Dict[str, Any]], exempt: bool = False) -> List[Dict[str, Any]]:
    """The reasons a lift is blocked. ``recorded`` or ``obs`` None means that read failed. The go-live test
    organization (``exempt``) has none: its checks, shadow records and days are not required."""
    reasons: List[Dict[str, Any]] = []
    if exempt:
        return reasons
    if recorded is not None and recorded < _TOTAL:
        reasons.append({"code": "checks_missing", "recorded": recorded})
    if recorded is None or obs is None:
        reasons.append({"code": "unreadable"})
    elif not obs["wouldHaveDone"]:
        reasons.append({"code": "no_shadow_records"})
    elif obs["daysObserved"] < SHADOW_DAYS_REQUIRED:
        reasons.append({"code": "days_short", "days": obs["daysObserved"]})
    return reasons


async def _test_org_mark(db) -> Optional[Dict[str, Any]]:
    """The go-live test organization mark; None when there is none or it cannot be read (fail closed)."""
    try:
        return await golive_test_org.current(db)
    except Exception:
        return None


def _is_marked(mark: Optional[Dict[str, Any]], tenant_id: str) -> bool:
    return bool(mark) and mark.get("tenantId") == tenant_id


async def _read(db, tenant_id: str, now: datetime):
    """(recorded, observation, is test organization); the first two are None when they could not be read."""
    try:
        recorded: Optional[int] = await _recorded_count(db)
    except Exception:
        recorded = None
    try:
        obs: Optional[Dict[str, Any]] = await observation(db, tenant_id, now)
    except Exception:
        obs = None
    return recorded, obs, _is_marked(await _test_org_mark(db), tenant_id)


async def lift_blockers(db, tenant_id: str, now: datetime) -> List[Dict[str, Any]]:
    """Why this organization may not leave shadow mode yet; empty means it may."""
    recorded, obs, exempt = await _read(db, tenant_id, now)
    return _reasons(recorded, obs, exempt)


async def lift_evidence(db, tenant_id: str, now: datetime) -> Dict[str, Any]:
    """What a lift rests on, for the audit event: days observed, simulated actions, checks recorded and
    whether the organization is the go-live test organization."""
    recorded, obs, exempt = await _read(db, tenant_id, now)
    return {"daysObserved": (obs or {}).get("daysObserved"), "wouldHaveDone": (obs or {}).get("wouldHaveDone"),
            "checksRecorded": recorded, "testOrganization": exempt}


def blocker_sentence(reasons: List[Dict[str, Any]]) -> str:
    """The reasons as plain sentences joined with a space."""
    parts = []
    for reason in reasons:
        code = reason.get("code")
        if code == "checks_missing":
            parts.append(f"Record all {_TOTAL} go-live checks first ({reason.get('recorded', 0)} of {_TOTAL} recorded).")
        elif code == "no_shadow_records":
            parts.append(f"No shadow records yet. Needs {SHADOW_DAYS_REQUIRED} days.")
        elif code == "days_short":
            days = reason.get("days", 0)
            parts.append(f"Needs {SHADOW_DAYS_REQUIRED} days of shadow records. {days} {'day' if days == 1 else 'days'} so far.")
        elif code == "unreadable":
            parts.append("Shadow records couldn't be read, so lifting is blocked.")
    return " ".join(parts)


async def overview(db, now: datetime) -> Dict[str, Any]:
    """What the Going live card shows: the five checks, every ticked organization with its observation and
    whether it can be lifted, the go-live test organization (or None) and the deployment-wide switch."""
    from autonomous_ops import sweep         # local: the sweep imports the whole Autonomous Ops package
    checks = await latest_checks(db)
    try:
        recorded: Optional[int] = await _recorded_count(db)
    except Exception:
        recorded = None
    mark = await _test_org_mark(db)
    organizations = []
    for tenant_id in await sweep._ticked_tenants(db):
        tenant = await raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "name": 1})
        own = await ao_settings.load(db, tenant_id)
        try:
            obs: Optional[Dict[str, Any]] = await observation(db, tenant_id, now)
        except Exception:
            obs = None
        marked = _is_marked(mark, tenant_id)
        reasons = _reasons(recorded, obs, marked)
        organizations.append({
            "id": tenant_id, "name": str((tenant or {}).get("name") or tenant_id), "shadow": own.shadow,
            "daysObserved": (obs or {}).get("daysObserved"), "wouldHaveDone": (obs or {}).get("wouldHaveDone", 0),
            "canLift": bool(own.shadow) and not reasons, "reasons": reasons, "testOrganization": marked})
    organizations.sort(key=lambda org: (org["name"].lower(), org["id"]))
    test_organization = None
    if mark:
        test_organization = {"id": mark.get("tenantId"), "name": mark.get("tenantName"),
                             "markedBy": mark.get("markedBy"), "markedAt": mark.get("markedAt")}
    return {"checks": checks, "recordedCount": sum(1 for c in checks if c["recorded"]),
            "organizations": organizations, "masterShadow": ao_settings.master_shadow(),
            "testOrganization": test_organization}
