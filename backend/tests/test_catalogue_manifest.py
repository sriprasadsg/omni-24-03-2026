"""Catalogue manifest sanity and route ownership (Phase 76, ACC-03).

Reads ``shared/catalogue-access.json`` and checks it against the frontend sources
(``types.ts``, ``components/Sidebar.tsx``, ``App.tsx``) with plain regexes (no TS
toolchain), against ``rbac_defaults`` (every string must be grantable) and against the
mounted route table (every prefix is real, every user route has an owner or a reason).

``manifest_problems`` holds the structural rules so negative controls can prove the
rules fire on a broken manifest, not only that the real one passes.
"""
import os
import re
from typing import Any, Dict, Iterable, List, Set

import pytest

import rbac_defaults
from tests._catalogue_parity import (
    REPO_ROOT, SLICES, load_manifest, owner_of, resolved_read, resolved_write,
)
from tests._route_walk import run_real_app_walk

ENFORCED_GROUPS = {"infra", "security", "mgmt"}
SIDEBAR_GROUPS = [
    "dashboards", "observability", "infra", "security", "devsecops", "governance", "automation", "mgmt",
]
NINE_MISMATCHED = {
    "agentCapabilities": "view:agent_capabilities",
    "jobs": "view:jobs",
    "llmops": "view:llmops",
    "persistenceDetection": "view:persistence",
    "sustainability": "view:sustainability",
    "swarm": "view:swarm",
    "unifiedOps": "view:unified_ops",
    "vulnerabilityManagement": "view:vulnerabilities",
    "zeroTrustQuantum": "view:zero_trust",
}
D08_TRIO = ("subscriptionManagement", "invoices", "knowledgeBase")
ALLOWED_FIELDS = {"view", "label", "group", "nav", "permission", "read", "write", "routes", "noBackendReason"}
SHARES = re.compile(r"^shares routes with (\w+)$")
PERMISSION = re.compile(r"^[a-z_]+:[a-z_0-9]+$")


