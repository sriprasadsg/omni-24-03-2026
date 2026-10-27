"""Watchdog state: ids, the state file.

All timestamps in state are epoch seconds (never local-time strings). ``state.json`` lives in
the state directory, which only the watchdog user may write, so the backend user cannot edit it
and reset a restart budget.
"""
import json
import os
import secrets

STATE_VERSION = 1


def new_event_id():
    """A 32-hex id, generated once per event."""
    return secrets.token_hex(16)


def state_path(state_dir):
    return os.path.join(state_dir, "state.json")


def empty_state():
    return {"v": STATE_VERSION, "services": {}, "stopCache": None, "spoolDropped": 0}


def load_state(path):
    """The saved state, or an empty one when the file is missing or unusable."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return empty_state()
    if not isinstance(data, dict):
        return empty_state()
    state = empty_state()
    state.update(data)
    if not isinstance(state.get("services"), dict):
        state["services"] = {}
    return state


def save_state(path, state):
    """Atomic write: temp file in the same directory, fsync, then os.replace."""
    tmp = path + ".tmp"
    payload = json.dumps(state, separators=(",", ":"), sort_keys=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
