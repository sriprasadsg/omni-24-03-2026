"""One watchdog run: check the services, debounce, report to the backend.

``run_once(config, state_dir, *, run, http, now)`` is the whole run with every external effect
injected. The seams, exactly as plans 82-03, 82-04 and 82-05 call them:

    run(argv: list[str], timeout: float) -> (returncode: int, stdout: str)
    http(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> (status: int, body: bytes)
    now() -> float                      # epoch seconds

A fourth seam, ``sleep(seconds)``, is used only while polling a service after a restart (82-03);
tests pass the fake clock's ``advance``.

Sequence of one run: check -> debounce -> stop -> restart decision (82-03) -> certificate and disk warnings
(82-04) -> spool -> save state -> page incidents (82-05) -> save state -> sync -> deliver the backend's outbox
and test request -> post results -> external heartbeat -> save state.
A fifth seam, ``fs``, answers os.statvfs / os.stat for the disk checks (tests choose the numbers).
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import (DEFAULTS, SERVICE_ORDER, checks, config as config_mod, paging, restart, services, state as state_mod,
               sync, warnings)

CHILD_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}


def real_run(argv, timeout):
    """subprocess with an argument list, no shell, a minimal environment."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=CHILD_ENV,
                              shell=False, check=False)
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""
    out = done.stdout
    if done.returncode != 0:
        out = (out or "") + (done.stderr or "")      # a refused restart explains itself on stderr
    return done.returncode, out


def real_http(method, url, headers, body, timeout):
    """urllib with the default verified SSL context; only http and https URLs."""
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("unsupported URL scheme")
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310 (scheme checked above)
            return reply.status, reply.read(sync.MAX_RESPONSE)
    except urllib.error.HTTPError as err:
        return err.code, err.read(sync.MAX_RESPONSE)


def _host(cfg):
    return (cfg.get("host") or socket.gethostname() or "omni")[:128]


def run_once(config, state_dir, *, run, http, now, sleep=None, fs=None):
    """Check every service, update the state, send one sync. Returns a summary dict.

    A second concurrent run returns ``{"skipped": "locked"}`` at once, without checking or posting."""
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    with state_mod.run_lock(os.path.join(state_dir, "state.lock")) as acquired:
        if not acquired:
            return {"skipped": "locked"}
        return _run_locked({**DEFAULTS, **(config or {})}, state_dir, run=run, http=http, now=now,
                           sleep=sleep or time.sleep, fs=fs)


