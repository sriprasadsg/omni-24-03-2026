"""On-call delivery (Phase 82, plan 82-05, HEAL-05): the watchdog is the only sender.

The watchdog alone holds the PagerDuty routing key or webhook URL (``oncall.env``, D-01). It sends:

* its own incidents (``page_incidents``): newly opened incidents of one run become ONE trigger whose dedup
  key is the highest-severity member's key (D-03); every member records that ``pageKey``; the group's
  resolve goes out only when every member sharing the pageKey has cleared. ``sent`` is set only after the
  channel accepted the trigger, so a failure leaves the incident unsent and it is retried on a later run
  as the same group (one incident never produces a second page, PROH-82-08);
* the backend's queued notices (``deliver_outbox``, D-04): each is delivered once; the last 500 ids are
  remembered in ``state["delivered"]`` so a lost acknowledgement never re-pages (Pitfall 16);
* the Super Admin's test alert (``send_test``, D-21): a trigger immediately followed by a resolve with the
  same dedup key and routing key, so no incident stays open on the channel (Pitfall 11).

Rules for every send: the default verified SSL context (``run.real_http``), 429 and 5xx (and a failed
connection) retried at most twice inside the run (1 s, then 3 s), any other 4xx never retried, at most
``MAX_SENDS`` messages per run and no new send after ``SEND_WINDOW`` seconds of the run (the unit stops a
run at 45 s). Messages are fixed English templates per incident kind; no text from the backend is ever
used as a command. The routing key, the webhook URL and the heartbeat URL are never logged, put into an
event, an error, or the sync body.
"""
import hashlib
import json
import logging
import re
import time

from . import DISPLAY
from .services import iso, make_event

logger = logging.getLogger(__name__)

EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"
SOURCE = "omni-watchdog"
SEVERITY_MAP = {"critical": "critical", "warning": "warning", "info": "info"}     # Events v2 also knows "error"; unused
_RANK = {"critical": 3, "warning": 2, "info": 1}

RETRY_WAITS = (1, 3)        # seconds before the first and second retry
SEND_TIMEOUT = 10
HEARTBEAT_TIMEOUT = 5
MAX_SENDS = 10              # messages per run (a retry is not another message)
SEND_WINDOW = 28            # no new send starts later than this many seconds into the run (TimeoutStartSec is 45)
SUMMARY_MAX = 1024          # PagerDuty payload.summary
DEDUP_MAX = 255             # PagerDuty dedup_key
ERROR_MAX = 300
EVENT_TEXT_MAX = 300
DELIVERED_KEEP = 500
MAX_LISTED = 20             # incidents named in a group's details

NO_CHANNEL = "No on-call channel is set up on the server."
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _text(value, limit):
    """One line, control characters removed, capped."""
    return _CONTROL.sub(" ", str(value if value is not None else "")).strip()[:limit]


class Budget:
    """What one run may still send: ``sends`` messages, and no new message once ``clock()`` reaches ``deadline``."""

    def __init__(self, sends=MAX_SENDS, clock=None, deadline=None):
        self.sends, self.clock, self.deadline = sends, clock, deadline

    def timed_out(self):
        return self.deadline is not None and self.clock is not None and self.clock() >= self.deadline

    def can_send(self, count=1):
        return self.sends >= count and not self.timed_out()

    def spend(self, count=1):
        self.sends -= count


def _budget(budget):
    return budget if budget is not None else Budget(sends=10 ** 9)


# --- message shapes ----------------------------------------------------------------------------

def dedup_key(host, key):
    """``omni:<host>:<key>``, at most 255 characters (a long key keeps a hash of the whole so it stays unique)."""
    full = "omni:%s:%s" % (host, key)
    if len(full) <= DEDUP_MAX:
        return full
    return full[:DEDUP_MAX - 17] + ":" + hashlib.sha1(full.encode("utf-8")).hexdigest()[:16]


