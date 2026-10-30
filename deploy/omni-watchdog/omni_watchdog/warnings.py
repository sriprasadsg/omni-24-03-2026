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
import os
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

# Disk fullness: percent used, highest threshold first. An open disk incident clears only when the usage falls
# HYSTERESIS_POINTS below its threshold, so a disk hovering at a threshold does not flap.
MAX_DISKS = 32          # same backend limit as certs
DISK_LADDER = ((95, "95", "critical", 3), (90, "90", "warning", 2), (80, "80", "info", 1))
HYSTERESIS_POINTS = 2.0

# Fill forecast: days until full, smallest threshold first. A forecast incident clears when days_to_full rises
# FORECAST_CLEAR_FACTOR times above its threshold, or when growth stops.
FORECAST_LADDER = ((1, "1d", "critical", 3), (7, "7d", "warning", 2), (14, "14d", "info", 1))
FORECAST_CLEAR_FACTOR = 1.2
SAMPLE_EVERY = 3600     # one disk sample per filesystem per hour ...
SAMPLE_KEEP = 8 * DAY   # ... kept for 8 days
FORECAST_SPAN = 7 * DAY  # the slope needs this much history
CLOCK_STEP = 300        # a sample this much older than the previous one means the clock was stepped back


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


# --- disks -------------------------------------------------------------------------------------

class RealFs:
    """The fs seam on the real machine; tests pass an object with the same two methods."""

    @staticmethod
    def statvfs(path):
        return os.statvfs(path)

    @staticmethod
    def stat(path):
        return os.stat(path)


def disk_usage(fs, path):
    """``df`` semantics: used = blocks - free blocks, percent = used / (used + available to users).

    Returns ``dev, used, avail, total`` (bytes) and ``pct`` (a float, never rounded), or None when the
    path cannot be read."""
    try:
        vfs, dev = fs.statvfs(path), fs.stat(path).st_dev
        size = vfs.f_frsize
        used, avail, total = (vfs.f_blocks - vfs.f_bfree) * size, vfs.f_bavail * size, vfs.f_blocks * size
    except (OSError, AttributeError, TypeError):
        return None
    denominator = used + avail
    return {"dev": dev, "used": used, "avail": avail, "total": total,
            "pct": 100.0 * used / denominator if denominator > 0 else 0.0}


def record_sample(samples, now, used, avail):
    """Keep one ``[epoch, used, avail]`` sample per SAMPLE_EVERY for SAMPLE_KEEP. True when one was added.

    A sample more than CLOCK_STEP older than the previous one (the clock was stepped back) is discarded."""
    cutoff = now - SAMPLE_KEEP
    samples[:] = [s for s in samples if isinstance(s, (list, tuple)) and len(s) == 3 and s[0] >= cutoff]
    if samples:
        last = samples[-1][0]
        if now < last - CLOCK_STEP or now - last < SAMPLE_EVERY:
            return False
    samples.append([now, used, avail])
    return True


