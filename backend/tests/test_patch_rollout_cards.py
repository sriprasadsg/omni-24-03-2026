"""Staged patch rollouts, plan 84-10: the rollout approval cards and the line approve and deny routes.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. The card payload is
built from the real approval rows a controller tick raises; the routes are mounted as in production (behind the
Autonomous Ops catalogue guard) with the caller's identity replaced by a dependency override, so the real
permission checks run.

Value: protects=PTCH-06 / D-07 / D-08 / T-84-33 / T-84-34 / T-84-35 / PROH-84-04c: a person with approval rights
sees one card per waiting ring with every line spelled out and decides a whole line with one request, exactly
once; a view-only person, an API key, a stop, a bad path or another organization's rollout can decide nothing;
fails_when=a line shows a flag the caller does not hold, a reboot line shows before it is raised, a settled
line loses its result text, a key or a viewer approves, or one request reaches more than one line;
no_claim=the card on screen (84-15) and the agent receiving the instruction.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import views as ops_views
from autonomous_ops.rollout import cards, controller, dispatcher, lines, reboots, store
from tests._autonomous_ops_http import _env, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.rollout_support import seed_rollout_tenant
from tests.test_patch_rollout_lines import (APPROVER, NOW, T, base, begin, host, online_at, pass_the_canary,
                                            rows)

PATCHES = ("openssl", "curl", "bash", "zlib", "nginx")


@pytest.fixture
def clock(monkeypatch):
    """The dispatcher's own clock (``approvals.approve`` hands it none): set ``clock["now"]`` to freeze it."""
    state = {"now": None}
    real = dispatcher._now

    def fake(now=None):
        return real(state["now"] if now is None and state["now"] is not None else now)

    monkeypatch.setattr(dispatcher, "_now", fake)
    return state


def caller(*, control=True, interactive=True, staff=False):
    return ops_views.Caller(user=None, tier="owner" if staff else None, interactive=interactive, is_super=staff,
                            can_control=control, can_manage=False, can_platform=False)


async def ring_one_world(db, n=12, patches=PATCHES):
    """A rollout whose canary passed and whose ring one holds ``n`` computers that each need ``patches``.
    Returns (rollout id, a time inside the open window after the canary passed)."""
    await base(db)
    await host(db, "a1", canary=True, pending=patches)
    for i in range(n):
        await host(db, f"b{i:02d}", pending=patches)
    rollout_id = await begin(db, list(patches))
    return rollout_id, await pass_the_canary(db, rollout_id, list(patches))


async def page(db, now, **kw):
    return await cards.list_cards(db, T, kw.pop("who", caller()), offset=kw.pop("offset", 0),
                                  limit=kw.pop("limit", 10), now=now)


def only(result):
    assert result["total"] == 1 and len(result["items"]) == 1, result
    return result["items"][0]


def by_line(card):
    return {line["line"]: line for line in card["lines"]}


# ---------------------------------------------------------------- the install line

async def test_a_ring_with_five_patches_on_twelve_computers_is_one_card_with_one_install_line(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db)
    card = only(await page(db, later))
    assert (card["kind"], card["rolloutId"], card["ring"]) == ("rollout", rollout_id, "1")
    assert card["anchorId"] == f"approval-rollout-{rollout_id}-1"
    assert card["name"] == "Nov" and card["subtitle"] == "Ring 2 of 2: Everyone else · 12 computers"
    assert [l["line"] for l in card["lines"]] == ["install"]
    line = card["lines"][0]
    assert line["state"] == "pending" and line["resultText"] is None
    assert line["label"] == "Install 5 patches on 12 computers"
    assert line["targetText"] == "openssl, curl, bash +2 more"
    assert line["computerTotal"] == 12 and len(line["computers"]) == 10
    assert line["computers"] == sorted(line["computers"]) and line["computers"][0] == "host-b00"
    assert line["why"].startswith("Canary passed its health check at ") and line["why"].endswith("Everyone else is next.")
    assert "Installs these patches inside your maintenance window (open now, closes " in line["whatHappens"]
    assert "more than 10% of its computers fail" in line["whatHappens"]
    assert (line["canApprove"], line["canDeny"]) == (True, True)
    assert line["expiresAt"] == card["expiresAt"] and line["expiresAt"] is not None
    assert (await page(db, later))["countText"] == "1 rollout ring"


