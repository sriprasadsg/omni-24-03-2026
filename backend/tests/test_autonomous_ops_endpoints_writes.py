"""Autonomous Ops write routes (Phase 81, plan 81-09): stop and resume, level, maximum level, shadow
lift, restore-level, never-touch, approve/deny/undo, the platform router and the permission matrix.

Real MongoDB through the throwaway database of tests/_mongo_test_db.py (skips without a server); the
routers are mounted as in production with the identity replaced by a dependency override. The
permission matrix runs on the full mounted app through ``probe_real_app`` (no database: an allowed
route answers 422, 404 or 503, a refused one 403).

Value: protects=every write route enforces the D-05/D-06/D-10/D-11 split, API keys can press a stop
but never resume, approve, deny, undo or change a setting, only the platform router changes a maximum
level or a shadow flag, and a platform person's name stays private from tenants; fails_when=a role or
key reaches a route it should not, a level goes above its cap, or a name leaks;
no_claim=the screen (81-10) and a real browser session.
"""
from autonomous_ops import gate, ledger, protected
from tests._autonomous_ops_http import NOW, PLATFORM, _case, _env, _probe, api  # noqa: F401  (fixtures)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

# ================================================================== Task 2: write routes and the platform router

ALL_SCOPES = ["view:autonomous_ops", "manage:autonomous_ops", "control:autonomous_ops",
              "control:platform_autonomous_ops"]
ALICE = {"username": "alice", "display": "Alice", "tier": "tenant"}
STOP_BASE = "/api/autonomous-ops"
PLAT = "/api/platform/autonomous-ops"


async def _stop_state(db, tenant="t1"):
    return (await db.autonomy_settings.find_one({"tenantId": tenant}, {"_id": 0})).get("stop")


async def _controls(db, tenant, event=None):
    flt = {"tenantId": tenant, "kind": "control"}
    if event:
        flt["controlEvent"] = event
    return [r async for r in db.autonomy_actions.find(flt, {"_id": 0})]


# ------------------------------------------------------------------ stop and resume

async def test_press_a_stop_then_press_again_then_resume_with_a_reason(api):
    """protects=D-11/D-14 on the tenant routes: a stop is pressed by a control holder, a second press is
    a 409 naming who pressed, resume needs a typed reason and a manage holder; fails_when=the second
    press succeeds, a blank reason resumes, or security_analyst (control only) resumes."""
    pressed = await api.call("POST", f"{STOP_BASE}/stop", role="security_analyst", username="sam@t1.test",
                             json={"reason": "  Investigating a spike  "})
    assert pressed.status_code == 200
    body = pressed.json()
    assert body["stop"]["tenant"]["by"] == "sam@t1.test" and body["stop"]["tenant"]["reason"] == "Investigating a spike"
    assert (await _stop_state(api.db))["active"] is True
    assert len(await _controls(api.db, "t1", "stop_pressed")) == 1

    again = await api.call("POST", f"{STOP_BASE}/stop", role="tenant_admin", username="ann@t1.test")
    assert again.status_code == 409 and again.json()["by"] == "sam@t1.test" and again.json()["detail"]

    assert (await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", json={})).status_code == 422
    assert (await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", json={"reason": "   "})).status_code == 422
    assert (await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin",
                           json={"reason": "x" * 501})).status_code == 422
    assert (await api.call("POST", f"{STOP_BASE}/resume", role="security_analyst",
                           json={"reason": "Checked it"})).status_code == 403
    assert (await _stop_state(api.db))["active"] is True

    resumed = await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", username="ann@t1.test",
                             json={"reason": "Checked it"})
    assert resumed.status_code == 200 and resumed.json()["stop"]["tenant"] is None
    assert (await _stop_state(api.db))["active"] is False
    assert len(await _controls(api.db, "t1", "stop_cleared")) == 1
    gone = await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", json={"reason": "again"})
    assert gone.status_code == 409


