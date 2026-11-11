"""Phase 88 plan 10: plans inside the partner channel (real MongoDB).

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import partner_endpoints as pe
import partner_platform_endpoints as ppe
import partner_store
from auth_types import TokenData
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

SUPER = TokenData(username="root@example.com", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)


@pytest.fixture
def wired(mongo_db):  # noqa: F811
    handle = SimpleNamespace(db=mongo_db)
    with patch.object(ppe, "mongodb", handle), patch.object(pe, "mongodb", handle), \
            patch("audit_ledger.event", new=AsyncMock()) as audit, \
            patch("partner_invites.send_invite_email", new=AsyncMock(return_value=False)):
        yield SimpleNamespace(db=mongo_db, audit=audit)


def _body(response):
    return json.loads(response.body)


def _actions(wired, action, tenant=None):
    return [c for c in wired.audit.await_args_list
            if c.args[0] == action and (tenant is None or c.args[1] == tenant)]


async def _appoint(name="Retailer A", **extra):
    out = await ppe.create_partner(
        ppe.PartnerCreate(name=name, poolSize=100, screenCeiling=["all"], adminName="Bo Boss",
                          adminEmail=f"boss@{name.lower().replace(' ', '')}.test", **extra),
        current_user=SUPER)
    return out["partner"]


async def _stored_partner(wired, pid):
    return (await wired.db.tenants.find_one({"id": pid}))["partner"]


# --- Task 1: the Super Admin sets each partner's plan ceiling (D-13) ---------------------------------------

async def test_appointing_with_a_plan_ceiling_stores_canonical_keys_in_order(wired):
    """protects=D-13 the ceiling is stored as canonical plan keys; fails_when=case is kept or a duplicate stays."""
    summary = await _appoint(planCeiling=["Pro", "free", "PRO"])
    assert (await _stored_partner(wired, summary["id"]))["planCeiling"] == ["Pro", "Free"]
    assert summary["planCeiling"] == ["Pro", "Free"]


async def test_appointing_without_a_plan_ceiling_stores_free_only(wired):
    """protects=an omitted ceiling is ['Free']; fails_when=a partner can sell paid plans by default."""
    summary = await _appoint()
    assert (await _stored_partner(wired, summary["id"]))["planCeiling"] == ["Free"]
    assert summary["planCeiling"] == ["Free"]


async def test_an_unknown_plan_at_appointment_is_refused_before_anything_is_written(wired):
    """protects=422 invalid_plan with no partner stored; fails_when=a half-appointed partner remains."""
    out = await ppe.create_partner(
        ppe.PartnerCreate(name="Bad", poolSize=5, screenCeiling=["all"], adminName="Bo", adminEmail="bo@bad.test",
                          planCeiling=["Gold"]), current_user=SUPER)
    assert out.status_code == 422 and _body(out)["code"] == "invalid_plan"
    assert await wired.db.tenants.count_documents({"type": "partner"}) == 0


async def test_editing_the_plan_ceiling_stores_it_and_records_the_change_on_both_ledgers(wired):
    """protects=D-13 update records before and after; fails_when=no ledger entry or the platform ledger is missed."""
    pid = (await _appoint())["id"]
    out = await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=["Free", "Pro", "Enterprise"]), current_user=SUPER)
    assert out["partner"]["planCeiling"] == ["Free", "Pro", "Enterprise"]
    assert (await _stored_partner(wired, pid))["planCeiling"] == ["Free", "Pro", "Enterprise"]
    changed = _actions(wired, "partner.plan_ceiling_changed")
    assert {c.args[1] for c in changed} == {pid, "platform-admin"}
    assert changed[0].kwargs["before"] == ["Free"] and changed[0].kwargs["after"] == ["Free", "Pro", "Enterprise"]


async def test_an_unknown_plan_in_an_edit_is_refused_and_changes_nothing(wired):
    """protects=422 invalid_plan; fails_when=the stored ceiling changes or an event is recorded."""
    pid = (await _appoint())["id"]
    out = await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=["Gold"]), current_user=SUPER)
    assert out.status_code == 422 and _body(out)["code"] == "invalid_plan"
    assert (await _stored_partner(wired, pid))["planCeiling"] == ["Free"]
    assert _actions(wired, "partner.plan_ceiling_changed") == []


async def test_saving_the_same_ceiling_again_records_nothing(wired):
    """protects=no noise in the ledger; fails_when=an unchanged list is recorded as a change."""
    pid = (await _appoint(planCeiling=["Free", "Pro"]))["id"]
    await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=["free", "pro"]), current_user=SUPER)
    assert _actions(wired, "partner.plan_ceiling_changed") == []


async def test_an_empty_ceiling_is_allowed_and_means_no_plan_changes(wired):
    """protects=an empty list is stored as given; fails_when=it is replaced by the default."""
    pid = (await _appoint())["id"]
    out = await ppe.update_partner(pid, ppe.PartnerUpdate(planCeiling=[]), current_user=SUPER)
    assert out["partner"]["planCeiling"] == []
    assert (await _stored_partner(wired, pid))["planCeiling"] == []


async def test_a_partner_stored_before_phase_88_summarizes_as_free_only(wired):
    """protects=A-88-PLAN-CEILING-DEFAULT, fail closed; fails_when=the summary invents paid plans or omits the field."""
    doc = {"id": "partner_old", "name": "Old", "type": "partner", "partner": {"poolSize": 5, "allocated": 0}}
    assert partner_store.plan_ceiling(doc) == ["Free"]
    assert partner_store.partner_summary(doc, 0)["planCeiling"] == ["Free"]
    assert partner_store.partner_summary({**doc, "partner": {"planCeiling": ["Pro"]}}, 0)["planCeiling"] == ["Pro"]
