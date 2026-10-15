"""Billing and identity slice (Phase 76-09): FinOps, payments, billing, knowledge base, users, tenants, SSO/LDAP.

D-08: payments, billing and knowledge-base routes need manage:settings and FinOps reads need
view:finops. D-09: user and role administration keep their guards. Public sign-in routes
(SSO, SAML, LDAP, tenant lookup-key, Stripe webhook) never carry a guard (D-02).
"""
import catalogue_mounts_billing_identity as billing_identity
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import (
    load_manifest, parity_offenders, resolved_read, resolved_write, slice_modules,
)
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"

# Modules of the slice whose guards land in a later task of this plan; shrinks to empty.
_PENDING = {
    "user_endpoints", "role_endpoints", "api_key_endpoints", "tenant_endpoints",
    "tenant_enrollment_endpoints", "bundle_endpoints", "sso_endpoints", "ldap_endpoints",
}

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
    offenders = parity_offenders(records, manifest, [m for m in modules if m not in _PENDING])
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
