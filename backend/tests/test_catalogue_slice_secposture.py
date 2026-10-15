"""Security-posture slice (Phase 76-08): cloud, application, data and vulnerability routes carry the manifest guard.

DevSecOps-owned routers (iac_security, k8s_security, pipeline_security, supply_chain_security,
api_security, dam) belong to a non-enforced group and must stay unguarded here (D-01).
"""
import catalogue_mounts_secposture as secposture
from catalogue_mounts import MOUNT_GUARDS
from tests._catalogue_parity import (
    load_manifest, parity_offenders, resolved_read, resolved_write, slice_modules,
)
from tests._route_walk import probe_real_app, run_real_app_walk

TENANT = "tenant-a"
DEVSECOPS_MODULES = (
    "iac_security_endpoints", "k8s_security_endpoints", "pipeline_security_endpoints",
    "supply_chain_security_endpoints", "api_security_endpoints", "dam_endpoints",
)


def _case(path, role, *, method="GET"):
    return {"method": method, "path": path, "role": role, "tenant_id": TENANT, "auth": "session"}


def test_secposture_slice_parity():
    records = run_real_app_walk()["routes"]
    manifest = load_manifest()
    modules = slice_modules("secposture", records, manifest)
    for expected in ("cloud_account_endpoints", "dlp_endpoints", "vuln_endpoints", "pam_endpoints",
                     "zero_trust_service", "pentest_endpoints"):
        assert expected in modules
    offenders = parity_offenders(records, manifest, modules)
    assert offenders == [], "unguarded or mis-guarded secposture-slice routes:\n" + "\n".join(offenders)


def test_secposture_guards_match_manifest():
    """Every mount entry carries exactly the manifest's resolved read/write for its catalogue."""
    manifest = load_manifest()
    by_view = {c["view"]: c for c in manifest["catalogues"]}
    for key, guard in secposture.MOUNTS.items():
        meta = guard.__catalogue_guard__
        entry = by_view[meta["catalogue"]]
        assert sorted(meta["read"]) == sorted(resolved_read(entry)), (key, meta)
        assert sorted(meta["write"]) == sorted(resolved_write(entry)), (key, meta)
        assert MOUNT_GUARDS[key] is guard


def test_secposture_devsecops_routers_left_unguarded():
    records = run_real_app_walk()["routes"]
    tagged = [f"{','.join(r['methods'])} {r['path']} ({r['module']})"
              for r in records if r.get("module") in DEVSECOPS_MODULES and r["tags"]]
    assert tagged == [], "non-enforced DevSecOps routers must not carry a catalogue guard (D-01):\n" + "\n".join(tagged)
    for module in DEVSECOPS_MODULES:
        assert not any(key[0] == module for key in secposture.MOUNTS)


def test_secposture_real_app_enforced():
    cloud_reads = ["/api/cloud-accounts", "/api/cloud-accounts/summary", "/api/cloud-checks",
                   "/api/cloud/remediation/history", "/api/iac/results", "/api/container/results"]
    # nobody holds no permission; incident_responder holds view:security but not view:cloud_security
    for role in ("nobody", "incident_responder"):
        denied = probe_real_app([_case(p, role) for p in cloud_reads])
        assert denied == [403] * len(cloud_reads), (role, dict(zip(cloud_reads, denied)))
    # viewer and tenant_admin hold view:cloud_security; the catalogue guard must not refuse them
    for role in ("viewer", "tenant_admin"):
        allowed = probe_real_app([_case(p, role) for p in cloud_reads])
        assert 403 not in allowed, (role, dict(zip(cloud_reads, allowed)))

    other_reads = ["/api/dlp/policies", "/api/pam/accounts", "/api/pentest/jobs", "/api/sca/stats",
                   "/api/dast/scans", "/api/security/attack-paths", "/api/zero-trust/session-risks",
                   "/api/pqc/status"]
    denied = probe_real_app([_case(p, "nobody") for p in other_reads])
    assert denied == [403] * len(other_reads), dict(zip(other_reads, denied))
    allowed = probe_real_app([_case(p, "tenant_admin") for p in other_reads])
    assert 403 not in allowed, dict(zip(other_reads, allowed))


def test_secposture_vulnerability_read_needs_view_vulnerabilities():
    """D-11: vulnerabilityManagement resolves to view:vulnerabilities."""
    paths = ["/api/vulnerabilities", "/api/vulnerabilities/stats"]
    # viewer holds view:cloud_security and view:security-less reads but not view:vulnerabilities
    for role in ("nobody", "viewer"):
        denied = probe_real_app([_case(p, role) for p in paths])
        assert denied == [403] * len(paths), (role, dict(zip(paths, denied)))
    for role in ("security_analyst", "tenant_admin"):
        allowed = probe_real_app([_case(p, role) for p in paths])
        assert 403 not in allowed, (role, dict(zip(paths, allowed)))


def test_secposture_writes_use_existing_strings():
    """A write by a role holding the route's existing guard string is not refused by the catalogue guard."""
    statuses = probe_real_app([
        _case("/api/dlp/scan", "tenant_admin", method="POST"),                     # investigate:security
        _case("/api/vulnerabilities/scan", "tenant_admin", method="POST"),         # manage:patches et al.
        _case("/api/pentest/scan", "tenant_admin", method="POST"),                 # investigate:security
    ])
    assert 403 not in statuses, statuses
