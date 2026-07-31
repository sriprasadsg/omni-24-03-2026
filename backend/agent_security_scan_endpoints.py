"""
Agent Security Scan Ingestion — Phase 50 (NSCAN-03)

POST /api/agents/{agent_id}/security/scan-result — the agent reports a native
scan verdict (file/url/ip/hash). We persist it (security_scan_results,
tenant-scoped) and, on a Malicious verdict, raise a critical security alert via
the existing alert collection — cloning agent_security_endpoints._raise_malware_alert
but tagged source="native" (NOT virustotal). Agent-authenticated via
verify_agent_key; the tenant comes from the verified key.

Leaves the existing VirusTotal fim-events path in agent_security_endpoints
untouched.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends

from agent_auth import verify_agent_key
from database import get_database

logger = logging.getLogger("agent_security_scan_endpoints")
router = APIRouter(prefix="/api/agents", tags=["Agent Security Scan"])


def _tenant_of(agent_ctx: Dict[str, Any]) -> str:
    return agent_ctx.get("id") or agent_ctx.get("tenant_id") or agent_ctx.get("tenantId")


@router.post("/{agent_id}/security/scan-result")
async def ingest_scan_result(
    agent_id: str,
    result: Dict[str, Any] = Body(...),
    agent_ctx=Depends(verify_agent_key),
):
    """Ingest a native scan verdict; raise a native alert on Malicious."""
    db = get_database()
    tenant_id = _tenant_of(agent_ctx)
    now = datetime.now(timezone.utc).isoformat()

    verdict = result.get("verdict")
    sha256 = result.get("sha256")
    target = result.get("target")

    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "agentId": agent_id,
        "type": result.get("type"),
        "target": target,
        "verdict": verdict,
        "confidence": result.get("confidence"),
        "sha256": sha256,
        "matched": result.get("matched"),
        "source": "native",
        "created_at": now,
    }
    await db.security_scan_results.insert_one(doc)

    alerted = False
    if verdict == "Malicious":
        await db.security_alerts.insert_one({
            "id": str(uuid.uuid4()),
            "tenantId": tenant_id,
            "agent_id": agent_id,
            "type": "malware_detected",
            "severity": "critical",
            "source": "native",
            "title": f"Native scan flagged {result.get('type', 'file')} on agent {agent_id}",
            "description": f"'{target}' (SHA256 {sha256}) — Malicious "
                           f"(confidence {result.get('confidence')}, matched {result.get('matched')})",
            "sha256": sha256,
            "created_at": now,
            "status": "open",
        })
        alerted = True

    return {"status": "ok", "alerted": alerted}
