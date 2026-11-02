"""Partner catalogue slice (Phase 87, plan 87-05): the two partner routers are mounted through
catalogue_mounts_partners with the manifest's partners and partnerPortal read and write strings.

The partner screens are not part of the shared slice partition, so this file checks the same parity
directly for every route of the two modules, including routes later plans add (it iterates the walk).

Value: protects=the Super Admin Partners routes and the partner portal routes carry exactly the manifest's
permissions and authenticate people; fails_when=a guard drifts from the manifest, a route is mounted
unguarded or under the wrong catalogue, or a router disappears from the app;
no_claim=the per-role behaviour of each route (test_partner_tracer and the later partner endpoint tests).
"""
import catalogue_mounts_partners as partners
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import load_manifest, owner_of, resolved_read, resolved_write
from tests._route_walk import run_real_app_walk


def _entry(view):
    return next(c for c in load_manifest()["catalogues"] if c["view"] == view)


def test_partner_guards_match_the_manifest_and_are_the_mounts():
    for guard, view in ((partners.PARTNERS_GUARD, "partners"), (partners.PARTNER_PORTAL_GUARD, "partnerPortal")):
        entry = _entry(view)
        meta = guard.__catalogue_guard__
        assert meta["catalogue"] == view
        assert sorted(meta["read"]) == sorted(resolved_read(entry))
        assert sorted(meta["write"]) == sorted(resolved_write(entry))
    assert MOUNT_GUARDS[("partner_platform_endpoints", "router")] is partners.PARTNERS_GUARD
    assert MOUNT_GUARDS[("partner_endpoints", "router")] is partners.PARTNER_PORTAL_GUARD
    assert partners.MOUNTS == {("partner_platform_endpoints", "router"): partners.PARTNERS_GUARD,
                               ("partner_endpoints", "router"): partners.PARTNER_PORTAL_GUARD}


def _check_module(module, view):
    manifest = load_manifest()
    entry = _entry(view)
    mine = [r for r in run_real_app_walk()["routes"] if r["module"] == module]
    assert mine, f"no route of {module} is mounted"
    offenders = []
    for record in mine:
        owner = owner_of(record["path"], manifest)
        assert owner is not None and owner["view"] == view, record
        assert record["auth"] == "user", record
        matched = any(t["catalogue"] == view
                      and sorted(t["read"]) == sorted(resolved_read(entry))
                      and sorted(t["write"]) == sorted(resolved_write(entry)) for t in record["tags"])
        if not matched:
            offenders.append(f"{record['methods']} {record['path']}")
    assert offenders == [], offenders
    return mine


def test_every_super_admin_partner_route_carries_the_partners_guard():
    mine = _check_module("partner_platform_endpoints", "partners")
    assert ("GET", "/api/platform/partners") in {(m, r["path"]) for r in mine for m in r["methods"]}


def test_every_partner_portal_route_carries_the_partner_portal_guard():
    mine = _check_module("partner_endpoints", "partnerPortal")
    assert ("GET", "/api/partner/overview") in {(m, r["path"]) for r in mine for m in r["methods"]}