async def test_a_closed_window_says_when_it_next_opens(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)
    closed = NOW + timedelta(hours=5)                                   # the window closed at NOW + 3 h
    line = only(await page(db, closed))["lines"][0]
    assert "inside your maintenance window (next opens " in line["whatHappens"]
    assert "(open now" not in line["whatHappens"]


async def test_a_ring_that_is_not_the_canary_one_computer_reads_singular(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=1, patches=("openssl",))
    card = only(await page(db, later))
    assert card["subtitle"].endswith("· 1 computer")
    assert card["lines"][0]["label"] == "Install 1 patch on 1 computer"
    assert card["lines"][0]["targetText"] == "openssl"


async def test_a_canary_computer_that_cannot_be_checked_has_the_not_reversible_why(mongo_db):
    db = mongo_db
    await base(db)
    await host(db, "c1", canary=True, tokens=("reboot_host",), pending=("openssl",))
    await begin(db)
    await controller.tick(db, now=NOW)
    card = only(await page(db, NOW))
    assert card["ring"] == "0" and card["subtitle"] == "Ring 1 of 2: Canary · 1 computer"
    line = card["lines"][0]
    assert line["why"] == "openssl can't be reversed on every computer in this ring, so it needs your approval."
    assert line["label"] == "Install 1 patch on 1 computer"


# ---------------------------------------------------------------- the restart line

async def test_the_restart_line_appears_only_once_it_is_raised_and_lists_only_computers_that_need_one(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=4, patches=("openssl",))
    assert list(by_line(only(await page(db, later)))) == ["install"]
    result = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=later)
    assert result["status"] == "approved", result
    for agent in ("b00", "b01", "b02"):
        await store.set_host(db, T, rollout_id, agent, {"state": "installed", "rebootNeeded": True})
    await store.set_host(db, T, rollout_id, "b03", {"state": "installed", "rebootNeeded": False})
    rollout = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    raised = await reboots.raise_reboot_line(db, T, rollout, 1, await store.host_docs(db, T, rollout_id), later)
    assert raised["raised"] == 3

    card = only(await page(db, later + timedelta(seconds=5)))
    assert list(by_line(card)) == ["install", "reboot"]
    reboot = by_line(card)["reboot"]
    assert reboot["state"] == "pending" and reboot["label"] == "Restart 3 computers"
    assert reboot["computerTotal"] == 3 and reboot["computers"] == ["host-b00", "host-b01", "host-b02"]
    assert reboot["targetText"] == "" and reboot["why"] == "A restart is needed on 3 computers to finish installing."
    assert "5-minute warning" in reboot["whatHappens"] and (reboot["canApprove"], reboot["canDeny"]) == (True, True)
    install = by_line(card)["install"]
    assert install["state"] == "approved" and install["canApprove"] is False and install["canDeny"] is False
    assert install["resultText"].startswith("Approved. Installing now.")


# ---------------------------------------------------------------- flags

async def test_flags_follow_the_caller_and_the_stop(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)

    def flags(result):
        line = only(result)["lines"][0]
        return line["canApprove"], line["canDeny"]

    assert flags(await page(db, later, who=caller())) == (True, True)
    assert flags(await page(db, later, who=caller(control=False))) == (False, False)
    assert flags(await page(db, later, who=caller(interactive=False))) == (False, False)     # an API key
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {"active": True, "scope": "tenant"}}})
    stopped = await page(db, later)
    assert flags(stopped) == (False, True) and stopped["stopped"] == {"scope": "tenant"}


async def test_a_shadow_tenant_has_no_card(mongo_db):
    db = mongo_db
    await base(db, shadow=True)
    await host(db, "a1", canary=True, tokens=("reboot_host",))
    await begin(db)
    await controller.tick(db, now=NOW)
    assert (await page(db, NOW))["total"] == 0


