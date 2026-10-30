"""Response shaping for the Autonomous Ops routes (plan 81-09): who the caller is, which tenant a
request means, and the status and activity payloads the screen consumes.

Plain data only; no HTML. Every label and sentence comes from ``messages``. The raw Mongo handle
and an explicit tenantId are used everywhere; the ambient tenant ContextVar is never read.

D-25 lives here: for a platform-scope stop and its control rows, a tenant viewer is told "Platform
administrator" instead of the staff member's name (``display_actor``). Tenant-scope entries show the
real name to everyone.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

import rbac_defaults
from rbac_service import rbac_service as _rbac_service
from rbac_utils import has_platform_permission, is_super_admin, verify_permission

from . import (BUCKET_STATES, CONTROL_PERMISSION, LEVEL_RANK, MANAGE_PERMISSION, PLATFORM_CONTROL_PERMISSION,
               PLATFORM_TENANT_ID, health_messages, ledger, messages, registry, selfheal, settings, stop)
from .scope import raw

logger = logging.getLogger(__name__)

TENANT_ID_MAX = 128
_STATE_BUCKET = {state: bucket for bucket, states in BUCKET_STATES.items() for state in states}
_INTEGRATION_KEY_ROLE = "api-integration"      # the legacy tenant integration key (no person behind it)


# ---------------------------------------------------------------- who is calling

def is_interactive(user) -> bool:
    """True for a person signed in with a session. API keys (user-scoped and the legacy tenant
    key) are never interactive (D-10)."""
    if getattr(user, "auth_source", "session") == "api_key":
        return False
    return getattr(user, "role", None) != _INTEGRATION_KEY_ROLE


def _tenant_of(user) -> Optional[str]:
    return getattr(user, "tenant_id", None) or getattr(user, "tenantId", None)


def staff_tier(user) -> Optional[str]:
    """"owner" or "support" for platform staff who may name any tenant; None for everyone else
    (tenant roles, Platform Billing, and platform roles outside the platform tenant)."""
    tier = rbac_defaults.platform_tier(getattr(user, "role", None))
    if tier == "owner":
        return "owner"
    if tier == "support" and _tenant_of(user) == PLATFORM_TENANT_ID:
        return "support"
    return None


async def holds(user, permission: str) -> bool:
    """The role grants it and, for an API key, the key's scopes allow it."""
    return bool(await verify_permission(user, permission)) and _rbac_service._scopes_allow(user, permission)


@dataclass
class Caller:
    """What the routes need to know about the person or key behind a request."""
    user: Any
    tier: Optional[str]
    interactive: bool
    is_super: bool
    can_control: bool       # control:autonomous_ops (press a stop)
    can_manage: bool        # manage:autonomous_ops (resume, level, never-touch)
    can_platform: bool      # control:platform_autonomous_ops (stop or resume every organization)

    @property
    def staff(self) -> bool:
        """Platform staff see real names of platform staff (D-25)."""
        return self.tier in ("owner", "support")


async def build_caller(user) -> Caller:
    tier = staff_tier(user)
    support = rbac_defaults.platform_tier(getattr(user, "role", None)) == "support"
    return Caller(
        user=user, tier=tier, interactive=is_interactive(user), is_super=is_super_admin(getattr(user, "role", None)),
        can_control=(not support) and await holds(user, CONTROL_PERMISSION),
        can_manage=(not support) and await holds(user, MANAGE_PERMISSION),
        can_platform=bool(await has_platform_permission(user, PLATFORM_CONTROL_PERMISSION))
        and _rbac_service._scopes_allow(user, PLATFORM_CONTROL_PERMISSION))


async def actor_for(db, caller: Caller) -> Dict[str, str]:
    """The actor dict the stop and approval services record: {username, display, tier}."""
    username = str(getattr(caller.user, "username", None) or "unknown")
    display = username
    try:
        doc = await raw(db).users.find_one({"email": username}, {"_id": 0, "name": 1})
        if doc and doc.get("name"):
            display = str(doc["name"])
    except Exception as exc:                 # the name is a courtesy; the username always works
        logger.debug("autonomous_ops: display name for %s not read: %s", username, exc)
    return {"username": username, "display": display, "tier": "platform" if caller.tier == "owner" else "tenant"}


