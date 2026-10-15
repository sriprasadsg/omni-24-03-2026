"""Security-posture slice (Phase 76-08): cloud, application, data and vulnerability catalogues.

Every router below is user-authenticated end to end and owned by a single catalogue of the
enforced "Security (SecOps)" group, so each is guarded once at mount time (D-01, D-03).
Routers the manifest assigns to DevSecOps (iac_security, k8s_security, pipeline_security,
supply_chain_security, api_security, dam) are not enforced and stay unguarded for the ledger.

Read permissions (view:X or its manage: twin) and write strings mirror
``shared/catalogue-access.json``; ``test_catalogue_slice_secposture`` fails when the two drift.
Writes keep the strings the routes already require (Pitfall 2).
"""
from catalogue_guards import catalogue_guard
from catalogue_mounts_assets import VULNERABILITY_GUARD

__all__ = ["MOUNTS", "VULNERABILITY_GUARD"]

_CLOUD_READ = ("view:cloud_security",)
_SECURITY_READ = ("view:security",)
_INVESTIGATE = ("investigate:security",)

CLOUD_ACCOUNTS_GUARD = catalogue_guard(
    "cloudAccounts", read=_CLOUD_READ, write=("manage:settings", "view:cloud_security")
)
IAC_CONTAINER_GUARD = catalogue_guard(
    "iacContainer", read=_CLOUD_READ, write=("manage:settings", "view:dashboard")
)
ZERO_TRUST_GUARD = catalogue_guard(
    "zeroTrustQuantum", read=("view:zero_trust",), write=("manage:settings", "view:security")
)

MOUNTS = {
    # --- Cloud and application family ---------------------------------------------------
    ("cloud_account_endpoints", "router"): CLOUD_ACCOUNTS_GUARD,
    ("cloud_checks_endpoints", "router"): catalogue_guard(
        "cloudChecksScanner", read=_CLOUD_READ, write=("manage:compliance",)
    ),
    ("cloud_remediation_endpoints", "router"): catalogue_guard(
        "cloudSecurity", read=_CLOUD_READ, write=("investigate:security", "manage:security_cases")
    ),
    ("iac_scanner_endpoints", "router"): IAC_CONTAINER_GUARD,
    ("container_scanner_endpoints", "router"): IAC_CONTAINER_GUARD,
    ("dast_service", "router"): catalogue_guard("dast", read=_SECURITY_READ, write=_INVESTIGATE),
    ("sca_endpoints", "router"): catalogue_guard("scaAssessment", read=("view:sca",), write=_INVESTIGATE),
    ("pentest_endpoints", "router"): catalogue_guard(
        "pentest", read=_SECURITY_READ, write=("investigate:security", "manage:security_cases")
    ),
    # --- Data, identity and vulnerability family ----------------------------------------
    ("dlp_endpoints", "router"): catalogue_guard("dlp", read=_SECURITY_READ, write=_INVESTIGATE),
    ("pam_endpoints", "router"): catalogue_guard("pam", read=("manage:settings",), write=("manage:settings",)),
    ("attack_path_endpoints", "router"): catalogue_guard(
        "attackPath", read=("view:attack_path",), write=("investigate:security", "manage:security_cases")
    ),
    ("zero_trust_service", "router"): ZERO_TRUST_GUARD,
    ("pqc_endpoints", "router"): ZERO_TRUST_GUARD,
    ("vuln_endpoints", "router"): VULNERABILITY_GUARD,
}
