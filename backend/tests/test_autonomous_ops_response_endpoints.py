"""Response settings routes (Phase 83, plan 83-07, RESP-04, RESP-08, ACTV-02): the two-source switch, the
block length and the watched services, for a tenant admin and, across organizations, for the Super Admin.

Real MongoDB through the throwaway database of tests/_mongo_test_db.py (skips without a server); the
routers are mounted as in production (the tenant router behind its catalogue guard) with the identity
replaced by a dependency override. The role matrix runs on the full mounted app through ``probe_real_app``
(no database: an allowed route answers 200, 422 or 503, a refused one 403).

Value: protects=exactly the people D-04, D-10, D-13 and D-22 name can read and change the three settings,
every change that really happens leaves one control row and one audit event naming the person, and the
two-source rule is never turned off without that record (PROH-83-09); fails_when=a role, key or other
organization reaches a setting, a bad value is stored, an unchanged save is recorded, or a loosening goes
unrecorded; no_claim=the settings panel (a later plan), the agent receiving the list, and the sweep
reading the values.
"""
from unittest.mock import patch

import pytest

from autonomous_ops import PLATFORM_TENANT_ID, ledger, response_messages, response_settings
from tests._autonomous_ops_http import PLATFORM, _case, _env, _probe, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

pytestmark = pytest.mark.real_agent_capabilities       # restartAvailable reads the tenant's real capability list

ALL_SCOPES = ["view:autonomous_ops", "manage:autonomous_ops", "control:autonomous_ops",
              "control:platform_autonomous_ops"]
PATH = "/api/autonomous-ops/response-settings"
PLAT = "/api/platform/autonomous-ops/response-settings"


async def _controls(db, tenant, event=None):
    flt = {"tenantId": tenant, "kind": "control"}
    if event:
        flt["controlEvent"] = event
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0})]


async def _audit_actions(db, tenant):
    return [e["action"] async for e in db.audit_logs.find({"tenantId": tenant})]


async def _stored(db, tenant):
    return (await db.autonomy_settings.find_one({"tenantId": tenant}, {"_id": 0})).get("response")


# ================================================================== tenant routes

async def test_defaults_for_a_tenant_with_nothing_stored(api):
    """protects=D-04 / D-10 / D-13 defaults with no backfill; fails_when=a new tenant reads anything but
    two sources, 24 hours and an empty list."""
    got = await api.call("GET", PATH, role="tenant_admin")
    assert got.status_code == 200
    assert got.json() == {"twoSignal": True, "blockHours": 24, "watchedServices": [], "readable": True,
                          "restartAvailable": False}     # agentCapabilities unset: only the always-on ones


async def test_two_signal_off_is_recorded_with_the_persons_name_and_an_audit_event(api):
    """protects=PROH-83-09 / T-83-21; fails_when=the rule turns off with no control row, no audit event
    or no name."""
    done = await api.call("PUT", PATH, role="tenant_admin", username="alice@example.test",
                          json={"twoSignal": False})
    assert done.status_code == 200 and done.json()["twoSignal"] is False
    assert (await _stored(api.db, "t1"))["twoSignal"] is False
    rows = await _controls(api.db, "t1", "two_signal_off")
    assert len(rows) == 1
    assert rows[0]["actor"]["username"] == "alice@example.test" and rows[0]["scope"] == "tenant"
    assert rows[0]["reasonText"] == response_messages.CONTROL_REASONS["two_signal_off"]
    assert "autonomous_ops.two_signal_off" in await _audit_actions(api.db, "t1")

    back = await api.call("PUT", PATH, role="tenant_admin", json={"twoSignal": True})
    assert back.status_code == 200 and back.json()["twoSignal"] is True
    assert len(await _controls(api.db, "t1", "two_signal_on")) == 1


