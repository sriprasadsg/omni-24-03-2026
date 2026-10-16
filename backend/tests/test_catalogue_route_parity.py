"""Catalogue route parity (Phase 76, D-05).

76-01 covers the seeded Mobile Device Management catalogue and the negative controls that
prove the parity helper names untagged and mis-tagged routes. Later plans extend the
manifest and tighten these checks.
"""
import os
import re

from fastapi import APIRouter, Depends, FastAPI

from catalogue_guards import agent_tolerant, catalogue_exempt, catalogue_guard
from tests._catalogue_parity import (
    REPO_ROOT, SLICES, ledger_offenders, load_ledger, load_manifest, owner_of, parity_offenders,
    slice_modules,
)
from tests._route_walk import run_real_app_walk, walk_app


def _synthetic_records(*dependencies):
    # Imported here, not at module top: test_authentication reloads authentication_service,
    # and the walker compares dependency identity against the module's current functions.
    import authentication_service as auth
    get_current_user = auth.get_current_user
    router = APIRouter(prefix="/api/mdm")

    @router.get("/devices")
    async def list_devices(user=Depends(get_current_user)):
        return {}

    app = FastAPI()
    app.include_router(router, dependencies=list(dependencies))
    return walk_app(app)["routes"]


def test_mdm_routes_carry_manifest_guard():
    records = run_real_app_walk()["routes"]
    assert parity_offenders(records, load_manifest(), modules=["mdm_endpoints"]) == []
    tagged = [r for r in records
              if r["path"].startswith("/api/mdm") and any(t["catalogue"] == "mobileDeviceManagement" for t in r["tags"])]
    assert tagged, "no /api/mdm route carries the mobileDeviceManagement tag"
    assert all(r["known_guard"] for r in tagged)


def test_offender_named_for_untagged_route():
    offenders = parity_offenders(_synthetic_records(), load_manifest())
    assert len(offenders) == 1
    text = offenders[0]
    assert "GET" in text and "/api/mdm/devices" in text
    assert "tests.test_catalogue_route_parity" in text or "test_catalogue_route_parity" in text
    assert 'expected catalogue_guard("mobileDeviceManagement", read=[\'view:mdm\'], write=[\'manage:assets\'])' in text


def test_offender_named_for_wrong_tag():
    wrong = catalogue_guard("assetManagement", read=("view:assets",), write=("manage:assets",))
    offenders = parity_offenders(_synthetic_records(Depends(wrong)), load_manifest())
    assert len(offenders) == 1
    assert 'expected catalogue_guard("mobileDeviceManagement"' in offenders[0]
    assert 'found catalogue_guard("assetManagement"' in offenders[0]


def test_matching_tag_is_not_an_offender():
    right = catalogue_guard("mobileDeviceManagement", read=("view:mdm",), write=("manage:assets",))
    assert parity_offenders(_synthetic_records(Depends(right)), load_manifest()) == []


def test_longest_prefix_wins():
    manifest = {"groups": [{"id": "security", "title": "S", "enforce": True}], "catalogues": [
        {"view": "security", "group": "security", "permission": "view:security", "routes": ["/api/security"]},
        {"view": "attackPath", "group": "security", "permission": "view:attack_path",
         "routes": ["/api/security/attack-path"]},
    ]}
    assert owner_of("/api/security/attack-path/graph", manifest)["view"] == "attackPath"
    assert owner_of("/api/security/attack-path", manifest)["view"] == "attackPath"
    assert owner_of("/api/security/alerts", manifest)["view"] == "security"
    assert owner_of("/api/securityx", manifest) is None  # segment boundary, not string prefix


def test_slices_partition_every_in_scope_catalogue_once():
    views = [view for group in SLICES.values() for view in group]
    assert len(views) == len(set(views)) == 110  # 98 sidebar catalogues + 12 enforced views with no sidebar item
    # 76-03 moved the per-view sidebar entries into the presentation map (one key per nav view).
    sidebar = open(os.path.join(REPO_ROOT, "components", "sidebarPresentation.tsx"), encoding="utf-8").read()
    sidebar_views = set(re.findall(r"^\s+(\w+): \{ icon:", sidebar, re.M))
    assert sidebar_views, "no sidebar views parsed from components/sidebarPresentation.tsx"
    identity = {"userManagement", "roleManagement", "apiKeys", "profile", "notifications", "integrations"}
    aliases = {"agentChat", "supportChat", "vulnerabilities", "persistence", "insiderThreat", "fim"}
    assert identity | aliases <= set(views)
    assert set(views) - identity - aliases <= sidebar_views


