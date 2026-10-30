"""The restart decision (Phase 82, HEAL-01 / HEAL-02).

``decide`` runs after ``services.observe`` has debounced the checks and before the sync. For every
service that is counted down it either waits, restarts the unit, or gives up. Standard library only;
every host effect goes through the injected seams (``run``, ``clock``, ``sleep``, ``recheck``).

Restart timeline (D-07, read as in 82-RESEARCH assumption A1): restart 1 when the service is first
counted down, restart 2 one minute later, restart 3 two minutes after that, and four minutes after
restart 3 the service is declared ``gave_up``. These are the waits in ``WAITS``; at most ``BUDGET``
restarts of one service fit in any ``WINDOW`` seconds.

Giving up and getting the budget back (D-07, D-08): once ``BUDGET`` restarts are used and the last wait has
passed with the service still down, it is ``gave_up`` exactly once: one ``gave_up`` event and the open
incident ``svc:<id>`` (see incidents.py). A given-up service is never restarted again, even after its
restarts age out of ``WINDOW``; only ``REARM_AFTER`` seconds of unbroken health bring the budget back, with
one ``budget_rearmed`` event and the incident cleared. A restart that systemctl refuses (a missing polkit
rule) is a failed attempt like any other, so it ends in ``gave_up`` and one page, never a loop.

Order and pauses: MongoDB is judged first and the backend waits for it (D-09). While a stop is effective
(D-11) a down service is not restarted: one ``restart_skipped`` event per down episode, the counters stay
untouched, and its ``svc:<id>`` incident opens so on-call still hears about it.

Commands issued, and nothing else (the 82-06 polkit rule allows exactly these verbs on these units):
    systemctl is-active <unit>                  # read-only, to learn whether the unit is ``failed``
    systemctl reset-failed <unit>               # only when is-active said ``failed``
    systemctl restart --no-block <unit>
The unit always comes from ``UNITS``; Ollama only where the operator said it is expected.
"""
import re

from . import SERVICE_ORDER, UNITS, incidents
from .services import make_event

WAITS = (60, 120, 240)      # seconds after restart 1, 2, 3 before the next action
BUDGET = 3                  # restarts per service inside WINDOW
WINDOW = 1800               # 30 minutes
REARM_AFTER = 3600          # healthy for this long gives the budget back (D-08)
POLL_EVERY = 2              # seconds between health polls after a restart
POLL_FOR = 20               # give up polling one service after this long
POLL_BUDGET = 30            # all restarts of one run together may take this long (TimeoutStartSec is 45)
SLACK = 5                   # a run up to this early still counts as "the wait is over" (timer jitter)
ERROR_CAP = 300
RESTART_TIMEOUT = 15
NOT_HEALTHY = "Not healthy %d s after the restart."
NOT_CONFIRMED = "Restart issued; not yet confirmed. Checked again on the next run."
KIND_GAVE_UP = "service_gave_up"
KIND_DOWN = "service_down"

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


