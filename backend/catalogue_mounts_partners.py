"""Partner channel catalogue mounts (Phase 87): the two partner routers.

``/api/platform/partners`` is the Super Admin's Partners screen (``partners``): reads and writes both
need ``manage:partners``, a Super Admin only permission. ``/api/partner`` is the partner's own portal
(``partnerPortal``): reads need ``view:partner_portal`` (partner admin and partner viewer), writes need
``manage:partner_customers`` (partner admin only). Each route then pins the caller to its own partner
through ``partner_endpoints.current_partner``; the guard checks the permission, never the partner.

Read and write strings mirror ``shared/catalogue-access.json``; ``test_catalogue_slice_partners``
(plan 87-05) fails when the two drift.
"""
from catalogue_guards import catalogue_guard

__all__ = ["PARTNERS_GUARD", "PARTNER_PORTAL_GUARD", "MOUNTS"]

PARTNERS_GUARD = catalogue_guard(
    "partners",
    read=("manage:partners",),
    write=("manage:partners",),
)

PARTNER_PORTAL_GUARD = catalogue_guard(
    "partnerPortal",
    read=("view:partner_portal",),
    write=("manage:partner_customers",),
)

MOUNTS = {
    ("partner_platform_endpoints", "router"): PARTNERS_GUARD,
    ("partner_endpoints", "router"): PARTNER_PORTAL_GUARD,
}