async def test_who_may_press_a_stop(api):
    """protects=PROH-81-15 and D-10 for stop; fails_when=analyst, viewer or platform staff without the
    permission press one, or an API key with the control scope cannot."""
    for role in ("analyst", "viewer", "user", "itam_admin"):
        assert (await api.call("POST", f"{STOP_BASE}/stop", role=role)).status_code == 403, role
    for role in ("platform_support", "platform_billing"):
        assert (await api.call("POST", f"{STOP_BASE}/stop?tenantId=t1", role=role)).status_code == 403, role
    assert not ((await _stop_state(api.db)) or {}).get("active")        # none of the refused presses took effect
    no_scope = await api.call("POST", f"{STOP_BASE}/stop", role="tenant_admin", auth="api_key",
                              scopes=["view:autonomous_ops"])
    assert no_scope.status_code == 403
    key = await api.call("POST", f"{STOP_BASE}/stop", role="tenant_admin", auth="api_key",
                         scopes=["control:autonomous_ops"], username="ci-key")
    assert key.status_code == 200 and key.json()["stop"]["tenant"]["by"] == "ci-key"
    key_resume = await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", auth="api_key",
                                scopes=ALL_SCOPES, json={"reason": "I am a key"})
    assert key_resume.status_code == 403
    assert (await _stop_state(api.db))["active"] is True


