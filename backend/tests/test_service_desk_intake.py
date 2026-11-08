"""Who raised a ticket, and whether it is queued (Phase 85, plan 85-09, DESK-01 / DESK-02). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the server, not the client's tags, decides whether a person raised a ticket on each creation
path (portal, the signed-in agent route, the legacy tray route), an old tray's title prefix names its
template, and only an eligible tenant's person-raised ticket is queued; fails_when=an agent identity, an
API key, the Rust agent's instruction or a tray claim without a Windows user is queued, a stopped, Off or
screen-less tenant gets a job, an unreadable platform stop lets a job through, or a ticket created with no
raised_via is anything but automation; no_claim=the answer a queued ticket gets (85-04 onward), the new tray
route (85-19) and a real Ollama.
"""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_types import TokenData
from service_desk import intake, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant

ALICE = portal_user("t1", "alice")
API_KEY = portal_user("t1", "ci-key", auth_source="api_key")
AGENT = TokenData(username="a1", role="agent", tenant_id="t1", mfa_verified=False)
BODY = {"title": "VPN is down", "description": "The VPN has been down since this morning and I cannot work"}
TRAY_TAGS = ["user-raised", "tray"]
TRAY_INFO = {"hostname": "LAPTOP1", "username": "jdoe"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    import agent_auth
    import agent_capabilities
    import agent_tasks_endpoints
    from authentication_service import get_current_user_or_agent
    from autonomous_ops import ledger
    await ledger.ensure_indexes(mongo_db)
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1", mode="post")
    await mongo_db.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "LAPTOP1"})
    desk = desk_app(mongo_db, monkeypatch)
    monkeypatch.setattr(agent_tasks_endpoints, "get_database", lambda: mongo_db)
    desk.app.include_router(agent_tasks_endpoints.router)
    desk.app.dependency_overrides[get_current_user_or_agent] = lambda: desk.user
    tenant = {"id": "t1", "agentCapabilities": agent_capabilities.every_capability()}
    desk.app.dependency_overrides[agent_auth.verify_agent_key] = lambda: tenant
    return desk


async def _via_portal_route(world, user=ALICE, **extra):
    response = await world.call("POST", "/api/agents/a1/raise-ticket", user=user, json={**BODY, **extra})
    assert response.status_code == 200, response.text
    return response.json()["ticket"]


async def _via_tray_route(world, **extra):
    response = await world.call("POST", "/api/agents/a1/ticket", user=AGENT, json={**BODY, **extra})
    assert response.status_code == 200, response.text
    return await world.db.tickets.find_one({"id": response.json()["ticket_id"]}, {"_id": 0})


async def _queued(db, ticket_id):
    return await store.jobs(db).count_documents({"ticketId": ticket_id})


async def _no_trace(db, ticket_id):
    assert await _queued(db, ticket_id) == 0
    assert await store.jobs(db).count_documents({}) == 0
    assert await db.autonomy_actions.count_documents({}) == 0


# ------------------------------------------------------------------ who raised it: the signed-in agent route

async def test_raise_ticket_by_a_signed_in_person_is_portal_agent_and_queued(world):
    ticket = await _via_portal_route(world)
    stored = await world.db.tickets.find_one({"id": ticket["id"]}, {"_id": 0})
    assert stored["raised_via"] == "portal_agent"
    assert stored["requester_channel"]["portal"] is True
    assert await _queued(world.db, ticket["id"]) == 1


async def test_raise_ticket_by_an_agent_identity_is_automation_and_not_queued(world):
    ticket = await _via_portal_route(world, user=AGENT)
    stored = await world.db.tickets.find_one({"id": ticket["id"]}, {"_id": 0})
    assert stored["raised_via"] == "automation"
    assert stored["requester_channel"]["portal"] is False
    await _no_trace(world.db, ticket["id"])


async def test_raise_ticket_by_an_api_key_is_automation_and_not_queued(world):
    ticket = await _via_portal_route(world, user=API_KEY)
    stored = await world.db.tickets.find_one({"id": ticket["id"]}, {"_id": 0})
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, ticket["id"])


async def test_a_body_field_cannot_claim_a_person_raised_it(world):
    ticket = await _via_portal_route(world, user=AGENT, raised_via="portal_agent",
                                     requester_channel={"portal": True})
    stored = await world.db.tickets.find_one({"id": ticket["id"]}, {"_id": 0})
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, ticket["id"])


# ------------------------------------------------------------------ who raised it: the legacy tray route

async def test_legacy_tray_ticket_with_a_windows_user_is_tray_and_queued(world):
    stored = await _via_tray_route(world, title="Issue: VPN down", tags=TRAY_TAGS, endpoint_info=TRAY_INFO)
    assert stored["raised_via"] == "tray"
    assert stored["requester_channel"] == {"portal": False, "tray": True, "myTickets": False,
                                           "windowsUser": "jdoe", "template": "report_issue"}
    assert "agent-raised" in stored["tags"]       # the route still appends it after deciding
    assert await _queued(world.db, stored["id"]) == 1


async def test_legacy_tray_ticket_without_endpoint_info_is_automation(world):
    stored = await _via_tray_route(world, tags=TRAY_TAGS)
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, stored["id"])


async def test_legacy_tray_ticket_with_an_empty_windows_user_is_automation(world):
    stored = await _via_tray_route(world, tags=TRAY_TAGS, endpoint_info={"username": ""})
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, stored["id"])