async def test_another_organizations_rows_are_never_listed(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)
    other = await cards.list_cards(db, "t2", caller(), offset=0, limit=10, now=later)
    assert other["total"] == 0 and other["items"] == []


# ---------------------------------------------------------------- settled lines and order

async def test_a_denied_line_reads_its_result_for_one_poll_and_then_leaves(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)
    await lines.deny_line(db, T, rollout_id, 1, "install", approver=APPROVER)
    row = (await rows(db, **{"reason.inputs.ring": 1}))[0]
    decided = row["approval"]["decidedAt"].replace(tzinfo=timezone.utc)
    line = only(await page(db, decided + timedelta(seconds=10)))["lines"][0]
    assert line["state"] == "denied" and (line["canApprove"], line["canDeny"]) == (False, False)
    assert line["resultText"] == "Denied by Bo. The rollout halts at Everyone else."
    assert (await page(db, decided + timedelta(minutes=5)))["total"] == 0


async def test_an_approved_line_waiting_for_the_window_says_when_it_opens(mongo_db, clock):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)
    closed = NOW + timedelta(hours=5)
    clock["now"] = closed
    await db.autonomy_actions.update_many({"tenantId": T, "dispatcher": "patch_rollout", "reason.inputs.ring": 1},
                                          {"$set": {"approval.expiresAt": closed + timedelta(hours=20)}})
    result = await lines.approve_line(db, T, rollout_id, 1, "install", approver=APPROVER, now=closed)
    assert result["status"] == "approved" and result["when"] == "window", result
    decided = (await rows(db, **{"reason.inputs.ring": 1}))[0]["approval"]["decidedAt"].replace(tzinfo=timezone.utc)
    line = only(await page(db, decided + timedelta(seconds=5)))["lines"][0]
    assert line["state"] == "approved"
    assert line["resultText"].startswith("Approved. Installing when your window opens at ")


async def test_an_expired_line_reads_the_expired_result(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)
    from autonomous_ops import approvals
    expired_at = later + timedelta(hours=25)
    assert await approvals.expire_due(db, now=expired_at, tenant_id=T) == 2
    done = (await rows(db, **{"reason.inputs.ring": 1}))[0]["finishedAt"].replace(tzinfo=timezone.utc)
    line = only(await page(db, done + timedelta(seconds=5)))["lines"][0]
    assert line["state"] == "expired" and line["canApprove"] is False
    assert line["resultText"] == "Expired after 24 hours, counted as denied. The rollout halts at Everyone else."


async def test_cards_are_ordered_soonest_expiry_first_and_page_by_the_limit(mongo_db):
    db = mongo_db
    rollout_id, later = await ring_one_world(mongo_db, n=2)
    ring0 = {"tenantId": T, "dispatcher": "patch_rollout", "reason.inputs.ring": 1}
    await db.autonomy_actions.update_many(ring0, {"$set": {"approval.expiresAt": later + timedelta(hours=2)}})
    clone = await db.autonomy_actions.find_one({**ring0}, {"_id": 0})
    inputs = {**clone["reason"]["inputs"], "ring": 0}
    await db.autonomy_actions.insert_one({
        **clone, "id": "extra-0", "dedupeKey": "extra-0", "reason": {**clone["reason"], "inputs": inputs},
        "approval": {**clone["approval"], "expiresAt": later + timedelta(hours=1)}})
    result = await page(db, later)
    assert result["total"] == 2                                          # ring 0 (one row) and ring 1
    assert [c["ring"] for c in result["items"]] == ["0", "1"]            # ring 0 expires in 1 h, ring 1 in 2 h
    first = await page(db, later, limit=1)
    assert len(first["items"]) == 1 and first["total"] == 2 and first["items"][0]["ring"] == "0"
    second = await page(db, later, limit=1, offset=1)
    assert [c["ring"] for c in second["items"]] == ["1"]


# ================================================================== the routes (Task 2)

CARDS = "/api/autonomous-ops/rollout-cards"
SESSION_KEY_SCOPES = ["view:autonomous_ops", "control:autonomous_ops"]


def line_path(rollout_id, ring, line, what):
    return f"/api/autonomous-ops/rollout-lines/{rollout_id}/{ring}/{line}/{what}"