async def test_a_tenant_stop_pressed_by_the_super_admin_needs_the_super_admin_to_resume(api):
    """protects=D-11; fails_when=a tenant manage holder clears a stop a Super Admin pressed."""
    assert (await api.call("POST", f"{STOP_BASE}/stop?tenantId=t1", role="super_admin", username="root",
                           json={"reason": "Audit"})).status_code == 200
    assert (await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", json={"reason": "no"})).status_code == 403
    assert (await _stop_state(api.db))["active"] is True
    assert (await api.call("POST", f"{STOP_BASE}/resume?tenantId=t1", role="super_admin",
                           json={"reason": "Done"})).status_code == 200
    assert (await api.call("POST", f"{STOP_BASE}/stop?tenantId=nope", role="super_admin")).status_code == 404
    assert (await api.call("POST", f"{STOP_BASE}/stop", role="super_admin")).status_code == 400
    assert (await api.call("POST", f"{STOP_BASE}/stop?tenantId={PLATFORM}", role="super_admin")).status_code == 409


async def test_stop_reason_is_bounded(api):
    assert (await api.call("POST", f"{STOP_BASE}/stop", role="tenant_admin", json={"reason": "x" * 501})).status_code == 422
    assert (await api.call("POST", f"{STOP_BASE}/stop", role="tenant_admin", json={"reason": "x" * 500})).status_code == 200


# ------------------------------------------------------------------ level, maximum level, shadow

async def test_level_is_capped_by_the_maximum_and_only_the_platform_router_changes_the_maximum(api):
    """protects=GATE-13 / T-81-35; fails_when=a tenant admin raises its own level above the cap."""
    path = f"{STOP_BASE}/settings/level"
    low = await api.call("PUT", path, role="tenant_admin", json={"level": "suggest"})
    assert low.status_code == 200 and low.json()["level"] == "suggest"
    assert (await api.call("PUT", path, role="tenant_admin", json={"level": "bogus"})).status_code == 422
    assert (await api.call("PUT", path, role="tenant_admin", json={})).status_code == 422

    capped = await api.call("PUT", f"{PLAT}/tenants/t1/max-level", role="super_admin", json={"maxLevel": "suggest"})
    assert capped.status_code == 200
    doc = await api.db.autonomy_settings.find_one({"tenantId": "t1"})
    assert doc["maxLevel"] == "suggest" and doc["level"] == "suggest"

    assert (await api.call("PUT", path, role="tenant_admin", json={"level": "undoable_auto"})).status_code == 403
    assert (await api.call("PUT", path, role="tenant_admin", json={"level": "suggest"})).status_code == 200
    assert (await api.call("PUT", path, role="tenant_admin", json={"level": "off"})).status_code == 200
    assert (await api.call("PUT", path, role="tenant_admin", json={"level": "undoable_auto"})).status_code == 403
    assert (await api.db.autonomy_settings.find_one({"tenantId": "t1"}))["level"] == "off"

    for role in ("security_analyst", "incident_responder", "analyst", "viewer"):
        assert (await api.call("PUT", path, role=role, json={"level": "off"})).status_code == 403, role
    assert (await api.call("PUT", path, role="platform_support", json={"level": "off"})).status_code == 403
    for sub in ("max-level",):
        assert (await api.call("PUT", f"{STOP_BASE}/settings/{sub}", role="tenant_admin",
                               json={"maxLevel": "undoable_auto"})).status_code in (404, 405)
    assert (await api.call("PUT", f"{PLAT}/tenants/t1/max-level", role="tenant_admin",
                           json={"maxLevel": "undoable_auto"})).status_code == 403
    assert (await api.call("PUT", path, role="tenant_admin", auth="api_key", scopes=ALL_SCOPES,
                           json={"level": "off"})).status_code == 403


async def test_the_platform_organization_cannot_be_raised_above_off(api):
    """protects=D-04; fails_when=any route sets a level for platform-admin."""
    assert (await api.call("PUT", f"{STOP_BASE}/settings/level?tenantId={PLATFORM}", role="super_admin",
                           json={"level": "suggest"})).status_code == 409
    assert (await api.call("PUT", f"{PLAT}/tenants/{PLATFORM}/max-level", role="super_admin",
                           json={"maxLevel": "suggest"})).status_code == 409
    assert await api.db.autonomy_settings.find_one({"tenantId": PLATFORM}) is None     # nothing was written for it
    assert (await api.call("PUT", f"{PLAT}/tenants/nope/max-level", role="super_admin",
                           json={"maxLevel": "off"})).status_code == 404
    assert (await api.call("PUT", f"{PLAT}/tenants/t1/max-level", role="super_admin",
                           json={"maxLevel": "high"})).status_code == 422


async def test_only_the_platform_route_lifts_a_tenants_shadow_flag(api):
    """protects=D-03 / GATE-09; fails_when=a tenant route changes the shadow flag."""
    assert (await api.db.autonomy_settings.find_one({"tenantId": "t1"}))["shadow"] is True
    for role in ("tenant_admin", "platform_support", "security_analyst"):
        assert (await api.call("PUT", f"{PLAT}/tenants/t1/shadow", role=role, json={"shadow": False})).status_code == 403
    assert (await api.call("PUT", f"{STOP_BASE}/settings/shadow", role="tenant_admin",
                           json={"shadow": False})).status_code in (404, 405)
    assert (await api.call("PUT", f"{PLAT}/tenants/t1/shadow", role="super_admin", json={"shadow": "no"})).status_code == 422
    done = await api.call("PUT", f"{PLAT}/tenants/t1/shadow", role="super_admin", json={"shadow": False})
    assert done.status_code == 200
    assert (await api.db.autonomy_settings.find_one({"tenantId": "t1"}))["shadow"] is False
    restored = await api.call("PUT", f"{PLAT}/tenants/t1/shadow", role="super_admin", json={"shadow": True})
    assert restored.status_code == 200
    assert (await api.db.autonomy_settings.find_one({"tenantId": "t1"}))["shadow"] is True
    assert (await api.call("PUT", f"{PLAT}/tenants/t1/shadow", role="super_admin", auth="api_key",
                           scopes=ALL_SCOPES, json={"shadow": False})).status_code == 403
    assert (await api.call("PUT", f"{PLAT}/tenants/nope/shadow", role="super_admin",
                           json={"shadow": False})).status_code == 404


async def test_restore_level_after_a_breaker_trip(api):
    """protects=D-18; fails_when=restore works on an untripped tenant, for an analyst or on an API key."""
    path = f"{STOP_BASE}/settings/restore-level"
    assert (await api.call("POST", path, role="tenant_admin")).status_code == 409
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {
        "level": "suggest", "breaker": {"trippedAt": NOW, "previousLevel": "undoable_auto", "actionIds": ["a", "b", "c"]}}})
    for role in ("analyst", "security_analyst", "platform_support"):
        assert (await api.call("POST", path, role=role)).status_code == 403, role
    assert (await api.call("POST", path, role="tenant_admin", auth="api_key", scopes=ALL_SCOPES)).status_code == 403
    done = await api.call("POST", path, role="tenant_admin")
    assert done.status_code == 200 and done.json()["level"] == "undoable_auto" and done.json()["previousLevel"] is None
    assert len(await _controls(api.db, "t1", "level_restored")) == 1