def pagerduty_event(oncall, action, key, severity, summary, details, host):
    """The Events API v2 body. A resolve carries only the routing key, the action and the same dedup key."""
    event = {"routing_key": oncall.routing_key, "event_action": action, "dedup_key": key[:DEDUP_MAX]}
    if action == "trigger":
        event["payload"] = {"summary": _text(summary, SUMMARY_MAX), "source": _text(host, 255),
                            "severity": SEVERITY_MAP.get(severity, "warning"), "custom_details": details}
    return event


def webhook_message(fmt, action, key, severity, summary, details, host, at):
    """The webhook body: ``json`` {source, host, action, dedupKey, severity, summary, details, at},
    ``slack`` {text}, ``teams`` {text}."""
    if fmt in ("slack", "teams"):
        label = "resolved" if action == "resolve" else SEVERITY_MAP.get(severity, "warning")
        return {"text": _text("[%s] %s (%s)" % (label, summary, host), SUMMARY_MAX)}
    return {"source": SOURCE, "host": host, "action": action, "dedupKey": key, "severity": SEVERITY_MAP.get(severity, "warning"),
            "summary": _text(summary, SUMMARY_MAX), "details": details, "at": at}


def compose(oncall, action, key, severity, summary, details, host, now):
    """The message for the configured channel type (``pagerduty`` or ``webhook``)."""
    if oncall.type == "pagerduty":
        return pagerduty_event(oncall, action, key, severity, summary, details, host)
    return webhook_message(oncall.webhook_format, action, key, severity, summary, details, host, iso(now))


def send(http, oncall, message, *, sleep=time.sleep, budget=None):
    """POST ``message`` to the channel. Returns ``(ok, error)``; ``error`` is one capped line with no URL or key.

    Success is any 2xx. 429, 5xx and a failed connection are retried at most twice (after 1 s, then 3 s);
    any other answer is final. No retry starts once the run's send window is over."""
    if oncall.type == "pagerduty":
        url, who = EVENTS_URL, "PagerDuty"
        if not oncall.routing_key:
            return False, "The PagerDuty routing key is not set on the server."
    elif oncall.type == "webhook":
        url, who = oncall.webhook_url, "The webhook"
        if not url:
            return False, "The webhook URL is not set on the server."
    else:
        return False, NO_CHANNEL
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    error = ""
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            status, _raw = http("POST", url, headers, body, SEND_TIMEOUT)
        except ValueError:
            return False, "%s URL is not an http or https address." % who
        except Exception as exc:                  # a refused or timed-out connection: worth another try
            error = "%s could not be reached (%s)." % (who, type(exc).__name__)
        else:
            if 200 <= status < 300:
                return True, None
            error = "%s answered HTTP %d." % (who, status)
            if status != 429 and status < 500:
                return False, error
        if attempt < len(RETRY_WAITS):
            if budget is not None and budget.timed_out():
                break
            sleep(RETRY_WAITS[attempt])
    return False, _text(error, ERROR_MAX)


# --- incidents ---------------------------------------------------------------------------------

def incident_summary(incident):
    """The fixed English sentence for an incident kind (no text from outside is used)."""
    kind, target = incident.get("kind"), _text(incident.get("target"), 200)
    params = incident.get("params") if isinstance(incident.get("params"), dict) else {}
    if kind == "service_gave_up":
        return "%s is down. The watchdog restarted it %d times in 30 minutes and has stopped trying." % (
            DISPLAY.get(target, target), int(params.get("restarts") or 3))
    if kind == "service_down":
        return "%s is down and automatic restarts are paused." % DISPLAY.get(target, target)
    if kind == "cert_expired":
        return "The certificate %s has expired." % target
    if kind == "cert_expiring":
        days = params.get("daysLeft")
        left = "in less than a day" if not isinstance(days, (int, float)) or days < 1 else "in %d days" % int(days)
        return "The certificate %s expires %s." % (target, left)
    if kind == "cert_unreadable":
        return "The certificate %s can't be read." % target
    if kind == "disk_full":
        used = params.get("usedPct")
        return "Disk %s is %s%% full." % (target, int(used) if isinstance(used, (int, float)) else "very")
    if kind == "disk_forecast":
        days = params.get("forecastDays")
        left = "in less than a day" if not isinstance(days, (int, float)) or days < 1 else "in about %d days" % round(days)
        return "Disk %s is forecast to fill %s." % (target, left)
    return "An incident is open: %s." % _text(incident.get("key"), 200)


