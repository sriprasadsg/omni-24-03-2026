"""Billing and identity slice (Phase 76-09): FinOps, payments, billing, knowledge base, tenants, users, roles, API keys, SSO/LDAP admin.

``MOUNTS`` guards the routers whose every route is a user route of one catalogue (FinOps,
knowledge base, bundles, roles). The mixed routers (billing and payment routers that share
catalogues and carry the public Stripe webhook, users with /me routes, API keys with owner
self-service, tenants with a public lookup and self-service reads, SSO/LDAP with public
login) import the named guards below and add them per route; public, agent-only and
self-service routes never carry a guard (D-02).

D-08: payments, billing and knowledge-base routes need ``manage:settings``; FinOps reads
need ``view:finops``. D-09: user and role administration keep the guards they already have
(``_require_itam_admin``, the Phase 75 assignment ceiling, ``_require_role_list_access``)
and add the manifest tag, whose read rule is ``manage:users`` OR ``manage:rbac``.

Read permissions and write strings mirror ``shared/catalogue-access.json``;
``test_catalogue_slice_billing_identity`` fails when the two drift.
"""
from catalogue_guards import catalogue_exempt, catalogue_guard

__all__ = [
    "FINOPS_GUARD", "INVOICES_GUARD", "PAYMENT_SETTINGS_GUARD", "SUBSCRIPTION_GUARD",
    "KNOWLEDGE_GUARD", "USER_MANAGEMENT_GUARD", "ROLE_MANAGEMENT_GUARD", "API_KEYS_GUARD",
    "SELF_SERVICE_PROFILE", "SELF_SERVICE_API_KEYS", "TENANT_MANAGEMENT_GUARD",
    "BUNDLE_MANAGEMENT_GUARD", "TENANT_OWN_SCOPE", "TENANT_PLATFORM_STAFF", "TENANT_OWN_FEATURES",
    "MOUNTS",
]

_SETTINGS = ("manage:settings",)

# --- Task 1: financial catalogues (D-08) ---------------------------------------------------
FINOPS_GUARD = catalogue_guard("finops", read=("view:finops",), write=("manage:settings", "view:reporting"))
INVOICES_GUARD = catalogue_guard("invoices", read=_SETTINGS, write=_SETTINGS)
PAYMENT_SETTINGS_GUARD = catalogue_guard("paymentSettings", read=_SETTINGS, write=_SETTINGS)
SUBSCRIPTION_GUARD = catalogue_guard("subscriptionManagement", read=_SETTINGS, write=_SETTINGS)
KNOWLEDGE_GUARD = catalogue_guard("knowledgeBase", read=_SETTINGS, write=_SETTINGS)

# --- Task 2: users, roles and API keys (D-09) -----------------------------------------------
# Read is manage:users OR manage:rbac for both catalogues so itam_admin (manage:users) and
# tenant_admin (both) can still list users and roles. The routes keep _require_itam_admin, the
# Phase 75 assignment ceiling and _require_role_list_access; these guards only add the tag.
_USER_READ = ("manage:users", "manage:rbac")
USER_MANAGEMENT_GUARD = catalogue_guard("userManagement", read=_USER_READ, write=("manage:assets",))
ROLE_MANAGEMENT_GUARD = catalogue_guard("roleManagement", read=_USER_READ, write=("manage:rbac",))
API_KEYS_GUARD = catalogue_guard(
    "apiKeys", read=("manage:api_keys",), write=("manage:api_keys", "manage:assets")
)

# Self-service: each of these acts on the signed-in caller's own record only.
SELF_SERVICE_PROFILE = catalogue_exempt("self-service: caller's own profile and notification preferences")
SELF_SERVICE_API_KEYS = catalogue_exempt("self-service: caller's own API keys")

# --- Task 3: tenants, bundles, SSO and LDAP administration --------------------------------
# tenantManagement writes accept manage:settings so a tenant admin keeps changing their own
# tenant (branding, email, API keys); the routes' own checks still pin the tenant.
TENANT_MANAGEMENT_GUARD = catalogue_guard(
    "tenantManagement", read=("manage:tenants",), write=("manage:tenants", "manage:settings")
)
BUNDLE_MANAGEMENT_GUARD = catalogue_guard(
    "bundleManagement", read=("manage:tenants",), write=("manage:tenants",)
)

TENANT_OWN_SCOPE = catalogue_exempt(
    "self-service: caller's own tenant settings, pinned by _assert_tenant_access / _assert_tenant_read"
)
# Platform staff (spec C1-C4) pass has_platform_permission, never manage:tenants, which only the
# Super Admin holds; guarding these with the manifest string would lock Platform Support/Billing out.
TENANT_PLATFORM_STAFF = catalogue_exempt(
    "platform staff: gated by has_platform_permission (view:tenants / manage:tenant_license, spec C1-C4)"
)
TENANT_OWN_FEATURES = catalogue_exempt(
    "app-shell: the caller's own tenant feature list, loaded by FeaturesContext for every signed-in user"
)

MOUNTS = {
    ("finops_endpoints", "router"): FINOPS_GUARD,
    ("knowledge_endpoints", "router"): KNOWLEDGE_GUARD,
    ("role_endpoints", "router"): ROLE_MANAGEMENT_GUARD,
    ("api_key_endpoints", "admin_router"): API_KEYS_GUARD,
}