async def test_saving_the_same_values_writes_nothing(api):
    """protects=the activity list stays a record of real changes; fails_when=a no-op save adds a row."""
    first = await api.call("PUT", PATH, role="tenant_admin", json={"blockHours": 12, "twoSignal": True})
    assert first.status_code == 200
    assert len(await _controls(api.db, "t1")) == 1           # block length only; twoSignal was already true
    again = await api.call("PUT", PATH, role="tenant_admin", json={"blockHours": 12, "twoSignal": True})
    assert again.status_code == 200 and again.json()["blockHours"] == 12
    assert len(await _controls(api.db, "t1")) == 1


async def test_block_length_range_and_types(api):
    """protects=D-13 (whole hours 1 to 168); fails_when=a value outside the range, a fraction or a string is stored."""
    for bad in (0, 169, -1, 1.5, "12", True, None):
        got = await api.call("PUT", PATH, role="tenant_admin", json={"blockHours": bad})
        assert got.status_code == 422, bad
    assert await _stored(api.db, "t1") is None
    for good in (1, 168):
        assert (await api.call("PUT", PATH, role="tenant_admin", json={"blockHours": good})).json()["blockHours"] == good
    rows = await _controls(api.db, "t1", "block_length_changed")
    assert len(rows) == 2 and "7 days" in rows[0]["reasonText"] + rows[1]["reasonText"]


async def test_watched_services_validation(api):
    """protects=D-10 / T-83-22; fails_when=a name outside the agent's rule, a critical service, a duplicate
    or a 51st name is stored."""
    bad = {
        "my service": "invalid_service", "-x": "invalid_service", "": "empty_service",
        "sshd": "critical_service", "RpcSs": "critical_service", "a" * 129: "invalid_service",
    }
    for name, code in bad.items():
        got = await api.call("PUT", PATH, role="tenant_admin", json={"watchedServices": [name]})
        assert got.status_code == 422, name
        assert got.json()["detail"] == response_settings.SettingsError(code, name=name.strip()).detail, name
    dup = await api.call("PUT", PATH, role="tenant_admin", json={"watchedServices": ["nginx", "NGINX"]})
    assert dup.status_code == 422 and "already on the list" in dup.json()["detail"]
    many = await api.call("PUT", PATH, role="tenant_admin",
                          json={"watchedServices": [f"svc{i}" for i in range(51)]})
    assert many.status_code == 422 and many.json()["detail"] == "You can watch up to 50 services."
    assert (await api.call("PUT", PATH, role="tenant_admin", json={"watchedServices": "nginx"})).status_code == 422
    assert await _stored(api.db, "t1") is None

    fifty = [f"svc{i}" for i in range(50)]
    ok = await api.call("PUT", PATH, role="tenant_admin", json={"watchedServices": fifty})
    assert ok.status_code == 200 and ok.json()["watchedServices"] == fifty
    cleared = await api.call("PUT", PATH, role="tenant_admin", json={"watchedServices": ["  nginx ", "Spooler"]})
    assert cleared.json()["watchedServices"] == ["nginx", "Spooler"]
    assert len(await _controls(api.db, "t1", "watched_services_changed")) == 2


async def test_an_empty_body_changes_nothing(api):
    assert (await api.call("PUT", PATH, role="tenant_admin", json={})).status_code == 422
    assert await _controls(api.db, "t1") == []


