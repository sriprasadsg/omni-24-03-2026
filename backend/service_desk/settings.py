"""The tenant's service desk setting (D-03): what is stored under ``autonomy_settings.serviceDesk``.

Nothing stored means Drafts only. A value that is not understood, or a read that fails, also reads
Drafts only with ``readable`` False, so the desk never posts on a setting it could not read. ``load``
never raises. ``save`` and ``restore`` are the only writers: each value that really changes leaves one
control row in the Autonomous Ops ledger (mirrored to the audit chain) naming the person, and saving the
current values writes nothing (Phase 83 D-22). Post answers cannot be saved while the desk breaker is
stored (D-25): the one way back is ``restore``. The status view is added below by 85-11 task 2.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument

from autonomous_ops import PLATFORM_TENANT_ID, ledger
from autonomous_ops import settings as ao_settings
from autonomous_ops.scope import raw

from . import DEFAULT_MODE, MODES, WORD_MAX, WORD_MIN, WORDS_MAX, messages

logger = logging.getLogger(__name__)


@dataclass
class DeskSettings:
    mode: str = DEFAULT_MODE
    words: List[str] = field(default_factory=list)
    breaker: Optional[Dict[str, Any]] = None
    readable: bool = True


async def load(db, tenant_id: str) -> DeskSettings:
    """The tenant's desk setting; absent reads Drafts only (D-03)."""
    try:
        doc = await raw(db).autonomy_settings.find_one({"tenantId": tenant_id}, {"_id": 0, "serviceDesk": 1})
    except Exception as exc:
        logger.warning("service_desk: settings for %s could not be read: %s", tenant_id, exc)
        return DeskSettings(readable=False)
    stored = (doc or {}).get("serviceDesk")
    if stored is None:
        return DeskSettings()
    if not isinstance(stored, dict):
        return DeskSettings(readable=False)
    mode = stored.get("mode", DEFAULT_MODE)
    result = DeskSettings()
    if isinstance(mode, str) and mode in MODES:
        result.mode = mode
    else:
        result.readable = False
    words = stored.get("words")
    if isinstance(words, list):
        result.words = [w for w in words if isinstance(w, str)]
    breaker = stored.get("breaker")
    result.breaker = breaker if isinstance(breaker, dict) else None
    return result



# ---------------------------------------------------------------- validation

class SettingsError(ValueError):
    """A refused change. ``code`` is a key of ``messages.API_DETAIL``; ``detail`` is the sentence shown."""

    def __init__(self, code: str, **values: Any):
        self.code = code
        detail = messages.API_DETAIL[code]
        for key, value in values.items():
            detail = detail.replace("{" + key + "}", str(value))
        self.detail = detail
        super().__init__(detail)


class PlatformTenantError(SettingsError):
    """The platform organization has no service desk (Phase 81 D-04)."""

    def __init__(self):
        super().__init__("platform_tenant")


# Letters and digits of any script, then space, hyphen, apostrophe, ampersand, slash and dot.
_WORD_RE = re.compile(r"^[^\W_](?:[^\W_]|[ \-'&/.])*$")
_SPACES = re.compile(r"\s+")
SETTING_KEYS = ("mode", "words")


def validate_word(word: Any) -> str:
    """The word as it is stored (trimmed, inner spaces collapsed, casefolded), or SettingsError."""
    if not isinstance(word, str):
        raise SettingsError("word_shape")
    cleaned = _SPACES.sub(" ", word.strip())
    if not cleaned:
        raise SettingsError("word_empty")
    if not WORD_MIN <= len(cleaned) <= WORD_MAX or _WORD_RE.fullmatch(cleaned) is None:
        raise SettingsError("word_shape")
    return cleaned.casefold()


def validate_changes(body: Dict[str, Any]) -> Dict[str, Any]:
    """The cleaned changes for the keys of ``body`` that are settings (an empty result changes nothing).
    SettingsError: mode_invalid, word_limit (more than 50 words), word_empty, word_shape, word_duplicate."""
    cleaned: Dict[str, Any] = {}
    if body.get("mode") is not None:
        if not isinstance(body["mode"], str) or body["mode"] not in MODES:
            raise SettingsError("mode_invalid")
        cleaned["mode"] = body["mode"]
    if body.get("words") is not None:
        words = body["words"]
        if not isinstance(words, list):
            raise SettingsError("word_shape")
        if len(words) > WORDS_MAX:
            raise SettingsError("word_limit")
        seen: set = set()
        out: List[str] = []
        for word in words:
            stored = validate_word(word)
            if stored in seen:
                raise SettingsError("word_duplicate", word=stored)
            seen.add(stored)
            out.append(stored)
        cleaned["words"] = out
    return cleaned


# ---------------------------------------------------------------- writing

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _actor_name(actor: Any) -> str:
    if isinstance(actor, dict):
        return str(actor.get("username") or actor.get("display") or "system")
    return str(actor or "system")


