"""Golden per-role sets and table invariants for backend/rbac_defaults.py (ACC-02).

The expected sets are literals here on purpose: a change to a role's permissions
must show up as a reviewable gained/lost failure. Test files are outside the
drift scan, which reads only top-level backend/*.py.
"""
import ast
import os

import pytest

import rbac_defaults as d

GOLDEN = {
    "tenant_admin": frozenset({
        "control:remote_access", "export:reports", "investigate:security",
        "manage:active_response", "manage:advanced_hunting", "manage:agent_groups",
        "manage:agents", "manage:ai_risks", "manage:android_enterprise", "manage:api_keys",
        "manage:app_catalog", "manage:approvals", "manage:asset_intelligence", "manage:assets",
        "manage:automation", "manage:autopilot", "manage:branch_sites", "manage:compliance",
        "manage:compliance_evidence", "manage:conditional_access", "manage:config_drift",
        "manage:connectors_hub", "manage:dashboards", "manage:detection_rules",
        "manage:device_config_profiles", "manage:devsecops", "manage:experiments", "manage:fim",
        "manage:finance", "manage:firmware_drivers", "manage:itam", "manage:licenses", "manage:mam", "manage:mdm",
        "manage:mssp", "manage:patches", "manage:playbooks",
        "manage:procurement", "manage:rbac", "manage:retention_policies", "manage:sbom",
        "manage:sca", "manage:secrets", "manage:security_cases", "manage:security_playbooks",
        "manage:settings", "manage:users", "remediate:agents", "request:assets",
        "view:active_response", "view:advanced_bi", "view:advanced_hunting",
        "view:agent_capabilities", "view:agent_groups", "view:agent_logs", "view:agents",
        "view:ai_governance", "view:analytics", "view:android_enterprise", "view:app_catalog",
        "view:approvals", "view:asset_intelligence", "view:assets", "view:attack_path",
        "view:attack_timeline", "view:audit_log", "view:automation", "view:automl",
        "view:autopilot", "view:branch_sites", "view:chaos", "view:cloud_security",
        "view:compliance", "view:conditional_access", "view:config_drift", "view:connectors_hub",
        "view:cxo_dashboard", "view:dashboard", "view:detection_rules", "view:developer_hub",
        "view:device_config_profiles", "view:devsecops", "view:dora_metrics", "view:dspm",
        "view:fim", "view:finops", "view:firmware_drivers", "view:geographic_map",
        "view:governance", "view:insights", "view:integrations", "view:itam", "view:licenses",
        "view:llmops", "view:logs", "view:mam", "view:mdm", "view:mdr", "view:mlops", "view:mssp",
        "view:network", "view:patching", "view:persistence", "view:profile", "view:remote_access",
        "view:reporting", "view:retention_policies", "view:sbom", "view:sca", "view:secrets",
        "view:security", "view:security_audit", "view:security_copilot", "view:service_catalog",
        "view:software_deployment", "view:software_updates", "view:sustainability", "view:swarm",
        "view:threat_hunting", "view:threat_intel", "view:tracing", "view:unified_ops",
        "view:vulnerabilities", "view:web_monitoring", "view:xai", "view:xdr", "view:zero_trust",
    }),
    "user": frozenset({
        "view:agent_capabilities", "view:agents", "view:ai_governance", "view:assets",
        "view:audit_log", "view:automation", "view:cloud_security", "view:compliance",
        "view:dashboard", "view:developer_hub", "view:devsecops", "view:finops", "view:insights",
        "view:logs", "view:mdr", "view:patching", "view:profile", "view:reporting",
        "view:security", "view:threat_hunting", "view:tracing", "view:xdr",
    }),
    "analyst": frozenset({
        "investigate:security", "view:agents", "view:assets", "view:attack_path", "view:audit_log",
        "view:compliance", "view:dashboard", "view:devsecops", "view:dspm", "view:logs",
        "view:mdr", "view:profile", "view:reporting", "view:security", "view:threat_hunting",
        "view:threat_intel", "view:tracing", "view:vulnerabilities", "view:xdr",
    }),
    "security_analyst": frozenset({
        "investigate:security", "manage:security_cases", "view:assets", "view:attack_path",
        "view:audit_log", "view:compliance", "view:dashboard", "view:dspm", "view:logs",
        "view:mdr", "view:profile", "view:security", "view:threat_hunting", "view:threat_intel",
        "view:tracing", "view:vulnerabilities", "view:xdr",
    }),
    "incident_responder": frozenset({
        "investigate:security", "manage:security_cases", "view:agents", "view:assets",
        "view:audit_log", "view:dashboard", "view:logs", "view:mdr", "view:profile",
        "view:security", "view:threat_hunting", "view:xdr",
    }),
    "viewer": frozenset({
        "view:ai_governance", "view:assets", "view:cloud_security", "view:compliance",
        "view:dashboard", "view:finops", "view:profile", "view:reporting",
    }),
    "itam_admin": frozenset({
        "manage:assets", "manage:finance", "manage:itam", "manage:licenses", "manage:procurement",
        "manage:users", "view:itam", "view:profile",
    }),
    "itam_user": frozenset({
        "request:assets", "view:assets", "view:itam", "view:licenses", "view:profile",
    }),
    "itam_viewer": frozenset({
        "view:assets", "view:itam", "view:licenses", "view:profile",
    }),
    # Spec C1 platform roles.
    "platform_support": frozenset({
        "view:active_response", "view:advanced_bi", "view:advanced_hunting",
        "view:agent_capabilities", "view:agent_groups", "view:agents", "view:ai_governance",
        "view:analytics", "view:android_enterprise", "view:app_catalog", "view:asset_intelligence",
        "view:assets", "view:attack_path", "view:attack_timeline", "view:audit_log",
        "view:automation", "view:automl", "view:autopilot", "view:branch_sites", "view:chaos",
        "view:cloud_security", "view:compliance", "view:conditional_access", "view:config_drift",
        "view:connectors_hub", "view:cxo_dashboard", "view:dashboard", "view:detection_rules",
        "view:developer_hub", "view:device_config_profiles", "view:devsecops", "view:dora_metrics",
        "view:dspm", "view:fim", "view:finops", "view:firmware_drivers", "view:geographic_map",
        "view:governance", "view:insights", "view:integrations", "view:itam", "view:llmops",
        "view:logs", "view:mam", "view:mdm", "view:mdr", "view:mlops", "view:mssp", "view:network",
        "view:patching", "view:persistence", "view:platform_alerts", "view:profile",
        "view:reporting", "view:retention_policies", "view:sbom", "view:sca", "view:secrets",
        "view:security", "view:security_audit", "view:security_copilot", "view:service_catalog",
        "view:software_deployment", "view:software_updates", "view:sustainability", "view:swarm",
        "view:tenants", "view:threat_hunting", "view:threat_intel", "view:tracing",
        "view:unified_ops", "view:vulnerabilities", "view:web_monitoring", "view:xai", "view:xdr",
        "view:zero_trust",
    }),
    "platform_billing": frozenset({
        "manage:pending_agents", "manage:tenant_license", "view:audit_log", "view:platform_alerts",
        "view:platform_cost", "view:profile", "view:tenants",
    }),
}