def resolve_tenant(user, tenant_param: Optional[str], *, write: bool) -> str:
    """The tenant a request means. A tenant role always means its own tenant and may not name another
    (T-81-37); the platform owner and Platform Support must name one with ``tenantId``; Platform
    Support may only read (D-08); Platform Billing never reaches an Autonomous Ops tenant."""
    tier = rbac_defaults.platform_tier(getattr(user, "role", None))
    if tier == "billing":
        raise HTTPException(status_code=403, detail="Platform Billing cannot use Autonomous Ops")
    if tenant_param is not None and (not isinstance(tenant_param, str) or not tenant_param.strip()
                                     or len(tenant_param) > TENANT_ID_MAX):
        raise HTTPException(status_code=422, detail="tenantId is not valid")
    if staff_tier(user) is not None:
        if write and tier != "owner":
            raise HTTPException(status_code=403, detail="Platform Support can read Autonomous Ops but not change it")
        if not tenant_param:
            raise HTTPException(status_code=400, detail="tenantId is required")
        return tenant_param
    own = _tenant_of(user)
    if not own:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if tenant_param and tenant_param != own:
        raise HTTPException(status_code=403, detail="You can only use Autonomous Ops for your own organization")
    return own


async def require_tenant(db, tenant_id: str) -> None:
    """404 when platform staff name a tenant that does not exist."""
    found = await raw(db).tenants.find_one({"id": tenant_id}, {"_id": 0, "id": 1})
    if found is None:
        raise HTTPException(status_code=404, detail="Organization not found")


# ---------------------------------------------------------------- presentation

def _iso(value) -> Optional[str]:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    return str(value) if value else None


def display_actor(actor: Optional[Dict[str, Any]], scope: Optional[str], viewer_is_platform_staff: bool) -> str:
    """D-25: a platform-scope action is credited to "Platform administrator" for a tenant viewer;
    platform staff (and every viewer of a tenant-scope action) get the real display name."""
    if scope == "platform" and not viewer_is_platform_staff:
        return messages.PLATFORM_ADMIN_DISPLAY
    actor = actor if isinstance(actor, dict) else {}
    return str(actor.get("display") or actor.get("username") or "")


def stop_view(doc: Optional[Dict[str, Any]], viewer_is_platform_staff: bool) -> Optional[Dict[str, Any]]:
    """The StopView of an active stop, else None."""
    if not settings.stop_active(doc):
        return None
    scope = "platform" if doc.get("scope") == "platform" else "tenant"
    return {"scope": scope, "by": display_actor(doc.get("pressedBy"), scope, viewer_is_platform_staff),
            "at": _iso(doc.get("pressedAt")), "reason": doc.get("reason") or None}


def bucket_of(row: Dict[str, Any]) -> str:
    """The one Activity bucket a row belongs to; control rows and platform-health rows have their own.
    A platform-health row is decided before any state lookup, so it can never read as refused."""
    if row.get("kind") == "platform_health":
        return "platform_health"
    if row.get("kind") == "control":
        return "control"
    return _STATE_BUCKET.get(row.get("state"), "refused")      # an unknown state never reads as done


def _class_line(row: Dict[str, Any]) -> Optional[str]:
    if row.get("kind") == "control":
        return None
    spec = registry.resolve(row.get("command"))
    if (row.get("approval") or {}).get("requiredBy") or (spec is not None and spec.cls == "approve"):
        return messages.CLASS_LINES["approve"]
    if spec is not None and spec.cls == "auto":
        return messages.CLASS_LINES["auto"]
    return None


def _action_label(row: Dict[str, Any]) -> str:
    if row.get("kind") == "control":
        return messages.CONTROL_LABELS.get(row.get("controlEvent"), "Control event")
    command = row.get("command")
    label = messages.ACTION_LABELS.get(command)
    if label:
        return label
    if isinstance(command, str) and command:
        return command.replace("_", " ").capitalize()
    return "Action"


def _result_text(row: Dict[str, Any], label: str, host: Optional[str]) -> Optional[str]:
    if row.get("kind") == "control":
        return None
    state = row.get("state")
    if state == "shadow":
        where = host or row.get("target")
        template = messages.SIMULATION_WOULD_HAVE.get(row.get("wouldHave"), messages.SIMULATION_WOULD_HAVE["other"])
        return messages.simulation_result(template.format(action=label, host=f" on {where}" if where else ""))
    return messages.STATE_RESULT.get(state)