# ------------------------------------------------------------------ never-touch

async def test_never_touch_entries_for_a_tenant(api):
    path = f"{STOP_BASE}/never-touch"
    made = await api.call("POST", path, role="tenant_admin", json={"kind": "ip", "value": "198.51.100.5", "note": "VPN"})
    assert made.status_code == 201
    entry = made.json()
    assert entry["kind"] == "ip" and entry["value"] == "198.51.100.5" and entry["scope"] == "tenant"
    assert entry["builtin"] is False and entry["note"] == "VPN"
    cidr = await api.call("POST", path, role="tenant_admin", json={"kind": "cidr", "value": "198.51.100.0/24"})
    assert cidr.status_code == 201
    for bad in ({"kind": "ip", "value": "not-an-ip"}, {"kind": "cidr", "value": "10.0.0.1"}, {"kind": "mac", "value": "x"},
                {"kind": "host", "value": "bad host"}, {"kind": "ip", "value": "198.51.100.6", "note": "n" * 201},
                {"kind": "host", "value": "h" * 254}, {"value": "x"}):
        assert (await api.call("POST", path, role="tenant_admin", json=bad)).status_code == 422, bad
    listing = await api.call("GET", path, role="analyst")
    assert listing.status_code == 200
    items = listing.json()["items"]
    scopes = {i["scope"] for i in items}
    assert "builtin" in scopes and "tenant" in scopes
    assert entry["id"] in [i["id"] for i in items] and all(i["builtin"] is (i["scope"] == "builtin") for i in items)

    builtin = next(i for i in items if i["builtin"])
    assert (await api.call("DELETE", f"{path}/{builtin['id']}", role="tenant_admin")).status_code == 403
    assert (await api.call("DELETE", f"{path}/NT-unknown", role="tenant_admin")).status_code == 404
    assert (await api.call("DELETE", f"{path}/{entry['id']}", role="security_analyst")).status_code == 403
    assert (await api.call("DELETE", f"{path}/{entry['id']}", role="tenant_admin", auth="api_key",
                           scopes=ALL_SCOPES)).status_code == 403
    assert (await api.call("DELETE", f"{path}/{entry['id']}", role="tenant_admin")).status_code == 200
    assert (await api.call("DELETE", f"{path}/{entry['id']}", role="tenant_admin")).status_code == 404
    assert (await api.call("POST", path, role="security_analyst", json={"kind": "ip", "value": "198.51.100.9"})).status_code == 403
    assert (await api.call("POST", path, role="tenant_admin", auth="api_key", scopes=ALL_SCOPES,
                           json={"kind": "ip", "value": "198.51.100.9"})).status_code == 403
    assert (await api.call("POST", path, role="platform_support", json={"kind": "ip", "value": "198.51.100.9"}
                           )).status_code == 403


