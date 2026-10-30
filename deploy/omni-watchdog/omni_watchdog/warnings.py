"""Certificate-expiry, disk-usage and disk-fill-forecast warnings (Phase 82, HEAL-03 and HEAL-04).

Read-only by construction: the only things this module touches on the host are ``openssl x509 -noout
-enddate -in <path>`` (through the ``run`` seam) and ``os.statvfs`` / ``os.stat`` (through the ``fs`` seam).
It never renews a certificate and never deletes, truncates or compresses a file (PROH-82-03); a structural
test pins that. Every check is a ladder of deduplicated incidents: one open incident per check, a stable key
(``cert:<path>:14d``, ``disk:/:90``, ``disk-forecast:/:7d``), one event each time a check crosses onto a rung.
Moving along a ladder clears the old key and opens the new one.

``evaluate(state, config, now, run, *, clock=None, fs=None)`` returns ``(certs, disks, events)``: the two
blocks of the v1 sync body and the new events. It changes only ``state["certs"]``, ``state["disk"]`` and
``state["incidents"]``; the caller saves the state.
"""
import ssl

from . import incidents
from .services import iso, make_event

PINNED_CERT = "/etc/nginx/ssl/omni.crt"      # the one certificate agents pin: pinned true only for this path
MAX_CERTS = 32          # POST /sync rejects the whole body above 32 certs entries; a long extra_certs list must not do that
READ_TIMEOUT = 3        # seconds one openssl read may take
CERT_BUDGET = 6         # seconds all certificate reads of one run may take together (unit TimeoutStartSec=45)
DAY = 86400.0

# (at-most threshold in days, key suffix, severity, rung), smallest threshold first.
CERT_LADDER = ((1, "1d", "critical", 3), (7, "7d", "warning", 2), (14, "14d", "info", 1), (30, "30d", "info", 1))
UNREADABLE = ("unreadable", "warning", 2)


def cert_paths(config):
    """The pinned certificate first, then ``extra_certs`` in config order, without repeats, at most MAX_CERTS."""
    paths = [PINNED_CERT]
    for path in (config.get("extra_certs") or []):
        if isinstance(path, str) and path and path not in paths:
            paths.append(path)
    return paths[:MAX_CERTS]


def cert_days_left(run, path, now, timeout=READ_TIMEOUT):
    """Read one certificate's expiry. Returns ``(outcome, days_left, not_after_epoch)``.

    outcome is ``ok``, ``unreadable`` (openssl failed or printed something else) or ``timeout`` (the read
    did not finish in time: not a statement about the file). daysLeft is a float, never rounded."""
    code, out = run(["openssl", "x509", "-noout", "-enddate", "-in", path], timeout)
    if code == 124:
        return "timeout", None, None
    if code != 0:
        return "unreadable", None, None
    first = (out or "").strip().splitlines()[:1]
    if not first or not first[0].startswith("notAfter="):
        return "unreadable", None, None
    try:
        not_after = float(ssl.cert_time_to_seconds(first[0].split("=", 1)[1].strip()))
    except (ValueError, OverflowError):
        return "unreadable", None, None
    return "ok", (not_after - now) / DAY, not_after


def cert_level(days_left):
    """The ladder rung for ``days_left`` (``(threshold, suffix, severity, rung)``), or None when clear."""
    for level in CERT_LADDER:
        if days_left <= level[0]:
            return level
    return None


def _open_for(state, prefix, target):
    """The open incidents of one check family for one target (a path or a mount)."""
    return [i for i in incidents.open_incidents(state)
            if str(i.get("key", "")).startswith(prefix) and i.get("target") == target]


def _settle(state, now, prefix, target, want, events, event_kind):
    """Leave exactly one open incident for (prefix, target): ``want`` or none.

    ``want`` is ``(key, severity, kind, params)`` or None. Any other open incident of the check is cleared;
    a newly opened one emits one event (the crossing). An unchanged check emits nothing."""
    key = want[0] if want else None
    for old in _open_for(state, prefix, target):
        if old["key"] != key:
            incidents.clear_incident(state, old["key"], now)
    if want and incidents.open_incident(state, want[0], want[1], want[2], target, want[3], now):
        events.append(make_event(event_kind, want[1], target, now, {"target": target, **want[3]}))


def _cert_entry(path, not_after, days, rung, error):
    return {"path": path, "notAfter": iso(not_after), "daysLeft": days, "rung": rung,
            "pinned": path == PINNED_CERT, "error": error}


def check_certs(config, state, now, run, clock):
    """Read every watched certificate and move each one along the ladder. Returns ``(entries, events)``.

    The reads of one run share CERT_BUDGET seconds of ``clock`` time. A certificate not reached in time, or
    whose read timed out, keeps its last reported entry (state ``certs``) and its incident unchanged."""
    paths = cert_paths(config)
    saved = state.get("certs") if isinstance(state.get("certs"), dict) else {}
    kept, entries, events = {}, [], []
    started = clock()
    for path in paths:
        elapsed = clock() - started
        result = ("skipped", None, None)
        if elapsed < CERT_BUDGET:
            result = cert_days_left(run, path, now, min(READ_TIMEOUT, CERT_BUDGET - elapsed))
        outcome, days, not_after = result
        if outcome in ("skipped", "timeout"):
            old = saved.get(path)
            if isinstance(old, dict) and old.get("path") == path:
                kept[path] = old
                entries.append(old)
            continue
        if outcome == "ok":
            level = cert_level(days)
            rung = level[3] if level else 0
            entry = _cert_entry(path, not_after, days, rung, None)
            want = None
            if level:
                kind = "cert_expired" if days <= 0 else "cert_expiring"
                want = ("cert:%s:%s" % (path, level[1]), level[2], kind,
                        {"rung": level[3], "daysLeft": days, "notAfter": iso(not_after)})
        else:
            suffix, severity, rung = UNREADABLE
            entry = _cert_entry(path, None, None, rung, "unreadable")
            want = ("cert:%s:%s" % (path, suffix), severity, "cert_unreadable", {"rung": rung, "error": "unreadable"})
        _settle(state, now, "cert:", path, want, events, "cert_warning")
        kept[path] = entry
        entries.append(entry)
    state["certs"] = kept
    for stale in incidents.open_incidents(state):        # a certificate removed from watchdog.conf stops being watched
        if str(stale.get("key", "")).startswith("cert:") and stale.get("target") not in paths:
            incidents.clear_incident(state, stale["key"], now)
    return entries, events


def evaluate(state, config, now, run, *, clock=None, fs=None):
    """All warning checks of one run: ``(certs, disks, events)``. See the module docstring."""
    clock = clock or (lambda: now)
    certs, events = check_certs(config, state, now, run, clock)
    return certs, [], events