def present_row(row: Dict[str, Any], *, viewer_is_platform_staff: bool, host: Optional[str] = None) -> Dict[str, Any]:
    """One ledger row as the Activity list shows it."""
    if row.get("kind") == "platform_health":
        return _present_health_row(row)
    control = row.get("kind") == "control"
    targets = row.get("targets") or []
    target = row.get("target")
    if target is not None and targets and str(target) == str(targets[0]) and host:
        target = None                         # the host name already says it; never show an agent id beside it
    rule = (row.get("reason") or {}).get("ruleId")
    label = _action_label(row)
    return {
        "id": row.get("id"),
        "bucket": bucket_of(row),
        "state": row.get("state"),
        "createdAt": _iso(row.get("createdAt")),
        "actionLabel": label,
        "classLine": _class_line(row),
        "reasonText": row.get("reasonText") or messages.REASON_TEXT.get(row.get("reasonCode")) or None,
        "ruleId": rule if isinstance(rule, str) else None,
        "host": host,
        "target": str(target) if target else None,
        "resultText": _result_text(row, label, host),
        "controlEvent": row.get("controlEvent") if control else None,
        "by": display_actor(row.get("actor"), row.get("scope"), viewer_is_platform_staff) if control else None,
        "healthChip": None,
        "source": None,
    }


def _present_health_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """A platform-health row: every word comes from ``health_messages`` (HEAL-07)."""
    event = row.get("healthEvent")
    params = row.get("healthParams") if isinstance(row.get("healthParams"), dict) else {}
    created = row.get("createdAt")
    words = health_messages.render(event, params, row.get("host"), created if isinstance(created, datetime) else None)
    return {
        "id": row.get("id"), "bucket": "platform_health", "state": row.get("state"), "createdAt": _iso(created),
        "actionLabel": words["actionLabel"], "classLine": None, "reasonText": words["reasonText"],
        "ruleId": words["ruleId"], "host": words["host"], "target": words["target"],
        "resultText": words["resultText"], "controlEvent": None, "by": None,
        "healthChip": row.get("healthChip") or health_messages.chip_for(event, params), "source": words["source"],
    }


async def _host_names(db, tenant_id: str, rows: List[Dict[str, Any]]) -> Dict[str, str]:
    ids = sorted({str(r["targets"][0]) for r in rows if r.get("kind") != "control" and r.get("targets")})
    if not ids:
        return {}
    found = raw(db).agents.find({"tenantId": tenant_id, "id": {"$in": ids}}, {"_id": 0, "id": 1, "hostname": 1})
    return {a["id"]: a["hostname"] async for a in found if a.get("hostname")}


async def list_page(db, tenant_id: str, *, bucket: str, limit: int, cursor: Optional[str],
                    viewer_is_platform_staff: bool, include_platform_health: bool = False) -> Dict[str, Any]:
    """A page of the tenant's activity, newest first (createdAt then id, both descending). A real
    tenant's list also carries the platform-scope control rows (stop pressed or cleared for every
    organization). Counts and the total are added to the first page only.

    Platform-health rows (watchdog events) are excluded for every tenant id, the platform tenant
    included, unless ``include_platform_health`` is True; only the Super Admin's platform route
    sets it (D-23, PROH-82-06)."""
    include_health = include_platform_health and tenant_id == PLATFORM_TENANT_ID
    own: Dict[str, Any] = {"tenantId": tenant_id}
    if tenant_id != PLATFORM_TENANT_ID:
        scope: Dict[str, Any] = {"$or": [own, {"tenantId": PLATFORM_TENANT_ID, "kind": "control", "scope": "platform"}]}
    else:
        scope = own
    if not include_health:
        scope = {"$and": [scope, {"kind": {"$ne": "platform_health"}}]}
    flt: Dict[str, Any] = dict(scope)
    if bucket == "platform_health":
        if not include_health:
            raise ValueError(f"unknown bucket {bucket!r}")
        flt = {"tenantId": PLATFORM_TENANT_ID, "kind": "platform_health"}
    elif bucket != "all":
        if bucket not in BUCKET_STATES:
            raise ValueError(f"unknown bucket {bucket!r}")
        flt = {"$and": [scope, {"state": {"$in": list(BUCKET_STATES[bucket])}}]}
    paged = flt
    if cursor:
        created, row_id = ledger._decode_cursor(cursor)
        paged = {"$and": [flt, {"$or": [{"createdAt": {"$lt": created}},
                                        {"createdAt": created, "id": {"$lt": row_id}}]}]}
    found = raw(db).autonomy_actions.find(paged, {"_id": 0}).sort([("createdAt", -1), ("id", -1)]).limit(limit + 1)
    rows = [ledger._normalize(r) async for r in found]
    page = rows[:limit]
    hosts = await _host_names(db, tenant_id, page)
    out: Dict[str, Any] = {
        "items": [present_row(r, viewer_is_platform_staff=viewer_is_platform_staff,
                              host=hosts.get(str(r["targets"][0])) if r.get("targets") else None) for r in page],
        "nextCursor": ledger._encode_cursor(page[-1]) if len(rows) > limit else None,
    }
    if not cursor:
        out["counts"] = await ledger.counts(db, tenant_id)
        if include_health:
            out["counts"]["platform_health"] = await raw(db).autonomy_actions.count_documents(
                {"tenantId": PLATFORM_TENANT_ID, "kind": "platform_health"})
        out["total"] = await raw(db).autonomy_actions.count_documents(flt)
    return out


