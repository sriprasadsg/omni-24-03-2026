"""Billing and identity slice (Phase 76-09): FinOps, payments, billing, knowledge base, users, tenants, SSO/LDAP.

D-08: payments, billing and knowledge-base routes need manage:settings and FinOps reads need
view:finops. D-09: user and role administration keep their guards. Public sign-in routes
(SSO, SAML, LDAP, tenant lookup-key, Stripe webhook) never carry a guard (D-02).
"""
import catalogue_mounts_billing_identity as billing_identity
import rbac_defaults
from catalogue_guards import manage_twin
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import (
    load_manifest, owner_of, parity_offenders, resolved_read, resolved_write, slice_modules,
)
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"

PUBLIC_PREFIXES = ("/api/sso/", "/api/auth/saml", "/api/auth/ldap")
PUBLIC_PATHS = ("/api/tenants/lookup-key", "/api/payments/webhook/stripe")


def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": "session"}


def test_billing_identity_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = slice_modules("billing_identity", records, manifest)
    for expected in ("finops_endpoints", "billing_endpoints", "payment_gateway_endpoints",
                     "payment_billing_endpoints", "knowledge_endpoints", "user_endpoints",
                     "tenant_endpoints", "sso_endpoints", "ldap_endpoints"):
        assert expected in modules
    offenders = parity_offenders(records, manifest, modules)
    assert offenders == [], "unguarded or mis-guarded billing/identity routes:\n" + "\n".join(offenders)


def test_billing_identity_guards_match_manifest():
    """Every mount entry and named guard carries exactly the manifest's resolved read/write."""
    manifest = load_manifest()
    by_view = {c["view"]: c for c in manifest["catalogues"]}
    named = [getattr(billing_identity, n) for n in dir(billing_identity) if n.endswith("_GUARD")]
    named += list(billing_identity.MOUNTS.values())
    assert named
    for guard in named:
        meta = guard.__catalogue_guard__
        entry = by_view[meta["catalogue"]]
        assert sorted(meta["read"]) == sorted(resolved_read(entry)), meta
        assert sorted(meta["write"]) == sorted(resolved_write(entry)), meta
    for key, guard in billing_identity.MOUNTS.items():
        assert MOUNT_GUARDS[key] is guard


def test_d08_billing_requires_manage_settings():
    """viewer holds view:dashboard but not manage:settings: billing, payments and knowledge refuse it."""
    reads = ["/api/billing/invoices", "/api/billing/payment-methods", "/api/payments/subscription-info",
             "/api/payments/invoices", "/api/payments/configured-gateways", "/api/knowledge/docs"]
    for role in ("nobody", "viewer"):
        denied = probe_real_app([_case(p, role) for p in reads])
        assert denied == [403] * len(reads), (role, dict(zip(reads, denied)))
    allowed = probe_real_app([_case(p, "tenant_admin") for p in reads])
    assert 403 not in allowed, dict(zip(reads, allowed))


def test_d08_finops_requires_view_finops():
    """analyst holds view:dashboard and view:reporting but not view:finops: FinOps reads refuse it."""
    reads = ["/api/finops/costs", "/api/finops/costs/history", "/api/finops/pricing"]
    for role in ("nobody", "analyst"):
        denied = probe_real_app([_case(p, role) for p in reads])
        assert denied == [403] * len(reads), (role, dict(zip(reads, denied)))
    # viewer holds view:finops and view:reporting; the catalogue guard must not refuse it
    allowed = probe_real_app([_case("/api/finops/costs", "viewer"), _case("/api/finops/costs", "tenant_admin")])
    assert 403 not in allowed, allowed


def test_d09_user_and_role_admin():
    """User and role administration keep their guards; the tag adds manage:users OR manage:rbac."""
    admin_reads = ["/api/users", "/api/roles"]
    for role in ("itam_admin", "tenant_admin"):
        allowed = probe_real_app([_case(p, role) for p in admin_reads])
        assert 403 not in allowed, (role, dict(zip(admin_reads, allowed)))
    for role in ("nobody", "viewer", "analyst"):
        denied = probe_real_app([_case(p, role) for p in admin_reads])
        assert denied == [403] * len(admin_reads), (role, dict(zip(admin_reads, denied)))
    # Self-service stays reachable by every signed-in role.
    self_service = ["/api/users/me", "/api/users/me/notification-preferences", "/api/api-keys",
                    "/api/api-keys/scopes"]
    roles = ["nobody", *sorted(rbac_defaults.builtin_role_keys())]
    cases = [_case(p, r) for r in roles for p in self_service]
    statuses = probe_real_app(cases)
    refused = [(c["role"], c["path"]) for c, st in zip(cases, statuses) if st == 403]
    assert refused == [], refused
    # Admin API-key listing needs the apiKeys read string on top of the ITAM admin check.
    assert probe_real_app([_case("/api/admin/api-keys", "tenant_admin")])[0] != 403
    assert probe_real_app([_case("/api/admin/api-keys", "viewer")])[0] == 403