async def test_legacy_tray_ticket_with_only_the_user_raised_tag_is_automation(world):
    stored = await _via_tray_route(world, tags=["user-raised"], endpoint_info=TRAY_INFO)
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, stored["id"])


async def test_the_rust_agents_create_ticket_instruction_is_automation(world):
    stored = await _via_tray_route(world, tags=["agent-raised", "omni-agent-rust"])
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, stored["id"])


async def test_a_tray_claim_that_also_says_agent_raised_is_automation(world):
    stored = await _via_tray_route(world, tags=["user-raised", "tray", "agent-raised"], endpoint_info=TRAY_INFO)
    assert stored["raised_via"] == "automation"
    await _no_trace(world.db, stored["id"])


# ------------------------------------------------------------------ the title prefixes (D-02)

@pytest.mark.parametrize("title,template", [
    ("software install request: Zoom", "install_software"),
    ("Hardware Request: mouse", "hardware_request"),
    ("Security Concern: phish", "security_concern"),
    ("Access Request: share", "access_request"),
    ("Issue: VPN down", "report_issue"),
    ("Printer help", "custom"),
    ("Software Install Request Zoom", "custom"),
    ("", "custom"),
])
def test_legacy_template_from_the_title_prefix(title, template):
    assert intake.legacy_template(title) == template


def test_legacy_template_of_a_title_that_is_not_text_is_custom():
    assert intake.legacy_template(None) == "custom"
    assert intake.legacy_template(12) == "custom"


async def test_a_stored_legacy_tray_ticket_carries_its_template(world):
    stored = await _via_tray_route(world, title="Hardware Request: mouse", tags=TRAY_TAGS, endpoint_info=TRAY_INFO)
    assert stored["requester_channel"]["template"] == "hardware_request"
    edited = await _via_tray_route(world, title="Need a mouse", tags=TRAY_TAGS, endpoint_info=TRAY_INFO)
    assert edited["requester_channel"]["template"] == "custom"


def test_tray_claim_needs_lists_and_a_dict():
    assert intake.tray_claim(TRAY_TAGS, TRAY_INFO) == "jdoe"
    assert intake.tray_claim(None, TRAY_INFO) is None
    assert intake.tray_claim(TRAY_TAGS, "jdoe") is None
    assert intake.tray_claim(TRAY_TAGS, {"username": 5}) is None
    assert intake.tray_claim(TRAY_TAGS, {"username": "   "}) is None


# ------------------------------------------------------------------ the remaining eligibility checks

async def _portal_ticket(world, user=ALICE):
    response = await world.call("POST", "/api/tickets", user=user, json=BODY)
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_eligible_portal_ticket_is_queued(world):
    ticket = await _portal_ticket(world)
    assert await _queued(world.db, ticket["id"]) == 1


async def test_level_suggest_still_enqueues(world):
    await seed_desk_tenant(world.db, "t1", level="suggest", mode="post")
    ticket = await _portal_ticket(world)
    assert await _queued(world.db, ticket["id"]) == 1


async def test_level_off_gives_no_job_and_no_ledger_row(world):
    await seed_desk_tenant(world.db, "t1", level="off", mode="post")
    ticket = await _portal_ticket(world)
    await _no_trace(world.db, ticket["id"])


async def test_a_tenant_stop_gives_no_job_and_no_ledger_row(world):
    await world.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    ticket = await _portal_ticket(world)
    await _no_trace(world.db, ticket["id"])


async def test_a_platform_stop_gives_no_job_and_no_ledger_row(world):
    await world.db.system_settings.insert_one({"type": "autonomous_ops", "stop": {"active": True}})
    ticket = await _portal_ticket(world)
    await _no_trace(world.db, ticket["id"])


async def test_an_unreadable_platform_stop_counts_as_on(world, monkeypatch):
    from autonomous_ops import settings as ao_settings
    monkeypatch.setattr(ao_settings, "platform_stop", AsyncMock(side_effect=RuntimeError("no database")))
    ticket = await _portal_ticket(world)
    await _no_trace(world.db, ticket["id"])


async def test_a_stop_that_is_not_active_does_not_block(world):
    await world.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": False}}})
    await world.db.system_settings.insert_one({"type": "autonomous_ops", "stop": {"active": False}})
    ticket = await _portal_ticket(world)
    assert await _queued(world.db, ticket["id"]) == 1


@pytest.mark.parametrize("screen", ["screen:internalTickets", "screen:knowledgeBase"])
async def test_a_switched_off_screen_gives_no_job_and_no_ledger_row(world, screen):
    await world.db.tenants.update_one({"id": "t1"}, {"$pull": {"enabledFeatures": screen}})
    ticket = await _portal_ticket(world)
    await _no_trace(world.db, ticket["id"])


async def test_the_desk_set_to_off_gives_no_job_and_no_ledger_row(world):
    await world.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "off"}}})
    ticket = await _portal_ticket(world)
    await _no_trace(world.db, ticket["id"])


async def test_a_ticket_created_without_raised_via_is_automation_and_never_queued(world):
    from tickets_service import tickets_service
    ticket = await tickets_service.create_ticket(data={"title": "Asset warranty ending"}, reporter="itam-bridge",
                                                 tenant_id="t1")
    assert ticket["raised_via"] == "automation"
    assert await intake.on_ticket_created(world.db, ticket, via="automation") is None
    await _no_trace(world.db, ticket["id"])