def _ordered(members):
    """Highest severity first, then the oldest, then by key: the first member is the group's lead."""
    return sorted(members, key=lambda i: (-_RANK.get(i.get("severity"), 0), i.get("openedAt") or 0, i.get("key") or ""))


def group_summary(members):
    ordered = _ordered(members)
    lead = incident_summary(ordered[0])
    if len(ordered) == 1:
        return _text(lead, SUMMARY_MAX)
    others = "; ".join(incident_summary(i) for i in ordered[1:])
    return _text("%s Also open (%d): %s" % (lead, len(ordered) - 1, others), SUMMARY_MAX)


def _store(state):
    store = state.get("incidents")
    if not isinstance(store, dict):
        store = state["incidents"] = {}
    return store


def _set_last(state, now, ok, error, kind):
    """What the sync body's oncall block reports as the last delivery: {at, ok, error, kind}."""
    state["oncallLast"] = {"at": iso(now), "ok": bool(ok), "error": error if not ok else None, "kind": kind}


def _call_save(save):
    if save is not None:
        save()


def _group_event(kind, severity, members, now, params):
    lead = _ordered(members)[0]
    return make_event(kind, severity, lead.get("target"), now, params)


def page_incidents(state, oncall, http, host, now, *, sleep=time.sleep, budget=None, save=None):
    """Send the triggers and resolves that are due. Returns the events to report (page_sent, page_resolved,
    page_failed). Mutates ``state["incidents"]`` and ``state["oncallLast"]``; ``save()`` is called after the
    pageKey is recorded and before the trigger is sent, and again once ``sent`` is set (Pitfall 15).

    With no channel configured nothing is sent and nothing in the store changes."""
    if oncall.type == "none":
        return []
    budget = _budget(budget)
    store = _store(state)
    events = []

    # An incident that cleared before anyone was told about it is forgotten.
    for key in [k for k, i in store.items() if isinstance(i, dict) and i.get("clearedAt") is not None and not i.get("sent")]:
        del store[key]

    # Resolves first (a ladder move resolves the old key, then triggers the new one).
    groups = {}
    for incident in store.values():
        if isinstance(incident, dict) and incident.get("sent") and incident.get("pageKey"):
            groups.setdefault(incident["pageKey"], []).append(incident)
    for page_key in sorted(groups):
        members = groups[page_key]
        if any(i.get("clearedAt") is None for i in members):
            continue                                # the group resolves when its last member clears
        if not budget.can_send():
            break
        summary = group_summary(members)
        budget.spend()
        ok, error = send(http, oncall, compose(oncall, "resolve", dedup_key(host, page_key), "info", "Resolved: " + summary,
                                               {"host": host}, host, now), sleep=sleep, budget=budget)
        _set_last(state, now, ok, error, "resolve")
        if ok:
            for member in members:
                if store.get(member["key"]) is member:
                    del store[member["key"]]
            events.append(_group_event("page_resolved", "info", members, now,
                                       {"incident": _text(summary, EVENT_TEXT_MAX), "channel": oncall.type}))
        else:
            events.extend(_failed(members, now, oncall, summary, error))
        _call_save(save)

    # Triggers: a group that failed earlier is retried under its own pageKey; the rest form one new group.
    pending = [i for i in store.values() if isinstance(i, dict) and i.get("clearedAt") is None and not i.get("sent")]
    retry, fresh = {}, []
    for incident in pending:
        if incident.get("pageKey"):
            retry.setdefault(incident["pageKey"], []).append(incident)
        else:
            fresh.append(incident)
    todo = [(key, members) for key, members in sorted(retry.items())]
    if fresh:
        new_key = _ordered(fresh)[0]["key"]
        for incident in fresh:
            incident["pageKey"] = new_key
        _call_save(save)                            # the group is on disk before anything is sent
        todo.append((new_key, fresh))
    for page_key, members in todo:
        if not budget.can_send():
            break
        ordered = _ordered(members)
        summary = group_summary(members)
        details = {"host": host, "incidents": [{"key": _text(i.get("key"), 200), "severity": i.get("severity"),
                                                "kind": i.get("kind"), "target": _text(i.get("target"), 200)}
                                               for i in ordered[:MAX_LISTED]]}
        budget.spend()
        ok, error = send(http, oncall, compose(oncall, "trigger", dedup_key(host, page_key), ordered[0].get("severity"),
                                               summary, details, host, now), sleep=sleep, budget=budget)
        _set_last(state, now, ok, error, "page")
        if ok:
            for member in members:
                member["sent"], member["sentAt"] = True, now
                member.pop("failedError", None)
            events.append(_group_event("page_sent", "info", members, now,
                                       {"incident": _text(summary, EVENT_TEXT_MAX), "channel": oncall.type}))
        else:
            events.extend(_failed(members, now, oncall, summary, error))
        _call_save(save)
    return events