def test_slice_modules_assign_each_module_to_one_slice():
    manifest = {"groups": [{"id": "infra", "title": "I", "enforce": True}], "catalogues": [
        {"view": "assetManagement", "group": "infra", "permission": "view:assets", "routes": ["/api/assets"]},
        {"view": "agents", "group": "infra", "permission": "view:agents", "routes": ["/api/agents"]},
        {"view": "mobileDeviceManagement", "group": "infra", "permission": "view:mdm", "routes": ["/api/mdm"]},
    ]}

    def rec(module, path):
        return {"methods": ["GET"], "path": path, "module": module, "auth": "user", "tags": [], "exempt": None}

    records = [
        rec("mixed", "/api/assets/a"), rec("mixed", "/api/assets/b"), rec("mixed", "/api/agents/a"),
        rec("tie", "/api/mdm/a"), rec("tie", "/api/agents/a"),
        {**rec("agent_only", "/api/agents/x"), "auth": "agent"},
    ]
    assert slice_modules("assets", records, manifest) == ["mixed"]
    assert slice_modules("agents", records, manifest) == ["tie"]  # tie goes to the earlier slice
    assert slice_modules("devices", records, manifest) == []


# --- Phase 76-11: gap ledger and ratchets (ACC-04, ACC-05, D-05) -------------------------------
# Negative controls run on synthetic apps and synthetic manifest/ledger dicts, so each failure
# mode is proven to fire without touching the committed ledger (PROH-76-03).

LEDGER_MANIFEST = {
    "groups": [
        {"id": "infra", "title": "Infra", "enforce": True},
        {"id": "governance", "title": "Governance", "enforce": False},
    ],
    "catalogues": [
        {"view": "mobileDeviceManagement", "group": "infra", "permission": "view:mdm", "routes": ["/api/mdm"]},
        {"view": "compliance", "group": "governance", "permission": "view:compliance", "routes": ["/api/compliance"]},
    ],
}


def _ledger(*routers, agent=0, exempt=0, agent_routes=None, exempt_routes=None):
    ledger = {"version": 1, "agentAuthExcludedRoutes": agent, "maxExemptRoutes": exempt,
              "routers": sorted(routers, key=lambda e: e["module"])}
    if agent_routes is not None:
        ledger["agentCapableRoutes"] = agent_routes
    if exempt_routes is not None:
        ledger["exemptRoutes"] = exempt_routes
    return ledger


def _entry(module="gov_mod", group="governance", maximum=2, reason="Governance group: guards deferred (D-01)"):
    return {"module": module, "group": group, "maxUnguardedRoutes": maximum, "reason": reason}


def _walk(*specs):
    """Walk a synthetic app. Spec: (path, module, extra dependencies, auth function name[, methods])."""
    import authentication_service as auth
    app = FastAPI()
    router = APIRouter()
    for index, spec in enumerate(specs):
        path, module, deps, auth_name = spec[:4]
        methods = list(spec[4]) if len(spec) > 4 else ["GET"]
        user_auth = getattr(auth, auth_name)

        def endpoint(user=Depends(user_auth)):
            return {}

        endpoint.__module__ = module
        endpoint.__name__ = f"endpoint_{index}"
        router.add_api_route(path, endpoint, methods=methods, dependencies=list(deps))
    app.include_router(router)
    return walk_app(app)["routes"]


def _gov(path, module="gov_mod", deps=(), auth_name="get_current_user", methods=("GET",)):
    return (path, module, deps, auth_name, methods)


