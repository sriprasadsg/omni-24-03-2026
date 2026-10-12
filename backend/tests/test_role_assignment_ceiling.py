"""D-18/D-20/D-21: the role-assignment ceiling shared by user CRUD and directory mappings.

``assert_can_assign_role`` compares the caller's and the target role's effective
permission sets (one resolver, so a tenant-scoped document that widens a built-in
counts) under the manage:X implies view:X / request:X closure. The expected
caller x target matrix below is hard-coded on purpose: a table edit that changes
who may assign what must show up here as a reviewable failure.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from auth_types import TokenData
from role_assignment import assert_can_assign_role
from tests.rbac_test_support import StoreCollection, role_store, shared_role_docs

TENANT = "tenant-a"

_TENANT_ADMIN_TARGETS = {
    "Tenant Admin", "admin", "user", "analyst", "security_analyst", "incident_responder",
    "viewer", "itam_admin", "itam_user", "itam_viewer",
}
_ALL_ROLES = sorted(_TENANT_ADMIN_TARGETS)

EXPECTED = {
    "Tenant Admin": _TENANT_ADMIN_TARGETS,
    "admin": _TENANT_ADMIN_TARGETS,
    "user": {"user", "viewer"},
    "analyst": {"analyst"},
    "security_analyst": {"security_analyst"},
    "incident_responder": {"incident_responder"},
    "viewer": {"viewer"},
    "itam_admin": {"itam_admin", "itam_user", "itam_viewer"},
    "itam_user": {"itam_user", "itam_viewer"},
    "itam_viewer": {"itam_viewer"},
}

SUPER_SPELLINGS = ["Super Admin", "super_admin", "platform-admin"]


def _caller(role, tenant=TENANT, username="caller@tenant-a.test"):
    return TokenData(username=username, role=role, tenant_id=tenant)


def _store(extra_docs=()):
    db, _raw = role_store(roles=shared_role_docs() + list(extra_docs))
    return db


class _BrokenRoles(StoreCollection):
    async def find_one(self, *a, **k):
        raise RuntimeError("roles store unreachable")


@pytest.mark.asyncio
@pytest.mark.parametrize("target", _ALL_ROLES)
@pytest.mark.parametrize("caller_role", sorted(EXPECTED))
async def test_caller_target_matrix(caller_role, target):
    db = _store()
    call = assert_can_assign_role(db, _caller(caller_role), target, target_tenant_id=TENANT)
    if target in EXPECTED[caller_role]:
        assert await call is None
    else:
        with pytest.raises(HTTPException) as exc:
            await call
        assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("target", SUPER_SPELLINGS)
@pytest.mark.parametrize("caller_role", sorted(EXPECTED))
async def test_non_super_callers_never_assign_the_super_admin_tier(caller_role, target):
    with pytest.raises(HTTPException) as exc:
        await assert_can_assign_role(_store(), _caller(caller_role), target, target_tenant_id=TENANT)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("target", _ALL_ROLES + SUPER_SPELLINGS)
@pytest.mark.parametrize("caller_role", SUPER_SPELLINGS)
async def test_super_admin_callers_assign_every_role(caller_role, target):
    assert await assert_can_assign_role(
        _store(), _caller(caller_role, tenant=None), target, target_tenant_id=TENANT) is None


@pytest.mark.asyncio
async def test_changing_own_role_is_refused():
    with pytest.raises(HTTPException) as exc:
        await assert_can_assign_role(
            _store(), _caller("itam_admin", username="Me@tenant-a.test"), "itam_viewer",
            target_tenant_id=TENANT, target_email="me@tenant-a.test", current_role="itam_admin")
    assert exc.value.status_code == 403
    assert "own role" in exc.value.detail


@pytest.mark.asyncio
async def test_super_admin_cannot_change_own_role_either():
    with pytest.raises(HTTPException) as exc:
        await assert_can_assign_role(
            _store(), _caller("Super Admin", tenant=None, username="root@platform.test"), "admin",
            target_tenant_id=TENANT, target_email="root@platform.test", current_role="super_admin")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("resent", ["itam_admin", "ITAM Admin", " itam-admin "])
async def test_resending_the_same_role_is_not_a_change(resent):
    assert await assert_can_assign_role(
        _store(), _caller("itam_admin", username="me@tenant-a.test"), resent,
        target_tenant_id=TENANT, target_email="me@tenant-a.test", current_role="itam_admin") is None


@pytest.mark.asyncio
async def test_other_users_are_not_a_self_change():
    assert await assert_can_assign_role(
        _store(), _caller("itam_admin", username="me@tenant-a.test"), "itam_viewer",
        target_tenant_id=TENANT, target_email="other@tenant-a.test", current_role="itam_user") is None


@pytest.mark.asyncio
async def test_tenant_document_that_widens_the_target_counts():
    widened = {"name": "itam_user", "tenantId": TENANT, "permissions": ["manage:rbac"]}
    db = _store([widened])
    with pytest.raises(HTTPException) as exc:
        await assert_can_assign_role(db, _caller("itam_admin"), "itam_user", target_tenant_id=TENANT)
    assert exc.value.status_code == 403
    # The document belongs to tenant-a only: in tenant-b the same assignment is fine.
    assert await assert_can_assign_role(
        db, _caller("itam_admin", tenant="tenant-b"), "itam_user", target_tenant_id="tenant-b") is None


@pytest.mark.asyncio
async def test_a_star_document_cannot_unlock_the_super_admin_tier():
    star = {"name": "itam_admin", "tenantId": TENANT, "permissions": ["*"]}
    db = _store([star])
    # WR-01: the resolver ignores '*' in documents, so the star widens nothing.
    with pytest.raises(HTTPException) as exc:
        await assert_can_assign_role(db, _caller("itam_admin"), "admin", target_tenant_id=TENANT)
    assert exc.value.status_code == 403
    for target in SUPER_SPELLINGS:
        with pytest.raises(HTTPException) as exc:
            await assert_can_assign_role(db, _caller("itam_admin"), target, target_tenant_id=TENANT)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_role_store_error_refuses_the_assignment():
    db, _raw = role_store(roles=_BrokenRoles(shared_role_docs()))
    with pytest.raises(HTTPException) as exc:
        await assert_can_assign_role(db, _caller("itam_admin"), "itam_user", target_tenant_id=TENANT)
    assert exc.value.status_code == 503
