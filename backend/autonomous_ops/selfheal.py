"""Platform self-healing: the backend side of the watchdog contract (Phase 82, HEAL-05/HEAL-07).

The watchdog (a separate process on the server) reports through one loopback endpoint
(``watchdog_ingest_endpoints``). This module stores what it reports: a heartbeat and the latest
status snapshot in the ``platform_health`` collection (singleton documents with fixed ``_id``
``heartbeat`` and ``snapshot``) and each accepted event as a ``platform_health`` ledger row at
platform scope. The event vocabulary is closed: an unknown kind, a kind only the backend may write,
or a malformed event is dropped and counted, never stored. Event parameters are limited to a fixed
set of keys with scalar values, so no free text beyond a capped error string reaches the screen;
the words themselves come from ``health_messages``.

Raw Mongo handle (``scope.raw``) with explicit ids; the ambient tenant ContextVar is never used.
"""
import asyncio
import logging
import math
import re
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import PLATFORM_TENANT_ID, ledger, settings
from .scope import raw

logger = logging.getLogger(__name__)

# Kinds the watchdog may report.
WATCHDOG_EVENT_KINDS = frozenset({
    "service_down", "service_recovered", "restart", "restart_skipped", "gave_up", "budget_rearmed",
    "unexpected_running", "cert_warning", "disk_warning", "disk_forecast", "page_sent", "page_resolved",
    "page_failed", "test_alert", "state_reset",
})
# Kinds only the backend writes; the watchdog can never send these.
BACKEND_EVENT_KINDS = frozenset({"watchdog_silent", "watchdog_back", "retention_run", "retention_confirmed"})

# The closed set of event parameter keys; anything else is dropped.
PARAM_KEYS = ("target", "rung", "daysLeft", "notAfter", "usedPct", "forecastDays", "attempt", "seconds", "ok",
              "error", "incident", "channel", "requestId", "records", "tenants", "by", "mode", "minutes")

MAX_EVENTS = 50
MAX_TEXT = 300
MAX_HOST = 128
_EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SNAPSHOT_DEPTH = 4

HEARTBEAT_ID = "heartbeat"
SNAPSHOT_ID = "snapshot"

# The watchdog counts as silent after 300 s without a heartbeat, judged only once this backend
# process has run for 180 s, so a backend restart never raises a false alarm (A-82-A10).
SILENT_AFTER = 300
STARTUP_GRACE = 180
PROCESS_STARTED_AT = time.time()

# The dead-man sweep (D-05): one runner at a time under a renewed distributed lock, every 60 s.
LOCK_NAME = "autonomous_ops_selfheal"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
SWEEP_EVERY = 60


def _coll(db):
    return raw(db).platform_health


async def ensure_indexes(db) -> None:
    """Idempotent. The singleton documents use fixed ``_id`` values; the index serves the dead-man check."""
    await _coll(db).create_index("lastSeenAt", name="last_seen")


def clean_text(value: Any, limit: int = MAX_TEXT) -> str:
    """A string capped at ``limit`` characters with control characters removed."""
    return _CONTROL.sub("", str(value))[:limit]


_INT64_MIN = -2 ** 63
_INT64_MAX = 2 ** 63 - 1


def _storable(value: Any) -> bool:
    """True when a Mongo document can hold the number and a JSON response can carry it: a bool, an integer in
    signed 64-bit range, or a finite float. ``math.isfinite`` runs on floats only: on a huge integer it raises."""
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return _INT64_MIN <= value <= _INT64_MAX
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _scrub(value: Any, depth: int = 0) -> Any:
    """Snapshot values: scalars kept (strings capped), nested dicts and lists limited in depth. A number a stored
    row cannot hold (infinity, NaN, an integer outside signed 64-bit) becomes None at any depth."""
    if isinstance(value, str):
        return clean_text(value)
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value if _storable(value) else None
    if depth >= _SNAPSHOT_DEPTH:
        return None
    if isinstance(value, dict):
        return {clean_text(k, 64): _scrub(v, depth + 1) for k, v in list(value.items())[:64]}
    if isinstance(value, (list, tuple)):
        return [_scrub(v, depth + 1) for v in list(value)[:64]]
    return None