def poll_healthy(check, clock, sleep, limit=POLL_FOR):
    """Poll ``check()`` every POLL_EVERY seconds for up to ``limit`` (at most POLL_FOR) seconds.

    Returns (healthy, seconds taken). The loop is also bounded by its iteration count, so a clock
    that does not move can never make it spin."""
    limit = min(limit, POLL_FOR)
    start = clock()
    for _ in range(int(limit // POLL_EVERY)):
        sleep(POLL_EVERY)
        if check():
            return True, int(round(max(0.0, clock() - start)))
        if clock() - start >= limit:
            break
    return False, None


class _Run:
    """What one ``decide`` call shares across services: the seams, the stop and the polling allowance."""

    def __init__(self, state, stop, now, run, clock, sleep, recheck, persist):
        self.state, self.stop, self.now = state, stop or {}, now
        self.run, self.clock, self.sleep, self.recheck, self.persist = run, clock, sleep, recheck, persist
        self.started = clock()

    def allowance(self):
        """Seconds of polling still allowed in this run: one POLL_FOR at most, and the whole run
        (restart commands and polling of every service) never beyond POLL_BUDGET."""
        return max(0.0, min(POLL_FOR, POLL_BUDGET - (self.clock() - self.started)))

    def save(self):
        if self.persist is not None:
            self.persist()


def decide(state, health, stop, now, config, *, run, clock, sleep, recheck, persist=None):
    """Judge every restartable service once. Returns the new events; mutates ``state``.

    ``state``   the watchdog state dict (``services`` already updated by services.observe)
    ``health``  {service id: (ok, detail)} from this run's checks
    ``stop``    {"effective": bool, "source": str}; while effective nothing is restarted (D-11)
    ``now``     epoch seconds of this run (all timestamps in state use it)
    ``clock``   the now() seam, read while polling after a restart
    ``recheck`` recheck(service id) -> (ok, detail), the service's own check
    ``persist`` called right after a restart is recorded and before polling, so a run killed while
                polling cannot forget the restart and repeat it

    Services are judged in SERVICE_ORDER, MongoDB first. While MongoDB is not healthy in this run the
    backend is only marked ``waitingOn`` mongod: it is not restarted and its failures cost no budget
    (D-09). Polling after restarts shares one allowance of POLL_BUDGET seconds per run, so a run that
    restarts several services still finishes inside the unit's start timeout and every restart event
    reaches the spool; a restart the allowance cannot cover is recorded as issued and judged next run.
    """
    ctx = _Run(state, stop, now, run, clock, sleep, recheck, persist)
    mongo_ok = bool(health["mongod"][0]) if "mongod" in health else True
    events = []
    for sid in managed_ids(config):
        svc = state["services"].get(sid)
        if svc is None or sid not in health:
            continue
        blocked = sid == "omni-backend" and not mongo_ok
        events.extend(_step(ctx, sid, svc, bool(health[sid][0]), blocked))
    return events


def _step(ctx, sid, svc, ok, blocked):
    events = []
    now = ctx.now
    svc["restarts"] = [r for r in (svc.get("restarts") or []) if now - r < WINDOW]
    if ok:
        svc["waitingOn"] = None
        svc["skipped"] = False
        svc["nextRestartAt"] = None
        if svc.get("healthySince") is None:
            svc["healthySince"] = now
        _clear_pause_incident(ctx.state, sid, now)
        if svc.get("gaveUp"):
            if now - svc["healthySince"] >= REARM_AFTER:
                events.append(_rearm(ctx.state, sid, svc, now))
            else:
                svc["budgetReturnsAt"] = svc["healthySince"] + REARM_AFTER
        else:
            svc["budgetReturnsAt"] = None
    else:
        svc["healthySince"] = None
        svc["budgetReturnsAt"] = None
        if blocked:
            svc["waitingOn"] = "mongod"
            svc["nextRestartAt"] = None
        else:
            svc["waitingOn"] = None
            if svc.get("state") != "checking":
                events.extend(_down(ctx, sid, svc))
    svc["restartsInWindow"] = min(len(svc["restarts"]), BUDGET)
    return events


def _rearm(state, sid, svc, now):
    """D-08: an hour healthy gives the budget back and clears the service's incident."""
    svc.update(gaveUp=False, restarts=[], nextActionAt=None, nextRestartAt=None, budgetReturnsAt=None,
               pagedAt=None, skipped=False)
    incidents.clear_incident(state, "svc:" + sid, now)
    return make_event("budget_rearmed", "info", sid, now)


def _open_incident(state, sid, kind, now):
    """Open svc:<sid> (critical). A pause incident that is open already is upgraded to gave-up."""
    key = "svc:" + sid
    params = {"restarts": BUDGET} if kind == KIND_GAVE_UP else {}
    created = incidents.open_incident(state, key, "critical", kind, sid, params, now)
    if created is None and kind == KIND_GAVE_UP:
        current = state["incidents"].get(key)
        if incidents.is_open(current):
            current["kind"], current["params"] = kind, params
    return created is not None


def _clear_pause_incident(state, sid, now):
    """A service that is healthy again no longer needs the incident opened while restarts were paused.
    The gave-up incident is not cleared here: it waits for the re-arm (D-08)."""
    current = (state.get("incidents") or {}).get("svc:" + sid)
    if incidents.is_open(current) and current.get("kind") == KIND_DOWN:
        incidents.clear_incident(state, "svc:" + sid, now)


def _down(ctx, sid, svc):
    """The service is counted down (down, restarting or gave_up): wait, give up, pause, or restart."""
    events = []
    now = ctx.now
    if svc.get("gaveUp"):
        svc["state"] = "gave_up"             # sticky: no restart until the budget is re-armed (PROH-82-09)
        svc["nextRestartAt"] = None
        return events
    nxt = svc.get("nextActionAt")
    if nxt is not None and now < nxt - SLACK:
        svc["nextRestartAt"] = nxt
        return events                        # still inside the wait after the last restart
    if len(svc["restarts"]) >= BUDGET:
        svc["gaveUp"] = True
        svc["state"] = "gave_up"
        svc["nextRestartAt"] = None
        events.append(make_event("gave_up", "critical", sid, now))
        if _open_incident(ctx.state, sid, KIND_GAVE_UP, now):
            svc["pagedAt"] = now
        ctx.save()
        return events
    if ctx.stop.get("effective"):            # D-11: checks, events and incidents go on; restarts do not
        svc["nextRestartAt"] = None
        if not svc.get("skipped"):
            svc["skipped"] = True
            events.append(make_event("restart_skipped", "warning", sid, now))
        if _open_incident(ctx.state, sid, KIND_DOWN, now):
            svc["pagedAt"] = now
            ctx.save()
        return events
    return _restart(ctx, sid, svc)


def _restart(ctx, sid, svc):
    now = ctx.now
    count = len(svc["restarts"])
    attempt = count + 1
    started_ok, error = restart_unit(ctx.run, UNITS[sid])
    svc["restarts"].append(now)
    svc["nextActionAt"] = now + WAITS[count]
    svc["nextRestartAt"] = svc["nextActionAt"]
    svc["state"] = "restarting"
    ctx.save()
    params = {"attempt": attempt}
    healed = False
    if not started_ok:
        params.update(ok=False, error=error)
    else:
        allowed = ctx.allowance()
        if allowed < POLL_EVERY:             # the run's polling allowance is used up: judged next run
            params.update(ok=False, error=NOT_CONFIRMED)
        else:
            healed, seconds = poll_healthy(lambda: bool(ctx.recheck(sid)[0]), ctx.clock, ctx.sleep, allowed)
            if healed:
                params.update(ok=True, seconds=seconds)
            else:
                params.update(ok=False, error=NOT_HEALTHY % int(allowed))
    events = [make_event("restart", "info" if healed else "warning", sid, now, params)]
    if healed:
        svc.update(state="healthy", failedChecks=0, detail="", since=now, healthySince=now,
                   nextRestartAt=None, skipped=False)
        _clear_pause_incident(ctx.state, sid, now)
        events.append(make_event("service_recovered", "info", sid, now))
    return events