GOLDEN_SIZES = {"tenant_admin": 127, "user": 22, "analyst": 19, "security_analyst": 17,
                "incident_responder": 12, "viewer": 8, "itam_admin": 8, "itam_user": 5, "itam_viewer": 4,
                "platform_support": 76, "platform_billing": 7}

D02_VIEW = [
    "view:zero_trust", "view:attack_timeline", "view:geographic_map", "view:analytics", "view:web_monitoring",
    "view:persistence", "view:security_copilot", "view:autopilot", "view:conditional_access", "view:mdm",
    "view:branch_sites", "view:app_catalog", "view:asset_intelligence", "view:mam", "view:android_enterprise",
    "view:device_config_profiles", "view:firmware_drivers", "view:advanced_hunting", "view:detection_rules",
    "view:connectors_hub", "view:mssp", "view:retention_policies", "view:sca", "view:agent_groups",
    "view:config_drift", "view:fim",
]
D02_MANAGE = [
    "manage:autopilot", "manage:conditional_access", "manage:mdm", "manage:branch_sites", "manage:app_catalog",
    "manage:asset_intelligence", "manage:mam", "manage:android_enterprise", "manage:device_config_profiles",
    "manage:firmware_drivers", "manage:advanced_hunting", "manage:detection_rules", "manage:connectors_hub",
    "manage:mssp", "manage:retention_policies", "manage:sca", "manage:agent_groups", "manage:config_drift",
    "manage:fim",
]
D21 = ["manage:finance", "manage:licenses", "manage:procurement", "manage:users", "request:assets", "view:licenses"]
ITAM_ROLES = ["itam_admin", "itam_user", "itam_viewer"]


