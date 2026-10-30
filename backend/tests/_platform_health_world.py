"""Shared fixtures of the platform health tests (plan 82-08): the platform API and the watchdog on one database."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from autonomous_ops import oncall, selfheal
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_platform_health_sync import Watchdog, _body

STATUS = "/api/platform/autonomous-ops/status"
HEALTH = "/api/platform/autonomous-ops/health"
STOP = "/api/platform/autonomous-ops/stop"
RESUME = "/api/platform/autonomous-ops/resume"


class World:
    """The platform API and the watchdog on one database."""

    def __init__(self, api, dog):
        self.api, self.dog, self.db = api, dog, api.db

    async def sync(self, **extra):
        res = await self.dog.post(body=_body(**extra))
        assert res.status_code == 200, res.text
        return res

    async def get(self, path, role="super_admin"):
        return await self.api.call("GET", path, role=role)

    async def summary(self):
        res = await self.get(STATUS)
        assert res.status_code == 200, res.text
        return res.json()["health"]


@pytest.fixture
async def world(api, monkeypatch, tmp_path):
    await selfheal.ensure_indexes(api.db)
    await oncall.ensure_indexes(api.db)
    dog = Watchdog(api.db, monkeypatch, tmp_path)
    dog.set_token()
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", datetime.now(timezone.utc).timestamp() - 3600)
    return World(api, dog)


T0 = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


def NAIVE(dt):  # noqa: N802  (a datetime as MongoDB returns it: UTC without tzinfo)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _oncall(kind="pagerduty", last=None):
    return {"type": kind, "heartbeatConfigured": False, "last": last}


async def _test_result(db, rid, state, sent_at, error=None):
    await db.oncall_test_requests.insert_one({"id": rid, "requestedAt": sent_at - timedelta(minutes=1), "requestedBy": {},
                                              "state": state, "sentAt": sent_at, "error": error})