def _utc(value: Any) -> Optional[datetime]:
    """A timezone-aware UTC datetime from a datetime (naive means UTC, as MongoDB returns it) or an ISO-8601
    string; None for anything else. Never raises."""
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def clean_params(params: Any, target: Any = None) -> Dict[str, Any]:
    """Keep only the closed key set with scalar values; strings are capped at 300 characters. A number a stored
    row cannot hold (infinity, NaN, an integer outside signed 64-bit) is dropped, so the key is simply absent."""
    out: Dict[str, Any] = {}
    source = dict(params) if isinstance(params, dict) else {}
    if target and "target" not in source:
        source["target"] = target
    for key in PARAM_KEYS:
        value = source.get(key)
        if isinstance(value, (bool, int, float)):
            if _storable(value):
                out[key] = value
        elif isinstance(value, str) and value:
            out[key] = clean_text(value)
    return out


async def record_heartbeat(db, host: str, now: datetime) -> None:
    """``firstSeenAt`` is set once, on the first sync ever; ``lastSeenAt`` on every sync. A heartbeat that ends
    a silence the sweep had raised (``alarmedAt`` set) clears it and writes one ``watchdog_back`` row."""
    update = {"$setOnInsert": {"firstSeenAt": now}, "$set": {"lastSeenAt": now, "host": clean_text(host, MAX_HOST),
                                                              "alarmedAt": None}}
    before = None
    for attempt in (1, 2):
        try:
            before = await _coll(db).find_one_and_update({"_id": HEARTBEAT_ID}, update, upsert=True,
                                                         return_document=ReturnDocument.BEFORE)
            break
        except DuplicateKeyError:           # two first syncs raced to create the singleton; the second now updates
            if attempt == 2:
                raise
    if before and before.get("alarmedAt") is not None:
        try:
            await ledger.record_platform_health(db, "back-" + uuid.uuid4().hex[:16], "watchdog_back", {}, at=now,
                                                host=clean_text(host, MAX_HOST), actor=None)
        except Exception as exc:            # the heartbeat itself is stored; only the Activity row is lost
            logger.error("selfheal: the watchdog-back row was not recorded: %s", type(exc).__name__)


async def store_snapshot(db, body: Dict[str, Any], now: datetime) -> None:
    """Replace the latest status snapshot (services, certificates, disks, on-call channel, stop)."""
    doc = {"_id": SNAPSHOT_ID, "host": clean_text(body.get("host") or "", MAX_HOST), "receivedAt": now,
           "sentAt": clean_text(body.get("sentAt") or "", 64) or None}
    for block in ("services", "certs", "disks", "oncall", "stop"):
        doc[block] = _scrub(body.get(block))
    await _coll(db).replace_one({"_id": SNAPSHOT_ID}, doc, upsert=True)


async def ingest_events(db, events: Iterable[Any], host: str, now: datetime) -> Tuple[List[str], int]:
    """Store each valid watchdog event as a platform-health ledger row.

    Returns ``(accepted ids, dropped count)``. A re-sent event is acknowledged again (its row
    already exists) so the watchdog can clear it from its spool. An event the ledger could not
    record is neither accepted nor dropped: it stays in the watchdog's spool and is sent again.
    Any other failure on one event counts it as dropped and the loop goes on, so one malformed event
    never turns the whole sync into a 503. Only the event id and the exception class are logged,
    because the exception text can carry the event's content."""
    accepted: List[str] = []
    dropped = 0
    for event in events:
        if not isinstance(event, dict):
            dropped += 1
            continue
        event_id, kind = event.get("id"), event.get("kind")
        if (not isinstance(event_id, str) or not _EVENT_ID.match(event_id)
                or kind not in WATCHDOG_EVENT_KINDS):
            dropped += 1
            continue
        try:
            params = clean_params(event.get("params"), event.get("target"))
            await ledger.record_platform_health(db, event_id, kind, params, at=_utc(event.get("at")) or now,
                                                host=clean_text(host, MAX_HOST), actor=None)
        except ledger.LedgerUnavailable as exc:
            logger.error("selfheal: event %s was not recorded: %s", event_id, exc)
            continue
        except Exception as exc:                # asyncio.CancelledError is not an Exception: it propagates
            dropped += 1
            logger.error("selfheal: event %s dropped: %s", event_id, type(exc).__name__)
            continue
        accepted.append(event_id)
    return accepted, dropped


def _epoch(value: Any) -> Optional[float]:
    """Seconds since the epoch from a datetime (naive means UTC) or a number; None for anything else."""
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def watchdog_state(heartbeat: Optional[Dict[str, Any]], now: Any, process_started_at: Any) -> str:
    """``not_installed`` when no heartbeat document exists (D-24), ``silent`` when ``lastSeenAt`` is
    more than ``SILENT_AFTER`` seconds old and this backend process has run for more than
    ``STARTUP_GRACE`` seconds, otherwise ``running``. ``now`` and ``process_started_at`` are
    datetimes or epoch seconds."""
    if not heartbeat:
        return "not_installed"
    last, current, started = _epoch(heartbeat.get("lastSeenAt")), _epoch(now), _epoch(process_started_at)
    if last is None or current is None or started is None:
        return "running"
    if current - last > SILENT_AFTER and current - started > STARTUP_GRACE:
        return "silent"
    return "running"


