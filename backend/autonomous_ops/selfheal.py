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
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from . import ledger, settings
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


def _coll(db):
    return raw(db).platform_health


async def ensure_indexes(db) -> None:
    """Idempotent. The singleton documents use fixed ``_id`` values; the index serves the dead-man check."""
    await _coll(db).create_index("lastSeenAt", name="last_seen")


def clean_text(value: Any, limit: int = MAX_TEXT) -> str:
    """A string capped at ``limit`` characters with control characters removed."""
    return _CONTROL.sub("", str(value))[:limit]


def _scrub(value: Any, depth: int = 0) -> Any:
    """Snapshot values: scalars kept (strings capped), nested dicts and lists limited in depth."""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if depth >= _SNAPSHOT_DEPTH:
        return None
    if isinstance(value, dict):
        return {clean_text(k, 64): _scrub(v, depth + 1) for k, v in list(value.items())[:64]}
    if isinstance(value, (list, tuple)):
        return [_scrub(v, depth + 1) for v in list(value)[:64]]
    return None


def _utc(value: Any) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def clean_params(params: Any, target: Any = None) -> Dict[str, Any]:
    """Keep only the closed key set with scalar values; strings are capped at 300 characters."""
    out: Dict[str, Any] = {}
    source = dict(params) if isinstance(params, dict) else {}
    if target and "target" not in source:
        source["target"] = target
    for key in PARAM_KEYS:
        value = source.get(key)
        if isinstance(value, bool) or (isinstance(value, (int, float)) and value == value):
            out[key] = value
        elif isinstance(value, str) and value:
            out[key] = clean_text(value)
    return out


async def record_heartbeat(db, host: str, now: datetime) -> None:
    """``firstSeenAt`` is set once, on the first sync ever; ``lastSeenAt`` on every sync."""
    update = {"$setOnInsert": {"firstSeenAt": now}, "$set": {"lastSeenAt": now, "host": clean_text(host, MAX_HOST)}}
    for attempt in (1, 2):
        try:
            await _coll(db).update_one({"_id": HEARTBEAT_ID}, update, upsert=True)
            return
        except DuplicateKeyError:           # two first syncs raced to create the singleton; the second now updates
            if attempt == 2:
                raise


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
    record is neither accepted nor dropped: it stays in the watchdog's spool and is sent again."""
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
        params = clean_params(event.get("params"), event.get("target"))
        try:
            await ledger.record_platform_health(db, event_id, kind, params, at=_utc(event.get("at")) or now,
                                                host=clean_text(host, MAX_HOST), actor=None)
        except ledger.LedgerUnavailable as exc:
            logger.error("selfheal: event %s was not recorded: %s", event_id, exc)
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