async def states(db, ring=1, **extra):
    return [r["state"] for r in await rows(db, **{"reason.inputs.ring": ring, **extra})]


async def test_the_card_list_needs_only_view_access_and_flags_follow_the_caller(api):
    rollout_id, _ = await ring_one_world(api.db, n=3)
    admin = await api.call("GET", CARDS, role="tenant_admin")
    assert admin.status_code == 200
    body = admin.json()
    assert body["total"] == 1 and body["countText"] == "1 rollout ring" and body["stopped"] is None
    line = body["items"][0]["lines"][0]
    assert (line["line"], line["canApprove"], line["canDeny"], line["computerTotal"]) == ("install", True, True, 3)
    viewer = (await api.call("GET", CARDS, role="analyst")).json()["items"][0]["lines"][0]
    assert (viewer["canApprove"], viewer["canDeny"]) == (False, False)
    key = (await api.call("GET", CARDS, role="tenant_admin", auth="api_key", scopes=SESSION_KEY_SCOPES)).json()
    assert (key["items"][0]["lines"][0]["canApprove"], key["items"][0]["lines"][0]["canDeny"]) == (False, False)
    assert (await api.call("GET", CARDS + "?limit=51", role="tenant_admin")).status_code == 422
    assert (await api.call("GET", CARDS + "?tenantId=t1", role="tenant_admin", tenant="t2")).status_code == 403
    other = await api.call("GET", CARDS, role="tenant_admin", tenant="t2")
    assert other.status_code == 200 and other.json()["items"] == []
    assert (await api.call("GET", CARDS, role="viewer")).status_code == 403              # no view:autonomous_ops


async def test_a_person_with_control_approves_a_whole_line_with_one_request_and_a_second_answers_409(api):
    db = api.db
    rollout_id, _ = await ring_one_world(db, n=3, patches=("openssl",))
    got = await api.call("POST", line_path(rollout_id, 1, "install", "approve"), role="tenant_admin",
                         username="ann@example.test")
    assert got.status_code == 200, got.text
    body = got.json()
    assert (body["status"], body["when"], body["approved"], body["refused"]) == ("approved", "now", 3, [])
    assert body["message"].startswith("Approved. Installing now")
    found = await rows(db, **{"reason.inputs.ring": 1})
    assert [r["state"] for r in found] == ["dispatching"] * 3
    assert {r["approval"]["approver"]["username"] for r in found} == {"ann@example.test"}      # T-84-35
    again = await api.call("POST", line_path(rollout_id, 1, "install", "approve"), role="tenant_admin")
    assert again.status_code == 409 and again.json()["status"] == "already_handled"
    assert again.json()["detail"] == again.json()["message"]
    assert len(await rows(db, **{"reason.inputs.ring": 1})) == 3


async def test_an_api_key_and_a_role_without_control_cannot_approve_or_deny(api):
    db = api.db
    rollout_id, _ = await ring_one_world(db, n=2, patches=("openssl",))
    for what in ("approve", "deny"):
        path = line_path(rollout_id, 1, "install", what)
        key = await api.call("POST", path, role="tenant_admin", auth="api_key", scopes=SESSION_KEY_SCOPES)
        assert key.status_code == 403, (what, key.text)
        for role in ("analyst", "viewer", "platform_support"):
            assert (await api.call("POST", path, role=role)).status_code == 403, (what, role)
    assert await states(db) == ["awaiting_approval"] * 2


async def test_a_stop_refuses_approve_with_409_but_still_allows_deny(api):
    db = api.db
    rollout_id, _ = await ring_one_world(db, n=2, patches=("openssl",))
    await db.autonomy_settings.update_one({"tenantId": T}, {"$set": {"stop": {"active": True, "scope": "tenant"}}})
    stopped = await api.call("POST", line_path(rollout_id, 1, "install", "approve"), role="tenant_admin")
    assert stopped.status_code == 409 and stopped.json()["status"] == "stopped"
    assert await states(db) == ["awaiting_approval"] * 2
    denied = await api.call("POST", line_path(rollout_id, 1, "install", "deny"), role="tenant_admin",
                            json={"reason": "x" * 500})
    assert denied.status_code == 200 and denied.json()["status"] == "denied"
    assert await states(db) == ["denied"] * 2


