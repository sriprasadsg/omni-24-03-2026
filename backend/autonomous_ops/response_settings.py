"""Per-tenant response settings for the automatic sweep (Phase 83, D-04, D-13).

Stored as ``autonomy_settings.response`` ({twoSignal, blockHours, watchedServices}). A new tenant
reads the defaults with nothing stored, so there is no backfill: two sources required, a block
lasts 24 hours, no watched services. ``load`` never raises. A value that is present but not
understood reads as the safe default and sets ``readable`` False so a caller can say so.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import PLATFORM_TENANT_ID, agent_support, ledger, messages, response_messages, settings
from .scope import raw

logger = logging.getLogger(__name__)

DEFAULT_TWO_SIGNAL = True
DEFAULT_BLOCK_HOURS = 24
MIN_BLOCK_HOURS = 1
MAX_BLOCK_HOURS = 168          # 604800 seconds, the contract's longest block
MAX_SERVICES = 50
SERVICE_NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"      # the rule the agent enforces (UI-SPEC R12)
_SERVICE_RE = re.compile(SERVICE_NAME_RE)
SETTING_KEYS = ("twoSignal", "blockHours", "watchedServices")


@dataclass
class ResponseSettings:
    two_signal: bool = DEFAULT_TWO_SIGNAL
    block_hours: int = DEFAULT_BLOCK_HOURS
    watched_services: List[str] = field(default_factory=list)
    readable: bool = True


def _is_hours(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and MIN_BLOCK_HOURS <= value <= MAX_BLOCK_HOURS


async def load(db, tenant_id: str) -> ResponseSettings:
    """The tenant's response settings; defaults for anything absent, the safe default plus
    ``readable`` False for anything malformed or unreadable. Never raises."""
    s = ResponseSettings()
    try:
        doc = await raw(db).autonomy_settings.find_one({"tenantId": tenant_id}, {"_id": 0, "response": 1})
    except Exception as exc:
        logger.warning("autonomous_ops: response settings for %s could not be read: %s", tenant_id, exc)
        s.readable = False
        return s
    stored = (doc or {}).get("response")
    if stored is None:
        return s
    if not isinstance(stored, dict):
        s.readable = False
        return s
    if "twoSignal" in stored:
        if isinstance(stored["twoSignal"], bool):
            s.two_signal = stored["twoSignal"]
        else:
            s.readable = False
    if "blockHours" in stored:
        if _is_hours(stored["blockHours"]):
            s.block_hours = stored["blockHours"]
        else:
            s.readable = False
    if "watchedServices" in stored:
        names = stored["watchedServices"]
        if isinstance(names, list) and all(isinstance(n, str) for n in names):
            s.watched_services = list(names)
        else:
            s.readable = False
    return s


# ---------------------------------------------------------------- validation and writing

class SettingsError(ValueError):
    """A refused change. ``code`` is a key of ``response_messages.API_DETAIL``; ``detail`` is the sentence."""

    def __init__(self, code: str, **values: Any):
        self.code = code
        self.detail = response_messages.fill(response_messages.API_DETAIL[code], **values)
        super().__init__(self.detail)


class PlatformTenantError(SettingsError):
    """The platform organization has no response settings (D-04 of Phase 81)."""

    def __init__(self):
        ValueError.__init__(self, messages.API_DETAIL["platform_tenant"])
        self.code, self.detail = "platform_tenant", messages.API_DETAIL["platform_tenant"]


def validate_service_name(name: Any) -> str:
    """The trimmed service name, or SettingsError: empty_service, invalid_service or critical_service
    (a name on the contract's criticalServices list, compared case-insensitively)."""
    if not isinstance(name, str):
        raise SettingsError("invalid_service")
    cleaned = name.strip()
    if not cleaned:
        raise SettingsError("empty_service")
    if _SERVICE_RE.fullmatch(cleaned) is None:
        raise SettingsError("invalid_service")
    if cleaned.casefold() in {str(c).casefold() for c in agent_support.CONTRACT["criticalServices"]}:
        raise SettingsError("critical_service", name=cleaned)
    return cleaned


def validate_changes(body: Dict[str, Any]) -> Dict[str, Any]:
    """The cleaned changes for the keys of ``body`` that are settings. Raises SettingsError for a value
    outside its range, a bad or duplicate service name, more than 50 names, or no setting at all."""
    cleaned: Dict[str, Any] = {}
    if "twoSignal" in body:
        if not isinstance(body["twoSignal"], bool):
            raise SettingsError("invalid_setting")
        cleaned["twoSignal"] = body["twoSignal"]
    if "blockHours" in body:
        if not _is_hours(body["blockHours"]):
            raise SettingsError("invalid_block_length")
        cleaned["blockHours"] = body["blockHours"]
    if "watchedServices" in body:
        names = body["watchedServices"]
        if not isinstance(names, list):
            raise SettingsError("invalid_setting")
        if len(names) > MAX_SERVICES:
            raise SettingsError("too_many_services")
        seen, out = set(), []
        for name in names:
            name = validate_service_name(name)
            if name.casefold() in seen:
                raise SettingsError("duplicate_service", name=name)
            seen.add(name.casefold())
            out.append(name)
        cleaned["watchedServices"] = out
    if not cleaned:
        raise SettingsError("no_setting_change")
    return cleaned


def _current_values(s: ResponseSettings) -> Dict[str, Any]:
    return {"twoSignal": s.two_signal, "blockHours": s.block_hours, "watchedServices": list(s.watched_services)}


def _control_event(key: str, value: Any) -> str:
    if key == "twoSignal":
        return "two_signal_on" if value else "two_signal_off"
    return "block_length_changed" if key == "blockHours" else "watched_services_changed"


def _control_reason(key: str, value: Any) -> str:
    templates = response_messages.CONTROL_REASONS
    if key == "twoSignal":
        return templates[_control_event(key, value)]
    if key == "blockHours":
        return response_messages.fill(templates["block_length_changed"],
                                      length=response_messages.length_text(value * 3600))
    if not value:
        return templates["watched_services_none"]
    return response_messages.fill(templates["watched_services_changed"], count=len(value), names=", ".join(value))


async def save(db, tenant_id: str, changes: Dict[str, Any], *, actor: Optional[Dict[str, Any]],
               scope: str = "tenant") -> ResponseSettings:
    """Write ``changes`` (validated here again) to the tenant's own setting and record one control row per
    value that really changed, each naming ``actor`` (mirrored to the audit chain by the ledger). The
    platform organization is refused. If a control row cannot be recorded the values are put back and
    the error is raised: a safeguard is never loosened without a record (PROH-83-09)."""
    if tenant_id == PLATFORM_TENANT_ID:
        raise PlatformTenantError()
    changes = validate_changes(changes)
    await settings.ensure_tenant(db, tenant_id)
    before = await load(db, tenant_id)
    now_values, old_values = _current_values(before), _current_values(before)
    changed = [k for k in SETTING_KEYS if k in changes and changes[k] != old_values[k]]
    now_values.update({k: changes[k] for k in changed})
    if not changed and before.readable:
        return before
    if before.readable:
        await settings.update(db, tenant_id, {f"response.{k}": now_values[k] for k in changed}, actor=actor)
    else:
        await settings.update(db, tenant_id, {"response": now_values}, actor=actor)      # repairs a malformed value
    try:
        for key in changed:
            await ledger.record_control(db, tenant_id, _control_event(key, now_values[key]), scope=scope,
                                        actor=actor or {}, reason=_control_reason(key, now_values[key]))
    except Exception:
        logger.error("autonomous_ops: response settings change for %s not recorded; restoring the old values",
                     tenant_id)
        await settings.update(db, tenant_id, {"response": old_values}, actor=actor)
        raise
    return await load(db, tenant_id)


# ---------------------------------------------------------------- the list, on its way to the agents

WATCH_CAPABILITY = "remediation_executor"          # the tick that carries service-failure reporting and the restart


async def heartbeat_reply(db, tenant_id: Optional[str], agent_id: Optional[str], permitted) -> Dict[str, Any]:
    """What the heartbeat reply adds for one agent: ``watchedServices``, the tenant's list, only when the tenant
    holds ``remediation_executor``. An empty list is sent as it is (the agent then stops every check). Anything
    that cannot be read, or is not a well-formed list, leaves the key out, which changes nothing on the agent. Read
    by the agent's own verified tenant id, one indexed ``find_one``, and never raises: a failed read never fails a
    heartbeat. ``agent_id`` is the canonical ``agents.id`` of the caller (the confirmed-isolation list uses it)."""
    try:
        if not isinstance(tenant_id, str) or not tenant_id or WATCH_CAPABILITY not in permitted:
            return {}
        stored = await load(db, tenant_id)
        return {"watchedServices": list(stored.watched_services)} if stored.readable else {}
    except Exception as exc:
        logger.warning("autonomous_ops: the watched services of %s were not added to a heartbeat reply: %s", tenant_id, exc)
        return {}