async def test_a_tenant_cannot_delete_another_tenants_or_a_platform_entry(api):
    other = await protected.add_entry(api.db, scope="tenant", tenant_id="t2", kind="ip", value="198.51.100.77")
    plat = await api.call("POST", f"{PLAT}/never-touch", role="super_admin", json={"kind": "ip", "value": "198.51.100.88"})
    assert plat.status_code == 201 and plat.json()["scope"] == "platform"
    for entry_id in (other.id, plat.json()["id"]):
        assert (await api.call("DELETE", f"{STOP_BASE}/never-touch/{entry_id}", role="tenant_admin")).status_code == 404
    mine = (await api.call("GET", f"{STOP_BASE}/never-touch", role="tenant_admin")).json()["items"]
    assert plat.json()["id"] in [i["id"] for i in mine] and other.id not in [i["id"] for i in mine]
    assert (await api.call("DELETE", f"{PLAT}/never-touch/{plat.json()['id']}", role="tenant_admin")).status_code == 403
    builtin = next(i for i in mine if i["builtin"])
    assert (await api.call("DELETE", f"{PLAT}/never-touch/{builtin['id']}", role="super_admin")).status_code == 403
    assert (await api.call("DELETE", f"{PLAT}/never-touch/{plat.json()['id']}", role="super_admin")).status_code == 200
    assert (await api.call("GET", f"{PLAT}/never-touch", role="super_admin")).status_code == 200


# ------------------------------------------------------------------ approve, deny, undo

def _req(action="isolate_host", target="a1", ip=None, key=None):
    params = {"ip_address": ip} if ip else {}
    return gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=[action], targets=[target],
                              params=params, dedupe_key=key or f"t1|{action}|{target}|{ip}",
                              reason={"ruleId": "test", "inputs": {}})


async def _card(api, **kw):
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    await seed_agent(api.db, "t1", "a1", hostname="web-01")
    decision = await gate.decide(api.db, _req(**kw), master_shadow=False)
    assert decision.state == "awaiting_approval", decision
    return decision.action_id


async def test_approve_deny_and_undo_over_http(api):
    """protects=GATE-10/GATE-13 over HTTP: approving needs control and a session, dispatches once, and
    the loser reads 409; fails_when=an analyst or a key approves, or a second approve dispatches again."""
    card = await _card(api)
    path = f"{STOP_BASE}/actions/{card}"
    assert (await api.call("POST", f"{path}/approve", role="analyst")).status_code == 403
    assert (await api.call("POST", f"{path}/approve", role="platform_support")).status_code == 403
    assert (await api.call("POST", f"{path}/approve", role="security_analyst", auth="api_key", scopes=ALL_SCOPES)).status_code == 403
    assert await api.db.agent_instructions.count_documents({}) == 0
    done = await api.call("POST", f"{path}/approve", role="security_analyst", username="sam@t1.test")
    assert done.status_code == 200 and done.json()["status"] == "dispatched"
    assert done.json()["action"]["id"] == card and done.json()["action"]["state"] == "dispatching"
    assert await api.db.agent_instructions.count_documents({}) == 1
    assert (await api.call("POST", f"{path}/approve", role="tenant_admin")).status_code == 409
    assert await api.db.agent_instructions.count_documents({}) == 1
    assert (await api.call("POST", f"{STOP_BASE}/actions/AO-missing/approve", role="tenant_admin")).status_code == 404

    other = await _card(api, action="kill_process", key="k2")
    denied = await api.call("POST", f"{STOP_BASE}/actions/{other}/deny", role="incident_responder",
                            json={"reason": "Not now"})
    assert denied.status_code == 200 and denied.json()["status"] == "denied"
    assert denied.json()["action"]["state"] == "denied"
    assert (await api.call("POST", f"{STOP_BASE}/actions/{other}/deny", role="tenant_admin")).status_code == 409
    third = await _card(api, action="reboot_host", key="k3")
    assert (await api.call("POST", f"{STOP_BASE}/actions/{third}/deny", role="tenant_admin",
                           json={"reason": "x" * 501})).status_code == 422
    assert (await api.call("POST", f"{STOP_BASE}/actions/{third}/deny", role="analyst")).status_code == 403
    assert (await api.call("POST", f"{STOP_BASE}/actions/{third}/deny", role="tenant_admin", auth="api_key",
                           scopes=ALL_SCOPES)).status_code == 403
    assert (await api.call("POST", f"{STOP_BASE}/actions/{third}/deny", role="tenant_admin")).status_code == 200


