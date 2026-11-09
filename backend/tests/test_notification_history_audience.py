"""The notice history serves what the feed serves (Phase 85, plan 85-31, DESK-01, CR-501, decisions D-11 and D-33,
gap G-85-4 UD-4). Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=CR-501 / D-33 / UD-4 / PROH-85-22 / T-85-107 / T-85-108: GET /api/notifications/history reads
through the shared audience filter keyed on tenantId, so a view:dashboard user never reads a notice addressed to
someone else, one that excludes them, a tenant_admins notice without manage:agents or a ticket_staff notice
without manage:tickets, and the Super Admin's cross-tenant view keeps the per-person rules;
fails_when=any reader's history lists a notice the feed hides from them, a notice stored with tenantId only is
missing from its tenant's history, a snake tenant_id that disagrees with tenantId decides the tenant, the Super
Admin reads a notice addressed to someone else, a caller without a tenant gets a 500 or the tenant-less notices,
or severity, limit, the newest-first order or the {notifications, count} shape change;
no_claim=notices without an audience or recipient (ticket lifecycle notices, A-85-G21) stay tenant-wide.
"""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_types import TokenData
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

READ = ("view:dashboard",)
STAFF = ("view:dashboard", "manage:tickets")
TENANT_ADMIN = ("view:dashboard", "manage:agents", "manage:tickets")

ALICE = TokenData(username="alice@x.co", role="user", tenant_id="t1")
CAROL = TokenData(username="carol@x.co", role="user", tenant_id="t1")
BOB = TokenData(username="bob@x.co", role="analyst", tenant_id="t1")
ADMIN = TokenData(username="admin@x.co", role="tenant_admin", tenant_id="t1")
DAVE = TokenData(username="dave@x.co", role="user", tenant_id="t2")
SUPER = TokenData(username="super@x.co", role="Super Admin", tenant_id="platform-admin")


async def _seed(db):
    """t1: eight notices in increasing sent_at order (stored as send_alert stores them: tenantId and tenant_id
    unless named otherwise); t2: three."""
    order = iter(range(1, 50))

    def notice(alert_id, tenant="t1", severity="info", snake="same", **metadata):
        doc = {"alert_id": alert_id, "tenantId": tenant, "severity": severity,
               "sent_at": f"2026-11-08T00:00:{next(order):02d}", "metadata": metadata or None}
        if snake == "same":
            doc["tenant_id"] = tenant
        elif snake:
            doc["tenant_id"] = snake
        return doc

    await db.notifications.insert_many([
        notice("alice-only", recipient="alice@x.co"),
        notice("carol-only", recipient="carol@x.co"),
        notice("tenant-wide"),
        notice("admins", audience="tenant_admins"),
        notice("staff", audience="ticket_staff", excludeRecipients=["alice@x.co"]),
        notice("tenantid-only", snake=None),
        notice("mismatch", snake="t2"),
        notice("critical", severity="critical"),
        notice("t2-alice-only", tenant="t2", recipient="alice@x.co"),
        notice("t2-wide", tenant="t2"),
        notice("t2-super", tenant="t2", recipient="super@x.co"),
    ])


async def _history(db, user, *, perms=READ, **kwargs):
    """Run get_notification_history as ``user``: tenant context of the token (platform-admin for a Super Admin),
    the isolated database handle and the permissions stubbed, as the route's request would carry them."""
    import reporting_endpoints as re_
    from database import TenantIsolatedDatabase
    from rbac_service import rbac_service
    token = set_tenant_id(user.tenant_id or "")
    try:
        with patch.object(re_, "get_database", return_value=TenantIsolatedDatabase(db)), \
                patch.object(rbac_service, "get_user_permissions", AsyncMock(return_value=list(perms))):
            result = await re_.get_notification_history(**{"limit": 50, "severity": None, **kwargs}, _current_user=user)
    finally:
        reset_tenant_id(token)
    assert result["count"] == len(result["notifications"])
    return result


def _ids(result):
    return [n["alert_id"] for n in result["notifications"]]


async def test_a_requester_reads_her_own_and_the_tenant_wide_notices_only(mongo_db):
    """protects=CR-501 / PROH-85-22; fails_when=Alice's history lists Carol's notice, the tenant_admins notice, the
    staff notice that excludes her or another tenant's notice, or misses her own or a tenant-wide one."""
    await _seed(mongo_db)
    assert sorted(_ids(await _history(mongo_db, ALICE))) == sorted(
        ["alice-only", "tenant-wide", "tenantid-only", "mismatch", "critical"])


