"""Catalogue route parity (Phase 76, D-05).

76-01 covers the seeded Mobile Device Management catalogue and the negative controls that
prove the parity helper names untagged and mis-tagged routes. Later plans extend the
manifest and tighten these checks.
"""
import os
import re

from fastapi import APIRouter, Depends, FastAPI

from authentication_service import get_current_user
from catalogue_guards import catalogue_guard
from tests._catalogue_parity import (
    REPO_ROOT, SLICES, load_manifest, owner_of, parity_offenders, slice_modules,
)
from tests._route_walk import run_real_app_walk, walk_app


def _synthetic_records(*dependencies):
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
    assert len(views) == len(set(views)) == 104  # 98 sidebar catalogues + 6 identity views
    sidebar = open(os.path.join(REPO_ROOT, "components", "Sidebar.tsx"), encoding="utf-8").read()
    sidebar_views = set(re.findall(r"view:\s*'(\w+)'", sidebar))
    identity = {"userManagement", "roleManagement", "apiKeys", "profile", "notifications", "integrations"}
    assert identity <= set(views)
    assert set(views) - identity <= sidebar_views


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