async def test_approve_is_refused_during_a_stop_and_in_another_tenant(api):
    card = await _card(api)
    await seed_tenant(api.db, "t3", shadow=False)
    assert (await api.call("POST", f"{STOP_BASE}/actions/{card}/approve", role="tenant_admin", tenant="t3")).status_code == 404
    await seed_platform_stop(api.db)
    blocked = await api.call("POST", f"{STOP_BASE}/actions/{card}/approve", role="tenant_admin")
    assert blocked.status_code == 409 and blocked.json()["detail"]
    assert await api.db.agent_instructions.count_documents({}) == 0
    # Deny still works during a stop (it dispatches nothing).
    assert (await api.call("POST", f"{STOP_BASE}/actions/{card}/deny", role="tenant_admin")).status_code == 200


async def test_undo_over_http(api):
    await api.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"shadow": False}})
    await seed_agent(api.db, "t1", "a1", hostname="web-01")
    d = await gate.decide(api.db, _req(action="block_ip", ip="203.0.113.7", key="blk"), master_shadow=False)
    assert d.state == "dispatching"
    assert (await gate.execute(api.db, "t1", d.action_id, command="block_ip", agent_id="a1",
                               params={"ip_address": "203.0.113.7"}))["status"] == "queued"
    await ledger.transition(api.db, "t1", d.action_id, ("dispatching",), "executed")
    path = f"{STOP_BASE}/actions/{d.action_id}/undo"
    assert (await api.call("POST", path, role="analyst")).status_code == 403
    assert (await api.call("POST", path, role="tenant_admin", auth="api_key", scopes=ALL_SCOPES)).status_code == 403
    done = await api.call("POST", path, role="security_analyst")
    assert done.status_code == 200 and done.json()["status"] == "undone" and done.json()["action"]["state"] == "undone"
    assert (await api.call("POST", path, role="security_analyst")).status_code == 409
    assert (await api.call("POST", f"{STOP_BASE}/actions/AO-missing/undo", role="security_analyst")).status_code == 404
    suggested = await gate.suggest(api.db, _req(action="block_ip", ip="203.0.113.50", key="sg"), master_shadow=False)
    refused = await api.call("POST", f"{STOP_BASE}/actions/{suggested.action_id}/undo", role="security_analyst")
    assert refused.status_code == 409


# ------------------------------------------------------------------ the platform router

