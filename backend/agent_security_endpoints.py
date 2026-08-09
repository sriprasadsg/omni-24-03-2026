from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Dict, Any, List
from database import get_database
from authentication_service import get_current_user
from datetime import datetime, timezone
import asyncio
import uuid
from agent_auth import verify_agent_key
import logging

router = APIRouter(prefix="/api/agents", tags=["Agents"])
logger = logging.getLogger("agent_security_endpoints")

# Cap on agent-supplied arrays fanned out into per-item DB writes
_MAX_ARRAY = 500


async def _raise_malware_alert(db, tenant_id, agent_id, target, sha256, verdict, ts, rule="file"):
    """Insert a critical security alert for a VirusTotal-confirmed malicious hash."""
    await db.security_alerts.insert_one({
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "agent_id": agent_id,
        "type": "malware_detected",
        "severity": "critical",
        "title": f"VirusTotal flagged {rule} on agent {agent_id}",
        "description": f"'{target}' (SHA256 {sha256}) — {verdict.get('verdict')} {verdict.get('detectionRatio')}",
        "sha256": sha256,
        "vt_detection_ratio": verdict.get("detectionRatio"),
        "created_at": ts,
        "status": "open",
    })


@router.post("/{agent_id}/fim-events")
async def ingest_fim_event(
    agent_id: str,
    payload: Dict[str, Any] = Body(...),
    db=Depends(get_database),
    _auth=Depends(verify_agent_key),
):
    """Receive FIM events via HTTP. Accepts a single event or a batch
    ({"changes": [...]}); created/modified file hashes are enriched via VirusTotal."""
    tenant_id = _auth.get("id") or _auth.get("tenant_id") or ""
    received_at = datetime.now(timezone.utc).isoformat()

    changes = payload.get("changes")
    events: List[Dict[str, Any]] = changes[:_MAX_ARRAY] if isinstance(changes, list) else [payload]

    # Collect created/modified file hashes and enrich them server-side. The
    # rich shape (Phase 52-01) carries `hash_after` as the primary post-change
    # hash; fall back to the legacy `new_hash`/`hash` for backward compatibility.
    def _primary_hash(ev: Dict[str, Any]) -> str:
        return ev.get("hash_after") or ev.get("new_hash") or ev.get("hash") or ""

    hashes = [_primary_hash(ev) for ev in events
              if isinstance(ev, dict) and _primary_hash(ev)]
    from virustotal_client import enrich_file_hashes
    verdicts = await asyncio.to_thread(enrich_file_hashes, hashes) if hashes else {}

    stored: List[str] = []
    malicious_count = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        file_hash = _primary_hash(ev)
        verdict = verdicts.get(file_hash.strip().lower()) if file_hash else None
        doc = {
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "tenantId": tenant_id,
            "path": ev.get("path", payload.get("path", "")),
            "event_type": ev.get("event", ev.get("event_type", payload.get("event_type", "unknown"))),
            "severity": ev.get("severity", payload.get("severity", "high")),
            "message": ev.get("message", payload.get("message", "")),
            "source": payload.get("source", "FileWatcher"),
            "sha256": file_hash,
            "vt_verdict": (verdict or {}).get("verdict"),
            "vt_detection_ratio": (verdict or {}).get("detectionRatio"),
            "received_at": received_at,
            # Rich FIM change-event fields (Phase 52-01, FIM-02) — additive;
            # absent fields default to None so legacy events still ingest.
            "change_type": ev.get("change_type"),
            "hash_before": ev.get("hash_before"),
            "hash_after": ev.get("hash_after"),
            "process": ev.get("process"),
            "user": ev.get("user"),
            "ts": ev.get("ts"),
        }
        await db.fim_events.insert_one(doc)
        doc.pop("_id", None)
        stored.append(doc["id"])
        if verdict and (verdict.get("malicious") or 0) > 0:
            malicious_count += 1
            await _raise_malware_alert(db, tenant_id, agent_id, doc["path"], file_hash, verdict, received_at, rule="FIM change")

    return {"ok": True, "event_ids": stored, "malicious_count": malicious_count}


