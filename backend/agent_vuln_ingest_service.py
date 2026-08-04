"""Agent vulnerability-finding ingest (Phase 51 Plan 03, VULN-01/03).

Bridges the agent's `vulnerability_scanning` capability output — carried on the
heartbeat at `payload.meta.vulnerability_scanning.vulnerabilities` (each
capability's `collect()` is merged into `meta[<id>]`; the vuln capability's id
is `vulnerability_scanning`) — into the real `vulnerabilities` collection the
dashboard reads (`vuln_service` / `vuln_endpoints`), replacing the mock seeds.

Findings are upserted tenant-scoped and deduped on (tenantId, agentId, cve_id,
affected_path) with first_seen/last_seen maintained. Ingest is non-blocking: a
failure here must never fail the heartbeat (see `ingest_from_heartbeat`).
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# The confirmed heartbeat payload path for the vuln capability's collect() output.
VULN_CAPABILITY_ID = "vulnerability_scanning"

_SEVERITY_TITLE = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_severity(severity: Any) -> str:
    s = (severity or "").strip()
    return _SEVERITY_TITLE.get(s.upper(), s.title() or "Medium")


async def ingest_findings(
    db: Any,
    tenant_id: str,
    agent_id: str,
    findings: List[Dict[str, Any]],
) -> int:
    """Upsert agent vuln findings into the `vulnerabilities` collection.

    Deduped on (tenantId, agentId, cve_id, affected_path). For findings without
    a CVE (misconfig/secret), `detail` joins the key so distinct issues at the
    same path are not collapsed. Returns the number of findings processed.

    Uses the request-scoped wrapped `db` passed by the caller — never `db._db`.
    May raise on a DB error; callers that must stay non-blocking use
    `ingest_from_heartbeat`.
    """
    if not findings:
        return 0

    processed = 0
    for f in findings:
        if not isinstance(f, dict):
            continue
        cve_id = f.get("cve_id") or f.get("cveId")
        affected = f.get("affected_path") or f.get("affected") or f.get("package") or ""
        cvss = f.get("cvss")
        severity = _title_severity(f.get("severity"))
        detail = f.get("detail")
        now = _now()

        match: Dict[str, Any] = {
            "tenantId": tenant_id,
            "agentId": agent_id,
            "cve_id": cve_id,
            "affected_path": affected,
        }
        # Non-CVE findings share affected_path (e.g. sshd_config) — keep them
        # distinct by detail so a second issue at the same path is not merged.
        if not cve_id:
            match["detail"] = detail

        set_fields: Dict[str, Any] = {
            "cveId": cve_id,  # UI alias (VulnerabilityManagement reads cveId)
            "cvss": cvss,
            "cvssScore": cvss,  # UI alias (reads cvssScore/cvss_score)
            "severity": severity,
            "type": f.get("type"),
            "remediation_hint": f.get("remediation_hint"),
            "playbook_ref": f.get("playbook_ref"),
            "detail": detail,
            "description": detail or (cve_id or ""),
            "package": affected,
            "affectedSoftware": affected,
            "source": "agent",
            "status": "Open",
            "last_seen": now,
        }

        await db.vulnerabilities.update_one(
            match,
            {"$set": set_fields, "$setOnInsert": {"first_seen": now, "created_at": now}},
            upsert=True,
        )
        processed += 1

    return processed


async def ingest_from_heartbeat(
    db: Any,
    tenant_id: str,
    agent_id: str,
    payload: Dict[str, Any],
) -> None:
    """Non-blocking heartbeat entry point: pull the vuln findings from the
    confirmed payload path and ingest them, swallowing any error.

    A vuln-ingest failure must never fail or block the heartbeat (T-51-07).
    """
    try:
        meta = (payload or {}).get("meta") or {}
        cap = meta.get(VULN_CAPABILITY_ID) or {}
        findings = cap.get("vulnerabilities") or []
        if not isinstance(findings, list) or not findings:
            return
        count = await ingest_findings(db, tenant_id, agent_id, findings)
        if count:
            logger.debug("Ingested %d vuln finding(s) for agent %s", count, agent_id)
    except Exception as exc:  # noqa: BLE001 — non-blocking by design
        logger.warning("Vuln ingest skipped for agent %s: %s", agent_id, exc)