def test_ledger_offender_for_unledgered_router():
    records = _walk(_gov("/api/compliance/a"), _gov("/api/compliance/b"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger())
    assert len(offenders) == 1
    text = offenders[0]
    assert "gov_mod" in text and "not in shared/catalogue-gaps.json" in text
    assert '"module": "gov_mod"' in text and '"group": "governance"' in text
    assert '"maxUnguardedRoutes": 2' in text


def test_ledger_offender_for_unowned_router_group():
    records = _walk(_gov("/api/other/a", module="loose_mod"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger())
    assert len(offenders) == 1 and '"group": "unowned"' in offenders[0]


def test_ledger_offender_when_count_above_ratchet():
    records = _walk(_gov("/api/compliance/a"), _gov("/api/compliance/b"), _gov("/api/compliance/c"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(_entry(maximum=2)))
    assert len(offenders) == 1
    assert "gov_mod" in offenders[0] and "3" in offenders[0] and "2" in offenders[0]
    assert "above" in offenders[0]


def test_ledger_offender_when_ratchet_has_slack():
    records = _walk(_gov("/api/compliance/a"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(_entry(maximum=3)))
    assert len(offenders) == 1
    assert "gov_mod" in offenders[0] and "lower" in offenders[0] and "1" in offenders[0]


def test_ledger_offender_for_stale_entry_without_unguarded_routes():
    guarded = Depends(catalogue_exempt("not a ledger concern, reviewed elsewhere"))
    records = _walk(_gov("/api/compliance/a", deps=[guarded]))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(_entry(maximum=1), agent=0, exempt=1))
    assert len(offenders) == 1
    assert "stale" in offenders[0] and "gov_mod" in offenders[0]


def test_ledger_offender_for_unmounted_module():
    records = _walk(_gov("/api/compliance/a"))
    ledger = _ledger(_entry(maximum=1), _entry(module="ghost_mod", maximum=1))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, ledger)
    assert len(offenders) == 1
    assert "stale" in offenders[0] and "ghost_mod" in offenders[0]


def test_ledger_offender_for_missing_reason_or_group():
    records = _walk(_gov("/api/compliance/a"))
    for field in ("reason", "group"):
        broken = {**_entry(maximum=1), field: "  "}
        offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(broken))
        assert len(offenders) == 1
        assert "gov_mod" in offenders[0] and field in offenders[0]


def test_ledger_offender_for_enforced_route_in_ledger():
    records = _walk(_gov("/api/mdm/a", module="mdm_mod"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(_entry(module="mdm_mod", group="infra", maximum=1)))
    assert len(offenders) == 1
    assert "mdm_mod" in offenders[0] and "enforced" in offenders[0] and "/api/mdm/a" in offenders[0]


def test_enforced_route_without_ledger_entry_is_left_to_parity():
    records = _walk(_gov("/api/mdm/a", module="mdm_mod"))
    assert ledger_offenders(records, LEDGER_MANIFEST, _ledger()) == []
    assert len(parity_offenders(records, LEDGER_MANIFEST)) == 1


def test_ledger_offender_for_agent_capable_over_ratchet():
    records = _walk(_gov("/api/compliance/a", module="agent_mod", auth_name="get_current_user_or_agent"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=0))
    assert len(offenders) == 1
    assert "agentAuthExcludedRoutes" in offenders[0] and "/api/compliance/a" in offenders[0]


def test_ledger_offender_for_exempt_over_ratchet_or_short_reason():
    exempt = Depends(catalogue_exempt("self-service: caller's own record"))
    records = _walk(_gov("/api/mdm/a", module="mdm_mod", deps=[exempt]))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(exempt=0))
    assert len(offenders) == 1
    assert "maxExemptRoutes" in offenders[0] and "/api/mdm/a" in offenders[0]
    terse = Depends(catalogue_exempt("n/a"))
    records = _walk(_gov("/api/mdm/a", module="mdm_mod", deps=[terse]))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(exempt=1))
    assert len(offenders) == 1
    assert "/api/mdm/a" in offenders[0] and "reason" in offenders[0]


def test_ledger_offender_for_duplicate_entries():
    records = _walk(_gov("/api/compliance/a"))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(_entry(maximum=1), _entry(maximum=1)))
    assert any("duplicate" in o and "gov_mod" in o for o in offenders)


def test_known_guard_and_tagged_routes_need_no_ledger_entry():
    from rbac_utils import require_permission
    from catalogue_guards import catalogue_guard
    tagged = Depends(catalogue_guard("compliance", read=("view:compliance",), write=("manage:compliance",)))
    records = _walk(
        _gov("/api/compliance/a", deps=[Depends(require_permission("view:compliance"))]),
        _gov("/api/compliance/b", module="other_mod", deps=[tagged]),
    )
    assert ledger_offenders(records, LEDGER_MANIFEST, _ledger()) == []


