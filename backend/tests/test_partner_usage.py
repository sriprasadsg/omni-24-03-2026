"""Phase 87 plan 09 task 3: the usage roll-up a partner reads (PART-08, D-16) on real MongoDB.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. These lock behaviour that partner_store.customer_rows gained in
87-01, so they pass as soon as they are written; they would fail if the counting rules drifted.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(pe, "mongodb", handle), patch("audit_ledger.event", new=AsyncMock()):
        yield SimpleNamespace(db=mongo_db)


async def _overview(pid="partner_a"):
    user = TokenData(username="boss@x.test", role="partner_admin", tenant_id=pid, mfa_verified=True)
    return await pe.get_overview(ctx=await pe.current_partner(current_user=user))


async def _partner(wired, pool=40, allocated=25, expires=None):
    await wired.db.tenants.insert_one({
        "id": "partner_a", "type": "partner", "name": "Alpha", "license": {"maxAgents": 0},
        "partner": {"poolSize": pool, "allocated": allocated, "status": "active", "screenCeiling": [],
                    "expiresAt": expires},
    })


async def _customer(wired, cid, name, seats=10, used=None, expires=None):
    lic = {"maxAgents": seats}
    if used is not None:
        lic["seatsUsed"] = used
    if expires:
        lic["expiresAt"] = expires
    await wired.db.tenants.insert_one({"id": cid, "name": name, "partnerId": "partner_a", "license": lic})


async def _agents(wired, cid, statuses):
    await wired.db.agents.insert_many([
        {"id": f"{cid}-{n}", "hostname": f"{cid}-h{n}", "tenantId": cid, "status": status}
        for n, status in enumerate(statuses)])


async def test_the_pool_figures_equal_the_partner_document(wired):
    """protects=D-16 pool size, handed out and free; fails_when=any figure drifts from poolSize and allocated."""
    await _partner(wired, pool=40, allocated=25)
    pool = (await _overview())["pool"]
    assert (pool["size"], pool["handedOut"], pool["free"]) == (40, 25, 15)


async def test_a_partner_without_customers_reads_an_empty_list_and_its_pool(wired):
    await _partner(wired, pool=7, allocated=0)
    out = await _overview()
    assert out["customers"] == [] and out["pool"]["free"] == 7


async def test_each_row_counts_seats_and_agents_by_the_licence_and_status_rules(wired):
    """protects=PART-08; fails_when=seatsAssigned or seatsUsed leave the licence counters, Pending or
    Rejected agents are counted, or an Online agent is missed."""
    await _partner(wired)
    await _customer(wired, "c1", "Cafe", seats=12, used=4)
    await _agents(wired, "c1", ["Online", "Offline", "Online", "Pending", "Rejected"])
    await _customer(wired, "c2", "Bar", seats=8)  # no seatsUsed counter yet: falls back to the agent count
    await _agents(wired, "c2", ["Offline", "Pending"])
    rows = {row["id"]: row for row in (await _overview())["customers"]}
    assert (rows["c1"]["seatsAssigned"], rows["c1"]["seatsUsed"]) == (12, 4)
    assert (rows["c1"]["agentsOnline"], rows["c1"]["agentsTotal"]) == (2, 3)
    assert (rows["c2"]["seatsAssigned"], rows["c2"]["seatsUsed"]) == (8, 1)
    assert (rows["c2"]["agentsOnline"], rows["c2"]["agentsTotal"]) == (0, 1)


async def test_the_licence_expiry_is_the_earlier_of_the_customers_and_the_pools(wired):
    """protects=D-16 expiry; fails_when=the later date, or the wrong source, is shown."""
    await _partner(wired, expires="2030-06-01T00:00:00+00:00")
    await _customer(wired, "early", "Early", expires="2029-01-01T00:00:00+00:00")
    await _customer(wired, "late", "Late", expires="2031-01-01T00:00:00+00:00")
    await _customer(wired, "none", "None")
    rows = {row["id"]: row for row in (await _overview())["customers"]}
    assert rows["early"]["licenseExpiresAt"] == "2029-01-01T00:00:00+00:00"
    assert rows["late"]["licenseExpiresAt"] == "2030-06-01T00:00:00+00:00"
    assert rows["none"]["licenseExpiresAt"] == "2030-06-01T00:00:00+00:00"


async def test_customers_are_ordered_by_name_ignoring_case_then_id(wired):
    """protects=PART-05 ordering; fails_when=capital letters sort first or equal names are unordered."""
    await _partner(wired)
    await _customer(wired, "c9", "alpha")
    await _customer(wired, "c1", "Alpha")
    await _customer(wired, "c5", "bravo")
    await _customer(wired, "c3", "Charlie")
    assert [row["id"] for row in (await _overview())["customers"]] == ["c1", "c9", "c5", "c3"]
