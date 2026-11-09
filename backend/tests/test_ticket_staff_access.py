"""The ticket-staff permission and its one test (Phase 85, plan 85-30, gap G-85-4, WR-502).

Value: protects=WR-502 / G-85-4 UD-1 / UD-3 / PROH-85-20 / T-85-105 / T-85-106: manage:tickets sits on
exactly the four built-in staff roles, a requester role or a custom role without it is never ticket
staff, the role editor's catalogue offers it, and ticket_access.is_ticket_staff is the one answer
(granted permissions first, API-key scopes second, built-in fallback when the role store is down);
fails_when=user, viewer, platform_support or an undocumented custom role counts as staff, a custom
role of another tenant makes this tenant's role staff, an API key escapes its scopes, the role
catalogue stops offering the permission, or an unreachable role store grants more than the built-in
table; no_claim=any route enforcing staff (85-32 onward).
Fake role store only (MagicMock/AsyncMock): no database is touched.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import permission_vocabulary
import rbac_defaults
import rbac_service as rbac_module
import role_contents
import role_endpoints
import ticket_access
from auth_types import TokenData

TICKETS = "manage:tickets"
STAFF_ROLES = ["tenant_admin", "admin", "analyst", "security_analyst", "incident_responder"]
REQUESTER_ROLES = ["user", "viewer", "platform_support", "itam_user"]


def _technician(tenant, perms):
    return {"name": "Technician", "nameKey": "technician", "tenantId": tenant, "permissions": list(perms)}


def _role_store(*docs):
    """A role store holding ``docs``: find_one answers the first document matching every filter key."""
    async def find_one(query, *_args, **_kwargs):
        for doc in docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return doc
        return None

    db = MagicMock()
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(side_effect=find_one)
    db.tenants = MagicMock()
    db.tenants.find_one = AsyncMock(return_value=None)
    db._db = db
    return db


def _use(monkeypatch, db):
    monkeypatch.setattr(rbac_module, "get_database", lambda: db)


def _user(role, tenant="t1", **kw):
    return TokenData(username="u@x.co", role=role, tenant_id=tenant, mfa_verified=True, **kw)


def _staff(user):
    return asyncio.run(ticket_access.is_ticket_staff(user))


@pytest.mark.parametrize("role", STAFF_ROLES)
def test_built_in_staff_roles_hold_manage_tickets(monkeypatch, role):
    _use(monkeypatch, _role_store())
    granted = asyncio.run(rbac_module.granted_permissions(_role_store(), role, "t1"))
    assert TICKETS in granted
    assert _staff(_user(role)) is True


@pytest.mark.parametrize("role", REQUESTER_ROLES)
def test_requester_roles_do_not_hold_manage_tickets(monkeypatch, role):
    _use(monkeypatch, _role_store())
    granted = asyncio.run(rbac_module.granted_permissions(_role_store(), role, "t1"))
    assert TICKETS not in granted
    assert _staff(_user(role)) is False


def test_super_admin_reaches_staff_only_through_the_wildcard(monkeypatch):
    _use(monkeypatch, _role_store())
    assert asyncio.run(rbac_module.granted_permissions(_role_store(), "Super Admin", None)) == ["*"]
    assert TICKETS not in rbac_defaults.defaults_for("super_admin")
    assert _staff(_user("Super Admin", tenant=None)) is True


def test_only_the_four_staff_rows_name_the_permission():
    holders = sorted(key for key, perms in rbac_defaults.ROLE_DEFAULTS.items() if TICKETS in perms)
    assert holders == ["analyst", "incident_responder", "security_analyst", "tenant_admin"]


def test_the_permission_is_known_and_grantable_to_a_custom_role():
    assert TICKETS in permission_vocabulary.KNOWN_PERMISSIONS
    assert TICKETS in role_contents.GRANTABLE_PERMISSIONS
    assert role_contents.validate_permissions([TICKETS]) == [TICKETS]


def test_the_role_catalogue_offers_it_to_a_tenant_administrator(monkeypatch):
    monkeypatch.setattr(role_endpoints, "get_database", lambda: _role_store())
    body = asyncio.run(role_endpoints.permission_catalogue(current_user=_user("tenant_admin")))
    assert TICKETS in body["permissions"]
    assert body["superAdmin"] is False


def test_a_custom_role_without_the_permission_is_not_staff(monkeypatch):
    _use(monkeypatch, _role_store(_technician("t1", ["view:dashboard"])))
    assert _staff(_user("Technician")) is False


def test_the_same_custom_role_with_the_permission_is_staff(monkeypatch):
    _use(monkeypatch, _role_store(_technician("t1", ["view:dashboard", TICKETS])))
    assert _staff(_user("Technician")) is True


def test_a_custom_role_of_another_tenant_does_not_make_this_tenants_role_staff(monkeypatch):
    _use(monkeypatch, _role_store(_technician("t2", ["view:dashboard", TICKETS]),
                                  _technician("t1", ["view:dashboard"])))
    assert _staff(_user("Technician", tenant="t1")) is False
    assert _staff(_user("Technician", tenant="t2")) is True


def test_api_key_scopes_can_only_narrow_staff(monkeypatch):
    _use(monkeypatch, _role_store())
    assert _staff(_user("analyst", auth_source="api_key", scopes=["view:dashboard"])) is False
    assert _staff(_user("analyst", auth_source="api_key", scopes=[TICKETS])) is True
    assert _staff(_user("analyst", auth_source="api_key", scopes=["*"])) is True
    assert _staff(_user("analyst", auth_source="api_key", scopes=[])) is False
    assert _staff(_user("user", auth_source="api_key", scopes=[TICKETS])) is False


def test_explicit_permissions_decide_without_a_role_lookup(monkeypatch):
    def refuse():
        raise AssertionError("the role store must not be read when permissions are passed")

    monkeypatch.setattr(rbac_module, "get_database", refuse)
    assert asyncio.run(ticket_access.is_ticket_staff(_user("user"), [TICKETS])) is True
    assert asyncio.run(ticket_access.is_ticket_staff(_user("analyst"), ["view:dashboard"])) is False
    assert asyncio.run(ticket_access.is_ticket_staff(_user("user"), ["*"])) is True
    assert asyncio.run(ticket_access.is_ticket_staff(_user("analyst", scopes=["view:dashboard"]), [TICKETS])) is False


def test_holds_ticket_staff_is_a_pure_check():
    assert ticket_access.holds_ticket_staff([TICKETS]) is True
    assert ticket_access.holds_ticket_staff(["*"]) is True
    assert ticket_access.holds_ticket_staff(["view:dashboard"]) is False
    assert ticket_access.holds_ticket_staff([]) is False
    assert ticket_access.holds_ticket_staff(None) is False


def test_an_unreachable_role_store_falls_back_to_the_built_in_table(monkeypatch):
    def down():
        raise RuntimeError("role store unreachable")

    monkeypatch.setattr(rbac_module, "get_database", down)
    assert _staff(_user("analyst")) is True
    assert _staff(_user("user")) is False
    assert _staff(_user("Technician")) is False
