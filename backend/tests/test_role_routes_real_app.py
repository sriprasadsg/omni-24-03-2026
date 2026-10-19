"""Phase 77 plan 10 (ACC-09, SC5): the role write and visibility routes on the production router registry.

One probe run (a fresh interpreter over the real app with a throwaway environment, never the live
database) samples at most 20 cases: the role write routes refuse roles without manage:rbac, the
visibility route refuses roles that cannot list roles, and the Super Admin passes every guard.
The role x screen matrix runs at function level (test_role_visibility.py).
"""
import rbac_defaults
from tests._route_walk import probe_real_app

TENANT = "tenant-a"
PLATFORM = rbac_defaults.PLATFORM_TENANT_ID
ROLES = "/api/roles"
CATALOGUE = "/api/roles/permission-catalogue"
VISIBILITY = "/api/roles/role-viewer/visibility"
ONE_ROLE = "/api/roles/role-x"


def _case(method, path, role):
    tenant = PLATFORM if role == "super_admin" else TENANT
    return {"method": method, "path": path, "role": role, "tenant_id": tenant, "auth": "session"}


# (method, path, role, expectation): "refused" -> 403, "admitted" -> past the guard (not 401/403)
CASES = [
    ("POST", ROLES, "viewer", "refused"),
    ("POST", ROLES, "itam_admin", "refused"),
    ("POST", ROLES, "tenant_admin", "admitted"),
    ("GET", CATALOGUE, "viewer", "refused"),
    ("GET", CATALOGUE, "tenant_admin", "admitted"),
    ("GET", VISIBILITY, "viewer", "refused"),
    ("GET", VISIBILITY, "itam_admin", "admitted"),
    ("GET", VISIBILITY, "tenant_admin", "admitted"),
    ("PUT", ONE_ROLE, "viewer", "refused"),
    ("DELETE", ONE_ROLE, "viewer", "refused"),
    ("POST", ROLES, "super_admin", "admitted"),
    ("PUT", ONE_ROLE, "super_admin", "admitted"),
    ("DELETE", ONE_ROLE, "super_admin", "admitted"),
    ("GET", CATALOGUE, "super_admin", "admitted"),
    ("GET", VISIBILITY, "super_admin", "admitted"),
]


def test_role_routes_guards_on_the_real_app():
    assert len(CASES) <= 20  # each probe run costs minutes (RESEARCH A7)
    statuses = probe_real_app([_case(m, p, r) for m, p, r, _e in CASES])
    assert len(statuses) == len(CASES)
    for (method, path, role, expected), status in zip(CASES, statuses):
        message = f"{method} {path} as {role}: got {status}, expected {expected}"
        if expected == "refused":
            assert status == 403, message
        else:
            assert status not in (401, 403), message