async def _stored(db, tenant_id: str):
    """(document present, its serviceDesk value) as stored."""
    doc = await raw(db).autonomy_settings.find_one({"tenantId": tenant_id}, {"_id": 0, "serviceDesk": 1})
    return doc is not None and "serviceDesk" in doc, (doc or {}).get("serviceDesk")


def _control_event(key: str) -> str:
    return "service_desk_mode_changed" if key == "mode" else "service_desk_words_changed"


def _control_reason(key: str, value: Any) -> str:
    texts = messages.CONTROL_REASONS
    if key == "mode":
        return texts["service_desk_mode_changed"].format(mode=messages.MODE_LABELS[value])
    if not value:
        return texts["service_desk_words_none"]
    return texts["service_desk_words_changed"].format(count=len(value), words=", ".join(value))


def _actor_dict(actor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return actor if isinstance(actor, dict) else {"username": _actor_name(actor)}


async def save(db, tenant_id: str, changes: Dict[str, Any], *, actor: Optional[Dict[str, Any]],
               scope: str = "tenant") -> DeskSettings:
    """Write ``changes`` (validated here again) and record one control row per value that really changed,
    each naming ``actor``. The platform organization is refused. Post answers is refused while the desk
    breaker is stored, checked again inside the write itself so a trip that lands in between wins. If a
    control row cannot be recorded the old values are put back and the error is raised: a setting never
    changes without a record."""
    if tenant_id == PLATFORM_TENANT_ID:
        raise PlatformTenantError()
    changes = validate_changes(changes)
    await ao_settings.ensure_tenant(db, tenant_id)
    before = await load(db, tenant_id)
    if changes.get("mode") == "post" and before.breaker is not None:
        raise SettingsError("breaker_tripped")
    old = {"mode": before.mode, "words": list(before.words)}
    changed = [k for k in SETTING_KEYS if k in changes and changes[k] != old[k]]
    if not changed and before.readable:
        return before
    present, stored = await _stored(db, tenant_id)
    new = {**old, **{k: changes[k] for k in changed}}
    meta = {"updatedAt": _now(), "updatedBy": _actor_name(actor)}
    flt: Dict[str, Any] = {"tenantId": tenant_id}
    if present and not isinstance(stored, dict):
        fields: Dict[str, Any] = {"serviceDesk": {**new, "breaker": None}}     # repairs a value that was not understood
    elif not before.readable:
        fields = {"serviceDesk.mode": new["mode"], "serviceDesk.words": new["words"]}
    else:
        fields = {f"serviceDesk.{k}": new[k] for k in changed}
    guarded = "mode" in changed and new["mode"] == "post"
    if guarded:
        flt["serviceDesk.breaker"] = None             # still no breaker at the moment of the write
    done = await raw(db).autonomy_settings.update_one(flt, {"$set": {**fields, **meta}})
    if guarded and done.matched_count == 0:
        raise SettingsError("breaker_tripped")
    try:
        for key in changed:
            await ledger.record_control(db, tenant_id, _control_event(key), scope=scope, actor=_actor_dict(actor),
                                        reason=_control_reason(key, new[key]))
    except Exception:
        logger.error("service_desk: settings change for %s not recorded; restoring the old values", tenant_id)
        await raw(db).autonomy_settings.update_one(
            {"tenantId": tenant_id}, {"$set": {"serviceDesk.mode": old["mode"], "serviceDesk.words": old["words"],
                                               **meta}})
        raise
    return await load(db, tenant_id)


async def restore(db, tenant_id: str, *, actor: Optional[Dict[str, Any]], scope: str = "tenant") -> DeskSettings:
    """Clear the desk breaker and set Post answers again (D-25), recording ``service_desk_restored`` naming
    the person. SettingsError ``not_tripped`` when there is no breaker. The one atomic update clears it,
    so two people pressing Restore record one row."""
    if tenant_id == PLATFORM_TENANT_ID:
        raise PlatformTenantError()
    await ao_settings.ensure_tenant(db, tenant_id)
    meta = {"updatedAt": _now(), "updatedBy": _actor_name(actor)}
    before = await raw(db).autonomy_settings.find_one_and_update(
        {"tenantId": tenant_id, "serviceDesk.breaker": {"$type": "object"}},
        {"$set": {"serviceDesk.mode": "post", "serviceDesk.breaker": None, **meta}},
        projection={"_id": 0, "serviceDesk": 1}, return_document=ReturnDocument.BEFORE)
    if before is None:
        raise SettingsError("not_tripped")
    try:
        await ledger.record_control(db, tenant_id, "service_desk_restored", scope=scope, actor=_actor_dict(actor),
                                    reason=messages.CONTROL_REASONS["service_desk_restored"])
    except Exception:
        logger.error("service_desk: restore for %s not recorded; putting the breaker back", tenant_id)
        old = (before or {}).get("serviceDesk") or {}
        await raw(db).autonomy_settings.update_one(
            {"tenantId": tenant_id},
            {"$set": {"serviceDesk.mode": old.get("mode", DEFAULT_MODE), "serviceDesk.breaker": old.get("breaker"),
                      **meta}})
        raise
    return await load(db, tenant_id)
