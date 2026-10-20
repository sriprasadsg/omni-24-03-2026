"""Settings and platform-operations slice (Phase 76-10): settings, system health, cache, HA/DR, secrets,
retention, integrations, MSSP, notifications, data warehouse, ticketing and webhook management.

Inbound webhook receivers and the public duplicate /api/system/health never carry a guard (D-02).
Settings routes that live in compliance modules (/api/settings/evidence-staleness and
/api/settings/remediation-sla) belong to the governance catalogues, which are not enforced yet (D-01).
"""
import catalogue_mounts_settings_ops as settings_ops
import rbac_defaults
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import (
    load_manifest, owner_of, parity_offenders, resolved_read, resolved_write, slice_modules,
)
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"
PUBLIC_PATHS = ("/api/webhooks/jira/inbound", "/api/webhooks/zoho/inbound")


# The webhook management routes resolve the caller with get_current_user_or_api_key.
API_KEY_PATHS = ("/api/webhooks",)


def _case(path, role, *, method="GET"):
    auth = "api_key" if path in API_KEY_PATHS else "session"
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": auth}


def test_settings_ops_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = slice_modules("settings_ops", records, manifest)
    for expected in ("settings_endpoints", "system_health_endpoints", "cache_endpoints", "hadr_endpoints",
                     "secrets_endpoints", "integration_endpoints", "notification_endpoints",
                     "webhook_endpoints", "final_endpoints", "reporting_endpoints"):
        assert expected in modules
    offenders = parity_offenders(records, manifest, modules)
    assert offenders == [], "unguarded or mis-guarded settings/ops routes:\n" + "\n".join(offenders)


def test_settings_ops_guards_match_manifest():
    """Every named guard and mount entry carries exactly the manifest's resolved read/write."""
    manifest = load_manifest()
    by_view = {c["view"]: c for c in manifest["catalogues"]}
    named = [getattr(settings_ops, n) for n in dir(settings_ops) if n.endswith("_GUARD")]
    assert named
    for guard in named:
        meta = guard.__catalogue_guard__
        entry = by_view[meta["catalogue"]]
        assert sorted(meta["read"]) == sorted(resolved_read(entry)), meta
        assert sorted(meta["write"]) == sorted(resolved_write(entry)), meta
    for key, guard in settings_ops.MOUNTS.items():
        assert MOUNT_GUARDS[key] is guard


def test_settings_ops_public_routes_untouched():
    records = run_real_app_walk()["routes"]
    receivers = [r for r in records if r["path"] in PUBLIC_PATHS]
    assert {r["path"] for r in receivers} == set(PUBLIC_PATHS)
    public_health = [r for r in records if r["path"] == "/api/system/health" and r["auth"] == "public"]
    assert public_health, "the public /api/system/health duplicate disappeared"
    for record in receivers + public_health:
        assert record["auth"] == "public", record
        assert record["tags"] == [] and not record["exempt"], record


def test_settings_ops_governance_settings_stay_unguarded():
    """Compliance-module settings routes belong to unenforced governance catalogues (D-01)."""
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    for path in ("/api/settings/evidence-staleness", "/api/settings/remediation-sla"):
        matching = [r for r in records if r["path"] == path]
        assert matching, path
        assert owner_of(path, manifest)["group"] == "governance"
        for record in matching:
            assert record["tags"] == [] and not record["exempt"], record


def test_settings_ops_real_app_enforced():
    """viewer lacks manage:settings: settings, secrets and system reads refuse it; tenant_admin passes."""
    reads = ["/api/settings/llm", "/api/settings/database", "/api/secrets/list", "/api/secrets/stats",
             "/api/system/health", "/api/retention/policies",
             "/api/webhooks", "/api/integrations/configs", "/api/cloud-integrations"]
    for role in ("nobody", "viewer"):
        denied = probe_real_app([_case(p, role) for p in reads])
        assert denied == [403] * len(reads), (role, dict(zip(reads, denied)))
    allowed = probe_real_app([_case(p, "tenant_admin") for p in reads])
    assert 403 not in allowed, dict(zip(reads, allowed))
    # HA/DR backs up and restores the platform database: a platform screen, refused to every tenant role.
    assert probe_real_app([_case("/api/hadr/status", role) for role in ("viewer", "tenant_admin")]) == [403, 403]
    assert probe_real_app([_case("/api/hadr/status", "super_admin")])[0] != 403
    # A write needs the manifest write string through the same guard.
    writes = [("POST", "/api/cache/clear"), ("POST", "/api/settings/llm"), ("POST", "/api/webhooks")]
    assert probe_real_app([_case(p, "viewer", method=m) for m, p in writes]) == [403] * len(writes)
    # Cache administration keeps its own Super Admin check; the guard only adds to it.
    assert probe_real_app([_case("/api/cache/stats", "viewer")]) == [403]
    assert probe_real_app([_case("/api/cache/clear", "super_admin", method="POST")])[0] != 403


def test_settings_ops_role_scoped_catalogues():
    """Catalogues with their own read string: MSSP, retention tiers, data warehouse, notifications."""
    manifest = load_manifest()
    paths = ["/api/mssp/overview", "/api/retention-tiers/stats", "/api/warehouse/stats",
             "/api/notifications", "/api/notifications/history", "/api/fleet/observability"]
    roles = sorted(r for r in rbac_defaults.ROLE_DEFAULTS if r != "super_admin") + ["nobody"]
    for path in paths:
        accepted = set()
        for perm in resolved_read(owner_of(path, manifest)):
            accepted.update({perm, "manage:" + perm.split(":", 1)[1] if perm.startswith("view:") else perm})
        cases = [{"method": "GET", "path": path, "role": role,
                  "tenant_id": rbac_defaults.PLATFORM_TENANT_ID if role in rbac_defaults.PLATFORM_ROLE_KEYS
                  else TENANT, "auth": "session"} for role in roles]
        statuses = probe_real_app(cases)
        for role, status in zip(roles, statuses):
            held = set(rbac_defaults.ROLE_DEFAULTS.get(role, ()))
            if not (held & accepted) and "*" not in held:
                assert status == 403, (path, role, status, sorted(accepted))
    assert 403 not in probe_real_app([_case(p, "super_admin") for p in paths])


def test_webhook_management_keeps_tenant_integration_keys():
    """The legacy tenant key (role api-integration) still manages webhooks; the other routes stay session-only."""
    key = {"role": "api-integration", "tenant_id": TENANT, "auth": "api_key"}
    cases = [{"method": "GET", "path": "/api/webhooks", **key},
             {"method": "POST", "path": "/api/webhooks", **key}]
    assert 403 not in probe_real_app(cases)
    # A user-scoped key or session is checked against the catalogue: viewer is refused.
    viewer = {"role": "viewer", "tenant_id": TENANT, "auth": "api_key"}
    assert probe_real_app([{"method": "GET", "path": "/api/webhooks", **viewer}]) == [403]