async def test_deny_names_the_person_and_the_ring_and_a_long_reason_is_refused(api):
    db = api.db
    rollout_id, _ = await ring_one_world(db, n=2, patches=("openssl",))
    path = line_path(rollout_id, 1, "install", "deny")
    assert (await api.call("POST", path, role="tenant_admin", json={"reason": "x" * 501})).status_code == 422
    assert await states(db) == ["awaiting_approval"] * 2
    done = await api.call("POST", path, role="tenant_admin", username="ann@example.test")
    assert done.status_code == 200
    assert done.json()["message"] == "Denied by ann@example.test. The rollout halts at Everyone else."


async def test_a_bad_path_is_422_and_an_unknown_or_foreign_rollout_is_404(api):
    db = api.db
    rollout_id, _ = await ring_one_world(db, n=1, patches=("openssl",))
    for bad in (line_path(rollout_id, 1, "bogus", "approve"), line_path(rollout_id, 4, "install", "approve"),
                line_path(rollout_id, -1, "install", "deny"), line_path(rollout_id, "x", "install", "deny"),
                line_path("r" * 65, 1, "install", "approve")):
        assert (await api.call("POST", bad, role="tenant_admin")).status_code == 422, bad
    assert (await api.call("POST", line_path("nope", 1, "install", "approve"), role="tenant_admin")).status_code == 404
    assert (await api.call("POST", line_path(rollout_id, 1, "install", "approve"), role="tenant_admin",
                           tenant="t2")).status_code == 404                  # another organization's rollout
    assert (await api.call("POST", line_path(rollout_id, 1, "install", "deny"), role="tenant_admin",
                           tenant="t2")).status_code == 404
    assert await states(db) == ["awaiting_approval"]
    nothing = await api.call("POST", line_path(rollout_id, 0, "reboot", "approve"), role="tenant_admin")
    assert nothing.status_code == 409 and nothing.json()["status"] == "refused"


async def test_one_request_decides_one_line_of_one_ring_only(api):
    db = api.db
    rollout_id, later = await ring_one_world(db, n=3, patches=("openssl",))
    for agent in ("b00", "b01"):
        await store.set_host(db, T, rollout_id, agent, {"state": "installed", "rebootNeeded": True})
    rollout = await db.patch_rollouts.find_one({"id": rollout_id}, {"_id": 0})
    await reboots.raise_reboot_line(db, T, rollout, 1, await store.host_docs(db, T, rollout_id), later)
    assert await states(db, **{"reason.inputs.line": "reboot"}) == ["awaiting_approval"] * 2
    ring_zero = await states(db, ring=0)

    done = await api.call("POST", line_path(rollout_id, 1, "install", "approve"), role="tenant_admin")
    assert done.status_code == 200 and done.json()["approved"] == 3
    assert await states(db, **{"reason.inputs.line": "reboot"}) == ["awaiting_approval"] * 2
    assert await states(db, ring=0) == ring_zero
    deny = await api.call("POST", line_path(rollout_id, 1, "reboot", "deny"), role="tenant_admin")
    assert deny.status_code == 200 and deny.json()["status"] == "denied"
    assert await states(db, **{"reason.inputs.line": "install"}) == ["dispatching"] * 3      # the install is untouched


async def test_the_platform_organization_cannot_decide_a_line_and_staff_must_name_an_organization(api):
    from tests._autonomous_ops_http import PLATFORM
    rollout_id, _ = await ring_one_world(api.db, n=1, patches=("openssl",))
    path = line_path(rollout_id, 1, "install", "approve")
    assert (await api.call("POST", path, role="super_admin")).status_code == 400            # tenantId is required
    assert (await api.call("POST", path + f"?tenantId={PLATFORM}", role="super_admin")).status_code == 409
    assert (await api.call("POST", path, role="platform_support")).status_code == 403
    done = await api.call("POST", path + "?tenantId=t1", role="super_admin")
    assert done.status_code == 200 and done.json()["status"] == "approved"