def test_compliant_synthetic_app_has_no_ledger_offenders():
    exempt = Depends(catalogue_exempt("self-service: caller's own record"))
    records = _walk(
        _gov("/api/compliance/a"), _gov("/api/compliance/b"),
        _gov("/api/mdm/a", module="mdm_mod", deps=[exempt]),
        _gov("/api/compliance/c", module="agent_mod", auth_name="get_current_user_or_agent"),
    )
    ledger = _ledger(_entry(maximum=2), agent=1, exempt=1)
    assert ledger_offenders(records, LEDGER_MANIFEST, ledger) == []



# --- Phase 76-11: strict whole-app gate over the production route table -------------------------
# One walk of the production registry (cached for the session), so the verdicts do not depend
# on test order or parallelism. None of these tests writes the committed ledger (PROH-76-03).


def test_load_ledger_is_shaped_and_sorted():
    ledger = load_ledger()
    assert set(ledger) >= {"version", "agentAuthExcludedRoutes", "maxExemptRoutes", "routers",
                           "agentCapableRoutes"}
    modules = [entry["module"] for entry in ledger["routers"]]
    assert modules == sorted(modules)
    assert all(entry["reason"].strip() and entry["group"].strip() for entry in ledger["routers"])
    listed = ledger["agentCapableRoutes"]
    routes = [entry["route"] for entry in listed]
    assert routes == sorted(routes)
    assert all(entry["reason"].strip() for entry in listed)
    assert len(listed) == ledger["agentAuthExcludedRoutes"]


def test_all_enforced_routes_guarded():
    """D-05: every user route owned by an enforce:true catalogue carries its catalogue guard."""
    offenders = parity_offenders(run_real_app_walk()["routes"], load_manifest())
    assert offenders == [], "unguarded or mis-guarded enforced routes:\n" + "\n".join(offenders)


def test_unguarded_routers_are_ledgered():
    """D-05 deny-by-default: an unguarded router must be in the committed gap ledger with a reason."""
    offenders = ledger_offenders(run_real_app_walk()["routes"], load_manifest(), load_ledger())
    unledgered = [o for o in offenders if "not in shared/catalogue-gaps.json" in o]
    assert unledgered == [], "unguarded routers missing from shared/catalogue-gaps.json:\n" + "\n".join(unledgered)


def test_ledger_ratchets():
    """The ledger can only shrink: no stale entries, no enforced routes, counts within ratchets."""
    offenders = ledger_offenders(run_real_app_walk()["routes"], load_manifest(), load_ledger())
    assert offenders == [], "gap ledger out of step with the route table:\n" + "\n".join(offenders)


# --- Phase 76-14: agent-capable routes in the parity scope and the reviewed agentCapableRoutes list ---
# (WR-01 gate half, D-05, D-02). Synthetic apps only; the committed ledger is never written (PROH-76-03).

MDM_TOLERANT = agent_tolerant(catalogue_guard("mobileDeviceManagement", read=("view:mdm",), write=("manage:mdm",)))
MDM_PLAIN = catalogue_guard("mobileDeviceManagement", read=("view:mdm",), write=("manage:mdm",))


def _agent_route(path="/api/mdm/a", deps=(), methods=("GET",), module="agent_mod"):
    return _gov(path, module=module, deps=deps, auth_name="get_current_user_or_agent", methods=methods)


def test_untagged_agent_capable_read_in_enforced_catalogue_is_a_parity_offender():
    offenders = parity_offenders(_walk(_agent_route()), LEDGER_MANIFEST)
    assert len(offenders) == 1
    text = offenders[0]
    assert "GET /api/mdm/a (agent_mod)" in text
    assert 'agent_tolerant(catalogue_guard("mobileDeviceManagement", read=[\'view:mdm\'], write=[\'manage:mdm\']))' in text


def test_agent_tolerant_tag_on_agent_capable_read_is_not_an_offender():
    records = _walk(_agent_route(deps=[Depends(MDM_TOLERANT)]))
    assert parity_offenders(records, LEDGER_MANIFEST) == []


def test_plain_guard_on_agent_capable_route_would_refuse_the_agent():
    offenders = parity_offenders(_walk(_agent_route(deps=[Depends(MDM_PLAIN)])), LEDGER_MANIFEST)
    assert len(offenders) == 1
    assert "refuse the agent" in offenders[0] and "agent_tolerant" in offenders[0]
    assert "GET /api/mdm/a" in offenders[0]