async def test_platform_wide_stop_and_resume_and_name_masking(api):
    """protects=D-11/D-25 through the routes: the Super Admin stops every organization, a tenant sees
    'Platform administrator', only the Super Admin resumes and a key can press but not resume;
    fails_when=a name leaks to a tenant or a tenant admin can use the platform router."""
    for role in ("tenant_admin", "security_analyst", "platform_support", "platform_billing"):
        assert (await api.call("POST", f"{PLAT}/stop", role=role)).status_code == 403, role
        assert (await api.call("GET", f"{PLAT}/status", role=role)).status_code == 403, role
    pressed = await api.call("POST", f"{PLAT}/stop", role="super_admin", username="Root Admin", json={"reason": "Incident"})
    assert pressed.status_code == 200
    assert pressed.json()["stop"]["platform"]["by"] == "Root Admin" and pressed.json()["scope"] == "platform"
    again = await api.call("POST", f"{PLAT}/stop", role="super_admin", username="Root Admin")
    assert again.status_code == 409 and again.json()["by"] == "Root Admin"

    tenant_view = await api.call("GET", f"{STOP_BASE}/status", role="tenant_admin")
    assert tenant_view.json()["stop"]["platform"]["by"] == "Platform administrator"
    assert "Root Admin" not in tenant_view.text
    assert "Root Admin" not in (await api.call("GET", f"{STOP_BASE}/actions", role="tenant_admin")).text
    support = await api.call("GET", f"{STOP_BASE}/status?tenantId=t1", role="platform_support")
    assert support.json()["stop"]["platform"]["by"] == "Root Admin"

    status = await api.call("GET", f"{PLAT}/status", role="super_admin")
    assert status.status_code == 200 and set(status.json()) == {"scope", "stop", "tenantStopsCount", "canStopPlatform",
                                                                  "canResumePlatform", "health"}
    assert status.json()["canResumePlatform"] is True and status.json()["tenantStopsCount"] == 0
    listed = (await api.call("GET", f"{PLAT}/actions", role="super_admin")).json()
    assert [i["controlEvent"] for i in listed["items"]] == ["platform_stop_pressed"]
    assert listed["items"][0]["by"] == "Root Admin"

    assert (await api.call("POST", f"{PLAT}/resume", role="super_admin", auth="api_key", scopes=ALL_SCOPES,
                           json={"reason": "key"})).status_code == 403
    assert (await api.call("POST", f"{PLAT}/resume", role="super_admin", json={})).status_code == 422
    assert (await api.call("POST", f"{PLAT}/resume", role="tenant_admin", json={"reason": "no"})).status_code == 403
    # The tenant manage holder cannot clear it from the tenant router either.
    assert (await api.call("POST", f"{STOP_BASE}/resume", role="tenant_admin", json={"reason": "no"})).status_code == 409
    done = await api.call("POST", f"{PLAT}/resume", role="super_admin", json={"reason": "All clear"})
    assert done.status_code == 200 and done.json()["stop"]["platform"] is None
    assert (await api.call("POST", f"{PLAT}/resume", role="super_admin", json={"reason": "again"})).status_code == 409
    events = [r["controlEvent"] for r in await _controls(api.db, PLATFORM)]
    assert sorted(events) == ["platform_stop_cleared", "platform_stop_pressed"]


async def test_a_key_may_press_the_platform_stop(api):
    scoped = await api.call("POST", f"{PLAT}/stop", role="super_admin", auth="api_key",
                            scopes=["control:platform_autonomous_ops"], username="ci-key")
    assert scoped.status_code == 200
    unscoped = await api.call("POST", f"{PLAT}/stop", role="super_admin", auth="api_key", scopes=["view:autonomous_ops"])
    assert unscoped.status_code == 403


# ------------------------------------------------------------------ the permission matrix on the mounted app

TENANT_KEY = dict(auth="api_key", scopes=ALL_SCOPES)
WRITES_NO_KEY = [("POST", "/api/autonomous-ops/resume"), ("PUT", "/api/autonomous-ops/settings/level"),
                 ("POST", "/api/autonomous-ops/settings/restore-level"), ("POST", "/api/autonomous-ops/never-touch"),
                 ("DELETE", "/api/autonomous-ops/never-touch/NT-x"),
                 ("POST", "/api/autonomous-ops/actions/AO-x/approve"), ("POST", "/api/autonomous-ops/actions/AO-x/deny"),
                 ("POST", "/api/autonomous-ops/actions/AO-x/undo")]
PLATFORM_ROUTES = [("GET", "/api/platform/autonomous-ops/status"), ("GET", "/api/platform/autonomous-ops/actions"),
                   ("POST", "/api/platform/autonomous-ops/stop"), ("POST", "/api/platform/autonomous-ops/resume"),
                   ("PUT", "/api/platform/autonomous-ops/tenants/t1/max-level"),
                   ("PUT", "/api/platform/autonomous-ops/tenants/t1/shadow"),
                   ("GET", "/api/platform/autonomous-ops/never-touch"), ("POST", "/api/platform/autonomous-ops/never-touch"),
                   ("DELETE", "/api/platform/autonomous-ops/never-touch/NT-x")]


