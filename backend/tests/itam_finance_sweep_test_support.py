"""Shared test support for the Phase 59 warranty alert sweep tests
(ITAM-FIN-02): the raw-handle db stub used to prove the sweep never
resolves get_database() and never crashes on a handle with no _db
attribute (RESEARCH Pitfall 1).

Split out from test_itam_finance_sweep.py so both that file and
test_itam_finance_sweep_resilience.py stay under the CLAUDE.md 500-line
limit — mirrors itam_finance_test_support.py's own split for Plan 59-01.

This module is deliberately not named `test_*.py` so pytest does not try
to collect it directly.
"""
import asyncio
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ===========================================================================
# _RawSweepDb — plain-class stub designed to genuinely lack _db
# ===========================================================================
class _RawSweepDb:
    """Plain-class db stub, NOT a MagicMock and with NO __getattr__ fallback
    and NO _db attribute, so hasattr(stub, "_db") is genuinely False.

    A mock-based fixture auto-creates _db on attribute access and would make
    every Pitfall-1 assertion in this file pass vacuously while the real
    defect survived.

    Collection attributes are in-memory dicts seeded at construction time.
    Assets live as docs in a list; updates mutate them in place so a second
    pass sees the markers the first pass wrote.
    """

    def __init__(self, assets=None, users=None, rules=None, channels=None):
        self._docs = {  # in-memory document store keyed by (coll, id)
            "assets": {d["id"]: dict(d) for d in (assets or [])},
            "users": list(users or []),
        }
        self._rules = list(rules or [])
        self._channels = list(channels or [])

        self._captured_asset_filters = []
        self._captured_user_filters = []
        self._captured_update_one_filters = []
        self._captured_notifications = []
        self._settings_find_one_result = None
        self._settings_find_one_call_count = 0

        # Expose collection-shaped attributes for itam_finance_service code
        self.assets = _AssetsCollection(self)
        self.users = _UsersCollection(self)
        self.system_settings = _SystemSettings(self)
        self.notifications = _Notifications(self)
        self.notification_rules = _NotificationRules(self)
        self.notification_channels = _NotificationChannels(self)


class _AssetsCollection:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec, projection=None):
        self._db._captured_asset_filters.append(filter_spec)
        matched = [d for d in self._db._docs["assets"].values()
                   if all(d.get(k) == v if not isinstance(v, dict) else True
                          for k, v in filter_spec.items()
                          if not isinstance(v, dict))]
        # Apply $exists negation filter
        filtered = []
        for d in matched:
            skip = False
            for k, v in filter_spec.items():
                if isinstance(v, dict) and "$exists" in v:
                    if v["$exists"] and k in d:
                        continue
                    elif not v["$exists"] and k not in d:
                        continue
                    elif v["$exists"] and k not in d:
                        skip = True
                    elif not v["$exists"] and k in d:
                        skip = True
            if not skip:
                filtered.append(d)
        return _AsyncCursor(filtered)

    async def update_one(self, filter_spec, update):
        self._db._captured_update_one_filters.append(filter_spec)
        doc_id = filter_spec.get("id")
        tenant_id = filter_spec.get("tenantId")
        for d in self._db._docs["assets"].values():
            if d["id"] == doc_id and d.get("tenantId") == tenant_id:
                for k, v in update.get("$set", {}).items():
                    d[k] = v
                break


class _UsersCollection:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec):
        self._db._captured_user_filters.append(filter_spec)
        matched = []
        for user in self._db._docs["users"]:
            match = True
            for k, v in filter_spec.items():
                if k == "role" and isinstance(v, dict) and "$in" in v:
                    if user.get("role") not in v["$in"]:
                        match = False
                elif user.get(k) != v:
                    match = False
            if match:
                matched.append(user)
        return _AsyncCursor(matched)


class _SystemSettings:
    def __init__(self, db):
        self._db = db

    async def find_one(self, query):
        # Return a default 30-day window for the warranty alert window setting
        if query.get("type") == "itam_warranty_alert_window":
            return {"windowDays": 30}
        return None


class _Notifications:
    def __init__(self, db):
        self._db = db

    async def insert_one(self, doc):
        self._db._captured_notifications.append(doc)


class _NotificationRules:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec):
        matched = []
        for rule in self._db._rules:
            match = True
            for k, v in filter_spec.items():
                if rule.get(k) != v:
                    match = False
            if match:
                matched.append(rule)
        return _AsyncCursor(matched)


class _NotificationChannels:
    def __init__(self, db):
        self._db = db

    def find(self, filter_spec):
        matched = []
        for ch in self._db._channels:
            match = True
            for k, v in filter_spec.items():
                if ch.get(k) != v:
                    match = False
            if match:
                matched.append(ch)
        return _AsyncCursor(matched)


class _AsyncCursor:
    """Async-iterable cursor stub."""

    def __init__(self, docs=()):
        self._docs = list(docs)
        self._iter = iter(self._docs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        return list(self._docs)


def _run(coro):
    return asyncio.run(coro)


def _asset(**overrides):
    asset = {
        "id": "asset-1",
        "tenantId": "tenant-a",
        "assetTag": "TAG-001",
        "purchaseDate": "2026-01-15T00:00:00Z",
        "warrantyMonths": 12,
    }
    asset.update(overrides)
    return asset


def _user(**overrides):
    user = {
        "id": "user-1",
        "email": "admin@tenant-a.com",
        "role": "admin",
        "tenantId": "tenant-a",
    }
    user.update(overrides)
    return user
