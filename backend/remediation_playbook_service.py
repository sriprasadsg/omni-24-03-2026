"""Deterministic YAML remediation playbook layer (Phase 53, AUTO-02).

Playbooks are loaded from vendored YAML files, validated against a fixed
ACTION_MAP allowlist, and selected per finding class. No LLM anywhere in
this module — selection and step resolution are pure, deterministic
lookups. Operators can extend the vendored set via the dedicated
`remediation_playbooks` collection (remediation_playbook_endpoints.py),
which is distinct from the LLM-driven `playbooks` store
(enhanced_playbook_endpoints.py) — the engine (53-03) only ever executes
playbooks from this deterministic store.
"""
import logging
import os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

PLAYBOOKS_DIR = os.path.join(os.path.dirname(__file__), "playbooks")

# Fixed action allowlist: action name -> agent instruction command. Every
# playbook step/rollback action MUST resolve here or validate() rejects it.
ACTION_MAP: Dict[str, str] = {
    "patch_package": "upgrade_software",
    "kill_process": "kill_process",
    "restore_file": "restore_file",
    "block_ip": "block_ip",
    "unblock_ip": "unblock_ip",
    "disable_service": "disable_service",
    "enable_service": "enable_service",
    "rotate_key": "rotate_key",
    "rotate_key_rollback": "rotate_key_rollback",
}

_REQUIRED_PLAYBOOK_FIELDS = ("name", "finding_class", "steps")
_REQUIRED_STEP_FIELDS = ("action",)


def validate(playbook: Dict[str, Any]) -> None:
    """Raises ValueError if the playbook is structurally invalid or
    references an action outside ACTION_MAP."""
    for field in _REQUIRED_PLAYBOOK_FIELDS:
        if field not in playbook:
            raise ValueError(f"Playbook missing required field: {field}")

    steps = playbook.get("steps") or []
    if not isinstance(steps, list) or len(steps) == 0:
        raise ValueError(f"Playbook '{playbook.get('name')}' must have at least one step")

    for step in steps:
        for field in _REQUIRED_STEP_FIELDS:
            if field not in step:
                raise ValueError(f"Playbook '{playbook.get('name')}' step missing field: {field}")
        if step["action"] not in ACTION_MAP:
            raise ValueError(f"Playbook '{playbook.get('name')}' references unknown action: {step['action']}")

    for step in playbook.get("rollback") or []:
        if step.get("action") not in ACTION_MAP:
            raise ValueError(f"Playbook '{playbook.get('name')}' rollback references unknown action: {step.get('action')}")


def load_default_playbooks() -> List[Dict[str, Any]]:
    """Reads + validates every vendored YAML playbook. Hermetic — no DB."""
    playbooks: List[Dict[str, Any]] = []
    if not os.path.isdir(PLAYBOOKS_DIR):
        return playbooks

    for fname in sorted(os.listdir(PLAYBOOKS_DIR)):
        if not fname.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(PLAYBOOKS_DIR, fname)
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if not data:
            continue
        data.setdefault("steps", [])
        data.setdefault("rollback", [])
        data.setdefault("match", {})
        validate(data)
        data["source"] = "vendored"
        playbooks.append(data)
    return playbooks


def _finding_attr(finding: Any, name: str, default=None):
    if isinstance(finding, dict):
        return finding.get(name, default)
    return getattr(finding, name, default)


def select_playbook(finding: Any, playbooks: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Deterministically maps a finding to the playbook that remediates its
    class. `playbooks` defaults to the vendored set (hermetic); the engine
    passes the merged default+operator set from the DB.

    finding_class mapping (grounded in the actual finding shapes):
      - fim  -> restore_file
      - nscan + scan type "ip" -> block_ip; otherwise -> kill_process
      - vuln + playbook_ref rotate_key + fingerprint -> rotate_key
      - vuln + a resolvable CVE id -> patch_package; no CVE (misconfig) -> disable_service
      - anomaly + anomaly_rule "shadow_ai_detected" + a real agent_id -> kill_process
        (reuses the existing agent-dispatch playbook verbatim, AUT-03); every
        other anomaly (no agent_id, or a different anomaly_rule) honestly
        returns None -> no_playbook. Pure deterministic lookup, no LLM (D-02).
    """
    if playbooks is None:
        playbooks = load_default_playbooks()
    by_name = {p["name"]: p for p in playbooks}

    finding_type = _finding_attr(finding, "finding_type")
    details = _finding_attr(finding, "details", {}) or {}

    if finding_type == "fim":
        return by_name.get("restore_file")

    if finding_type == "nscan":
        scan_type = details.get("type") or details.get("scan_type")
        if scan_type == "ip":
            return by_name.get("block_ip")
        return by_name.get("kill_process")

    if finding_type == "vuln":
        if details.get("playbook_ref") == "rotate_key" and details.get("fingerprint"):
            return by_name.get("rotate_key")
        cve_id = details.get("cveId") or details.get("cve_id")
        if cve_id:
            return by_name.get("patch_package")
        return by_name.get("disable_service")

    if finding_type == "anomaly":
        anomaly_details = _finding_attr(finding, "details", {}) or {}
        agent_id = _finding_attr(finding, "agent_id")
        if anomaly_details.get("anomaly_rule") == "shadow_ai_detected" and agent_id:
            return by_name.get("kill_process")
        return None

    return None


async def sync_default_playbooks_to_db(db) -> int:
    """Idempotently upserts the vendored defaults into `remediation_playbooks`
    (keyed by name) so operators can list/override them via the CRUD
    endpoints. Never overwrites an operator-edited row's steps."""
    count = 0
    for playbook in load_default_playbooks():
        existing = await db.remediation_playbooks.find_one({"name": playbook["name"], "source": "vendored"})
        if existing:
            continue
        doc = dict(playbook)
        doc["id"] = f"vendored-{playbook['name']}"
        await db.remediation_playbooks.insert_one(doc)
        count += 1
    return count


async def load_playbooks(db) -> List[Dict[str, Any]]:
    """Returns the full merged set (vendored defaults + operator-authored)
    from the `remediation_playbooks` collection, seeding defaults on first
    call."""
    await sync_default_playbooks_to_db(db)
    docs = await db.remediation_playbooks.find({}, {"_id": 0}).to_list(length=200)
    return docs