# ---------------------------------------------------------------- status

def _previous_level(breaker: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(breaker, dict):
        return None
    previous = breaker.get("previousLevel")
    return previous if previous in LEVEL_RANK else "suggest"


async def status_payload(db, caller: Caller, tenant_id: str) -> Dict[str, Any]:
    """GET /status for one tenant. The platform stop is read uncached; an unreadable one raises."""
    s = await settings.load(db, tenant_id)
    platform_tenant = tenant_id == PLATFORM_TENANT_ID
    platform_doc = await settings.platform_stop(db)
    on, source = settings.shadow_state(s)
    tenant_stop = s.stop if settings.stop_active(s.stop) else None
    can_resume = bool(
        caller.interactive and tenant_stop is not None and not platform_tenant
        and stop.can_clear(tenant_stop, actor_is_super_admin=caller.is_super, actor_has_manage=caller.can_manage))
    return {
        "tenantId": tenant_id,
        "tenantName": s.name or tenant_id,
        "scope": "tenant",
        "platformTenant": platform_tenant,
        "eligible": bool(s.eligible) and not platform_tenant,
        "levelReadable": bool(s.readable),
        "level": "off" if platform_tenant else s.level,
        "maxLevel": "off" if platform_tenant else s.max_level,
        "previousLevel": _previous_level(s.breaker),
        "shadow": {"effective": on, "source": source},
        "stop": {"tenant": stop_view(tenant_stop, caller.staff), "platform": stop_view(platform_doc, caller.staff)},
        "canStop": bool(caller.can_control and not platform_tenant),
        "canResume": can_resume,
        "canStopPlatform": bool(caller.can_platform),
        "canResumePlatform": bool(caller.can_platform and caller.interactive and settings.stop_active(platform_doc)),
    }


async def platform_status_payload(db, caller: Caller) -> Dict[str, Any]:
    """GET /api/platform/autonomous-ops/status."""
    platform_doc = await settings.platform_stop(db)
    stopped = await raw(db).autonomy_settings.count_documents({"stop.active": True})
    try:
        health = await selfheal.health_summary(db, datetime.now(timezone.utc))
    except Exception as exc:        # the banners are optional; the stop status must still answer
        logger.error("autonomous_ops: platform health summary failed: %s", type(exc).__name__)
        health = None
    return {
        "scope": "platform",
        "stop": {"platform": stop_view(platform_doc, True)},
        "tenantStopsCount": stopped,
        "canStopPlatform": bool(caller.can_platform),
        "canResumePlatform": bool(caller.can_platform and caller.interactive and settings.stop_active(platform_doc)),
        "health": health,
    }


# ---------------------------------------------------------------- one row, never-touch entries

async def present_one(db, tenant_id: str, action_id: str, caller: Caller) -> Optional[Dict[str, Any]]:
    """The row as the list shows it, read fresh (after a decision changed it)."""
    row = await ledger.get(db, tenant_id, action_id)
    if row is None:
        return None
    hosts = await _host_names(db, tenant_id, [row])
    host = hosts.get(str(row["targets"][0])) if row.get("targets") else None
    return present_row(row, viewer_is_platform_staff=caller.staff, host=host)


def entry_view(entry) -> Dict[str, Any]:
    return {"id": entry.id, "scope": entry.scope, "kind": entry.kind, "value": entry.value,
            "note": entry.note, "builtin": bool(entry.builtin)}


_INFRASTRUCTURE_ENTRY = {"id": "builtin:platform-infrastructure", "scope": "builtin", "kind": "host",
                         "value": "This platform's own servers and agents", "note": "built in", "builtin": True}


def visible_entries(entries, viewer_is_platform_staff: bool) -> List[Dict[str, Any]]:
    """The never-touch list as the viewer may read it. Built-in entries derived from this server's
    own addresses, configuration and platform agents are shown to platform staff only; everyone else
    sees the general ranges plus one line standing for the rest (no platform address is disclosed)."""
    from . import protected
    general = {e.id for e in protected._special_networks()}
    shown, hidden = [], False
    for entry in entries:
        if entry.builtin and entry.id not in general and not viewer_is_platform_staff:
            hidden = True
            continue
        shown.append(entry_view(entry))
    if hidden:
        shown.append(dict(_INFRASTRUCTURE_ENTRY))
    return shown