def _diff(actual, expected):
    return f"gained={sorted(set(actual) - set(expected))} lost={sorted(set(expected) - set(actual))}"


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_role_set_matches_golden(key):
    actual = d.ROLE_DEFAULTS[key]
    assert frozenset(actual) == GOLDEN[key], f"{key}: {_diff(actual, GOLDEN[key])}"
    assert len(actual) == GOLDEN_SIZES[key], f"{key}: size {len(actual)} != {GOLDEN_SIZES[key]}"


def test_table_has_exactly_the_eleven_golden_keys():
    assert set(d.ROLE_DEFAULTS) == set(GOLDEN)


@pytest.mark.parametrize("key", sorted(GOLDEN))
def test_tuples_are_sorted_and_duplicate_free(key):
    perms = list(d.ROLE_DEFAULTS[key])
    assert perms == sorted(perms)
    assert len(perms) == len(set(perms))


def test_admin_alias_equals_tenant_admin():
    """D-01"""
    assert d.defaults_for("admin") == d.defaults_for("tenant_admin")
    assert d.canonical_key("admin") == "tenant_admin"
    assert d.canonical_key("viewer") == "viewer"


def test_d02_catalogues_belong_to_tenant_admin_only():
    assert len(D02_VIEW) == 26 and len(D02_MANAGE) == 19
    ta = set(d.defaults_for("tenant_admin"))
    assert set(D02_VIEW) <= ta and set(D02_MANAGE) <= ta
    for key in set(d.ROLE_DEFAULTS) - {"tenant_admin"} - d.PLATFORM_ROLE_KEYS:
        assert not (set(D02_VIEW + D02_MANAGE) & set(d.ROLE_DEFAULTS[key])), key
    assert not (set(D02_MANAGE) & set(d.defaults_for("platform_support"))), "support is read-only"


def test_super_admin_only_catalogues_and_manage_tenants_are_never_granted():
    """D-03 / D-06"""
    assert len(d.SUPER_ADMIN_ONLY_PERMISSIONS) == 8  # + manage:pricing (QA ISSUE-005)
    assert "manage:tenants" in d.SUPER_ADMIN_ONLY_PERMISSIONS
    for key, perms in d.ROLE_DEFAULTS.items():
        assert not (d.SUPER_ADMIN_ONLY_PERMISSIONS & set(perms)), key
    assert "manage:tenants" not in d.defaults_for("admin")
    assert d.defaults_for("super_admin") == ("*",)


@pytest.mark.parametrize("key", ITAM_ROLES)
def test_itam_roles_hold_profile_and_not_dashboard(key):
    """D-08 / D-09"""
    perms = set(d.defaults_for(key))
    assert "view:profile" in perms
    assert "view:dashboard" not in perms


def test_itam_grants_follow_d11_and_d10():
    assert set(d.defaults_for("itam_user")) >= {"view:assets", "view:itam", "view:licenses", "request:assets"}
    assert set(d.defaults_for("itam_viewer")) >= {"view:assets", "view:itam", "view:licenses"}
    admin = set(d.defaults_for("itam_admin"))
    assert admin >= {"manage:assets", "manage:licenses", "manage:users", "view:itam", "manage:procurement",
                     "manage:finance", "manage:itam"}


def test_d21_strings_are_on_tenant_admin_and_the_ceiling_is_consistent():
    ta = d.defaults_for("tenant_admin")
    assert set(D21) <= set(ta)
    for target in ITAM_ROLES:
        assert d.ceiling_allows(ta, d.defaults_for(target)), target
    for target in ("itam_user", "itam_viewer"):
        assert d.ceiling_allows(d.defaults_for("itam_admin"), d.defaults_for(target)), target
    assert not d.ceiling_allows(d.defaults_for("itam_admin"), ta)
    assert not d.ceiling_allows(d.defaults_for("itam_user"), d.defaults_for("itam_admin"))
    assert d.ceiling_allows(("*",), ta)


