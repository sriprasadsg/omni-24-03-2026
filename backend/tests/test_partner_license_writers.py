"""Phase 87 plan 10: every other writer of a customer's seats respects the partner pool (real MongoDB).

Value: protects=a partner's pool total holds for the licence PATCH, approve-and-raise, customer
deletion and the direct create path, and no new module can write license.maxAgents behind the
pool's back; fails_when=a PATCH or approval lifts a partner customer past the pool, a refusal still
changes a document, deleting a customer leaks its seats, a partner with customers can be deleted, or
a new seat writer appears outside the allowlist; no_claim=the HTTP layer (route functions are called
directly with a TokenData, the audit writers are mocked).
"""
import ast
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tenant_endpoints as te
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)

PRE_CHANGE_KEYS = {"id", "name", "subscriptionTier", "registrationKey", "enabledFeatures", "agentCapabilities",
                   "notificationPreferences", "emailConfig", "maxAgents", "license", "createdAt", "updatedAt",
                   "trial"}


@pytest.fixture
def wired(mongo_db):
    """The tenant routes run against the private database; auditing and session revocation are mocked."""
    audit = MagicMock(log_action_async=AsyncMock())
    with patch.object(te, "mongodb", SimpleNamespace(db=mongo_db)), \
            patch("audit_service.get_audit_service", return_value=audit), \
            patch.object(te, "get_database", return_value=mongo_db), \
            patch.object(te, "revoke_user_sessions", new=AsyncMock()):
        yield mongo_db


async def _partner(db, pool=100, allocated=0, status="active", pid="p1", expires=None):
    doc = {"id": pid, "name": f"Partner {pid}", "type": "partner", "license": {"maxAgents": 0},
           "partner": {"poolSize": pool, "allocated": allocated, "status": status, "screenCeiling": ["all"]}}
    if expires:
        doc["partner"]["expiresAt"] = expires
    await db.tenants.insert_one(doc)
    return pid


async def _customer(db, partner_id, seats, used=0, cid="c1"):
    doc = {"id": cid, "name": f"Customer {cid}", "maxAgents": seats,
           "license": {"maxAgents": seats, "seatsUsed": used, "inactiveReclaimDays": 30}}
    if partner_id:
        doc["partnerId"] = partner_id
    await db.tenants.insert_one(doc)
    return cid


async def _allocated(db, pid="p1"):
    return (await db.tenants.find_one({"id": pid}))["partner"]["allocated"]


async def _seats(db, cid="c1"):
    return (await db.tenants.find_one({"id": cid}))["license"]["maxAgents"]


def _body(resp):
    return json.loads(resp.body)


async def test_create_tenant_uses_the_shared_builder_and_stores_the_same_fields(wired):
    import tenant_docs
    with patch.object(tenant_docs, "build_tenant_doc", wraps=tenant_docs.build_tenant_doc) as builder:
        out = await te.create_tenant(te.TenantCreate(name="Direct Co", maxAgents=7), current_user=SUPER)
    assert builder.call_count == 1
    stored = await wired.tenants.find_one({"id": out["id"]}, {"_id": 0})
    assert set(stored) == PRE_CHANGE_KEYS and "partnerId" not in stored
    assert stored["license"]["maxAgents"] == 7 and stored["registrationKey"].startswith("reg_")


async def test_patch_seats_on_a_partner_customer_claims_the_pool(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    out = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=50), current_user=SUPER)
    assert out["maxAgents"] == 50
    assert (await _seats(wired), await _allocated(wired)) == (50, 95)


async def test_patch_past_the_pool_answers_pool_full_and_changes_nothing(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    resp = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=80), current_user=SUPER)
    assert resp.status_code == 409
    body = _body(resp)
    assert body["code"] == "pool_full" and body["free"] == 25
    assert (await _seats(wired), await _allocated(wired)) == (30, 75)


async def test_patch_below_the_seats_used_succeeds_and_returns_the_seats(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30, used=30)
    out = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=10), current_user=SUPER)
    assert (out["maxAgents"], out["seatsUsed"]) == (10, 30)
    assert (await _seats(wired), await _allocated(wired)) == (10, 55)


async def test_a_raise_ignores_the_partners_suspension_and_expiry_but_not_the_pool_total(wired):
    await _partner(wired, pool=100, allocated=75, status="suspended", expires="2020-01-01T00:00:00+00:00")
    await _customer(wired, "p1", 30)
    await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=40), current_user=SUPER)
    assert (await _seats(wired), await _allocated(wired)) == (40, 85)
    resp = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=200), current_user=SUPER)
    assert resp.status_code == 409 and _body(resp)["code"] == "pool_full"