def _read(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as handle:
        return handle.read()


def _appview_members() -> List[str]:
    text = _read("types.ts")
    body = text[text.index("export type AppView"):]
    body = body[: body.index(";")]
    return re.findall(r"\|\s*'(\w+)'", body)


def _sidebar_nav() -> List[Dict[str, str]]:
    """Items of the ``navGroups`` literal in order, or [] once Sidebar reads the manifest."""
    text = _read("components/Sidebar.tsx")
    start = text.find("const navGroups")
    if start < 0 or "title:" not in text[start:start + 600]:
        return []
    end = text.index("], []);", start)
    items, group = [], None
    for line in text[start:end].splitlines():
        title = re.search(r'title: "([^"]+)"', line)
        if title:
            group = title.group(1)
        item = re.search(r"\{ view: '(\w+)', label: '([^']*)'.*?permission: '([^']+)'", line)
        if item:
            items.append({"group": group, "view": item.group(1), "label": item.group(2), "permission": item.group(3)})
    return items


def _app_permission_map() -> Dict[str, str]:
    """``viewPermissionMap`` literal from App.tsx, or {} once App reads the manifest."""
    text = _read("App.tsx")
    start = text.find("const viewPermissionMap")
    if start < 0:
        return {}
    body = text[start:]
    body = body[: body.index("};")]
    return dict(re.findall(r"^\s*(\w+): '([^']+)'", body, re.M))


def _granted() -> Set[str]:
    granted: Set[str] = set(rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS)
    for perms in rbac_defaults.ROLE_DEFAULTS.values():
        granted.update(perms)
    return granted


def _matches(prefix: str, path: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def manifest_problems(manifest: Dict[str, Any], mounted_paths: Iterable[str] = ()) -> List[str]:
    """Structural rules (EDGE-ACC-03-adjacency and EDGE-ACC-03-empty)."""
    problems: List[str] = []
    cats = manifest.get("catalogues") or []
    groups = manifest.get("groups") or []
    if not cats:
        problems.append("manifest has no catalogues")
    views = {c["view"] for c in cats}
    for group in groups:
        if not any(c["group"] == group["id"] for c in cats):
            problems.append(f"group {group['id']} has no catalogues")
    claimed: Dict[str, str] = {}
    paths = list(mounted_paths)
    for cat in cats:
        routes, reason = cat.get("routes") or [], (cat.get("noBackendReason") or "").strip()
        if not routes and not reason:
            problems.append(f"{cat['view']}: empty routes without noBackendReason")
        if routes and reason:
            problems.append(f"{cat['view']}: has routes and a noBackendReason")
        shared = SHARES.match(reason)
        if shared and shared.group(1) not in views:
            problems.append(f"{cat['view']}: noBackendReason names unknown view {shared.group(1)}")
        for prefix in routes:
            if not prefix.startswith("/api/"):
                problems.append(f"{cat['view']}: prefix {prefix} does not start with /api/")
            if prefix in claimed:
                problems.append(f"prefix {prefix} claimed by {claimed[prefix]} and {cat['view']}")
            claimed[prefix] = cat["view"]
            if paths and not any(_matches(prefix, p) for p in paths):
                problems.append(f"{cat['view']}: prefix {prefix} matches no mounted route")
    return problems


@pytest.fixture(scope="module")
def manifest() -> Dict[str, Any]:
    return load_manifest()


@pytest.fixture(scope="module")
def by_view(manifest) -> Dict[str, Dict[str, Any]]:
    return {c["view"]: c for c in manifest["catalogues"]}


@pytest.fixture(scope="module")
def walk() -> List[Dict[str, Any]]:
    return run_real_app_walk()["routes"]


def test_views_equal_appview_union(manifest):
    expected = _appview_members()
    got = [c["view"] for c in manifest["catalogues"]]
    assert len(expected) == len(set(expected)) == 202
    assert len(got) == len(set(got)), "duplicate view in manifest"
    assert sorted(set(expected) - set(got)) == [], "AppView members missing from the manifest"
    assert sorted(set(got) - set(expected)) == [], "manifest views that are not AppView members"


def test_groups_are_sidebar_groups_in_order_and_only_three_enforce(manifest):
    assert [g["id"] for g in manifest["groups"]] == SIDEBAR_GROUPS
    assert {g["id"] for g in manifest["groups"] if g["enforce"]} == ENFORCED_GROUPS
    assert all(c["group"] in SIDEBAR_GROUPS for c in manifest["catalogues"])


def test_nav_entries_are_188_and_follow_sidebar_order(manifest):
    nav = [c for c in manifest["catalogues"] if c["nav"]]
    assert len(nav) == 188
    order = {g: i for i, g in enumerate(SIDEBAR_GROUPS)}
    assert [order[c["group"]] for c in nav] == sorted(order[c["group"]] for c in nav)
    literal = _sidebar_nav()
    if literal:
        assert [c["view"] for c in nav] == [i["view"] for i in literal]
        assert [c["label"] for c in nav] == [i["label"] for i in literal]


def test_every_entry_has_exactly_one_permission_string(manifest):
    for cat in manifest["catalogues"]:
        assert set(cat) <= ALLOWED_FIELDS, cat["view"]
        assert isinstance(cat["permission"], str) and PERMISSION.match(cat["permission"]), cat["view"]
        for key in ("read", "write"):
            assert all(PERMISSION.match(p) for p in cat.get(key, [])), (cat["view"], key)


def test_sidebar_and_app_agree_with_manifest(manifest, by_view):
    """Two-state rule: literals must match the manifest until 76-03 removes them."""
    sidebar, app_map = _sidebar_nav(), _app_permission_map()
    d08 = {v: "manage:settings" for v in D08_TRIO}
    if sidebar:
        for item in sidebar:
            want = d08.get(item["view"], item["permission"])
            assert by_view[item["view"]]["permission"] == want, item["view"]
            assert by_view[item["view"]]["group"] == next(
                g["id"] for g, title in zip(manifest["groups"], _group_titles(manifest)) if title == item["group"]
            ), item["view"]
    else:
        text = _read("components/Sidebar.tsx")
        assert "utils/catalogueAccess" in text, "Sidebar must read the shared manifest"
        assert not re.search(r"permission: '(view|manage|investigate):", text), "item-level permission literal left in Sidebar"
    if app_map:
        allowed = set(NINE_MISMATCHED) | set(D08_TRIO)
        diffs = {v for v, p in app_map.items() if by_view[v]["permission"] != p}
        assert diffs <= allowed, f"App map disagrees outside D-11/D-08: {sorted(diffs - allowed)}"
        assert set(app_map) == set(by_view)
    else:
        assert "catalogueAccess" in _read("App.tsx"), "App must resolve view permissions from the manifest"


def _group_titles(manifest) -> List[str]:
    return [g["title"] for g in manifest["groups"]]


def test_nine_mismatched_views_use_the_sidebar_string(by_view):
    for view, perm in NINE_MISMATCHED.items():
        assert by_view[view]["permission"] == perm, view
    assert "view:jobs" in rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS


def test_d08_billing_trio_is_manage_settings_and_finops_is_view_finops(by_view):
    for view in D08_TRIO:
        assert by_view[view]["permission"] == "manage:settings", view
    owned = {p for v in D08_TRIO + ("paymentSettings",) for p in by_view[v]["routes"]}
    for prefix in ("/api/payments", "/api/billing", "/api/knowledge"):
        assert prefix in {p for v in D08_TRIO for p in by_view[v]["routes"]}, prefix
    assert all(p.startswith(("/api/payments", "/api/billing", "/api/knowledge")) for p in owned)
    assert by_view["finops"]["permission"] == "view:finops"
    assert "/api/finops" in by_view["finops"]["routes"]


def test_d09_users_and_roles_read_rule_and_write_lists(by_view):
    for view in ("userManagement", "roleManagement"):
        assert sorted(resolved_read(by_view[view])) == ["manage:rbac", "manage:users"], view
        assert by_view[view]["permission"] == "manage:rbac", view
    assert "/api/users" in by_view["userManagement"]["routes"]
    assert "/api/roles" in by_view["roleManagement"]["routes"]
    # the existing /api/users writes are guarded by _require_itam_admin_session_only (manage:assets)
    assert resolved_write(by_view["userManagement"]) == ["manage:assets"]


def test_every_manifest_string_is_granted_by_some_role(manifest):
    granted = _granted()
    ungranted = sorted(
        (c["view"], p)
        for c in manifest["catalogues"]
        for p in [c["permission"], *c.get("read", []), *c.get("write", [])]
        if p not in granted
    )
    assert ungranted == [], f"strings no role holds and not super-admin only: {ungranted}"


def test_enforced_catalogues_have_explicit_write_lists(manifest):
    for cat in manifest["catalogues"]:
        if cat["group"] in ENFORCED_GROUPS and cat["routes"]:
            assert cat.get("write"), f"{cat['view']}: enforced catalogue with routes needs an explicit write list"


def test_structure_rules_hold_on_the_real_manifest(manifest, walk):
    problems = manifest_problems(manifest, [r["path"] for r in walk])
    assert problems == []


def test_every_mounted_user_route_is_owned_or_reasoned(manifest, walk):
    unowned = manifest["unownedPrefixes"]
    for entry in unowned:
        assert entry["prefix"].startswith("/api/") and entry["reason"].strip(), entry
        assert any(_matches(entry["prefix"], r["path"]) for r in walk), f"{entry['prefix']} matches no mounted route"
    stray = sorted({
        r["path"] for r in walk
        if r["auth"] == "user" and owner_of(r["path"], manifest) is None
        and not any(_matches(e["prefix"], r["path"]) for e in unowned)
    })
    assert stray == [], f"mounted user routes with no owner and no unownedPrefixes reason: {stray}"
    owned_and_unowned = [e["prefix"] for e in unowned if any(
        _matches(p, e["prefix"]) for c in manifest["catalogues"] for p in c["routes"])]
    assert owned_and_unowned == [], "a prefix is both owned and listed as unowned"


def test_slices_cover_each_enforced_catalogue_exactly_once(manifest):
    enforced = {c["view"] for c in manifest["catalogues"] if c["group"] in ENFORCED_GROUPS}
    listed = [v for views in SLICES.values() for v in views]
    assert len(listed) == len(set(listed)), "a view appears in two slices"
    assert set(listed) - enforced == set(), f"SLICES names views outside the enforced groups: {sorted(set(listed) - enforced)}"
    assert enforced - set(listed) == set(), f"enforced views missing from SLICES: {sorted(enforced - set(listed))}"


def test_nested_prefixes_resolve_to_the_longest_owner():
    manifest = {"catalogues": [
        {"view": "outer", "routes": ["/api/a"]}, {"view": "inner", "routes": ["/api/a/b"]},
    ]}
    assert owner_of("/api/a/x", manifest)["view"] == "outer"
    assert owner_of("/api/a/b", manifest)["view"] == "inner"
    assert owner_of("/api/a/b/c", manifest)["view"] == "inner"
    assert owner_of("/api/ab", manifest) is None


def test_structure_rules_fire_on_a_broken_manifest():
    assert "manifest has no catalogues" in manifest_problems({"catalogues": [], "groups": []})
    broken = {
        "groups": [{"id": "g1"}, {"id": "empty"}],
        "catalogues": [
            {"view": "a", "group": "g1", "routes": ["/api/x"]},
            {"view": "b", "group": "g1", "routes": ["/api/x"]},
            {"view": "c", "group": "g1", "routes": []},
            {"view": "d", "group": "g1", "routes": [], "noBackendReason": "shares routes with ghost"},
            {"view": "e", "group": "g1", "routes": ["no-slash"]},
            {"view": "f", "group": "g1", "routes": ["/api/nothing"]},
        ],
    }
    joined = "\n".join(manifest_problems(broken, ["/api/x/1"]))
    for needle in (
        "group empty has no catalogues", "prefix /api/x claimed by a and b", "c: empty routes without noBackendReason",
        "d: noBackendReason names unknown view ghost", "e: prefix no-slash does not start", "f: prefix /api/nothing matches no mounted route",
    ):
        assert needle in joined, needle