def _run_locked(cfg, state_dir, *, run, http, now, sleep, fs=None):
    t = now()
    path = state_mod.state_path(state_dir)
    state = state_mod.load_state(path, now=t)
    reset = bool(state.pop("_reset", False))

    results = checks.check_all(run, http, cfg)
    events = [services.make_event("state_reset", "warning", None, t)] if reset else []
    for sid, ok, detail in results:
        new, produced = services.observe(state["services"].get(sid), ok, detail, t, target=sid)
        state["services"][sid] = new
        events.extend(produced)

    # The stop used for this run: the STOP file, else the value cached from the last good sync (D-11).
    # A stop pressed less than a minute before a backend crash can be missed once (82-RESEARCH Open Question 5).
    stop_on, stop_source = sync.resolve_stop(cfg["stop_file"], None, state)
    stop = {"effective": stop_on, "source": stop_source}

    # Restart decision (82-03): only restarts pause during a stop; the checks above and the sync below do not.
    health = {sid: (ok, detail) for sid, ok, detail in results}
    events.extend(restart.decide(
        state, health, stop, t, cfg, run=run, clock=now, sleep=sleep,
        recheck=lambda sid: checks.check_one(sid, run, http, cfg),
        persist=lambda: state_mod.save_state(path, state)))

    # Certificate and disk warnings (82-04): read-only checks that run after the restart decision. Their events
    # join the restart events in the one spool below, so a backend outage cannot lose them.
    certs, disks, warning_events = warnings.evaluate(state, cfg, t, run, clock=now, fs=fs)
    events.extend(warning_events)

    spool = state_mod.Spool(os.path.join(state_dir, "spool.ndjson"))
    save = lambda: state_mod.save_state(path, state)

    # New events reach the spool (fsynced) before any send, so an outage cannot lose them.
    state["spoolDropped"] = int(state.get("spoolDropped") or 0) + spool.append(events)
    # The incidents opened above are on disk before the network (and any paging) is touched. A run killed
    # earlier leaves the previous complete state.json: save_state is an atomic replace.
    save()

    channel = config_mod.load_oncall(cfg["oncall_env_path"])
    host = _host(cfg)
    budget = paging.Budget(clock=now, deadline=t + paging.SEND_WINDOW)
    page_events = paging.page_incidents(state, channel, http, host, t, sleep=sleep, budget=budget, save=save)
    events.extend(page_events)
    state["spoolDropped"] = int(state.get("spoolDropped") or 0) + spool.append(page_events)
    save()

    pending = _list(state, "pendingDelivered")[:sync.MAX_EVENTS_PER_SYNC]
    body = sync.build_body(host, state["services"], certs, disks, paging.oncall_block(channel, state), stop, [],
                           pending, sent_at=t)
    token = config_mod.read_token(cfg["ingest_token_path"])
    synced, response = sync.sync_cycle(http, cfg, token, body, spool, state) if token else (False, None)
    if synced:
        sync.resolve_stop(cfg["stop_file"], response, state, now=t)     # refresh the cache for the next run
        state["pendingDelivered"] = _list(state, "pendingDelivered")[len(pending):]    # the backend took them
        events.extend(_deliver(cfg, state, channel, http, host, token, response, t, sleep, budget, spool, save))

    paging.ping_heartbeat(http, channel)       # the run reached its end: tell the external dead-man service
    save()
    return {"synced": synced, "response": response, "events": events, "stop": stop,
            "spooled": len(spool), "services": {sid: state["services"][sid]["state"] for sid in SERVICE_ORDER}}


def _list(state, key):
    value = state.get(key)
    return value if isinstance(value, list) else []


def _deliver(cfg, state, channel, http, host, token, response, t, sleep, budget, spool, save):
    """Send what the sync response handed out (outbox messages, a test request) and report the outcome.

    A test result is kept in ``state["pendingTest"]`` until ``/results`` accepts it, and a request whose
    result is already known is not sent a second time. Returns the new events (the test_alert event, which
    reaches the backend with the next sync)."""
    events = []
    delivered = paging.deliver_outbox(state, channel, http, host, response.get("outbox"), t, sleep=sleep, budget=budget,
                                      save=save)
    result = state.get("pendingTest") if isinstance(state.get("pendingTest"), dict) else None
    request = response.get("testRequest")
    if isinstance(request, dict) and not (result and result.get("id") == request.get("id")):
        fresh = paging.send_test(channel, http, host, request, t, sleep=sleep, budget=budget)
        if fresh is not None:
            result = state["pendingTest"] = fresh
            events.append(paging.test_event(fresh, channel, t))
            save()
    if delivered or result:
        accepted, _answer = sync.post_results(http, cfg["backend_url"], token, delivered, result)
        if accepted:
            state.pop("pendingTest", None)
        else:
            state["pendingDelivered"] = (_list(state, "pendingDelivered") + delivered)[-200:]
    state["spoolDropped"] = int(state.get("spoolDropped") or 0) + spool.append(events)
    return events


def main(argv=None):
    parser = argparse.ArgumentParser(prog="omni-watchdog", description="Omni-Agent AI platform watchdog: one check run.")
    parser.add_argument("--config", default="/etc/omni-watchdog/watchdog.conf", help="path to watchdog.conf")
    parser.add_argument("--state-dir", default=DEFAULTS["state_dir"], help="directory for state.json and the spool")
    parser.add_argument("--once", action="store_true", help="run one check pass (the default; accepted for clarity)")
    args = parser.parse_args(argv)
    try:
        run_once(config_mod.load_config(args.config), args.state_dir, run=real_run, http=real_http, now=time.time)
    except Exception as exc:  # never print headers or URLs: the class name is enough to find it in the journal
        print("omni-watchdog: run failed: %s" % type(exc).__name__, file=sys.stderr)
        return 1
    return 0
