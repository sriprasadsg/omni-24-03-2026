"""Catalogue manifest helpers for the parity tests (Phase 76, D-05).

Loads ``shared/catalogue-access.json``, resolves which catalogue owns a mounted path
(longest route prefix on a segment boundary), and names every in-scope user route that
lacks a matching ``catalogue_guard`` tag. ``SLICES`` partitions the in-scope catalogues
across the wave-3 guard plans so two plans never edit the same mount file.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MANIFEST_PATH = os.path.join(REPO_ROOT, "shared", "catalogue-access.json")

# 98 in-scope sidebar catalogues (RESEARCH Appendix A) plus twelve enforced views with
# no sidebar item (six identity views, two chat aliases, four security aliases). Slice
# order breaks ties in slice_modules().
SLICES: Dict[str, Tuple[str, ...]] = {
    "assets": ("assetManagement", "itam", "certificates"),
    "agents": (
        "agents", "agentCapabilities", "remoteAccess", "chat", "jobs", "serviceCatalog",
        "agentChat", "supportChat",
    ),
    "devices": (
        "patchManagement", "deploymentApprovals", "softwareUpdates", "softwareDeployment",
        "stagedDeployments", "windowsAutopilot", "mobileDeviceManagement", "mobileAppManagement",
        "androidEnterprise", "branchSites", "appCatalog", "assetIntelligence",
        "deviceConfigProfiles", "firmwareDriverUpdates",
    ),
    "secops": (
        "security", "alertManagement", "edr", "yaraRules", "mdr", "xdr", "mitreAttack",
        "threatHunting", "siem", "threatIntelligence", "securityIntelConnectors", "siemRules",
        "incidentResponse", "incidentWarRoom", "deception", "aiAnomaly", "ueba", "shadowAI",
        "ndr", "correlations", "emailSecurity", "incidentImpact", "persistenceDetection",
        "securitySimulation", "securityAudit", "advancedHunting", "detectionRules",
        "connectorsHub", "securityCopilot", "attackTimeline", "geographicMap", "agentGroups",
        "configDrift", "fimMonitoring", "activeResponse",
        "persistence", "insiderThreat", "fim",
    ),
    "secposture": (
        "cloudSecurity", "cloudAccounts", "cloudChecksScanner", "iacContainer", "dlp",
        "dataSecurity", "attackPath", "pentest", "dast", "zeroTrustQuantum",
        "vulnerabilityManagement", "runtimeSecurity", "pam", "scaAssessment", "vulnerabilities",
    ),
    "billing_identity": (
        "finops", "servicePricing", "paymentSettings", "subscriptionManagement", "invoices",
        "knowledgeBase", "tenantManagement", "bundleManagement", "userManagement",
        "roleManagement", "apiKeys", "profile",
    ),
    "settings_ops": (
        "cloudIntegrations", "secretsManagement", "hadr", "retentionPolicy",
        "retentionPolicies", "msspMonitoring", "geoSecurity", "fleetObservability",
        "fleetGeoMap", "nativeSecurity", "systemHealth", "apiStatus", "settings", "webhooks",
        "ticketing", "ticketWebhooks", "notificationPrefs", "dataWarehouse",
        "notifications", "integrations",
    ),
}


def load_manifest(path: str = MANIFEST_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _manage_twin(perm: str) -> str:
    from catalogue_guards import manage_twin
    return manage_twin(perm)


def resolved_read(entry: Dict[str, Any]) -> List[str]:
    return list(entry.get("read") or [entry["permission"]])


def resolved_write(entry: Dict[str, Any]) -> List[str]:
    return list(entry.get("write") or [_manage_twin(entry["permission"])])


def owner_of(path: str, manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Catalogue whose route prefix is the longest segment-boundary match for *path*."""
    best: Optional[Dict[str, Any]] = None
    best_len = -1
    for entry in manifest["catalogues"]:
        for prefix in entry.get("routes") or []:
            if (path == prefix or path.startswith(prefix + "/")) and len(prefix) > best_len:
                best, best_len = entry, len(prefix)
    return best


def _enforced_groups(manifest: Dict[str, Any]) -> set:
    return {g["id"] for g in manifest["groups"] if g.get("enforce")}


def _call(view: str, read: Sequence[str], write: Sequence[str]) -> str:
    return f'catalogue_guard("{view}", read={list(read)}, write={list(write)})'


def _in_scope(record: Dict[str, Any], manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Owning catalogue when the record is a user route under an enforce:true group."""
    if record.get("auth") != "user":
        return None
    owner = owner_of(record["path"], manifest)
    if owner is None or owner["group"] not in _enforced_groups(manifest):
        return None
    return owner


def parity_offenders(
    records: Iterable[Dict[str, Any]],
    manifest: Dict[str, Any],
    modules: Optional[Iterable[str]] = None,
) -> List[str]:
    """One line per method for every in-scope route without a matching guard tag."""
    wanted = set(modules) if modules is not None else None
    out: List[str] = []
    for record in records:
        if wanted is not None and record.get("module") not in wanted:
            continue
        owner = _in_scope(record, manifest)
        if owner is None or record.get("exempt"):
            continue
        read, write = resolved_read(owner), resolved_write(owner)
        matched = any(
            tag.get("catalogue") == owner["view"]
            and sorted(tag.get("read") or []) == sorted(read)
            and sorted(tag.get("write") or []) == sorted(write)
            for tag in record.get("tags") or []
        )
        if matched:
            continue
        found = "".join(
            f"; found {_call(t.get('catalogue'), t.get('read') or [], t.get('write') or [])}"
            for t in record.get("tags") or []
        )
        for method in record["methods"]:
            out.append(f"{method} {record['path']} ({record.get('module')}): "
                       f"expected {_call(owner['view'], read, write)}{found}")
    return sorted(out)


def slice_of(view: str) -> Optional[str]:
    for name, views in SLICES.items():
        if view in views:
            return name
    return None


def slice_modules(
    slice_name: str,
    records: Optional[Iterable[Dict[str, Any]]] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Modules assigned to *slice_name*: the slice owning most of the module's in-scope user routes.

    Every user route under an enforce:true catalogue counts, tagged or exempt or not, so
    the partition does not move while later plans add guards and exemptions. Ties go to
    the slice that comes first in SLICES.
    """
    if records is None:
        from tests._route_walk import run_real_app_walk
        records = run_real_app_walk()["routes"]
    if manifest is None:
        manifest = load_manifest()
    order = list(SLICES)
    counts: Dict[str, Dict[str, int]] = {}
    for record in records:
        owner = _in_scope(record, manifest)
        if owner is None:
            continue
        owning_slice = slice_of(owner["view"])
        if owning_slice is None or not record.get("module"):
            continue
        per_module = counts.setdefault(record["module"], {})
        per_module[owning_slice] = per_module.get(owning_slice, 0) + 1
    chosen = []
    for module, per_slice in counts.items():
        winner = max(per_slice, key=lambda s: (per_slice[s], -order.index(s)))
        if winner == slice_name:
            chosen.append(module)
    return sorted(chosen)
