"""The restart decision (Phase 82, HEAL-01 / HEAL-02).

``decide`` runs after ``services.observe`` has debounced the checks and before the sync. For every
service that is counted down it either waits, restarts the unit, or gives up. Standard library only;
every host effect goes through the injected seams (``run``, ``clock``, ``sleep``, ``recheck``).

Restart timeline (D-07, read as in 82-RESEARCH assumption A1): restart 1 when the service is first
counted down, restart 2 one minute later, restart 3 two minutes after that, and four minutes after
restart 3 the service is declared ``gave_up``. These are the waits in ``WAITS``; at most ``BUDGET``
restarts of one service fit in any ``WINDOW`` seconds.

Commands issued, and nothing else (the 82-06 polkit rule allows exactly these verbs on these units):
    systemctl is-active <unit>                  # read-only, to learn whether the unit is ``failed``
    systemctl reset-failed <unit>               # only when is-active said ``failed``
    systemctl restart --no-block <unit>
The unit always comes from ``UNITS``; Ollama only where the operator said it is expected.
"""
import re

from . import SERVICE_ORDER, UNITS
from .services import make_event

WAITS = (60, 120, 240)      # seconds after restart 1, 2, 3 before the next action
BUDGET = 3                  # restarts per service inside WINDOW
WINDOW = 1800               # 30 minutes
REARM_AFTER = 3600          # healthy for this long gives the budget back (D-08)
POLL_EVERY = 2              # seconds between health polls after a restart
POLL_FOR = 20               # give up polling after this long
SLACK = 5                   # a run up to this early still counts as "the wait is over" (timer jitter)
ERROR_CAP = 300
RESTART_TIMEOUT = 15
NOT_HEALTHY = "Not healthy %d s after the restart." % POLL_FOR

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def clean_error(text):
    """Error text on one line, capped at ERROR_CAP characters."""
    return _CONTROL.sub(" ", str(text or "")).strip()[:ERROR_CAP]


def managed_ids(config):
    """Service ids the watchdog may restart: Ollama only where it is expected (PROH-82-01)."""
    return [sid for sid in SERVICE_ORDER if sid != "ollama" or bool((config or {}).get("ollama_expected"))]


def restart_unit(run, unit):
    """Restart ``unit`` without waiting for it. Returns (ok, error text).

    A unit whose ``is-active`` answer is ``failed`` is reset first. ``ok`` only says systemd accepted
    the request; the caller polls the service's own health check afterwards."""
    if unit not in UNITS.values():
        raise ValueError("unit is not in the restart list")
    try:
        _rc, word = run(["systemctl", "is-active", unit], 5)
    except Exception:
        word = ""
    if (word or "").strip() == "failed":
        try:
            run(["systemctl", "reset-failed", unit], RESTART_TIMEOUT)
        except Exception:
            pass                       # the restart below reports the real problem
    try:
        rc, out = run(["systemctl", "restart", "--no-block", unit], RESTART_TIMEOUT)
    except Exception as exc:
        return False, clean_error(type(exc).__name__)
    if rc == 0:
        return True, ""
    return False, clean_error(out) or ("systemctl exited %d" % rc)


def poll_healthy(check, clock, sleep):
    """Poll ``check()`` every POLL_EVERY seconds for up to POLL_FOR seconds.

    Returns (healthy, seconds taken). The loop is also bounded by its iteration count, so a clock
    that does not move can never make it spin."""
    start = clock()
    for _ in range(POLL_FOR // POLL_EVERY):
        sleep(POLL_EVERY)
        if check():
            return True, int(round(max(0.0, clock() - start)))
        if clock() - start >= POLL_FOR:
            break
    return False, None


def decide(state, health, stop, now, config, *, run, clock, sleep, recheck, persist=None):
    """Judge every restartable service once. Returns the new events; mutates ``state["services"]``.

    ``state``   the watchdog state dict (``services`` already updated by services.observe)
    ``health``  {service id: (ok, detail)} from this run's checks
    ``stop``    {"effective": bool, "source": str}
    ``now``     epoch seconds of this run (all timestamps in state use it)
    ``clock``   the now() seam, read while polling after a restart
    ``recheck`` recheck(service id) -> (ok, detail), the service's own check
    ``persist`` called right after a restart is recorded and before polling, so a run killed while
                polling cannot forget the restart and repeat it
    """
    events = []
    for sid in managed_ids(config):
        svc = state["services"].get(sid)
        if svc is None or sid not in health:
            continue
        events.extend(_step(state, sid, svc, bool(health[sid][0]), now, run, clock, sleep, recheck, persist))
    return events


def _step(state, sid, svc, ok, now, run, clock, sleep, recheck, persist):
    events = []
    svc["restarts"] = [r for r in (svc.get("restarts") or []) if now - r < WINDOW]
    if ok:
        if svc.get("healthySince") is None:
            svc["healthySince"] = now
        svc["nextRestartAt"] = None
    else:
        svc["healthySince"] = None
        svc["budgetReturnsAt"] = None
        if svc.get("state") != "checking":
            events.extend(_act(sid, svc, now, run, clock, sleep, recheck, persist))
    svc["restartsInWindow"] = min(len(svc["restarts"]), BUDGET)
    return events


def _act(sid, svc, now, run, clock, sleep, recheck, persist):
    """The service is counted down (down, restarting or gave_up): wait, restart, or give up."""
    events = []
    nxt = svc.get("nextActionAt")
    if nxt is not None and now < nxt - SLACK:
        svc["nextRestartAt"] = nxt
        return events                      # still inside the wait after the last restart
    count = len(svc["restarts"])
    if count >= BUDGET:
        svc["state"] = "gave_up"
        svc["nextRestartAt"] = None
        events.append(make_event("gave_up", "critical", sid, now))
        return events
    attempt = count + 1
    started_ok, error = restart_unit(run, UNITS[sid])
    svc["restarts"].append(now)
    svc["nextActionAt"] = now + WAITS[count]
    svc["nextRestartAt"] = svc["nextActionAt"]
    svc["state"] = "restarting"
    if persist is not None:
        persist()
    params = {"attempt": attempt}
    healed = False
    if started_ok:
        healed, seconds = poll_healthy(lambda: bool(recheck(sid)[0]), clock, sleep)
        if healed:
            params.update(ok=True, seconds=seconds)
        else:
            params.update(ok=False, error=NOT_HEALTHY)
    else:
        params.update(ok=False, error=error)
    events.append(make_event("restart", "info" if healed else "warning", sid, now, params))
    if healed:
        svc.update(state="healthy", failedChecks=0, detail="", since=now, healthySince=now,
                   nextRestartAt=None)
        events.append(make_event("service_recovered", "info", sid, now))
    return events