async def get_heartbeat(db) -> Optional[Dict[str, Any]]:
    """The heartbeat singleton, or None while the watchdog has never reported."""
    return await _coll(db).find_one({"_id": HEARTBEAT_ID})


def _iso(value: Any) -> Optional[str]:
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


async def sync_response(db, accepted: List[str], dropped: int) -> Dict[str, Any]:
    """The frozen sync response. An unreadable platform stop is reported as active (fail closed).
    ``outbox`` lists up to 20 queued on-call messages and ``testRequest`` the pending test alert
    (82-07); neither can fail the sync, so an unreadable queue reads as empty."""
    from . import oncall
    try:
        stop_doc = await settings.platform_stop(db)
        active = settings.stop_active(stop_doc)
        pressed = _iso((stop_doc or {}).get("pressedAt")) if active else None
    except Exception as exc:
        logger.error("selfheal: the platform stop could not be read, reporting it as active: %s", exc)
        active, pressed = True, None
    outbox: List[Dict[str, Any]] = []
    test_request: Optional[Dict[str, Any]] = None
    try:
        outbox = await oncall.pending_outbox(db, datetime.now(timezone.utc))
    except Exception as exc:
        logger.error("selfheal: the on-call outbox could not be read: %s", type(exc).__name__)
    try:
        test_request = await oncall.pending_test(db, datetime.now(timezone.utc))
    except Exception as exc:
        logger.error("selfheal: the test alert request could not be read: %s", type(exc).__name__)
    return {"stop": {"active": active, "scope": "platform" if active else None, "pressedAt": pressed},
            "acceptedEventIds": accepted, "droppedEvents": dropped, "outbox": outbox, "testRequest": test_request}


# ---------------------------------------------------------------- what the Super Admin sees (82-08)

_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_OLDEST = datetime.min.replace(tzinfo=timezone.utc)
_CHANNEL_TYPES = ("none", "pagerduty", "webhook")
_STOP_SOURCES = ("file", "database", "cache", "none")
_CHANNEL_STATUS = {"working": "working", "failing": "not_working", "untested": "not_tested", "none": "not_set_up"}

INSTALL_CHECKLIST_PATH = "deploy/omni-watchdog/INSTALL.md"
CADENCE_SECONDS = 60
# The four services in the order the watchdog restarts them (MongoDB first): id -> (display name, unit).
SERVICE_NAMES = {"mongod": ("MongoDB", "mongod"), "omni-backend": ("Backend", "omni-backend"),
                 "nginx": ("nginx", "nginx"), "ollama": ("Ollama", "ollama")}


def _safe_error(value: Any) -> Optional[str]:
    """A delivery error as text for the screen: capped, control characters removed, any URL replaced."""
    text = clean_text(_URL.sub("[url]", str(value)), MAX_TEXT) if value else ""
    return text or None


def _candidate(when: Any, ok: Any, error: Any) -> Optional[Dict[str, Any]]:
    """One delivery outcome. A time that cannot be read sorts as the oldest; no outcome is no candidate."""
    if not isinstance(ok, bool):
        return None
    parsed = _utc(when)
    return {"when": parsed or _OLDEST, "at": parsed, "ok": ok, "error": None if ok else _safe_error(error)}


