"""The sync client: build the frozen v1 body and post it to the backend.

``POST <backend_url>/api/internal/watchdog/sync`` with ``Authorization: Bearer <token>``. The token
comes from the configured ingest.token file and is never logged. Every sync, successful or not,
is a single attempt per run; failures are handled by the spool (events stay until acknowledged).
"""
import json

from . import CONTRACT_VERSION, SERVICE_ORDER
from .services import iso

SYNC_PATH = "/api/internal/watchdog/sync"
RESULTS_PATH = "/api/internal/watchdog/results"
HTTP_TIMEOUT = 10
MAX_RESPONSE = 256 * 1024


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


def post_results(http, base_url, token, body):
    """(ok, response dict or None) for ``POST /results`` (delivered outbox ids, test result)."""
    return _post(http, base_url.rstrip("/") + RESULTS_PATH, token, body)