def test_public_identity_routes_untouched():
    records = run_real_app_walk()["routes"]
    public = [r for r in records
              if r["path"].startswith(PUBLIC_PREFIXES) or r["path"] in PUBLIC_PATHS]
    assert any(r["path"] == "/api/payments/webhook/stripe" for r in public)
    assert any(r["path"] == "/api/tenants/lookup-key" for r in public)
    assert any(r["path"].startswith("/api/auth/ldap") for r in public)
    assert any(r["path"].startswith("/api/auth/saml") for r in public)
    assert any(r["path"].startswith("/api/sso/") for r in public)
    for record in public:
        if record["auth"] == "public":
            assert record["tags"] == [] and not record["exempt"], record


IDENTITY_READS = ["/api/tenants", "/api/admin/sso/saml/config", "/api/admin/ldap/config", "/api/bundles"]
# These routes also keep _require_itam_admin_session_only (manage:assets), which the catalogue tag only adds to.
ITAM_ADMIN_PATHS = {"/api/admin/sso/saml/config", "/api/admin/ldap/config"}
TENANT_EXEMPT_MODULES = ("tenant_endpoints", "tenant_enrollment_endpoints", "bundle_endpoints")


def _case_for(path, role):
    tenant = rbac_defaults.PLATFORM_TENANT_ID if role in rbac_defaults.PLATFORM_ROLE_KEYS else TENANT
    return {"method": "GET", "path": path, "role": role, "tenant_id": tenant, "auth": "session"}


def test_identity_admin_enforced():
    """Tenant, bundle and SSO/LDAP administration follow the manifest owner's resolved read strings."""
    manifest = load_manifest()
    roles = sorted(r for r in rbac_defaults.ROLE_DEFAULTS if r != "super_admin") + ["nobody"]
    for path in IDENTITY_READS:
        accepted = set()
        for perm in resolved_read(owner_of(path, manifest)):
            accepted.update({perm, manage_twin(perm)})
        cases = [_case_for(path, role) for role in roles]
        statuses = probe_real_app(cases)
        for role, status in zip(roles, statuses):
            held = set(rbac_defaults.ROLE_DEFAULTS.get(role, ()))
            platform_listing = path == "/api/tenants" and role in rbac_defaults.PLATFORM_ROLE_KEYS \
                and "view:tenants" in held
            if platform_listing:
                # Spec C1: platform staff list tenants through view:tenants; the exemption keeps that.
                assert status != 403, (path, role, status)
            elif not (held & accepted):
                assert status == 403, (path, role, status, sorted(accepted))
            elif path not in ITAM_ADMIN_PATHS or "manage:assets" in held:
                assert status != 403, (path, role, status)
    owner_statuses = probe_real_app([_case_for(p, "super_admin") for p in IDENTITY_READS])
    assert 403 not in owner_statuses, dict(zip(IDENTITY_READS, owner_statuses))


def test_identity_admin_writes_use_tenant_settings():
    """A tenant admin keeps changing their own tenant (manage:settings); a viewer is refused."""
    writes = [("POST", f"/api/tenants/{TENANT}/branding"), ("PUT", f"/api/tenants/{TENANT}/email/preferences")]
    assert 403 not in probe_real_app([_case(p, "tenant_admin", method=m) for m, p in writes])
    assert probe_real_app([_case(p, "viewer", method=m) for m, p in writes]) == [403, 403]
    # Deleting a tenant stays Super Admin only: the route's own check still refuses the tenant admin.
    assert probe_real_app([_case(f"/api/tenants/{TENANT}", "tenant_admin", method="DELETE")]) == [403]


