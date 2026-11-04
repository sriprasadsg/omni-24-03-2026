"""Phase 87 plan 08: the Super Admin lists a partner's customers, finds direct customers and moves them (real MongoDB).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Route functions are called with a TokenData; the audit writer
and the invite mailer are mocked, so nothing reaches the live database or a mail server.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_platform_endpoints as ppe
import partner_store
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
PARTNER_ADMIN = TokenData(username="boss@retail.test", role="partner_admin", tenant_id="partner_x", mfa_verified=True)
SUPPORT = TokenData(username="help@example.com", role="platform_support", tenant_id="platform-admin", mfa_verified=True)


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(ppe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)):
        yield SimpleNamespace(db=mongo_db, audit=audit)


def _body(response):
    return json.loads(response.body)


async def _partner(wired, pid, name, pool, allocated=0, status="active"):
    await wired.db.tenants.insert_one({
        "id": pid, "type": "partner", "name": name, "license": {"maxAgents": 0}, "maxAgents": 0,
        "partner": {"poolSize": pool, "allocated": allocated, "status": status, "screenCeiling": ["all"], "expiresAt": None},
    })


async def _customer(wired, cid, name, seats, partner_id=None, features=("view:agents", "view:tickets")):
    doc = {"id": cid, "name": name, "license": {"maxAgents": seats, "seatsUsed": 1}, "maxAgents": seats,
           "enabledFeatures": list(features)}
    if partner_id:
        doc["partnerId"] = partner_id
    await wired.db.tenants.insert_one(doc)


async def _allocated(wired, pid):
    return (await wired.db.tenants.find_one({"id": pid}))["partner"]["allocated"]


async def _move(customer_id, target):
    return await ppe.move_customer(customer_id, ppe.MoveBody(targetPartnerId=target), current_user=SUPER)


def _moved(wired, tenant=None):
    return [c for c in wired.audit.await_args_list
            if c.args[0] == "partner.customer_moved" and (tenant is None or c.args[1] == tenant)]


# --- the customer lists --------------------------------------------------------------------------

async def test_a_partners_customers_carry_exactly_the_d01_fields(wired):
    await _partner(wired, "partner_a", "A", 50, allocated=7)
    await _customer(wired, "c_b", "bravo", 3, "partner_a")
    await _customer(wired, "c_a", "Alpha", 4, "partner_a")
    await _customer(wired, "c_other", "Other", 2)
    out = await ppe.get_partner_customers("partner_a", current_user=SUPER)
    assert [row["name"] for row in out["customers"]] == ["Alpha", "bravo"]
    assert all(tuple(row) == partner_store.CUSTOMER_FIELDS for row in out["customers"])
    assert out["customers"][0]["seatsAssigned"] == 4


async def test_an_unknown_partner_or_a_customer_id_is_a_404(wired):
    await _customer(wired, "c1", "Cafe", 1)
    for missing in ("nope", "c1"):
        refused = await ppe.get_partner_customers(missing, current_user=SUPER)
        assert refused.status_code == 404 and _body(refused)["code"] == "not_found"


async def test_direct_customers_exclude_partners_partner_customers_and_the_platform(wired):
    # protects=only organizations with no partner are offered to "Add existing customer"
    await _partner(wired, "partner_a", "A", 50, allocated=3)
    await wired.db.tenants.insert_one({"id": "platform-admin", "name": "Platform"})
    await _customer(wired, "c_in", "Owned", 3, "partner_a")
    await _customer(wired, "c_z", "zulu", 5)
    await _customer(wired, "c_a", "Alpha", 9)
    out = await ppe.get_direct_customers(current_user=SUPER)
    assert out == {"customers": [{"id": "c_a", "name": "Alpha", "seatsAssigned": 9},
                                 {"id": "c_z", "name": "zulu", "seatsAssigned": 5}]}


async def test_no_direct_customers_is_an_empty_list(wired):
    await _partner(wired, "partner_a", "A", 50)
    assert await ppe.get_direct_customers(current_user=SUPER) == {"customers": []}


# --- moves ---------------------------------------------------------------------------------------

async def test_a_move_that_fits_exactly_transfers_the_seats_and_the_customer(wired):
    # protects=D-11 / D-18 / D-19 with the boundary: free == needed; fails_when=counters drift or screens change
    await _partner(wired, "partner_a", "A", 50, allocated=10)
    await _partner(wired, "partner_b", "B", 10, allocated=0)
    await _customer(wired, "c1", "Cafe", 10, "partner_a")
    out = await _move("c1", "partner_b")
    assert out == {"customer": {"id": "c1", "name": "Cafe", "partnerId": "partner_b"}}
    assert await _allocated(wired, "partner_a") == 0 and await _allocated(wired, "partner_b") == 10
    doc = await wired.db.tenants.find_one({"id": "c1"})
    assert doc["partnerId"] == "partner_b" and doc["license"]["maxAgents"] == 10
    assert doc["enabledFeatures"] == ["view:agents", "view:tickets"]


async def test_after_a_move_the_old_partner_no_longer_lists_the_customer(wired):
    # protects=adjacency; fails_when=a stale list on either side
    await _partner(wired, "partner_a", "A", 50, allocated=4)
    await _partner(wired, "partner_b", "B", 50)
    await _customer(wired, "c1", "Cafe", 4, "partner_a")
    await _move("c1", "partner_b")
    assert (await ppe.get_partner_customers("partner_a", current_user=SUPER))["customers"] == []
    assert [r["id"] for r in (await ppe.get_partner_customers("partner_b", current_user=SUPER))["customers"]] == ["c1"]
    assert [p["customerCount"] for p in (await ppe.list_partners(current_user=SUPER))["partners"]] == [0, 1]


async def test_one_seat_too_few_free_refuses_and_changes_nothing(wired):
    await _partner(wired, "partner_a", "A", 50, allocated=10)
    await _partner(wired, "partner_b", "Beta", 10, allocated=1)
    await _customer(wired, "c1", "Cafe", 10, "partner_a")
    refused = await _move("c1", "partner_b")
    body = _body(refused)
    assert refused.status_code == 409 and body["code"] == "move_does_not_fit" and body["free"] == 9 and body["needed"] == 10
    assert "Beta" in body["error"] and "Cafe" in body["error"]
    assert (await wired.db.tenants.find_one({"id": "c1"}))["partnerId"] == "partner_a"
    assert await _allocated(wired, "partner_a") == 10 and await _allocated(wired, "partner_b") == 1
    assert _moved(wired) == []


async def test_a_move_to_direct_keeps_the_seats_as_the_customers_own_licence(wired):
    await _partner(wired, "partner_a", "A", 50, allocated=6)
    await _customer(wired, "c1", "Cafe", 6, "partner_a")
    out = await _move("c1", None)
    assert out["customer"]["partnerId"] is None
    doc = await wired.db.tenants.find_one({"id": "c1"})
    assert "partnerId" not in doc and doc["license"]["maxAgents"] == 6 and doc["maxAgents"] == 6
    assert await _allocated(wired, "partner_a") == 0
    assert [c["id"] for c in (await ppe.get_direct_customers(current_user=SUPER))["customers"]] == ["c1"]


async def test_adding_a_direct_customer_to_a_partner_claims_its_seats(wired):
    await _partner(wired, "partner_a", "A", 10, allocated=2)
    await _customer(wired, "c1", "Cafe", 8)
    await _customer(wired, "c2", "Diner", 1)
    await _move("c1", "partner_a")
    assert await _allocated(wired, "partner_a") == 10
    refused = await _move("c2", "partner_a")
    assert refused.status_code == 409 and _body(refused)["code"] == "move_does_not_fit" and _body(refused)["free"] == 0
    assert "partnerId" not in await wired.db.tenants.find_one({"id": "c2"})


async def test_a_customer_with_no_seats_moves_with_the_counters_unchanged(wired):
    await _partner(wired, "partner_a", "A", 5, allocated=5)
    await _partner(wired, "partner_b", "B", 5, allocated=0)
    await _customer(wired, "c0", "Empty", 0, "partner_a")
    await _move("c0", "partner_b")
    assert await _allocated(wired, "partner_a") == 5 and await _allocated(wired, "partner_b") == 0
    assert (await wired.db.tenants.find_one({"id": "c0"}))["partnerId"] == "partner_b"


async def test_a_customer_with_no_seats_cannot_move_into_a_suspended_partner(wired):
    # protects=87 WR-05, a suspended partner takes no new customer whatever its seats; fails_when=a 0-seat
    # claim skips the suspension check and partnerId is written; no_claim=the partner portal's own routes
    await _partner(wired, "partner_a", "A", 5, allocated=0)
    await _partner(wired, "partner_s", "Susp", 50, status="suspended")
    await _customer(wired, "c0", "Empty", 0, "partner_a")
    refused = await _move("c0", "partner_s")
    assert (refused.status_code, _body(refused)["code"]) == (409, "partner_suspended")
    assert (await wired.db.tenants.find_one({"id": "c0"}))["partnerId"] == "partner_a"


async def test_a_move_is_refused_for_the_wrong_target_or_customer(wired):
    await _partner(wired, "partner_a", "A", 50, allocated=2)
    await _partner(wired, "partner_s", "Susp", 50, status="suspended")
    await _customer(wired, "c1", "Cafe", 2, "partner_a")
    await wired.db.tenants.insert_one({"id": "platform-admin", "name": "Platform"})
    cases = [("c1", "partner_a", 409, "same_partner"), ("c1", "partner_s", 409, "partner_suspended"),
             ("c1", "nope", 404, "not_found"), ("c1", "c1", 404, "not_found"),
             ("nope", "partner_a", 404, "not_found"), ("partner_a", "partner_s", 404, "not_found"),
             ("platform-admin", "partner_a", 404, "not_found")]
    for customer, target, status, code in cases:
        refused = await _move(customer, target)
        assert (refused.status_code, _body(refused)["code"]) == (status, code), (customer, target)
    assert (await wired.db.tenants.find_one({"id": "c1"}))["partnerId"] == "partner_a"
    assert await _allocated(wired, "partner_a") == 2


async def test_the_target_must_be_named_explicitly(wired):
    # protects=an empty body never turns a partner customer into a direct one; fails_when=the field defaults to null
    with pytest.raises(ValidationError):
        ppe.MoveBody()
    with pytest.raises(ValidationError):
        ppe.MoveBody(targetPartnerId="x" * 65)


# --- the audit trail -----------------------------------------------------------------------------

async def test_every_move_is_recorded_under_the_platform_and_each_partner(wired):
    await _partner(wired, "partner_a", "A", 50, allocated=5)
    await _partner(wired, "partner_b", "B", 50)
    await _customer(wired, "c1", "Cafe", 5, "partner_a")
    await _move("c1", "partner_b")
    moved = _moved(wired)
    assert sorted(c.args[1] for c in moved) == ["partner_a", "partner_b", "platform-admin"]
    assert all(c.kwargs["seats"] == 5 and c.kwargs["from"] == "partner_a" and c.kwargs["to"] == "partner_b"
               and c.kwargs["customerId"] == "c1" for c in moved)
    await _move("c1", None)  # to direct: the platform and the old partner only
    await _customer(wired, "c2", "Diner", 1)
    await _move("c2", "partner_a")  # from direct: the platform and the new partner only
    later = _moved(wired)[3:]
    assert sorted(c.args[1] for c in later[:2]) == ["partner_b", "platform-admin"]
    assert sorted(c.args[1] for c in later[2:]) == ["partner_a", "platform-admin"]
    assert later[0].kwargs["to"] is None and later[2].kwargs["from"] is None


async def test_only_the_super_admin_reaches_the_customer_routes(wired):
    await _partner(wired, "partner_a", "A", 5)
    for user in (PARTNER_ADMIN, SUPPORT):
        for call in (lambda: ppe.get_partner_customers("partner_a", current_user=user),
                     lambda: ppe.get_direct_customers(current_user=user),
                     lambda: ppe.move_customer("c1", ppe.MoveBody(targetPartnerId=None), current_user=user)):
            with pytest.raises(HTTPException) as exc:
                await call()
            assert exc.value.status_code == 403