def _failed(members, now, oncall, summary, error):
    """One page_failed event per incident group and distinct error, not one per minute of a lasting failure."""
    error = _text(error, ERROR_MAX)
    fresh = any(m.get("failedError") != error for m in members)
    for member in members:
        member["failedError"] = error
    if not fresh:
        return []
    return [_group_event("page_failed", "warning", members, now,
                         {"incident": _text(summary, EVENT_TEXT_MAX), "error": error, "channel": oncall.type})]


# --- the backend's outbox ----------------------------------------------------------------------

def _scalars(value):
    """Scalar values of a dict, strings capped; nothing nested."""
    out = {}
    if isinstance(value, dict):
        for key, item in list(value.items())[:16]:
            if isinstance(item, bool) or isinstance(item, (int, float)):
                out[_text(key, 64)] = item
            elif isinstance(item, str):
                out[_text(key, 64)] = _text(item, 200)
    return out


def _remember(state, oid, error):
    memory = state.get("delivered")
    if not isinstance(memory, list):
        memory = state["delivered"] = []
    errors = state.get("deliveredErrors")
    if not isinstance(errors, dict):
        errors = state["deliveredErrors"] = {}
    if oid not in memory:
        memory.append(oid)
    if error:
        errors[oid] = error
    del memory[:-DELIVERED_KEEP]
    for stale in [k for k in errors if k not in memory]:
        del errors[stale]


def deliver_outbox(state, oncall, http, host, items, now, *, sleep=time.sleep, budget=None, save=None):
    """Deliver each queued message once. Returns ``[{id, ok, error?, at}]`` for ``POST /results``.

    A message whose id is remembered is not sent again; it is only reported again (the backend lost the
    acknowledgement). With no channel nothing is delivered or reported: the backend keeps the messages
    until they expire. Messages beyond the run's budget wait for the next run."""
    if oncall.type == "none" or not isinstance(items, list):
        return []
    budget = _budget(budget)
    memory = state.get("delivered") if isinstance(state.get("delivered"), list) else []
    errors = state.get("deliveredErrors") if isinstance(state.get("deliveredErrors"), dict) else {}
    results = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not _ID.match(item["id"]):
            continue
        oid = item["id"]
        if oid in memory:
            entry = {"id": oid, "ok": oid not in errors, "at": iso(now)}
            if oid in errors:
                entry["error"] = errors[oid]
            results.append(entry)
            continue
        if not budget.can_send():
            break
        action = "resolve" if item.get("kind") == "resolve" else "trigger"
        key = item.get("dedupKey") if isinstance(item.get("dedupKey"), str) and item["dedupKey"].strip() else None
        key = key.strip() if key else "omni:%s:%s" % (host, oid)
        summary = _text(item.get("summary"), SUMMARY_MAX) or "A notice from the Omni-Agent AI platform."
        budget.spend()
        ok, error = send(http, oncall, compose(oncall, action, key, item.get("severity"), summary, _scalars(item.get("details")),
                                               host, now), sleep=sleep, budget=budget)
        entry = {"id": oid, "ok": ok, "at": iso(now)}
        if not ok:
            entry["error"] = _text(error, ERROR_MAX)
        _remember(state, oid, entry.get("error"))
        memory = state["delivered"]
        errors = state["deliveredErrors"]
        _set_last(state, now, ok, error, "outbox")
        _call_save(save)
        results.append(entry)
    return results


