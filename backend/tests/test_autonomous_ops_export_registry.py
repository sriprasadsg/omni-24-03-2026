"""The Autonomous Ops Activity entry of the Reporting registry (Phase 86, plan 86-08, ACTV-06, D-09).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=an organization's own users export its last 30 days of all states through /api/reports/export
with the same builder, audit and DLP scan as the screen, and platform staff are refused before the registry's
cross-tenant elevation can run; fails_when=a Super Admin export reaches set_tenant_id('platform-admin') for this
type, another organization's rows appear, an empty period saves a 204 instead of a file, or the audit event
loses its entry name; no_claim=every other report type (backend/tests/test_audit_export.py) and the screen
route (test_autonomous_ops_export.py).
"""
import csv
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
import dlp_service
import export_report_endpoint as registry
import rbac_utils
from auth_types import TokenData
from autonomous_ops import protected
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant
from tests.test_autonomous_ops_export import HEADER, _doc, _put

TYPE = "Autonomous Ops Activity"
OPEN_ORG = "Open an organization in Tenants, then export from its Autonomous Ops screen."
PLATFORM = "platform-admin"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


class RegistryApi:
    def __init__(self, db, monkeypatch):
        self.db, self.user = db, None
        self.audit, self.elevate = AsyncMock(), MagicMock()
        monkeypatch.setattr(registry, "get_database", lambda: db, raising=False)
        monkeypatch.setattr(rbac_utils, "get_database", lambda: db)
        monkeypatch.setattr(registry, "set_tenant_id", self.elevate)
        monkeypatch.setattr(audit_ledger, "event", self.audit)
        monkeypatch.setattr(dlp_service, "scan_export", AsyncMock(return_value=([], [])))
        monkeypatch.setattr(dlp_service, "record_export_incident", AsyncMock())
        self.app = FastAPI()
        self.app.include_router(registry.router)
        self.app.dependency_overrides[rbac_utils.get_current_user] = lambda: self.user

    async def get(self, fmt="csv", *, role="tenant_admin", tenant="t1"):
        platform = role in ("super_admin", "platform_support")
        self.user = TokenData(username=f"{role}@example.test", role=role,
                              tenant_id=PLATFORM if platform else tenant, scopes=None, auth_source="session")
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/reports/export", params={"type": TYPE, "format": fmt})


@pytest.fixture
async def api(mongo_db, monkeypatch):
    for tenant in ("t1", "t2"):
        await seed_tenant(mongo_db, tenant)
        await mongo_db.tenants.update_one({"id": tenant}, {"$addToSet": {"enabledFeatures": "export:reports"}})
    return RegistryApi(mongo_db, monkeypatch)


def _at(days):
    return datetime.now(timezone.utc) - timedelta(days=days, minutes=1)


async def test_an_organizations_user_exports_all_states_of_the_last_thirty_days(api):
    await _put(api.db, _doc("AO-1", "t1", "executed", _at(1)), _doc("AO-2", "t1", "failed", _at(2)),
               _doc("AO-3", "t1", "executed", _at(40)), _doc("AO-4", "t2", "executed", _at(1)))
    got = await api.get()
    assert got.status_code == 200 and got.headers["x-export-rows"] == "2"
    table = list(csv.reader(io.StringIO(got.text)))
    assert table[0] == HEADER and {row[1] for row in table[1:]} == {"Done", "Failed"}
    api.audit.assert_awaited_once()
    fields = api.audit.await_args.kwargs
    assert api.audit.await_args.args == ("autonomous_ops.export", "t1")
    assert (fields["entry"], fields["bucket"], fields["days"], fields["rows"]) == ("registry", "all", "30", 2)
    api.elevate.assert_not_called()


async def test_a_role_without_the_screen_right_gets_the_registrys_own_refusal(api, monkeypatch):
    monkeypatch.setattr(rbac_utils, "granted_permissions", AsyncMock(return_value=["export:reports"]))
    got = await api.get(role="viewer")
    assert got.status_code == 403 and got.json()["detail"] == f"Exporting '{TYPE}' needs view:autonomous_ops"
    api.audit.assert_not_awaited()


@pytest.mark.parametrize("role,tenant,detail", [("super_admin", "t1", OPEN_ORG), ("tenant_admin", PLATFORM, OPEN_ORG),
                                                ("platform_support", "t1", None)])
async def test_platform_staff_are_refused_before_any_cross_tenant_elevation(api, role, tenant, detail):
    await _put(api.db, _doc("AO-1", "t1", "executed", _at(1)))
    got = await api.get(role=role, tenant=tenant)
    assert got.status_code == 403
    if detail:
        assert got.json()["detail"] == detail
    assert not any(call.args and call.args[0] == PLATFORM for call in api.elevate.call_args_list)
    api.audit.assert_not_awaited()


async def test_an_empty_period_still_gives_a_file(api):
    got = await api.get()
    assert got.status_code == 200 and got.headers["x-export-rows"] == "0"
    assert list(csv.reader(io.StringIO(got.text))) == [HEADER]
    pdf = await api.get("pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_a_blocking_dlp_finding_refuses_the_registry_export_too(api, monkeypatch):
    await _put(api.db, _doc("AO-1", "t1", "executed", _at(1)))
    monkeypatch.setattr(dlp_service, "scan_export", AsyncMock(return_value=([{"name": "Credit card"}], [])))
    got = await api.get()
    assert got.status_code == 403 and got.json()["detail"] == "Export blocked by DLP policy: Credit card"
    api.audit.assert_not_awaited()
