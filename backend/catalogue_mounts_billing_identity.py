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
    "KNOWLEDGE_GUARD", "MOUNTS",
]

_SETTINGS = ("manage:settings",)

# --- Task 1: financial catalogues (D-08) ---------------------------------------------------
FINOPS_GUARD = catalogue_guard("finops", read=("view:finops",), write=("manage:settings", "view:reporting"))
INVOICES_GUARD = catalogue_guard("invoices", read=_SETTINGS, write=_SETTINGS)
PAYMENT_SETTINGS_GUARD = catalogue_guard("paymentSettings", read=_SETTINGS, write=_SETTINGS)
SUBSCRIPTION_GUARD = catalogue_guard("subscriptionManagement", read=_SETTINGS, write=_SETTINGS)
KNOWLEDGE_GUARD = catalogue_guard("knowledgeBase", read=_SETTINGS, write=_SETTINGS)

MOUNTS = {
    ("finops_endpoints", "router"): FINOPS_GUARD,
    ("knowledge_endpoints", "router"): KNOWLEDGE_GUARD,
}