# --- the test alert ----------------------------------------------------------------------------

def send_test(oncall, http, host, request, now, *, sleep=time.sleep, budget=None):
    """Handle a testRequest ``{id, requestedAt}``. Returns the testResult ``{id, ok, error?, at}``, or None when
    this run cannot send it (the request stays pending for the next run).

    Sends a trigger (severity info, dedup key ``omni:<host>:test:<id>``) and at once a resolve with the same
    dedup key and routing key, so the test never leaves an incident open. With no channel nothing is sent."""
    if not isinstance(request, dict) or not isinstance(request.get("id"), str) or not _ID.match(request["id"]):
        return None
    result = {"id": request["id"], "ok": False, "at": iso(now)}
    if oncall.type == "none":
        result["error"] = NO_CHANNEL
        return result
    budget = _budget(budget)
    if not budget.can_send(2):
        return None
    budget.spend(2)
    key = "omni:%s:test:%s" % (host, request["id"])
    key = key if len(key) <= DEDUP_MAX else dedup_key(host, "test:" + request["id"])
    summary = "Test alert from the Omni-Agent AI watchdog on %s. It resolves itself at once." % host
    ok, error = send(http, oncall, compose(oncall, "trigger", key, "info", summary, {"host": host, "test": True}, host, now),
                     sleep=sleep, budget=budget)
    if ok:
        ok, error = send(http, oncall, compose(oncall, "resolve", key, "info", "Resolved: " + summary, {"host": host, "test": True},
                                               host, now), sleep=sleep, budget=budget)
        if not ok:
            error = "The test alert arrived but could not be resolved: %s" % error
    result["ok"] = bool(ok)
    if not ok:
        result["error"] = _text(error, ERROR_MAX)
    return result


def test_event(result, oncall, now):
    """The ``test_alert`` event for a test result. Its id is ``test-<request id>``, the id the backend uses for
    the row it writes from the testResult, so the Activity list shows the test once."""
    params = {"requestId": result["id"], "ok": bool(result.get("ok"))}
    if result.get("error"):
        params["error"] = _text(result["error"], ERROR_MAX)
    event = make_event("test_alert", "info" if result.get("ok") else "warning", None, now, params)
    event["id"] = "test-" + result["id"]
    return event


# --- the external heartbeat and the sync body's oncall block -----------------------------------

def ping_heartbeat(http, oncall):
    """One GET to HEARTBEAT_URL (5 s). Returns True/False, or None when none is configured. A failure is only
    logged, without the URL, and never changes the run's outcome."""
    if not oncall.heartbeat_url:
        return None
    try:
        status, _raw = http("GET", oncall.heartbeat_url, {}, None, HEARTBEAT_TIMEOUT)
    except Exception as exc:
        logger.warning("heartbeat ping failed (%s)", type(exc).__name__)
        return False
    if not 200 <= status < 300:
        logger.warning("heartbeat ping answered HTTP %s", status)
        return False
    return True


def oncall_block(oncall, state):
    """The sync body's ``oncall``: {type, heartbeatConfigured, last: {at, ok, error, kind}}; never a key or URL."""
    last = state.get("oncallLast")
    if isinstance(last, dict):
        last = {"at": last.get("at"), "ok": last.get("ok") is True,
                "error": _text(last.get("error"), ERROR_MAX) or None, "kind": last.get("kind")}
    else:
        last = None
    return {"type": oncall.type, "heartbeatConfigured": bool(oncall.heartbeat_url), "last": last}