def _slope(points):
    """Least-squares growth in bytes per second over (epoch, bytes) points, in floats."""
    n = float(len(points))
    mean_t = sum(t for t, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    var = sum((t - mean_t) ** 2 for t, _ in points)
    return sum((t - mean_t) * (y - mean_y) for t, y in points) / var if var > 0 else 0.0


def forecast_rung(days):
    """The forecast ladder rung for ``days`` until full (0 when clear)."""
    for threshold, _suffix, _severity, rung in FORECAST_LADDER:
        if days <= threshold:
            return rung
    return 0


def forecast(samples, avail, now):
    """``{state, days, rung}`` from the hourly samples.

    state is ``insufficient`` until the retained samples span FORECAST_SPAN (exactly 7 days counts), ``flat``
    when usage is not growing (no forecast), else ``ok`` with ``days`` = avail / slope. The slope is the
    least-squares fit over the newest FORECAST_SPAN of samples; samples dated after ``now`` are ignored."""
    points = sorted((float(s[0]), float(s[1])) for s in samples if now - SAMPLE_KEEP <= s[0] <= now)
    if len(points) < 2 or points[-1][0] - points[0][0] < FORECAST_SPAN:
        return {"state": "insufficient", "days": None, "rung": 0}
    window = [p for p in points if p[0] >= points[-1][0] - FORECAST_SPAN]
    slope = _slope(window) if len(window) >= 2 else 0.0
    if slope <= 0:
        return {"state": "flat", "days": None, "rung": 0}
    days = avail / slope / DAY
    return {"state": "ok", "days": days, "rung": forecast_rung(days)}


def _held(state, prefix, target, ladder):
    """The ladder entry of the open incident for (prefix, target), or None."""
    for incident in _open_for(state, prefix, target):
        suffix = incident["key"].rsplit(":", 1)[-1]
        for level in ladder:
            if level[1] == suffix:
                return level
    return None


def disk_level(pct, held):
    """The disk rung for ``pct`` (``(threshold, suffix, severity, rung)`` or None), keeping ``held`` while
    the usage is still within HYSTERESIS_POINTS of its threshold."""
    raw = next((level for level in DISK_LADDER if pct >= level[0]), None)
    if held and pct >= held[0] - HYSTERESIS_POINTS and (raw is None or held[0] > raw[0]):
        return held
    return raw


def forecast_level(fc, held):
    """The forecast rung for a ``forecast`` result, keeping ``held`` while days_to_full is within
    FORECAST_CLEAR_FACTOR of its threshold. Not enough history leaves the open incident as it is."""
    if fc["state"] == "insufficient":
        return held
    if fc["state"] == "flat":
        return None
    days = fc["days"]
    raw = next((level for level in FORECAST_LADDER if days <= level[0]), None)
    if held and days <= held[0] * FORECAST_CLEAR_FACTOR and (raw is None or held[0] < raw[0]):
        return held
    return raw


def _groups(config, fs):
    """Readable disk paths grouped by filesystem (st_dev), first path of each group is its mount name."""
    order, found = [], {}
    for path in (config.get("disk_paths") or []):
        usage = disk_usage(fs, path) if isinstance(path, str) and path else None
        if usage is None:
            continue
        if usage["dev"] not in found:
            order.append(usage["dev"])
            found[usage["dev"]] = {"mount": path, "paths": [], "usage": usage}
        if path not in found[usage["dev"]]["paths"]:
            found[usage["dev"]]["paths"].append(path)
    return [found[dev] for dev in order][:MAX_DISKS]


def check_disks(config, state, now, fs):
    """One entry per filesystem: fullness ladder with hysteresis, hourly sample and 7-day forecast.

    Returns ``(entries, events)``. Entry: ``{mount, paths, usedPct, freeBytes, totalBytes, rung,
    forecast: {state, days, rung}}``."""
    disk_state = state.get("disk") if isinstance(state.get("disk"), dict) else {}
    kept, entries, events = {}, [], []
    for group in _groups(config, fs):
        mount, usage = group["mount"], group["usage"]
        samples = disk_state.get(mount) if isinstance(disk_state.get(mount), list) else []
        record_sample(samples, now, usage["used"], usage["avail"])
        kept[mount] = samples

        level = disk_level(usage["pct"], _held(state, "disk:", mount, DISK_LADDER))
        want = None
        if level:
            want = ("disk:%s:%s" % (mount, level[1]), level[2], "disk_full", {"rung": level[3], "usedPct": usage["pct"]})
        _settle(state, now, "disk:", mount, want, events, "disk_warning")

        fc = forecast(samples, usage["avail"], now)
        flevel = forecast_level(fc, _held(state, "disk-forecast:", mount, FORECAST_LADDER))
        want = None
        if flevel:
            want = ("disk-forecast:%s:%s" % (mount, flevel[1]), flevel[2], "disk_forecast",
                    {"rung": flevel[3], "forecastDays": fc["days"]})
        _settle(state, now, "disk-forecast:", mount, want, events, "disk_forecast")

        entries.append({"mount": mount, "paths": group["paths"], "usedPct": usage["pct"],
                        "freeBytes": usage["avail"], "totalBytes": usage["total"], "rung": level[3] if level else 0,
                        "forecast": {"state": fc["state"], "days": fc["days"], "rung": flevel[3] if flevel else 0}})
    state["disk"] = kept
    configured = set(config.get("disk_paths") or [])
    for stale in incidents.open_incidents(state):       # a path removed from watchdog.conf stops being watched
        if str(stale.get("key", "")).startswith(("disk:", "disk-forecast:")) and stale.get("target") not in configured:
            incidents.clear_incident(state, stale["key"], now)
    return entries, events


def evaluate(state, config, now, run, *, clock=None, fs=None):
    """All warning checks of one run: ``(certs, disks, events)``. See the module docstring."""
    clock = clock or (lambda: now)
    certs, events = check_certs(config, state, now, run, clock)
    disks, disk_events = check_disks(config, state, now, fs or RealFs())
    return certs, disks, events + disk_events