def test_remote_access_view_and_control_are_independent():
    """Phase 74 D-06: neither string implies the other anywhere."""
    ta = set(d.defaults_for("tenant_admin"))
    assert "view:remote_access" in ta and "control:remote_access" in ta
    assert "control:remote_access" not in d.implied_closure({"view:remote_access"})
    assert "view:remote_access" not in d.implied_closure({"control:remote_access"})
    assert "view:x" not in d.implied_closure({"view:y"})
    assert d.implied_closure({"manage:x"}) == frozenset({"manage:x", "view:x", "request:x"})


def test_seed_role_documents_mirror_the_table():
    docs = d.seed_role_documents()
    assert [doc["name"] for doc in docs] == [r.name for r in d.BUILTIN_ROLES]
    assert len(docs) == 13
    assert len({doc["id"] for doc in docs}) == 13
    by_name = {doc["name"]: doc for doc in docs}
    assert by_name["Super Admin"]["tenantId"] == "platform"
    assert by_name["Super Admin"]["permissions"] == ["*"]
    platform_names = {"Super Admin", "Platform Support", "Platform Billing"}
    assert all(doc["tenantId"] == ("platform" if doc["name"] in platform_names else "all") for doc in docs)
    non_editable = {"Super Admin", "Tenant Admin", "admin", "itam_admin", "itam_user", "itam_viewer",
                    "Platform Support", "Platform Billing"}
    for doc in docs:
        assert doc["isEditable"] is (doc["name"] not in non_editable), doc["name"]
    for role in d.BUILTIN_ROLES:
        assert by_name[role.name]["permissions"] == list(d.defaults_for(role.key))
    assert "display_name" not in by_name["Super Admin"] and "display_name" not in by_name["Tenant Admin"]
    assert by_name["analyst"]["display_name"] == "Analyst"


def test_builtin_role_keys():
    assert d.builtin_role_keys() == frozenset({
        "super_admin", "tenant_admin", "admin", "user", "analyst", "security_analyst",
        "incident_responder", "viewer", "itam_admin", "itam_user", "itam_viewer",
        "platform_support", "platform_billing"})


def test_unknown_key_has_no_defaults():
    assert d.defaults_for("legacy_custom_role") == ()
    assert d.defaults_for("") == ()


def test_module_imports_nothing_outside_the_standard_library():
    path = os.path.join(os.path.dirname(__file__), "..", "rbac_defaults.py")
    tree = ast.parse(open(path).read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"database", "fastapi", "rbac_service", "rbac_utils"}


# --- Drift guard (SC3): no second role-to-permission table in backend/*.py ----------------

import glob
import re

from rbac_service import RBACService

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_REPO_DIR = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))

_PERM_RE = re.compile(r"^(view|manage|export|remediate|investigate|request|control|admin|read|write|delete):[A-Za-z_*:.\-]+$")

# (file name, enclosing assignment target) -> reason. Tenant feature-tier lists and a demo
# per-user array are a different concept from a role's permissions.
_TIER_LIST_ALLOWLIST = {
    ("authentication_endpoints.py", "free_features"): "tenant free-tier feature list",
    ("tenant_endpoints.py", "enabledFeatures"): "TenantCreate default tenant feature list",
    ("seed_demo_data.py", "tenants"): "demo tenant documents with their enabled features",
    ("seed_demo_data.py", "admin_permissions"): "demo per-user permission array, ignored by the resolver",
    ("unlock_enterprise_features.py", "ENTERPRISE_FEATURES"): "tenant enterprise tier feature list",
}