def test_write_permission_matrix_on_the_mounted_app():
    """protects=GATE-13 and PROH-81-10/15 on the full app (no database: an allowed route answers 422, 404
    or 503, never 403); fails_when=a key reaches a decision route, a role without manage reaches a manage
    route, or platform staff without the permission write."""
    stop_path = "/api/autonomous-ops/stop"
    groups = {
        "stop_allowed": [_case(stop_path, role, method="POST") for role in
                         ("tenant_admin", "security_analyst", "incident_responder")]
        + [_case(stop_path + "?tenantId=t1", "super_admin", method="POST"),
           _case(stop_path, "tenant_admin", method="POST", auth="api_key", scopes=["control:autonomous_ops"])],
        "stop_denied": [_case(stop_path, role, method="POST") for role in ("analyst", "viewer", "user", "itam_admin")]
        + [_case(stop_path + "?tenantId=t1", role, method="POST") for role in ("platform_support", "platform_billing")]
        + [_case(stop_path, "tenant_admin", method="POST", auth="api_key", scopes=["view:autonomous_ops"])],
    }
    for method, path in WRITES_NO_KEY:
        manage_only = path.endswith(("/resume", "/level", "/restore-level", "/never-touch")) or "never-touch/" in path
        groups[method, path, "key"] = [_case(path, "tenant_admin", method=method, **TENANT_KEY),
                                       _case(path + "?tenantId=t1", "super_admin", method=method, **TENANT_KEY)]
        groups[method, path, "support"] = [_case(path + "?tenantId=t1", "platform_support", method=method),
                                           _case(path + "?tenantId=t1", "platform_billing", method=method)]
        groups[method, path, "lacking"] = [_case(path, role, method=method) for role in
                                           (("analyst", "viewer", "security_analyst", "incident_responder")
                                            if manage_only else ("analyst", "viewer"))]
        groups[method, path, "session"] = [_case(path, "tenant_admin", method=method),
                                           _case(path + "?tenantId=t1", "super_admin", method=method)]
    got = _probe(groups)
    assert all(code != 403 for code in got["stop_allowed"]), got["stop_allowed"]
    assert got["stop_denied"] == [403] * len(got["stop_denied"]), got["stop_denied"]
    for key, codes in got.items():
        if not isinstance(key, tuple):
            continue
        method, path, kind = key
        if kind == "session":
            assert all(code != 403 for code in codes), (method, path, codes)
        else:
            assert codes == [403] * len(codes), (method, path, kind, codes)


def test_platform_router_matrix_on_the_mounted_app():
    """protects=T-81-35/36; fails_when=anyone but the Super Admin reaches the platform router, or a key
    resumes or lifts shadow."""
    scope = ["control:platform_autonomous_ops"]
    groups = {"denied": [], "super": [], "key_denied": [], "key_stop": []}
    for method, path in PLATFORM_ROUTES:
        groups["denied"] += [_case(path, role, method=method) for role in
                             ("tenant_admin", "security_analyst", "platform_support", "platform_billing", "analyst")]
        groups["super"].append(_case(path, "super_admin", method=method))
        if not path.endswith("/stop"):
            groups["key_denied"].append(_case(path, "super_admin", method=method, auth="api_key", scopes=scope))
    groups["key_stop"] = [_case("/api/platform/autonomous-ops/stop", "super_admin", method="POST", auth="api_key",
                                scopes=scope)]
    got = _probe(groups)
    assert got["denied"] == [403] * len(got["denied"]), got["denied"]
    assert all(code != 403 for code in got["super"]), got["super"]
    assert got["key_denied"] == [403] * len(got["key_denied"]), got["key_denied"]
    assert got["key_stop"][0] != 403