async def test_roles_keys_and_tenants(api):
    """protects=D-22 and the tenant boundary (T-83-23, T-83-24); fails_when=a role without manage, Platform
    Support, a key or another tenant reaches the settings."""
    body = {"blockHours": 6}
    for role in ("security_analyst", "incident_responder", "analyst", "viewer", "platform_support"):
        assert (await api.call("GET", PATH, role=role)).status_code == 403, role
        assert (await api.call("PUT", PATH, role=role, json=body)).status_code == 403, role
    assert (await api.call("GET", PATH, role="tenant_admin", auth="api_key", scopes=ALL_SCOPES)).status_code == 403
    assert (await api.call("PUT", PATH, role="tenant_admin", auth="api_key", scopes=ALL_SCOPES,
                           json=body)).status_code == 403
    assert (await api.call("PUT", PATH + "?tenantId=t2", role="tenant_admin", json=body)).status_code == 403
    assert (await api.call("GET", PATH + "?tenantId=t2", role="tenant_admin")).status_code == 403
    assert await _stored(api.db, "t1") is None and await _stored(api.db, "t2") is None

    other = await api.call("PUT", PATH + "?tenantId=t2", role="super_admin", json=body, username="root@example.test")
    assert other.status_code == 200 and other.json()["blockHours"] == 6
    assert (await _stored(api.db, "t2"))["blockHours"] == 6 and await _stored(api.db, "t1") is None
    row = (await _controls(api.db, "t2", "block_length_changed"))[0]
    assert row["actor"]["username"] == "root@example.test" and row["scope"] == "platform"
    assert (await api.call("GET", PATH + "?tenantId=nope", role="super_admin")).status_code == 404
    assert (await api.call("GET", PATH, role="super_admin")).status_code == 400
    assert (await api.call("PUT", PATH + f"?tenantId={PLATFORM}", role="super_admin", json=body)).status_code == 409
    assert (await api.call("GET", PATH + f"?tenantId={PLATFORM}", role="super_admin")).status_code == 409
    assert await api.db.autonomy_settings.find_one({"tenantId": PLATFORM}) is None


async def test_restart_is_unavailable_without_remediation_but_the_list_still_saves(api):
    """protects=D-21 / UI-SPEC section 6; fails_when=restartAvailable stays true without the tick, or the
    save is refused."""
    await api.db.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["chat_window"]}})
    got = await api.call("GET", PATH, role="tenant_admin")
    assert got.status_code == 200 and got.json()["restartAvailable"] is False
    saved = await api.call("PUT", PATH, role="tenant_admin", json={"watchedServices": ["nginx"]})
    assert saved.status_code == 200 and saved.json()["watchedServices"] == ["nginx"]
    assert saved.json()["restartAvailable"] is False
    await api.db.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["remediation_executor"]}})
    assert (await api.call("GET", PATH, role="tenant_admin")).json()["restartAvailable"] is True


async def test_a_malformed_stored_value_reads_as_the_safe_default(api):
    """protects=the sweep keeps two sources on unreadable data; fails_when=a malformed value reads as
    off or the response claims readable."""
    await api.db.autonomy_settings.update_one(
        {"tenantId": "t1"}, {"$set": {"response": {"twoSignal": "off", "blockHours": 99999, "watchedServices": 3}}})
    got = (await api.call("GET", PATH, role="tenant_admin")).json()
    assert got["readable"] is False and got["twoSignal"] is True and got["blockHours"] == 24
    assert got["watchedServices"] == []
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"response": "garbage"}})
    assert (await api.call("GET", PATH, role="tenant_admin")).json()["readable"] is False
    fixed = await api.call("PUT", PATH, role="tenant_admin", json={"blockHours": 12})
    assert fixed.status_code == 200 and fixed.json()["readable"] is True and fixed.json()["blockHours"] == 12


async def test_a_change_that_cannot_be_recorded_is_not_kept(api):
    """protects=PROH-83-09; fails_when=the rule stays off after its control row failed to record."""
    async def broken(*args, **kwargs):
        raise ledger.LedgerUnavailable("down")
    with patch.object(ledger, "record_control", broken):
        got = await api.call("PUT", PATH, role="tenant_admin", json={"twoSignal": False})
    assert got.status_code == 503
    assert (await api.call("GET", PATH, role="tenant_admin")).json()["twoSignal"] is True


async def test_the_platform_organization_is_refused_by_save(mongo_db):
    """protects=Phase 81 D-04; fails_when=save writes settings for the platform organization."""
    try:
        await response_settings.save(mongo_db, PLATFORM_TENANT_ID, {"twoSignal": False}, actor={"username": "x"})
    except response_settings.PlatformTenantError as exc:
        assert exc.code == "platform_tenant"
    else:
        raise AssertionError("save accepted the platform organization")
    assert await mongo_db.autonomy_settings.find_one({"tenantId": PLATFORM_TENANT_ID}) is None


