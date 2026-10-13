"""Catalogue guard tests (Phase 76, ACC-03/ACC-04).

Task 1 tracer: Mobile Device Management on the real mounted app.
"""
from tests._route_walk import probe_real_app


def test_tracer_mdm_enforced_on_real_app():
    denied, allowed = probe_real_app([
        {"method": "GET", "path": "/api/mdm/summary", "role": "viewer", "tenant_id": "tenant-a", "auth": "session"},
        {"method": "GET", "path": "/api/mdm/summary", "role": "admin", "tenant_id": "tenant-a", "auth": "session"},
    ])
    assert denied == 403, "a role without view:mdm / manage:mdm must be refused on /api/mdm"
    assert allowed != 403, "a role holding view:mdm must not be refused by the catalogue guard"
