"""Watchdog state: ids, the state file.

All timestamps in state are epoch seconds (never local-time strings). ``state.json`` lives in
the state directory, which only the watchdog user may write, so the backend user cannot edit it
and reset a restart budget.
"""
import contextlib
import fcntl
import json
import os
import secrets
import time

STATE_VERSION = 1


def new_event_id():
    """A 32-hex id, generated once per event."""
    return secrets.token_hex(16)


def state_path(state_dir):
    return os.path.join(state_dir, "state.json")


def empty_state():
    return {"v": STATE_VERSION, "services": {}, "stopCache": None, "spoolDropped": 0}


def load_state(path, now=None):
    """The saved state, or an empty one when the file is missing.

    A file that does not parse is renamed ``state.json.bad-<epoch>`` and the run continues from an empty
    state carrying ``_reset: True`` (the caller emits one state_reset event and drops the flag)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return empty_state()
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        try:
            os.replace(path, "%s.bad-%d" % (path, int(time.time() if now is None else now)))
        except OSError:
            pass
        state = empty_state()
        state["_reset"] = True
        return state
    state = empty_state()
    state.update(data)
    if not isinstance(state.get("services"), dict):
        state["services"] = {}
    return state


@contextlib.contextmanager
def run_lock(path):
    """Yield True when this process holds the exclusive run lock, False when another run has it."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        os.close(fd)        # closing the descriptor releases the lock


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


SPOOL_MAX_LINES = 2000
MAX_TRIES = 3      # hand-overs the backend neither accepted nor dropped before an event is abandoned


class Spool:
    """Events waiting to reach the backend: one JSON object per line in ``spool.ndjson``.

    Every event is appended (flush + fsync) before a send is attempted and leaves the spool only
    when the backend acknowledges it, so an outage loses nothing until the 2,000-line cap, which
    drops the oldest lines first. Order is file order: older events are always re-sent first."""

    def __init__(self, path, max_lines=SPOOL_MAX_LINES):
        self.path = path
        self.max_lines = max_lines

    def _lines(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                return [line for line in handle.read().split("\n") if line.strip()]
        except OSError:
            return []

    def _rewrite(self, lines):
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    def __len__(self):
        return len(self._lines())

    def append(self, events):
        """Append events; returns how many of the oldest lines the cap dropped."""
        if not events:
            return 0
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        lines = self._lines()
        excess = len(lines) - self.max_lines
        if excess > 0:
            self._rewrite(lines[excess:])
            return excess
        return 0

    def read(self, limit):
        """Up to ``limit`` events in file order; unreadable lines are skipped."""
        events = []
        for line in self._lines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                events.append(item)
                if len(events) >= limit:
                    break
        return events

    def remove(self, ids):
        """Drop the events with these ids (and any unreadable line) by rewriting through a temp file."""
        ids = set(ids)
        if not ids:
            return
        keep = []
        for line in self._lines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("id") not in ids:
                keep.append(line)
        self._rewrite(keep)

    def bump_tries(self, ids):
        """Count one more failed hand-over for these ids; returns the ids that reached MAX_TRIES."""
        ids, exhausted, keep = set(ids), [], []
        for line in self._lines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and item.get("id") in ids:
                item["tries"] = int(item.get("tries") or 0) + 1
                if item["tries"] >= MAX_TRIES:
                    exhausted.append(item["id"])
                    continue
                line = json.dumps(item, separators=(",", ":"))
            if isinstance(item, dict):
                keep.append(line)
        self._rewrite(keep)
        return exhausted

