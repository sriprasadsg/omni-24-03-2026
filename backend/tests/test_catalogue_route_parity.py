"""Catalogue route parity (Phase 76, D-05).

76-01 covers the seeded Mobile Device Management catalogue and the negative controls that
prove the parity helper names untagged and mis-tagged routes. Later plans extend the
manifest and tighten these checks.
"""
import os
import re

from fastapi import APIRouter, Depends, FastAPI

from catalogue_guards import catalogue_guard
from catalogue_guards import catalogue_exempt
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


def _ledger(*routers, agent=0, exempt=0):
    return {"version": 1, "agentAuthExcludedRoutes": agent, "maxExemptRoutes": exempt,
            "routers": sorted(routers, key=lambda e: e["module"])}


def _entry(module="gov_mod", group="governance", maximum=2, reason="Governance group: guards deferred (D-01)"):
    return {"module": module, "group": group, "maxUnguardedRoutes": maximum, "reason": reason}


def _walk(*specs):
    """Walk a synthetic app. Spec: (path, module, extra dependencies, auth function name)."""
    import authentication_service as auth
    app = FastAPI()
    router = APIRouter()
    for index, (path, module, deps, auth_name) in enumerate(specs):
        user_auth = getattr(auth, auth_name)

        def endpoint(user=Depends(user_auth)):
            return {}

        endpoint.__module__ = module
        endpoint.__name__ = f"endpoint_{index}"
        router.add_api_route(path, endpoint, methods=["GET"], dependencies=list(deps))
    app.include_router(router)
    return walk_app(app)["routes"]


def _gov(path, module="gov_mod", deps=(), auth_name="get_current_user"):
    return (path, module, deps, auth_name)


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