def test_tenant_exempt_routes_reachable_by_every_role():
    """Among the tenant GETs only branding and the bundle feature list stay exempt (WR-05)."""
    records = run_real_app_walk()["routes"]
    exempt = [r for r in records if r["module"] in TENANT_EXEMPT_MODULES and r["exempt"]
              and r["methods"] == ["GET"] and r["path"] != "/api/tenants"]
    assert sorted(r["path"] for r in exempt) == EXEMPT_TENANT_GETS, exempt
    roles = ["nobody", *sorted(rbac_defaults.ROLE_DEFAULTS)]
    cases = [_case(r["path"].replace("{tenant_id}", TENANT), role) for r in exempt for role in roles
             if role not in rbac_defaults.PLATFORM_ROLE_KEYS]
    statuses = probe_real_app(cases)
    refused = [(c["role"], c["path"]) for c, st in zip(cases, statuses) if st == 403]
    assert refused == [], refused


# WR-05: email settings, seat license, hardware allowlist and install keys are tenant
# administration reads. Tenant roles need manage:settings; platform staff read any tenant
# through view:tenants (spec C1-C4) on the controls paths only.
EXEMPT_TENANT_GETS = ["/api/bundles/tenant/{tenant_id}/features", "/api/tenants/{tenant_id}/branding"]
EMAIL_READS = ["/api/tenants/tenant-a/email/config", "/api/tenants/tenant-a/email/preferences"]
CONTROL_READS = ["/api/tenants/tenant-a/license"]
TASK2_READS = ["/api/tenants/tenant-a/allowlist", "/api/tenants/tenant-a/enrollment-keys"]
ROLE_MATRIX = ["nobody", "admin", "super_admin", *sorted(rbac_defaults.ROLE_DEFAULTS)]


def _holds(role, permission):
    key = rbac_defaults.canonical_key(rbac_defaults.normalize_role(role))
    return permission in rbac_defaults.ROLE_DEFAULTS.get(key, ())


def _expect_through(role, path, platform_reads):
    if role == "super_admin" or _holds(role, "manage:settings"):
        return True
    return platform_reads and role in rbac_defaults.PLATFORM_ROLE_KEYS and _holds(role, "view:tenants")


def test_tenant_settings_reads_are_role_gated():
    """Real app: a tenant role without manage:settings gets 403 on the five tenant admin reads (email config, preferences, license, allowlist, install keys)."""
    assert len(ROLE_MATRIX) >= 14
    groups = [(EMAIL_READS, False), (CONTROL_READS + TASK2_READS, True)]
    for paths, platform_reads in groups:
        for path in paths:
            cases = [_case_for(path, role) for role in ROLE_MATRIX]
            statuses = probe_real_app(cases)
            for role, status in zip(ROLE_MATRIX, statuses):
                if _expect_through(role, path, platform_reads):
                    assert status not in (401, 403), f"{role} {path} -> {status}, expected to pass"
                else:
                    assert status == 403, f"{role} {path} -> {status}, expected 403"


# CR-01 (code review 2026-10-18): GET /api/tenants/me is exempt for every signed-in role, so it
# returns display fields only. The stored tenant document also holds the agent registration key,
# SMTP settings, API keys and seat data, which the WR-05 guards above keep from tenant roles.
TENANT_SECRETS = ("registrationKey", "emailConfig", "apiKeys", "license", "maxAgents",
                  "notificationPreferences", "agentCapabilities")


async def test_tenants_me_returns_display_fields_only():
    import database
    import route_aliases
    from unittest.mock import MagicMock, patch
    from auth_types import TokenData

    stored = {"id": TENANT, "name": "Tenant A", "subscriptionTier": "Pro", "branding": {"primaryColor": "#123456"},
              "registrationKey": "reg_secret", "emailConfig": {"smtpUser": "u", "smtpPassword": "p"},
              "apiKeys": [{"key": "k"}], "license": {"maxAgents": 5}, "maxAgents": 5,
              "notificationPreferences": {}, "agentCapabilities": ["remote"]}
    queries = []

    async def find_one(query, projection=None):
        queries.append(query)
        return dict(stored)  # a store that ignores the projection must not leak either

    fake = MagicMock()
    fake.db.tenants.find_one = find_one
    with patch.object(database, "mongodb", fake):
        for role in ("viewer", "itam_viewer", "user", "tenant_admin"):
            body = await route_aliases.get_my_tenant(TokenData(username="u@example.com", role=role, tenant_id=TENANT))
            assert body == {"id": TENANT, "name": "Tenant A", "subscriptionTier": "Pro",
                            "branding": {"primaryColor": "#123456"}}, role
            assert not set(TENANT_SECRETS) & set(body), role
    assert all(q == {"id": TENANT} for q in queries)