# ================================================================== platform routes

async def test_distribution_counts_every_organization_but_the_platform_one(api):
    await seed_tenant(api.db, PLATFORM_TENANT_ID, name="Platform")
    await api.call("PUT", PATH, role="tenant_admin", json={"twoSignal": False, "blockHours": 12})
    got = await api.call("GET", PLAT, role="super_admin")
    assert got.status_code == 200
    body = got.json()
    assert body["organizations"] == 2 and body["twoSignal"] == {"on": 1, "off": 1}
    assert body["blockHours"] == {"12": 1, "24": 1}


async def test_bulk_writes_each_organization_with_its_own_rows(api):
    """protects=D-04 / D-13 (bulk = a write to each tenant's own setting); fails_when=the platform
    organization changes, an organization lacks its own control row, or the change is not per tenant."""
    await seed_tenant(api.db, PLATFORM_TENANT_ID, name="Platform")
    done = await api.call("PUT", PLAT + "/bulk", role="super_admin", username="root@example.test",
                          json={"twoSignal": False, "blockHours": 6})
    assert done.status_code == 200
    assert done.json() == {"changed": ["t1", "t2"], "failures": []}
    for tenant in ("t1", "t2"):
        assert await _stored(api.db, tenant) == {"twoSignal": False, "blockHours": 6}
        rows = await _controls(api.db, tenant, "two_signal_off")
        assert len(rows) == 1 and rows[0]["actor"]["username"] == "root@example.test"
        assert rows[0]["scope"] == "platform"
        assert len(await _controls(api.db, tenant, "block_length_changed")) == 1
        assert "autonomous_ops.two_signal_off" in await _audit_actions(api.db, tenant)
    assert await _stored(api.db, PLATFORM_TENANT_ID) is None
    assert await _controls(api.db, PLATFORM_TENANT_ID) == []
    # an organization's own administrator can change it back, and there is one value to read
    back = await api.call("PUT", PATH, role="tenant_admin", json={"twoSignal": True})
    assert back.status_code == 200 and back.json()["twoSignal"] is True and back.json()["blockHours"] == 6
    again = await api.call("PUT", PLAT + "/bulk", role="super_admin", json={"twoSignal": False, "blockHours": 6})
    assert again.json()["changed"] == ["t1", "t2"]
    assert len(await _controls(api.db, "t2", "two_signal_off")) == 1          # t2 was already off: no second row
    assert len(await _controls(api.db, "t1", "two_signal_off")) == 2


async def test_one_failing_organization_does_not_stop_the_others_and_a_retry_sends_only_it(api):
    """protects=the partial-failure contract of UI-SPEC section 7; fails_when=a failure aborts the rest,
    is not listed, or the retry rewrites the organizations that already changed."""
    real = response_settings.save

    async def flaky(db, tenant_id, changes, **kw):
        if tenant_id == "t1":
            raise RuntimeError("boom")
        return await real(db, tenant_id, changes, **kw)
    with patch.object(response_settings, "save", flaky):
        got = await api.call("PUT", PLAT + "/bulk", role="super_admin", json={"blockHours": 48})
    assert got.status_code == 200
    body = got.json()
    assert body["changed"] == ["t2"]
    assert [(f["tenantId"], f["name"]) for f in body["failures"]] == [("t1", "T1")]
    assert "boom" not in str(body)
    assert await _stored(api.db, "t1") is None and (await _stored(api.db, "t2"))["blockHours"] == 48

    retry = await api.call("PUT", PLAT + "/bulk", role="super_admin",
                           json={"blockHours": 48, "onlyTenants": ["t1"]})
    assert retry.json() == {"changed": ["t1"], "failures": []}
    assert len(await _controls(api.db, "t2", "block_length_changed")) == 1
    assert len(await _controls(api.db, "t1", "block_length_changed")) == 1

    missing = await api.call("PUT", PLAT + "/bulk", role="super_admin",
                             json={"blockHours": 24, "onlyTenants": ["t2", "gone"]})
    assert missing.json()["changed"] == ["t2"] and [f["tenantId"] for f in missing.json()["failures"]] == ["gone"]
    refused = await api.call("PUT", PLAT + "/bulk", role="super_admin",
                             json={"blockHours": 24, "onlyTenants": [PLATFORM_TENANT_ID]})
    assert refused.status_code == 409