async def test_a_colleague_never_reads_a_notice_addressed_to_someone_else(mongo_db):
    """protects=CR-501 / D-33; fails_when=Carol's history lists Alice's notice, the staff notice (she is not
    staff) or the tenant_admins notice, or misses her own."""
    await _seed(mongo_db)
    assert sorted(_ids(await _history(mongo_db, CAROL))) == sorted(
        ["carol-only", "tenant-wide", "tenantid-only", "mismatch", "critical"])


async def test_staff_read_the_staff_notice_unless_it_excludes_them(mongo_db):
    """protects=D-11 / UD-2 / WR-201; fails_when=Bob (manage:tickets) misses the staff notice, or still reads
    Alice's, Carol's or the tenant_admins notice."""
    await _seed(mongo_db)
    bob = _ids(await _history(mongo_db, BOB, perms=STAFF))
    assert "staff" in bob and "admins" not in bob and "alice-only" not in bob and "carol-only" not in bob
    excluded = TokenData(username="Alice@X.co ", role="analyst", tenant_id="t1")
    assert "staff" not in _ids(await _history(mongo_db, excluded, perms=STAFF))


async def test_a_tenant_admin_reads_the_admin_and_staff_notices(mongo_db):
    """protects=WR-202 audience rule; fails_when=a holder of manage:agents and manage:tickets misses the admins
    or the staff notice, or reads someone else's addressed notice."""
    await _seed(mongo_db)
    admin = _ids(await _history(mongo_db, ADMIN, perms=TENANT_ADMIN))
    assert {"admins", "staff", "tenant-wide"} <= set(admin)
    assert "alice-only" not in admin and "carol-only" not in admin and not [i for i in admin if i.startswith("t2-")]


async def test_a_notice_stored_with_tenant_id_only_is_read_and_the_snake_field_does_not_decide(mongo_db):
    """protects=UD-4 canonical field; fails_when=a notice with only tenantId is missing from t1's history, or the
    notice whose tenant_id says t2 but tenantId says t1 shows up in t2's history."""
    await _seed(mongo_db)
    t1 = _ids(await _history(mongo_db, CAROL))
    assert "tenantid-only" in t1 and "mismatch" in t1
    t2 = _ids(await _history(mongo_db, DAVE))
    assert "t2-wide" in t2 and "mismatch" not in t2 and "tenantid-only" not in t2 and "t2-alice-only" not in t2


async def test_the_super_admin_spans_every_tenant_under_the_per_person_rules(mongo_db):
    """protects=UD-4 / PROH-85-22 / T-85-108; fails_when=the Super Admin misses another tenant's tenant-wide or
    their own addressed notice, or reads a notice addressed to Alice or Carol in any tenant."""
    await _seed(mongo_db)
    seen = set(_ids(await _history(mongo_db, SUPER, perms=("*",), limit=100)))
    assert {"tenant-wide", "admins", "staff", "tenantid-only", "mismatch", "critical", "t2-wide", "t2-super"} <= seen
    assert not {"alice-only", "carol-only", "t2-alice-only"} & seen


async def test_a_caller_without_a_tenant_is_refused_not_served_or_crashed(mongo_db):
    """protects=UD-4; fails_when=a non-super caller with no tenant gets a 500, an empty 200 or any notice."""
    await _seed(mongo_db)
    nobody = TokenData(username="nobody@x.co", role="user", tenant_id=None)
    with pytest.raises(HTTPException) as refused:
        await _history(mongo_db, nobody)
    assert refused.value.status_code == 403 and refused.value.detail == "Tenant context required"


async def test_severity_and_limit_narrow_the_history_newest_first(mongo_db):
    """protects=the route's existing contract; fails_when=severity does not narrow, limit returns more than asked
    or not the newest, the order is not newest first or the count is not the list length."""
    await _seed(mongo_db)
    critical = await _history(mongo_db, CAROL, severity="critical")
    assert _ids(critical) == ["critical"] and critical["count"] == 1
    newest = await _history(mongo_db, CAROL, limit=2)
    assert _ids(newest) == ["critical", "mismatch"] and newest["count"] == 2
    assert set(newest) == {"notifications", "count"}