async def channel_status(db, snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The on-call channel as ``{channel, error, last}``. ``channel`` is ``none`` when the watchdog reports no
    channel type, otherwise the outcome of the newest of three records: the watchdog's last delivery, the
    latest test result the watchdog reported and the latest acknowledged outbox message. ``failing`` when that
    newest one failed, ``working`` when it succeeded, ``untested`` when there is none. Times arrive as strings
    (snapshot) and as naive or aware datetimes (MongoDB); all are compared as UTC."""
    from . import oncall
    block = (snapshot or {}).get("oncall")
    block = block if isinstance(block, dict) else {}
    if block.get("type") == "none":
        return {"channel": "none", "error": None, "last": None}
    found = []
    last = block.get("last")
    if isinstance(last, dict):
        found.append(_candidate(last.get("at"), last.get("ok"), last.get("error")))
    test = await raw(db).oncall_test_requests.find_one(
        {"state": {"$in": ["delivered", "failed"]}, "sentAt": {"$ne": None}}, sort=[("sentAt", -1)])
    if test:
        found.append(_candidate(test.get("sentAt"), test.get("state") == "delivered", test.get("error")))
    sent = await raw(db).oncall_outbox.find_one({"deliveredAt": {"$ne": None}}, sort=[("deliveredAt", -1)])
    if sent:
        found.append(_candidate(sent.get("deliveredAt"), sent.get("ok"), sent.get("error")))
    newest = max((c for c in found if c), key=lambda c: c["when"], default=None)
    if newest is None:
        return {"channel": "untested", "error": None, "last": None}
    return {"channel": "working" if newest["ok"] else "failing", "error": newest["error"],
            "last": {"at": newest["at"].isoformat() if newest["at"] else None, "ok": newest["ok"],
                     "error": newest["error"]}}


async def health_summary(db, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The compact summary on the platform status payload: ``{watchdog, lastSeenAt, channel, channelError}``.
    ``channel`` is None while the watchdog is not installed (D-24)."""
    now = now or datetime.now(timezone.utc)
    heartbeat = await get_heartbeat(db)
    state = watchdog_state(heartbeat, now, PROCESS_STARTED_AT)
    seen = _utc((heartbeat or {}).get("lastSeenAt"))
    channel = None
    if state != "not_installed":
        channel = await channel_status(db, await _coll(db).find_one({"_id": SNAPSHOT_ID}))
    return {"watchdog": state, "lastSeenAt": seen.isoformat() if seen else None,
            "channel": channel["channel"] if channel else None,
            "channelError": channel["error"] if channel and channel["channel"] == "failing" else None}


def _num(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value else None


def _str(value: Any, limit: int = MAX_TEXT) -> Optional[str]:
    return clean_text(value, limit) if isinstance(value, str) else None


def _stamp(value: Any) -> Optional[str]:
    parsed = _utc(value) if value is not None else None
    return parsed.isoformat() if parsed else None


def _items(value: Any) -> List[Dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _service(sid: str, entry: Any, stale: bool) -> Dict[str, Any]:
    e = entry if isinstance(entry, dict) else {}
    state = _str(e.get("state"), 32)
    name, unit = SERVICE_NAMES[sid]
    return {"id": sid, "name": name, "unit": unit, "state": state, "since": _str(e.get("since"), 64),
            "failedChecks": _num(e.get("failedChecks")), "restartsInWindow": _num(e.get("restartsInWindow")),
            "nextRestartAt": _str(e.get("nextRestartAt"), 64), "budgetReturnsAt": _str(e.get("budgetReturnsAt"), 64),
            "pagedAt": _str(e.get("pagedAt"), 64), "waitingOn": _str(e.get("waitingOn"), 32),
            "detail": _str(e.get("detail")), "stale": stale or state is None}


def _cert(entry: Dict[str, Any], stale: bool) -> Dict[str, Any]:
    return {"path": _str(entry.get("path")), "notAfter": _str(entry.get("notAfter"), 64), "daysLeft": _num(entry.get("daysLeft")),
            "rung": _num(entry.get("rung")), "pinned": entry.get("pinned") is True, "error": _str(entry.get("error"), 64),
            "stale": stale}


def _disk(entry: Dict[str, Any], stale: bool) -> Dict[str, Any]:
    forecast = entry.get("forecast")
    forecast = forecast if isinstance(forecast, dict) else {}
    paths = entry.get("paths")
    return {"mount": _str(entry.get("mount")), "paths": [_str(p) for p in paths if isinstance(p, str)] if isinstance(paths, list) else [],
            "usedPct": _num(entry.get("usedPct")), "freeBytes": _num(entry.get("freeBytes")),
            "totalBytes": _num(entry.get("totalBytes")), "rung": _num(entry.get("rung")),
            "forecast": {"state": _str(forecast.get("state"), 32), "days": _num(forecast.get("days")),
                         "rung": _num(forecast.get("rung"))}, "stale": stale}


async def health_document(db, now: Optional[datetime] = None) -> Dict[str, Any]:
    """GET /health (D-20, D-24). Everything below comes from the watchdog's latest snapshot, copied field by
    field: the backend reads no certificate and measures no disk. While the watchdog is silent, or before it
    ever reported, each entry carries ``stale`` true and its last known values (or null)."""
    from . import oncall
    now = now or datetime.now(timezone.utc)
    heartbeat = await get_heartbeat(db)
    state = watchdog_state(heartbeat, now, PROCESS_STARTED_AT)
    snap = await _coll(db).find_one({"_id": SNAPSHOT_ID}) or {}
    stale = state != "running"
    blocks = snap.get("services") if isinstance(snap.get("services"), dict) else {}
    certs = [_cert(c, stale) for c in _items(snap.get("certs"))]
    certs.sort(key=lambda c: (c["daysLeft"] is not None, c["daysLeft"] or 0, c["path"] or ""))    # unreadable first
    block = snap.get("oncall") if isinstance(snap.get("oncall"), dict) else {}
    channel = await channel_status(db, snap) if snap else {"channel": "none", "error": None, "last": None}
    stop = snap.get("stop") if isinstance(snap.get("stop"), dict) else {}
    return {
        "updatedAt": _stamp(snap.get("receivedAt")), "host": _str((heartbeat or {}).get("host"), MAX_HOST),
        "watchdog": {"state": state, "lastSeenAt": _stamp((heartbeat or {}).get("lastSeenAt")),
                     "firstSeenAt": _stamp((heartbeat or {}).get("firstSeenAt")), "cadenceSeconds": CADENCE_SECONDS,
                     "silentAfterSeconds": SILENT_AFTER},
        "installChecklist": {"path": INSTALL_CHECKLIST_PATH, "url": None},
        "stop": {"effective": stop.get("effective") is True,
                 "source": stop.get("source") if stop.get("source") in _STOP_SOURCES else "none"},
        "services": [_service(sid, blocks.get(sid), stale) for sid in SERVICE_NAMES],
        "certs": certs, "disks": [_disk(d, stale) for d in _items(snap.get("disks"))],
        "oncall": {"type": block.get("type") if block.get("type") in _CHANNEL_TYPES else None,
                   "heartbeatConfigured": block.get("heartbeatConfigured") is True,
                   "status": _CHANNEL_STATUS[channel["channel"]], "last": channel["last"]},
        "testAlert": await oncall.test_view(db),
    }


# ---------------------------------------------------------------- dead-man switch (D-05, D-24)

async def silence_sweep(db, now: datetime) -> Dict[str, Any]:
    """Find the watchdog silent and raise the in-app alarm once per silence episode. Armed only after the first
    heartbeat ever (``not_installed`` never alarms) and after the startup grace (``watchdog_state``). The claim
    is a compare-and-set on ``alarmedAt`` for this very ``lastSeenAt``, so a heartbeat arriving meanwhile or a
    second runner changes nothing. The alarm is a platform-health row plus one in-app notification and nothing
    else: it is never queued for on-call, because a silent watchdog could not send it."""
    from pending_agents import post_to_recipients
    heartbeat = await get_heartbeat(db)
    state = watchdog_state(heartbeat, now, PROCESS_STARTED_AT)
    result = {"state": state, "alarmed": False}
    if state != "silent" or heartbeat.get("alarmedAt") is not None:
        return result
    claimed_at = now.replace(microsecond=now.microsecond // 1000 * 1000)       # MongoDB keeps milliseconds
    last = _utc(heartbeat.get("lastSeenAt")) or claimed_at
    claim = await _coll(db).update_one({"_id": HEARTBEAT_ID, "lastSeenAt": heartbeat["lastSeenAt"], "alarmedAt": None},
                                       {"$set": {"alarmedAt": claimed_at}})
    if claim.modified_count != 1:
        return result
    try:
        await ledger.record_platform_health(db, f"silent-{int(last.timestamp() * 1000)}", "watchdog_silent",
                                            {"minutes": int((claimed_at - last).total_seconds() // 60)}, at=now,
                                            host=clean_text(heartbeat.get("host") or "", MAX_HOST) or None, actor=None)
        await post_to_recipients(
            raw(db), {"id": PLATFORM_TENANT_ID}, "The watchdog has gone silent",
            f"Last seen {last:%H:%M} UTC. Services are not being checked or restarted, and no on-call pages can be "
            "sent, until it reports again.", "critical", {"source": "autonomous_ops", "event": "watchdog_silent"})
    except Exception as exc:                # give the episode back so the next sweep tries again
        logger.error("selfheal: the watchdog-silent alarm could not be raised: %s", type(exc).__name__)
        await _coll(db).update_one({"_id": HEARTBEAT_ID, "alarmedAt": claimed_at}, {"$set": {"alarmedAt": None}})
        return result
    result["alarmed"] = True
    return result


async def run_sweep_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """One sweep under the single-runner lock; None when another runner holds it."""
    import distributed_lock
    lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        return await silence_sweep(db, now or datetime.now(timezone.utc))


async def selfheal_loop() -> None:
    """Sweep every SWEEP_EVERY seconds. A failed pass is logged and the loop carries on."""
    from database import get_database
    while True:
        try:
            await run_sweep_once(get_database())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("selfheal: sweep failed: %s", type(exc).__name__)
        await asyncio.sleep(SWEEP_EVERY)
