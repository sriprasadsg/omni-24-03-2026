"""The incident store (Phase 82): what is open right now that on-call should hear about once.

``state["incidents"]`` maps an incident key to one incident dict, all timestamps epoch seconds::

    {"key": "svc:mongod",        # check[:subject][:rung], stable: the PagerDuty dedup key is built from it
     "severity": "critical",     # info | warning | critical
     "kind": "service_gave_up",  # fixed vocabulary per check; the pager text is a fixed template per kind
     "target": "mongod",         # the service id, certificate path or mount the incident is about
     "params": {...},            # small structured facts for the message (never free text from outside)
     "openedAt": 1800000000.0,
     "pageKey": None,            # set by the pager (82-05): the dedup key of the group this was sent in
     "sent": False,              # set by the pager once the trigger was delivered
     "clearedAt": None}          # set when the cause is gone; the pager then sends the matching resolve

An incident opens once per key: opening an open key does nothing. A cleared incident stays in the store
(so the pager can still resolve it) until the pager drops it; opening a cleared key starts a new one.
Writing the state file before any page is sent is the caller's job (Pitfall 15).
"""

SEVERITIES = ("info", "warning", "critical")


def _store(state):
    store = state.get("incidents")
    if not isinstance(store, dict):
        store = state["incidents"] = {}
    return store


def is_open(incident):
    return isinstance(incident, dict) and incident.get("clearedAt") is None


def open_incident(state, key, severity, kind, target, params, now):
    """Open ``key``. Returns the new incident, or None when that key is already open."""
    if severity not in SEVERITIES:
        raise ValueError("unknown incident severity")
    store = _store(state)
    if is_open(store.get(key)):
        return None
    incident = {"key": key, "severity": severity, "kind": kind, "target": target,
                "params": dict(params or {}), "openedAt": now, "pageKey": None, "sent": False,
                "clearedAt": None}
    store[key] = incident
    return incident


def clear_incident(state, key, now):
    """Mark ``key`` cleared at ``now``. Returns the incident, or None when it was not open."""
    incident = _store(state).get(key)
    if not is_open(incident):
        return None
    incident["clearedAt"] = now
    return incident


def open_incidents(state):
    """Every incident that is open, oldest first."""
    found = [i for i in _store(state).values() if is_open(i)]
    return sorted(found, key=lambda i: (i.get("openedAt") or 0, i.get("key") or ""))
