"""One watchdog run: check the services, debounce, report to the backend.

``run_once(config, state_dir, *, run, http, now)`` is the whole run with every external effect
injected. The seams, exactly as plans 82-03, 82-04 and 82-05 call them:

    run(argv: list[str], timeout: float) -> (returncode: int, stdout: str)
    http(method: str, url: str, headers: dict, body: bytes | None, timeout: float) -> (status: int, body: bytes)
    now() -> float                      # epoch seconds

Restart, warning and paging stages are added to this sequence by 82-03, 82-04 and 82-05.
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import DEFAULTS, SERVICE_ORDER, checks, services, state as state_mod, sync

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
    return done.returncode, done.stdout


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


def _read_token(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def _host(cfg):
    return (cfg.get("host") or socket.gethostname() or "omni")[:128]


def run_once(config, state_dir, *, run, http, now):
    """Check every service, update the state, send one sync. Returns a summary dict."""
    cfg = {**DEFAULTS, **(config or {})}
    t = now()
    path = state_mod.state_path(state_dir)
    state = state_mod.load_state(path)

    results = checks.check_all(run, http, cfg)
    events = []
    for sid, ok, detail in results:
        new, produced = services.observe(state["services"].get(sid), ok, detail, t, target=sid)
        state["services"][sid] = new
        events.extend(produced)

    spool = state_mod.Spool(os.path.join(state_dir, "spool.ndjson"))
    # The stop used for this run: the STOP file, else the value cached from the last good sync (D-11).
    # A stop pressed less than a minute before a backend crash can be missed once (82-RESEARCH Open Question 5).
    stop_on, stop_source = sync.resolve_stop(cfg["stop_file"], None, state)
    stop = {"effective": stop_on, "source": stop_source}

    # New events reach the spool (fsynced) before any send, so an outage cannot lose them.
    state["spoolDropped"] = int(state.get("spoolDropped") or 0) + spool.append(events)

    oncall = {"type": "none", "heartbeatConfigured": False, "last": None}
    body = sync.build_body(_host(cfg), state["services"], [], [], oncall, stop, [], [], sent_at=t)
    token = _read_token(cfg["ingest_token_path"])
    synced, response = sync.sync_cycle(http, cfg, token, body, spool, state) if token else (False, None)
    if synced:
        sync.resolve_stop(cfg["stop_file"], response, state, now=t)     # refresh the cache for the next run

    state_mod.save_state(path, state)
    return {"synced": synced, "response": response, "events": events, "stop": stop,
            "spooled": len(spool), "services": {sid: state["services"][sid]["state"] for sid in SERVICE_ORDER}}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="omni-watchdog", description="Omni-Agent AI platform watchdog: one check run.")
    parser.add_argument("--config", default="/etc/omni-watchdog/watchdog.conf", help="path to watchdog.conf")
    parser.add_argument("--state-dir", default=DEFAULTS["state_dir"], help="directory for state.json and the spool")
    parser.add_argument("--once", action="store_true", help="run one check pass (the default; accepted for clarity)")
    args = parser.parse_args(argv)
    try:
        run_once(dict(DEFAULTS), args.state_dir, run=real_run, http=real_http, now=time.time)
    except Exception as exc:  # never print headers or URLs: the class name is enough to find it in the journal
        print("omni-watchdog: run failed: %s" % type(exc).__name__, file=sys.stderr)
        return 1
    return 0