def _is_perm_string(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(_PERM_RE.match(node.value))


def _str_consts(elts):
    return [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def _enclosing_target(node, parents):
    """Name of the nearest Assign/AnnAssign target above node, or None."""
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, ast.Assign) and cur.targets:
            target = cur.targets[0]
        elif isinstance(cur, ast.AnnAssign):
            target = cur.target
        else:
            cur = parents.get(cur)
            continue
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            return target.attr
        return None
    return None


def _parents_of(tree):
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def scan_permission_lists(source: str, filename: str):
    """Offenders: list/tuple/set literals made (mostly) of permission strings, outside the allowlist."""
    tree = ast.parse(source)
    parents = _parents_of(tree)
    base = os.path.basename(filename)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            continue
        strings = _str_consts(node.elts)
        if len(strings) < 5:
            continue
        matching = sum(1 for e in node.elts if _is_perm_string(e))
        if matching / len(strings) < 0.8:
            continue
        if (base, _enclosing_target(node, parents)) in _TIER_LIST_ALLOWLIST:
            continue
        offenders.append(f"{base}:{node.lineno}")
    return offenders


def _permission_collection(node) -> bool:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)) or not node.elts:
        return False
    return all(
        isinstance(e, ast.Constant) and isinstance(e.value, str) and (e.value == "*" or _PERM_RE.match(e.value))
        for e in node.elts
    )


def _is_builtin_role_name(node) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and RBACService._normalize_role(node.value) in d.builtin_role_keys())


def scan_role_tables(source: str, filename: str):
    """Offenders: role-keyed permission dicts and role document literals, of any size."""
    tree = ast.parse(source)
    base = os.path.basename(filename)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        hit = False
        fields = {}
        for key, value in zip(node.keys, node.values):
            if _is_builtin_role_name(key) and _permission_collection(value):
                hit = True
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                fields[key.value] = value
        if (not hit and "name" in fields and "permissions" in fields
                and _is_builtin_role_name(fields["name"]) and _permission_collection(fields["permissions"])):
            hit = True
        if hit:
            offenders.append(f"{base}:{node.lineno}")
    return offenders


def test_no_second_permission_table():
    offenders = []
    for path in sorted(glob.glob(os.path.join(_BACKEND_DIR, "*.py"))):
        name = os.path.basename(path)
        if name == "rbac_defaults.py":
            continue
        with open(path, encoding="utf-8-sig") as fh:
            source = fh.read()
        offenders += scan_permission_lists(source, name)  # a parse error raises and fails the test
        offenders += scan_role_tables(source, name)
    assert not offenders, "second role-to-permission table(s) outside rbac_defaults.py: " + ", ".join(offenders)


def test_scanner_flags_role_keyed_dict():
    src = 'TABLE = {"viewer": ["view:assets", "view:agents", "view:logs"]}\n'
    assert scan_role_tables(src, "x.py") == ["x.py:1"]


def test_scanner_flags_permission_list():
    src = ('perms = ["view:a", "view:b", "view:c", "manage:d", "manage:e", "export:f"]\n')
    assert scan_permission_lists(src, "x.py") == ["x.py:1"]


def test_scanner_flags_role_document():
    src = 'doc = {"name": "viewer", "permissions": ["view:assets", "view:agents"]}\n'
    assert scan_role_tables(src, "x.py") == ["x.py:1"]


def test_scanner_allows_named_tier_list():
    src = 'free_features = ["view:a", "view:b", "view:c", "manage:d", "manage:e", "export:f"]\n'
    assert scan_permission_lists(src, "authentication_endpoints.py") == []
    assert scan_permission_lists(src, "other.py") == ["other.py:1"]


_ARCHIVED_SCRIPTS = (
    "fix_rbac_integrations.py", "update_sbom_roles.py", "update_all_sbom_roles.py",
    "enable_compliance_for_admin.py", "reset_db_fresh.py",
)
_KEPT_SCRIPTS = ("fix_rbac.py", "fix_all_rbac.py", "unlock_enterprise_features.py", "diagnose_rbac.py")


def test_role_writing_scripts_are_archived():
    archive = os.path.join(_REPO_DIR, "archive", "backend-rbac-oneoffs")
    for name in _ARCHIVED_SCRIPTS:
        assert not os.path.exists(os.path.join(_BACKEND_DIR, name)), f"{name} must not live in backend/"
        assert os.path.isfile(os.path.join(archive, name)), f"{name} missing from the archive"
    assert os.path.isfile(os.path.join(archive, "ARCHIVED.md"))
    for name in _KEPT_SCRIPTS:
        assert os.path.isfile(os.path.join(_BACKEND_DIR, name)), f"{name} must stay in backend/"
