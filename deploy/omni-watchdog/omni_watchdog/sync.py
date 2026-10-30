"""The sync client: build the frozen v1 body and post it to the backend.

``POST <backend_url>/api/internal/watchdog/sync`` with ``Authorization: Bearer <token>``. The token
comes from the configured ingest.token file and is never logged. Every sync, successful or not,
is a single attempt per run; failures are handled by the spool (events stay until acknowledged).
"""
import json
import os

from . import CONTRACT_VERSION, SERVICE_ORDER
from .services import iso

SYNC_PATH = "/api/internal/watchdog/sync"
RESULTS_PATH = "/api/internal/watchdog/results"
HTTP_TIMEOUT = 10
MAX_RESPONSE = 256 * 1024
MAX_EVENTS_PER_SYNC = 50


def service_block(service_state):
    """One entry of the body's ``services`` map, in the v1 field names."""
    s = service_state or {}
    return {
        "state": s.get("state") or "healthy",
        "since": iso(s.get("since")),
        "failedChecks": int(s.get("failedChecks") or 0),
        "restartsInWindow": int(s.get("restartsInWindow") or 0),
        "nextRestartAt": iso(s.get("nextRestartAt")),
        "budgetReturnsAt": iso(s.get("budgetReturnsAt")),
        "pagedAt": iso(s.get("pagedAt")),
        "waitingOn": s.get("waitingOn"),
        "detail": s.get("detail") or "",
    }


def build_body(host, services, certs, disks, oncall, stop, events, delivered, *, sent_at):
    """The v1 request body. ``services`` is keyed in SERVICE_ORDER whatever order it arrives in."""
    ordered = {sid: service_block(services.get(sid)) for sid in SERVICE_ORDER}
    return {
        "v": CONTRACT_VERSION,
        "host": host,
        "sentAt": iso(sent_at),
        "services": ordered,
        "certs": list(certs),
        "disks": list(disks),
        "oncall": oncall,
        "stop": stop,
        "events": list(events),
        "delivered": list(delivered),
    }


def _post(http, url, token, body):
    if not token:
        return False, None
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
               "Accept": "application/json"}
    try:
        status, raw = http("POST", url, headers, payload, HTTP_TIMEOUT)
    except Exception:
        return False, None
    if status != 200:
        return False, None
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError:
        return False, None
    return (True, parsed) if isinstance(parsed, dict) else (False, None)


def post_sync(http, base_url, token, body):
    """(ok, response dict or None). ok only for a 200 answer carrying a JSON object."""
    return _post(http, base_url.rstrip("/") + SYNC_PATH, token, body)


def post_results(http, base_url, token, delivered, test_result):
    """(ok, response dict or None) for ``POST /results``: ``delivered`` is ``[{id, ok, error?, at}]`` for outbox
    messages, ``test_result`` is ``{id, ok, error?, at}`` or None. ok only for a 200 answer."""
    body = {"v": CONTRACT_VERSION, "delivered": list(delivered or [])[:MAX_EVENTS_PER_SYNC]}
    if test_result is not None:
        body["testResult"] = test_result
    return _post(http, base_url.rstrip("/") + RESULTS_PATH, token, body)


def resolve_stop(stop_file, last_sync_response, state, now=None):
    """The effective automatic-actions stop and where it came from (D-11): (active, source).

    A STOP file wins (``file``); else the stop returned by a successful sync (``database``), which is
    also cached in ``state["stopCache"]``; else, with the backend unreachable, the cached value
    (``cache``); with nothing at all the stop is off (``none``)."""
    stop = last_sync_response.get("stop") if isinstance(last_sync_response, dict) else None
    from_database = isinstance(stop, dict) and isinstance(stop.get("active"), bool)
    if from_database:
        state["stopCache"] = {"active": stop["active"], "pressedAt": stop.get("pressedAt") if stop["active"] else None,
                              "at": now}
    if stop_file and os.path.exists(stop_file):
        return True, "file"
    if from_database:
        return stop["active"], "database"
    cache = state.get("stopCache")
    if isinstance(cache, dict) and isinstance(cache.get("active"), bool):
        return cache["active"], "cache"
    return False, "none"


def sync_cycle(http, config, token, body, spool, state):
    """Send the oldest spooled events (at most 50) with ``body`` and clear what the backend took.

    ``body`` is the sync body without events. On a 200, every sent id leaves the spool except events
    the response neither accepted nor dropped (the backend could not record them): those stay for a
    re-send, and are abandoned after MAX_TRIES hand-overs. Returns (ok, response or None)."""
    batch = spool.read(MAX_EVENTS_PER_SYNC)
    sent = dict(body)
    sent["events"] = [{k: v for k, v in e.items() if k != "tries"} for e in batch]
    ok, response = post_sync(http, config["backend_url"], token, sent)
    if not ok:
        return False, None
    ids = [e["id"] for e in batch]
    accepted = response.get("acceptedEventIds")
    if not isinstance(accepted, list):
        spool.remove(ids)                       # an answer that does not list ids: everything was handled
        return True, response
    accepted = {i for i in accepted if isinstance(i, str)}
    left = [i for i in ids if i not in accepted]
    dropped = response.get("droppedEvents")
    dropped = dropped if isinstance(dropped, int) and not isinstance(dropped, bool) else 0
    if dropped >= len(left):
        spool.remove(ids)                       # whatever was not accepted was refused for good
    else:
        spool.remove(accepted)
        abandoned = spool.bump_tries(left)
        state["spoolAbandoned"] = int(state.get("spoolAbandoned") or 0) + len(abandoned)
    return True, response