def test_plain_guard_on_agent_capable_route_is_refused_outside_enforced_catalogues_too():
    plain = catalogue_guard("compliance", read=("view:compliance",), write=("manage:compliance",))
    records = _walk(_agent_route(path="/api/compliance/a", deps=[Depends(plain)], methods=("POST",)))
    offenders = parity_offenders(records, LEDGER_MANIFEST)
    assert len(offenders) == 1 and "refuse the agent" in offenders[0]


def test_untagged_agent_capable_write_is_not_a_parity_offender():
    assert parity_offenders(_walk(_agent_route(methods=("POST",))), LEDGER_MANIFEST) == []


def test_agent_capable_route_under_unenforced_catalogue_is_not_a_parity_offender():
    assert parity_offenders(_walk(_agent_route(path="/api/compliance/a")), LEDGER_MANIFEST) == []


def test_slice_modules_ignores_agent_capable_records():
    records = _walk(_agent_route(), _gov("/api/mdm/b", module="user_mod"))
    modules = [m for name in SLICES for m in slice_modules(name, records, LEDGER_MANIFEST)]
    assert modules == ["user_mod"]


def test_ledger_offender_for_unlisted_agent_capable_route_is_paste_ready():
    records = _walk(_agent_route(methods=("POST",)))
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1, agent_routes=[]))
    assert len(offenders) == 1
    assert "POST /api/mdm/a" in offenders[0] and "agentCapableRoutes" in offenders[0]
    assert '{"route": "POST /api/mdm/a", "reason": ' in offenders[0]


def test_listed_agent_capable_route_with_reason_is_clean():
    records = _walk(_agent_route(methods=("POST",)))
    listed = [{"route": "POST /api/mdm/a", "reason": "agent ingest: people need manage:agents"}]
    assert ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1, agent_routes=listed)) == []


def test_ledger_refuses_a_listed_agent_capable_read_under_an_enforced_catalogue():
    records = _walk(_agent_route())
    listed = [{"route": "GET /api/mdm/a", "reason": "agent reads the installer package"}]
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1, agent_routes=listed))
    assert len(offenders) == 1
    assert "GET /api/mdm/a" in offenders[0] and "agent_tolerant" in offenders[0]


def test_ledger_offender_for_stale_agent_capable_entry():
    records = _walk(_agent_route(methods=("POST",)))
    listed = [{"route": "POST /api/mdm/a", "reason": "agent ingest: people need manage:agents"},
              {"route": "POST /api/mdm/ghost", "reason": "agent ingest: route was removed"}]
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1, agent_routes=listed))
    assert len(offenders) == 1
    assert "stale" in offenders[0] and "/api/mdm/ghost" in offenders[0]


def test_ledger_offender_for_tagged_route_left_in_agent_capable_list():
    records = _walk(_agent_route(deps=[Depends(MDM_TOLERANT)]))
    listed = [{"route": "GET /api/mdm/a", "reason": "agent reads the installer package"}]
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=0, agent_routes=listed))
    assert len(offenders) == 1 and "stale" in offenders[0]


def test_ledger_offender_for_short_placeholder_or_duplicate_agent_capable_reason():
    records = _walk(_agent_route(methods=("POST",)))
    for reason in ("short", "<state why this agent-capable route carries no catalogue tag>"):
        listed = [{"route": "POST /api/mdm/a", "reason": reason}]
        offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1, agent_routes=listed))
        assert len(offenders) == 1 and "POST /api/mdm/a" in offenders[0] and "reason" in offenders[0]
    twice = [{"route": "POST /api/mdm/a", "reason": "agent ingest: people need manage:agents"}] * 2
    offenders = ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1, agent_routes=twice))
    assert any("duplicate" in o and "POST /api/mdm/a" in o for o in offenders)


def test_agent_ratchet_counts_only_untagged_agent_capable_routes():
    records = _walk(_agent_route(), _agent_route(path="/api/mdm/b", deps=[Depends(MDM_TOLERANT)]))
    assert ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=1)) == []
    assert any("agentAuthExcludedRoutes" in o for o in ledger_offenders(records, LEDGER_MANIFEST, _ledger(agent=2)))
