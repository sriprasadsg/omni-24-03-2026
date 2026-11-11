"""Phase 87 plan 09 task 2: a partner sells screens only within its ceiling (real MongoDB).

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Route functions are called with a TokenData; the audit writer and
the invite mailer are mocked.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
import tenant_features as tf
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

START = list(tf.START_FEATURES)
CEILING = ["view:agents", "screen:agents", "view:assets"]


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(pe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)):
        yield SimpleNamespace(db=mongo_db, audit=audit)


def _body(response):
    return json.loads(response.body)


async def _partner(wired, pid="partner_a", ceiling=tuple(CEILING)):
    await wired.db.tenants.insert_one({
        "id": pid, "type": "partner", "name": f"Partner {pid}", "license": {"maxAgents": 0},
        "partner": {"poolSize": 100, "allocated": 0, "status": "active", "screenCeiling": list(ceiling),
                    "expiresAt": None},
    })


async def _customer(wired, cid="c1", partner="partner_a", features=tuple(START), tier=None):
    await wired.db.tenants.insert_one({
        "id": cid, "name": f"Customer {cid}", "partnerId": partner, "license": {"maxAgents": 5, "seatsUsed": 0},
        "enabledFeatures": list(features), "registrationKey": "reg_secret",
        **({"subscriptionTier": tier} if tier else {}),
    })


async def _ctx(pid="partner_a", role="partner_admin"):
    return await pe.current_partner(
        current_user=TokenData(username=f"{role}@retail.test", role=role, tenant_id=pid, mfa_verified=True))


async def _put(cid, features, role="partner_admin", pid="partner_a"):
    return await pe.put_customer_features(cid, pe.FeaturesBody(enabledFeatures=features),
                                          ctx=await _ctx(pid, role))


async def _stored(wired, cid="c1"):
    return (await wired.db.tenants.find_one({"id": cid}))["enabledFeatures"]


# --- PART-06: the ceiling ------------------------------------------------------------------------

def test_every_switch_has_a_label_for_refusal_messages():
    """protects=the SWITCH_LABELS constant covers the whole vocabulary; fails_when=a refusal cannot name a screen."""
    assert set(tf.SWITCH_LABELS) == set(tf.SWITCHABLE)
    assert all(isinstance(label, str) and label for label in tf.SWITCH_LABELS.values())


async def test_a_list_equal_to_the_ceiling_plus_the_start_screens_is_accepted(wired):
    """protects=D-10 adjacency; fails_when=the exact ceiling is refused or stored in another order."""
    await _partner(wired)
    await _customer(wired)
    out = await _put("c1", ["view:assets", "view:agents", "screen:agents", "view:agents", *START])
    assert out["enabledFeatures"] == ["view:assets", "view:agents", "screen:agents", *START]
    assert await _stored(wired) == out["enabledFeatures"]
    assert out["ceiling"] == CEILING and out["unrestricted"] is False and out["kept"] == []
    changed = [c for c in wired.audit.await_args_list if c.args[0] == "partner.customer_screens_changed"]
    assert len(changed) == 1 and changed[0].args[1] == "partner_a"


async def test_one_string_beyond_the_ceiling_is_refused_naming_the_screen(wired):
    """protects=T-87-27; fails_when=a screen outside the ceiling is stored."""
    await _partner(wired)
    await _customer(wired)
    refused = await _put("c1", [*CEILING, "screen:chat"])
    assert refused.status_code == 422
    assert _body(refused)["code"] == "screen_outside_ceiling"
    assert _body(refused)["error"] == f"{tf.SWITCH_LABELS['screen:chat']} is not one of the screens you can sell."
    assert await _stored(wired) == START


async def test_an_empty_list_stores_the_start_screens_and_an_empty_ceiling_allows_nothing_else(wired):
    """protects=PART-06 empty; fails_when=an empty list wipes the start screens or an empty ceiling sells a screen."""
    await _partner(wired, ceiling=())
    await _customer(wired, features=("view:dashboard",))
    out = await _put("c1", [])
    assert out["enabledFeatures"] == START and out["ceiling"] == []
    refused = await _put("c1", ["view:agents"])
    assert refused.status_code == 422 and _body(refused)["code"] == "screen_outside_ceiling"
    assert await _stored(wired) == START


async def test_screens_outside_the_ceiling_the_customer_already_has_are_kept(wired):
    """protects=D-19; fails_when=an omitted kept screen disappears, or the order is not
    submitted, kept, missing start."""
    await _partner(wired)
    await _customer(wired, features=("view:dashboard", "view:tickets", "view:agents", "screen:agents"))
    got = await pe.get_customer_features("c1", ctx=await _ctx())
    assert got["kept"] == ["view:tickets"] and got["ceiling"] == CEILING
    out = await _put("c1", ["view:agents", "screen:agents"])
    assert out["enabledFeatures"] == ["view:agents", "screen:agents", "view:tickets", *START]
    assert out["kept"] == ["view:tickets"]
    assert await _stored(wired) == out["enabledFeatures"]
    again = await _put("c1", ["view:agents", "screen:agents", "view:tickets"])  # a kept screen may be re-sent
    assert again["enabledFeatures"] == ["view:agents", "screen:agents", "view:tickets", *START]


async def test_all_and_unknown_strings_are_refused(wired):
    """protects=T-87-27 vocabulary; fails_when='all' or an invented string is stored, even for an unrestricted ceiling."""
    await _partner(wired, ceiling=("all",))
    await _customer(wired)
    for bad in ("all", "screen:nope", ""):
        refused = await _put("c1", ["view:agents", bad])
        assert refused.status_code == 422 and _body(refused)["code"] == "invalid_screen", bad
    assert await _stored(wired) == START


async def test_a_switch_whose_parent_is_missing_is_refused_naming_both(wired):
    """protects=the switch tree; fails_when=a child is stored without its parent."""
    await _partner(wired)
    await _customer(wired)
    refused = await _put("c1", ["screen:agents"])
    assert refused.status_code == 422 and _body(refused)["code"] == "missing_parent"
    assert _body(refused)["error"] == f"{tf.SWITCH_LABELS['screen:agents']} needs {tf.SWITCH_LABELS['view:agents']}."
    assert await _stored(wired) == START


async def test_an_unrestricted_partner_may_sell_any_switch(wired):
    await _partner(wired, ceiling=("all",))
    await _customer(wired, tier="Enterprise")  # view:reporting is an Enterprise-plan screen too (D-30)
    out = await _put("c1", ["view:agents", "screen:chat", "view:reporting"])
    assert out["unrestricted"] is True and out["ceiling"] == ["all"]
    assert out["enabledFeatures"][:3] == ["view:agents", "screen:chat", "view:reporting"]


async def test_a_viewer_reads_the_screens_but_cannot_change_them(wired):
    await _partner(wired)
    await _customer(wired)
    got = await pe.get_customer_features("c1", ctx=await _ctx(role="partner_viewer"))
    assert set(got) == {"enabledFeatures", "ceiling", "unrestricted", "kept", "plan", "planScreens"}
    with pytest.raises(HTTPException) as exc:
        await _put("c1", ["view:agents"], role="partner_viewer")
    assert exc.value.status_code == 403


async def test_another_partners_customer_answers_like_an_unknown_id(wired):
    """protects=T-87-26; fails_when=the answers differ or the foreign document changes."""
    await _partner(wired)
    await _partner(wired, pid="partner_b")
    await _customer(wired, cid="theirs", partner="partner_b")
    foreign = await pe.get_customer_features("theirs", ctx=await _ctx())
    unknown = await pe.get_customer_features("missing", ctx=await _ctx())
    assert foreign.status_code == unknown.status_code == 404 and _body(foreign) == _body(unknown)
    foreign = await _put("theirs", ["view:agents"])
    unknown = await _put("missing", ["view:agents"])
    assert foreign.status_code == unknown.status_code == 404 and _body(foreign) == _body(unknown)
    assert await _stored(wired, "theirs") == START


async def test_the_features_answer_carries_no_secret(wired):
    await _partner(wired)
    await _customer(wired)
    out = await _put("c1", ["view:agents"])
    assert "reg_secret" not in json.dumps(out) and set(out) == {"enabledFeatures", "ceiling", "unrestricted", "kept", "plan", "planScreens"}


async def test_creation_validates_the_screens_with_the_same_rules(wired):
    """protects=PART-06 on create; fails_when=a creation stores a screen outside the ceiling or claims seats first."""
    await _partner(wired)
    base = dict(name="Cafe One", seats=5, adminName="Owner")
    refused = await pe.post_customer(pe.CustomerCreate(**base, adminEmail="a@cafe.test",
                                                       enabledFeatures=["screen:chat"]), ctx=await _ctx())
    assert refused.status_code == 422 and _body(refused)["code"] == "screen_outside_ceiling"
    assert (await wired.db.tenants.find_one({"id": "partner_a"}))["partner"]["allocated"] == 0
    made = await pe.post_customer(pe.CustomerCreate(**base, adminEmail="a@cafe.test",
                                                    enabledFeatures=["view:agents", "screen:agents"]), ctx=await _ctx())
    assert (await _stored(wired, made["customer"]["id"])) == ["view:agents", "screen:agents", *START]