async def test_patching_only_the_reclaim_window_never_touches_the_pool(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    with patch("partner_pool.change_allotment", new=AsyncMock()) as change:
        out = await te.update_tenant_license("c1", te.LicenseUpdate(inactiveReclaimDays=14), current_user=SUPER)
    assert out["inactiveReclaimDays"] == 14 and change.await_count == 0
    assert (await _seats(wired), await _allocated(wired)) == (30, 75)


async def test_a_direct_customer_is_patched_as_before(wired):
    await _customer(wired, None, 5)
    out = await te.update_tenant_license("c1", te.LicenseUpdate(maxAgents=500), current_user=SUPER)
    assert out["maxAgents"] == 500 and await _seats(wired) == 500


async def test_deleting_a_partner_customer_returns_its_seats_to_the_pool(wired):
    await _partner(wired, pool=100, allocated=75)
    await _customer(wired, "p1", 30)
    await te.delete_tenant("c1", current_user=SUPER)
    assert await wired.tenants.find_one({"id": "c1"}) is None
    assert await _allocated(wired) == 45


async def test_deleting_a_partner_with_customers_is_refused_and_deletes_nothing(wired):
    await _partner(wired, pool=100, allocated=30)
    await _customer(wired, "p1", 30)
    with pytest.raises(HTTPException) as exc:
        await te.delete_tenant("p1", current_user=SUPER)
    assert exc.value.status_code == 409 and exc.value.detail == "Move this partner's customers first."
    assert await wired.tenants.find_one({"id": "p1"}) is not None
    assert await _seats(wired) == 30


async def test_deleting_a_partner_without_customers_works(wired):
    await _partner(wired, pool=100, allocated=0)
    await te.delete_tenant("p1", current_user=SUPER)
    assert await wired.tenants.find_one({"id": "p1"}) is None


# ── approve-and-raise draws from the pool ────────────────────────────────────

async def _pending(db, cid="c1", agent_id="a1"):
    await db.agents.insert_one({"id": agent_id, "tenantId": cid, "hostname": f"host-{agent_id}",
                                "status": "Pending", "pendingReason": "seat_limit"})


async def test_approve_with_a_raise_claims_the_extra_seats_from_the_pool(wired):
    import pending_agents
    await _partner(wired, pool=100, allocated=98)
    await _customer(wired, "p1", 10, used=10)
    await _pending(wired)
    out = await pending_agents.approve(wired, "a1", "root", raise_limit_by=2)
    assert out["status"] == "Offline" and out["license"]["maxAgents"] == 12
    assert (await _seats(wired), await _allocated(wired)) == (12, 100)
    assert (await wired.tenants.find_one({"id": "c1"}))["license"]["seatsUsed"] == 11


async def test_approve_with_a_raise_the_pool_cannot_fit_is_refused_and_changes_nothing(wired):
    import pending_agents
    await _partner(wired, pool=100, allocated=99)
    await _customer(wired, "p1", 10, used=10)
    await _pending(wired)
    with pytest.raises(pending_agents.DecisionError) as exc:
        await pending_agents.approve(wired, "a1", "root", raise_limit_by=2)
    assert exc.value.status_code == 409 and exc.value.detail.startswith("no_free_seat")
    assert exc.value.extra["maxAgents"] == 10
    assert (await _seats(wired), await _allocated(wired)) == (10, 99)
    assert (await wired.agents.find_one({"id": "a1"}))["status"] == "Pending"


async def test_approve_with_a_raise_ignores_the_partners_suspension(wired):
    import pending_agents
    await _partner(wired, pool=100, allocated=90, status="suspended")
    await _customer(wired, "p1", 10, used=10)
    await _pending(wired)
    await pending_agents.approve(wired, "a1", "root", raise_limit_by=1)
    assert (await _seats(wired), await _allocated(wired)) == (11, 91)


async def test_approve_with_a_raise_on_a_direct_customer_is_unchanged(wired):
    import pending_agents
    await _customer(wired, None, 10, used=10)
    await _pending(wired)
    out = await pending_agents.approve(wired, "a1", "root", raise_limit_by=3)
    assert out["license"]["maxAgents"] == 13 and await _seats(wired) == 13
    assert (await wired.tenants.find_one({"id": "c1"}))["maxAgents"] == 13


# ── MSSP lists skip partner organizations ────────────────────────────────────

async def test_mssp_listings_never_show_a_partner_organization(mongo_db):
    import mssp_endpoints as mssp
    await _partner(mongo_db, pid="p1")
    await _customer(mongo_db, "p1", 5, cid="c1")
    await _customer(mongo_db, None, 5, cid="c2")
    await mongo_db.alerts.insert_one({"id": "al1", "tenantId": "c1", "severity": "High", "timestamp": "2026-01-01"})
    with patch.object(mssp, "get_database", return_value=mongo_db):
        listed = await mssp.list_managed_tenants(current_user=SUPER)
        overview = await mssp.mssp_overview(current_user=SUPER)
        alerts = await mssp.aggregated_alerts(severity=None, limit=50, current_user=SUPER)
    assert sorted(t["id"] for t in listed) == ["c1", "c2"]
    assert sorted(t["id"] for t in overview["tenants"]) == ["c1", "c2"] and overview["total_tenants"] == 2
    assert [a["tenant_name"] for a in alerts] == ["Customer c1"]


async def test_mssp_alert_feed_does_not_resolve_a_partner_name(mongo_db):
    """An alert whose tenantId is a partner organization falls back to the id, never the partner's name."""
    import mssp_endpoints as mssp
    await _partner(mongo_db, pid="p1")
    await mongo_db.alerts.insert_one({"id": "al2", "tenantId": "p1", "severity": "High", "timestamp": "2026-01-01"})
    with patch.object(mssp, "get_database", return_value=mongo_db):
        alerts = await mssp.aggregated_alerts(severity=None, limit=50, current_user=SUPER)
    assert all(a["tenant_name"] != "Partner p1" for a in alerts)


# ── drift guard: only the allowlisted modules write a customer's seats ───────

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
SEAT_WRITER_ALLOWLIST = {"licensing.py", "partner_pool.py", "tenant_docs.py", "pending_agents.py",
                         "authentication_endpoints.py"}
# Modules the scanner must always see, so a scanner that goes blind cannot pass the test.
SEAT_WRITERS_KNOWN = {"licensing.py", "partner_pool.py", "tenant_docs.py", "pending_agents.py"}
_SKIP_FILES = {"database_migrations.py"}


def _str_key(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def writes_license_max_agents(source: str) -> bool:
    """True when the source builds a dict that sets license.maxAgents: a "license.maxAgents" key (the
    $set / $inc form) or a "license": {"maxAgents": ...} literal. A literal 0 is not a seat grant (the
    partner organization carries no seats of its own) and is ignored."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            name = _str_key(key)
            if name == "license.maxAgents":
                return True
            if name == "license" and isinstance(value, ast.Dict):
                for k2, v2 in zip(value.keys, value.values):
                    if _str_key(k2) == "maxAgents" and not (isinstance(v2, ast.Constant) and v2.value == 0):
                        return True
    return False


def seat_writer_modules(root: str) -> set:
    """Backend modules are flat files in backend/ (tests, scripts and migrations live in sub-folders,
    and the folder also holds virtualenvs that must not be walked), so only its top level is scanned."""
    found = set()
    for fn in sorted(os.listdir(root)):
        path = os.path.join(root, fn)
        if not fn.endswith(".py") or fn in _SKIP_FILES or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            try:
                if writes_license_max_agents(fh.read()):
                    found.add(fn)
            except (SyntaxError, ValueError):
                continue
    return found


def test_only_the_allowlisted_modules_write_license_max_agents():
    found = seat_writer_modules(BACKEND_DIR)
    assert found - SEAT_WRITER_ALLOWLIST == set(), (
        f"{sorted(found - SEAT_WRITER_ALLOWLIST)} write license.maxAgents outside the partner pool's reach; "
        "route the change through partner_pool.change_allotment (or licensing.update_license for a direct customer)")
    assert SEAT_WRITERS_KNOWN <= found, f"the scanner no longer sees {sorted(SEAT_WRITERS_KNOWN - found)}"


def test_the_drift_scanner_catches_a_new_writer_and_ignores_a_zero_literal(tmp_path):
    (tmp_path / "rogue_set.py").write_text(
        "async def f(db):\n    await db.tenants.update_one({'id': 1}, {'$set': {'license.maxAgents': 99}})\n")
    (tmp_path / "rogue_inc.py").write_text(
        "async def f(db):\n    await db.tenants.update_one({'id': 1}, {'$inc': {'license.maxAgents': 5}})\n")
    (tmp_path / "rogue_literal.py").write_text("DOC = {'id': 1, 'license': {'maxAgents': 50, 'seatsUsed': 0}}\n")
    (tmp_path / "zero_literal.py").write_text("DOC = {'id': 1, 'license': {'maxAgents': 0}}\n")
    (tmp_path / "unrelated.py").write_text("X = {'maxAgents': 5}\n")
    assert seat_writer_modules(str(tmp_path)) == {"rogue_set.py", "rogue_inc.py", "rogue_literal.py"}
