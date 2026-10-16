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
LEDGER_PATH = os.path.join(REPO_ROOT, "shared", "catalogue-gaps.json")
MIN_EXEMPT_REASON = 10

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


def load_ledger(path: str = LEDGER_PATH) -> Dict[str, Any]:
    """Read the committed gap ledger. Read-only: no test may write or regenerate it (PROH-76-03)."""
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


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _parity_scope(record: Dict[str, Any], manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Owning catalogue when the record must carry its catalogue guard (D-05, WR-01).

    User routes as in ``_in_scope``. Agent-capable routes join the scope under an enforce:true
    group when they have a safe method (an unguarded read leaks to any viewer) or already carry a
    tag (it must then be the right one). Untagged agent-capable writes stay with the reviewed
    ``agentCapableRoutes`` list instead. ``slice_modules`` keeps ``_in_scope``.
    """
    if record.get("auth") == "agent_capable":
        owner = owner_of(record["path"], manifest)
        if owner is None or owner["group"] not in _enforced_groups(manifest):
            return None
        safe = any(m.upper() in SAFE_METHODS for m in record["methods"])
        return owner if safe or record.get("tags") else None
    return _in_scope(record, manifest)


def _refusing_tags(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Tags on an agent-capable record that would refuse the agent identity (D-02, PROH-76-06)."""
    if record.get("auth") != "agent_capable":
        return []
    return [t for t in record.get("tags") or [] if t.get("allow_agent") is not True]


def parity_offenders(
    records: Iterable[Dict[str, Any]],
    manifest: Dict[str, Any],
    modules: Optional[Iterable[str]] = None,
) -> List[str]:
    """One line per method for every in-scope route without a matching guard tag.

    Agent-capable routes must carry the owning catalogue's agent-tolerant tag, and any tag on an
    agent-capable route that would refuse the agent identity is an offender wherever it sits.
    """
    wanted = set(modules) if modules is not None else None
    out: List[str] = []
    for record in records:
        if wanted is not None and record.get("module") not in wanted:
            continue
        agent_capable = record.get("auth") == "agent_capable"
        owner = _parity_scope(record, manifest)
        if owner is not None and record.get("exempt"):
            owner = None
        refusing = _refusing_tags(record)
        expected = ""
        if owner is not None:
            read, write = resolved_read(owner), resolved_write(owner)
            matched = any(
                tag.get("catalogue") == owner["view"]
                and sorted(tag.get("read") or []) == sorted(read)
                and sorted(tag.get("write") or []) == sorted(write)
                and (not agent_capable or tag.get("allow_agent") is True)
                for tag in record.get("tags") or []
            )
            if not matched:
                call = _call(owner["view"], read, write)
                expected = f"expected agent_tolerant({call})" if agent_capable else f"expected {call}"
        if not expected and not refusing:
            continue
        found = "".join(
            f"; found {_call(t.get('catalogue'), t.get('read') or [], t.get('write') or [])}"
            for t in record.get("tags") or []
        )
        why = ("; this tag would refuse the agent identity, wrap the guard in agent_tolerant(...) (D-02)"
               if refusing else "")
        for method in record["methods"]:
            head = f"{method} {record['path']} ({record.get('module')}): "
            out.append(head + (expected or "tag mismatch") + found + why)
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


def _pairs(record: Dict[str, Any]) -> List[str]:
    return [f"{method} {record['path']}" for method in record["methods"]]


def _is_unguarded(record: Dict[str, Any]) -> bool:
    """Strict definition (RESEARCH A6): user route with no tag, no known guard dependency, no exemption."""
    return (record.get("auth") == "user" and not record.get("tags")
            and not record.get("known_guard") and not record.get("exempt"))


def _ledger_group(records: Sequence[Dict[str, Any]], manifest: Dict[str, Any]) -> str:
    counts: Dict[str, int] = {}
    for record in records:
        owner = owner_of(record["path"], manifest)
        group = owner["group"] if owner else "unowned"
        counts[group] = counts.get(group, 0) + len(record["methods"])
    return max(sorted(counts), key=lambda g: counts[g]) if counts else "unowned"


def ledger_offenders(
    records: Iterable[Dict[str, Any]],
    manifest: Dict[str, Any],
    ledger: Dict[str, Any],
) -> List[str]:
    """Deny-by-default ledger checks (D-05): completeness, staleness, ratchets, no enforced gaps."""
    records = list(records)
    enforced = _enforced_groups(manifest)
    out: List[str] = []

    # --- per-module unguarded user routes, split by whether an enforced catalogue owns them
    ledgerable: Dict[str, List[Dict[str, Any]]] = {}
    enforced_gaps: Dict[str, List[str]] = {}
    for record in records:
        if not _is_unguarded(record):
            continue
        module = record.get("module") or "<unknown>"
        owner = owner_of(record["path"], manifest)
        if owner is not None and owner["group"] in enforced:
            enforced_gaps.setdefault(module, []).extend(_pairs(record))
        else:
            ledgerable.setdefault(module, []).append(record)
    mounted = {record.get("module") for record in records}

    # --- ledger entries
    seen: Dict[str, int] = {}
    for entry in ledger.get("routers", []):
        module = entry.get("module") or "<missing module>"
        seen[module] = seen.get(module, 0) + 1
        if seen[module] == 2:
            out.append(f"{module}: duplicate ledger entries; keep one")
        for field in ("group", "reason"):
            if not str(entry.get(field) or "").strip():
                out.append(f"{module}: ledger entry has an empty {field}")
        if str(entry.get("reason") or "").strip().startswith("<"):
            out.append(f"{module}: ledger entry still carries the placeholder reason")
        if module in enforced_gaps:
            out.append(f"{module}: enforced routes cannot be ledgered; guard these routes instead: "
                       + ", ".join(sorted(enforced_gaps[module])))
        count = sum(len(r["methods"]) for r in ledgerable.get(module, []))
        maximum = entry.get("maxUnguardedRoutes")
        if module in enforced_gaps and count == 0:
            continue  # the enforced-route offender above is the whole story
        if module not in mounted or count == 0:
            out.append(f"{module}: stale ledger entry ({'module is not mounted' if module not in mounted else 'no unguarded user routes left'}); remove it")
        elif not isinstance(maximum, int) or isinstance(maximum, bool):
            out.append(f"{module}: maxUnguardedRoutes must be an integer")
        elif count > maximum:
            out.append(f"{module}: {count} unguarded routes, above maxUnguardedRoutes {maximum}; "
                       "guard the new route or review a ledger change")
        elif count < maximum and module not in enforced_gaps:
            out.append(f"{module}: maxUnguardedRoutes {maximum} leaves slack over {count} unguarded routes; "
                       f"lower it to {count}")

    # --- routers missing from the ledger
    for module in sorted(ledgerable):
        if module in seen:
            continue
        count = sum(len(r["methods"]) for r in ledgerable[module])
        paste = json.dumps({
            "module": module,
            "group": _ledger_group(ledgerable[module], manifest),
            "maxUnguardedRoutes": count,
            "reason": "<state why this router is unguarded>",
        })
        routes = ", ".join(sorted(p for r in ledgerable[module] for p in _pairs(r)))
        out.append(f"{module}: {count} unguarded user routes and not in shared/catalogue-gaps.json "
                   f"({routes}); guard them or add {paste}")

    # --- agent-capable and exempt ratchets
    untagged_agent = [r for r in records if r.get("auth") == "agent_capable" and not r.get("tags")]
    agent = sorted(p for r in untagged_agent for p in _pairs(r))
    if len(agent) > int(ledger.get("agentAuthExcludedRoutes", 0)):
        out.append(f"agentAuthExcludedRoutes: {len(agent)} untagged agent-capable routes, above the ratchet "
                   f"{ledger.get('agentAuthExcludedRoutes', 0)}: {', '.join(agent)}")
    elif len(agent) < int(ledger.get("agentAuthExcludedRoutes", 0)):
        out.append(f"agentAuthExcludedRoutes: ratchet {ledger['agentAuthExcludedRoutes']} leaves slack over "
                   f"{len(agent)} untagged agent-capable routes; lower it to {len(agent)}")
    exempt = [(p, r["exempt"]) for r in records if r.get("exempt") for p in _pairs(r)]
    if len(exempt) > int(ledger.get("maxExemptRoutes", 0)):
        out.append(f"maxExemptRoutes: {len(exempt)} exempt routes, above the ratchet "
                   f"{ledger.get('maxExemptRoutes', 0)}: {', '.join(sorted(p for p, _ in exempt))}")
    elif len(exempt) < int(ledger.get("maxExemptRoutes", 0)):
        out.append(f"maxExemptRoutes: ratchet {ledger['maxExemptRoutes']} leaves slack over "
                   f"{len(exempt)} exempt routes; lower it to {len(exempt)}")
    for pair, reason in sorted(exempt):
        if len(str(reason).strip()) < MIN_EXEMPT_REASON:
            out.append(f"{pair}: catalogue_exempt reason {reason!r} is shorter than {MIN_EXEMPT_REASON} characters")

    # --- reviewed lists (optional keys, so ledgers built without them keep their old meaning)
    if "agentCapableRoutes" in ledger:
        out.extend(_agent_capable_list_offenders(untagged_agent, manifest, ledger["agentCapableRoutes"]))
    return sorted(out)


def _listed(entries: Any, key: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Index a reviewed list by route; return (first entry per route, duplicate routes)."""
    index: Dict[str, Dict[str, Any]] = {}
    duplicates: List[str] = []
    for entry in entries or []:
        route = str(entry.get("route") or "<missing route>")
        if route in index:
            if route not in duplicates:
                duplicates.append(route)
            continue
        index[route] = entry
    return index, duplicates


def _agent_capable_list_offenders(
    untagged_agent: Sequence[Dict[str, Any]],
    manifest: Dict[str, Any],
    entries: Any,
) -> List[str]:
    """Every untagged agent-capable route is individually listed with a reason (D-05)."""
    enforced = _enforced_groups(manifest)
    index, duplicates = _listed(entries, "agentCapableRoutes")
    actual: Dict[str, Dict[str, Any]] = {}
    for record in untagged_agent:
        for pair in _pairs(record):
            actual[pair] = record
    out = [f"agentCapableRoutes: duplicate entries for {route}; keep one" for route in duplicates]
    for route, entry in index.items():
        record = actual.get(route)
        reason = str(entry.get("reason") or "").strip()
        if record is None:
            out.append(f"agentCapableRoutes: stale entry {route} (not an untagged agent-capable route); remove it")
            continue
        owner = owner_of(record["path"], manifest)
        method = route.split(" ", 1)[0].upper()
        if owner is not None and owner["group"] in enforced and method in SAFE_METHODS:
            out.append(f"agentCapableRoutes: {route} is a read under the enforced {owner['view']} catalogue; "
                       "reads must carry agent_tolerant(catalogue_guard(...)), a ledger entry cannot excuse it")
        if len(reason) < MIN_EXEMPT_REASON or reason.startswith("<"):
            out.append(f"agentCapableRoutes: {route} reason {reason!r} is a placeholder or shorter than "
                       f"{MIN_EXEMPT_REASON} characters")
    for route, record in sorted(actual.items()):
        if route in index:
            continue
        owner = owner_of(record["path"], manifest)
        method = route.split(" ", 1)[0].upper()
        if owner is not None and owner["group"] in enforced and method in SAFE_METHODS:
            continue  # parity_offenders names this read and the guard it needs
        paste = json.dumps({"route": route, "reason": "<state why this agent-capable route carries no catalogue tag>"})
        out.append(f"agentCapableRoutes: {route} ({record.get('module')}) is an agent-capable route without a "
                   f"catalogue tag and not in shared/catalogue-gaps.json; tag it or add {paste}")
    return out