async def test_bulk_refuses_empty_bad_and_service_bodies(api):
    for body in ({}, {"onlyTenants": ["t1"]}, {"blockHours": 0}, {"blockHours": 169}, {"twoSignal": "no"},
                 {"watchedServices": ["nginx"]}, {"twoSignal": False, "watchedServices": ["nginx"]}):
        assert (await api.call("PUT", PLAT + "/bulk", role="super_admin", json=body)).status_code == 422, body
    assert await _stored(api.db, "t1") is None and await _controls(api.db, "t1") == []


async def test_platform_routes_refuse_everyone_but_the_super_admin(api):
    for role in ("tenant_admin", "platform_support", "security_analyst", "platform_billing"):
        assert (await api.call("GET", PLAT, role=role)).status_code == 403, role
        assert (await api.call("PUT", PLAT + "/bulk", role=role, json={"blockHours": 6})).status_code == 403, role
    assert (await api.call("GET", PLAT, role="super_admin", auth="api_key", scopes=ALL_SCOPES)).status_code == 403
    assert (await api.call("PUT", PLAT + "/bulk", role="super_admin", auth="api_key", scopes=ALL_SCOPES,
                           json={"blockHours": 6})).status_code == 403
    assert await _controls(api.db, "t1") == []


# ================================================================== the full app (guards as shipped)

def test_the_role_matrix_on_the_real_app():
    """protects=the catalogue guard and the per-route permission both apply; fails_when=a role without
    manage, Platform Support, an API key or a tenant role on a platform route is let through."""
    tenant_key = {"auth": "api_key", "scopes": ALL_SCOPES}
    groups = {
        "tenant_allowed": [_case(PATH, "tenant_admin"), _case(PATH, "tenant_admin", method="PUT"),
                           _case(PATH + "?tenantId=t1", "super_admin"),
                           _case(PATH + "?tenantId=t1", "super_admin", method="PUT")],
        "tenant_denied": [_case(PATH, role, method=method) for role in
                          ("security_analyst", "incident_responder", "analyst", "viewer", "user", "itam_admin")
                          for method in ("GET", "PUT")]
        + [_case(PATH + "?tenantId=t1", role, method=method) for role in ("platform_support", "platform_billing")
           for method in ("GET", "PUT")]
        + [_case(PATH, "tenant_admin", method=method, **tenant_key) for method in ("GET", "PUT")]
        + [_case(PATH + "?tenantId=t1", "super_admin", method=method, **tenant_key) for method in ("GET", "PUT")],
        "platform_allowed": [_case(PLAT, "super_admin"), _case(PLAT + "/bulk", "super_admin", method="PUT")],
        "platform_denied": [_case(path, role, method=method) for role in
                            ("tenant_admin", "security_analyst", "platform_support", "platform_billing")
                            for path, method in ((PLAT, "GET"), (PLAT + "/bulk", "PUT"))]
        + [_case(path, "super_admin", method=method, **tenant_key)
           for path, method in ((PLAT, "GET"), (PLAT + "/bulk", "PUT"))],
    }
    got = _probe(groups)
    assert all(code in (200, 422, 503) for code in got["tenant_allowed"]), got["tenant_allowed"]
    assert all(code == 403 for code in got["tenant_denied"]), got["tenant_denied"]
    assert all(code in (200, 422, 503) for code in got["platform_allowed"]), got["platform_allowed"]
    assert all(code == 403 for code in got["platform_denied"]), got["platform_denied"]