@router.get("/{agent_id}/fim-events")
async def list_fim_events(
    agent_id: str,
    limit: int = 100,
    db=Depends(get_database),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Retrieve FIM events for a given agent (operator view)."""
    _SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    query: Dict[str, Any] = {"agent_id": agent_id}
    if user_role not in _SUPER_ROLES:
        # Verify agent belongs to caller's tenant before returning events
        agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 1})
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        query["tenantId"] = tenant_id
    cursor = db.fim_events.find(query, {"_id": 0}).sort("received_at", -1).limit(limit)
    return {"events": await cursor.to_list(limit)}


@router.post("/{agent_id}/shadow-ai-scan")
async def post_shadow_ai_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts Shadow AI detection results (local AI processes, ports, cloud connections)."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    scanned_at = datetime.now(timezone.utc).isoformat()
    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": scanned_at,
        "detected_count": body.get("detected_count", 0),
        "ai_connections": body.get("ai_connections", []),
        "local_ai_processes": body.get("local_ai_processes", []),
        "local_ai_ports": body.get("local_ai_ports", []),
    }
    await db.shadow_ai_scans.insert_one(doc)
    doc.pop("_id", None)

    for conn in body.get("ai_connections", [])[:_MAX_ARRAY]:
        await db.shadow_ai_events.update_one(
            {"agent_id": agent_id, "remote_host": conn.get("remote_host"), "process": conn.get("process")},
            {"$set": {
                "agent_id": agent_id,
                "tenantId": tenant_id,
                "process": conn.get("process"),
                "remote_ip": conn.get("remote_ip"),
                "remote_host": conn.get("remote_host"),
                "timestamp": scanned_at,
            }},
            upsert=True,
        )

    for proc in body.get("local_ai_processes", [])[:_MAX_ARRAY]:
        await db.security_alerts.insert_one({
            "tenantId": tenant_id,
            "agent_id": agent_id,
            "type": "shadow_ai_process",
            "severity": "medium",
            "title": f"Unauthorized AI process: {proc.get('name', 'unknown')}",
            "description": f"Local AI process '{proc.get('name')}' (PID {proc.get('pid')}) detected on agent {agent_id}",
            "created_at": scanned_at,
            "status": "open",
        })

    return {"success": True, "detected_count": doc["detected_count"]}


@router.get("/{agent_id}/shadow-ai-scans")
async def get_shadow_ai_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent Shadow AI scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    scans = await db.shadow_ai_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/vulnerability-scan")
async def post_vulnerability_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts its latest vulnerability scan results (OSV-backed)."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_packages": body.get("total_packages", 0),
        "vulnerable_packages": body.get("vulnerable_packages", []),
        "total_cves": body.get("total_cves", 0),
        "scan_source": body.get("scan_source", "osv"),
        "os_patches": body.get("os_patches", {}),
    }

    await db.agent_vulnerability_scans.insert_one(doc)
    doc.pop("_id", None)

    for pkg in body.get("vulnerable_packages", [])[:_MAX_ARRAY]:
        for cve in pkg.get("cves", []):
            severity = cve.get("severity", "Unknown")
            if severity in ("CRITICAL", "HIGH"):
                await db.vulnerabilities.update_one(
                    {"cveId": cve.get("id"), "agentId": agent_id},
                    {"$set": {
                        "cveId": cve.get("id"),
                        "agentId": agent_id,
                        "tenantId": tenant_id,
                        "affectedSoftware": pkg.get("name", ""),
                        "severity": severity,
                        "description": cve.get("summary", ""),
                        "source": "agent_osv_scan",
                        "reported_at": doc["scanned_at"],
                    }},
                    upsert=True,
                )

    return {"success": True, "scan_id": str(doc.get("_id", "")), "total_cves": doc["total_cves"]}


@router.get("/{agent_id}/vulnerability-scans")
async def get_vulnerability_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent vulnerability scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    scans = await db.agent_vulnerability_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/malware-scan")
async def post_malware_scan(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts YARA/malware scan hits; each file SHA256 is enriched via VirusTotal
    server-side. Confirmed-malicious hits raise a critical security alert."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    matches = body.get("matches", [])
    if not isinstance(matches, list):
        matches = []
    matches = matches[:_MAX_ARRAY]

    # Only look up hashes the agent did not already enrich locally (Option B).
    hashes = [m.get("sha256") for m in matches
              if isinstance(m, dict) and m.get("sha256") and not m.get("vt_verdict")]
    from virustotal_client import enrich_file_hashes
    verdicts = await asyncio.to_thread(enrich_file_hashes, hashes) if hashes else {}

    scanned_at = datetime.now(timezone.utc).isoformat()
    malicious_count = 0
    for m in matches:
        if not isinstance(m, dict):
            continue
        h = (m.get("sha256") or "").strip().lower()
        verdict = verdicts.get(h) if h else None
        if verdict:
            # Backend-sourced verdict — annotate the match.
            m["vt_verdict"] = verdict.get("verdict")
            m["vt_detection_ratio"] = verdict.get("detectionRatio")
            malicious = verdict.get("malicious") or 0
        else:
            # Agent-sourced verdict (Option B) already on the match, or no hash.
            verdict = {"verdict": m.get("vt_verdict"), "detectionRatio": m.get("vt_detection_ratio")}
            malicious = m.get("vt_malicious") or 0
        if h and malicious > 0:
            malicious_count += 1
            await _raise_malware_alert(
                db, tenant_id, agent_id, m.get("target", ""), h, verdict, scanned_at,
                rule=m.get("rule", "YARA hit"),
            )

    doc = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": scanned_at,
        "threats_found": bool(body.get("threats_found")),
        "match_count": len(matches),
        "malicious_count": malicious_count,
        "rules_applied": body.get("rules_applied", 0),
        "matches": matches,
        "scan_paths": body.get("scan_paths", []),
    }
    await db.agent_malware_scans.insert_one(doc)
    return {"success": True, "scan_id": doc["id"], "match_count": len(matches), "malicious_count": malicious_count}


@router.get("/{agent_id}/malware-scans")
async def get_malware_scans(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent malware scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    scans = await db.agent_malware_scans.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return scans


@router.post("/{agent_id}/persistence-findings")
async def post_persistence_findings(
    agent_id: str,
    body: Dict[str, Any] = Body(...),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
):
    """Agent posts persistence mechanism findings (registry, cron, startup entries)."""
    db = get_database()
    tenant_id = _tenant.get("id") or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")

    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    doc = {
        "agent_id": agent_id,
        "tenantId": tenant_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": body.get("total_entries", 0),
        "suspicious_entries": body.get("suspicious_entries", []),
        "critical_count": body.get("critical_count", 0),
        "high_count": body.get("high_count", 0),
        "platform": body.get("platform", "unknown"),
    }

    await db.agent_persistence_findings.insert_one(doc)
    doc.pop("_id", None)

    for entry in body.get("suspicious_entries", [])[:_MAX_ARRAY]:
        if entry.get("severity") in ("Critical", "High"):
            await db.security_alerts.insert_one({
                "tenantId": tenant_id,
                "agent_id": agent_id,
                "type": "persistence_mechanism",
                "severity": entry.get("severity", "High").lower(),
                "title": f"Suspicious persistence: {entry.get('name', 'unknown')}",
                "description": entry.get("command", entry.get("path", "")),
                "location": entry.get("location", ""),
                "risk_score": entry.get("risk_score", 0),
                "created_at": doc["scanned_at"],
                "status": "open",
            })

    return {"success": True, "critical_count": doc["critical_count"], "high_count": doc["high_count"]}


@router.get("/{agent_id}/persistence-findings")
async def get_persistence_findings(
    agent_id: str,
    limit: int = Query(10, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    """Retrieve recent persistence scan history for an agent."""
    db = get_database()
    query: Dict[str, Any] = {"agent_id": agent_id}
    user_role = getattr(current_user, "role", "user")
    if user_role not in ["Super Admin", "super_admin", "admin", "platform-admin"]:
        query["tenantId"] = getattr(current_user, "tenant_id", None)
    findings = await db.agent_persistence_findings.find(query, {"_id": 0}).sort("scanned_at", -1).to_list(length=limit)
    return findings
