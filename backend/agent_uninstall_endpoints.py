"""
Uninstall protection for endpoint agents.

Each agent gets a platform-issued uninstall code. The platform keeps the code
encrypted and shows it only to people with manage:agents (every reveal is
audited). The agent receives just a salted PBKDF2 hash with its heartbeat
response, so its uninstallers can check a typed code locally, even offline,
without the code itself ever being stored on the endpoint.

After an uninstall the agent reports it here: the platform marks the agent
Uninstalled, raises an alert and rotates the code, so each code works once.

A local administrator can still stop or delete the service by hand; that shows
up as the agent going Offline (app_background_tasks.monitor_agent_status).
"""
import audit_ledger
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from authentication_service import get_current_user_or_agent
from catalogue_mounts_agents import AGENTS_GUARD
from database import get_database
import licensing
from rbac_utils import require_permission

router = APIRouter(prefix="/api/agents", tags=["Agents"])

# 12 characters from an alphabet without look-alikes (0/O, 1/I/L): ~59 bits.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LEN = 12
PBKDF2_ITERATIONS = 200_000


def normalize_code(code: str) -> str:
    """Codes are shown as XXXX-XXXX-XXXX; accept any case, spaces or dashes."""
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def hash_code(code: str, salt_hex: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", normalize_code(code).encode(), bytes.fromhex(salt_hex), iterations
    ).hex()


def _new_protection(version: int, created_by: str) -> Dict[str, Any]:
    from encryption_service import get_encryption_service

    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LEN))
    code = "-".join(raw[i:i + 4] for i in range(0, _CODE_LEN, 4))
    salt = secrets.token_hex(16)
    return {
        "version": version,
        "salt": salt,
        "iterations": PBKDF2_ITERATIONS,
        "hash": hash_code(code, salt),
        "codeEncrypted": get_encryption_service().encrypt(code),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "createdBy": created_by,
    }


def public_part(protection: Dict[str, Any]) -> Dict[str, Any]:
    """What the endpoint may hold: enough to verify a code, not to recover it."""
    return {k: protection[k] for k in ("version", "salt", "iterations", "hash")}


async def _ensure(db, agent: Dict[str, Any], created_by: str = "system") -> Dict[str, Any]:
    protection = agent.get("uninstallProtection")
    if not protection:
        protection = _new_protection(1, created_by)
        await db.agents.update_one({"id": agent["id"]}, {"$set": {"uninstallProtection": protection}})
    return protection


async def heartbeat_uninstall_protection(db, agent_filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Called on every heartbeat: issue the agent's code on first contact and
    hand back the verification data, so rotations reach the endpoint."""
    agent = await db.agents.find_one(agent_filter, {"_id": 0, "id": 1, "uninstallProtection": 1})
    if not agent:
        return None
    return public_part(await _ensure(db, agent))


async def _audit(db, action: str, agent: Dict[str, Any], user: Any, **extra) -> None:
    await audit_ledger.record_legacy(db, {
        "action": action,
        "agent_id": agent.get("id"),
        "hostname": agent.get("hostname"),
        "performed_by": getattr(user, "username", str(user)),
        "tenant_id": agent.get("tenantId"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    })


async def _agent_or_404(db, agent_id: str) -> Dict[str, Any]:
    agent = await db.agents.find_one({"id": agent_id}, {"_id": 0})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _reveal(agent: Dict[str, Any], protection: Dict[str, Any]) -> Dict[str, Any]:
    from encryption_service import get_encryption_service
    return {
        "agentId": agent["id"],
        "hostname": agent.get("hostname"),
        "code": get_encryption_service().decrypt(protection["codeEncrypted"]),
        "version": protection["version"],
        "createdAt": protection["createdAt"],
        "singleUse": True,
    }


@router.get("/{agent_id}/uninstall-code", dependencies=[Depends(AGENTS_GUARD)])
async def reveal_uninstall_code(agent_id: str, current_user=Depends(require_permission("manage:agents"))):
    """Show the code an administrator types into the agent's uninstaller."""
    db = get_database()
    agent = await _agent_or_404(db, agent_id)
    protection = await _ensure(db, agent, getattr(current_user, "username", "unknown"))
    await _audit(db, "REVEAL_UNINSTALL_CODE", agent, current_user, version=protection["version"])
    return _reveal(agent, protection)


@router.post("/{agent_id}/uninstall-code/rotate", dependencies=[Depends(AGENTS_GUARD)])
async def rotate_uninstall_code(agent_id: str, current_user=Depends(require_permission("manage:agents"))):
    """Replace the code (e.g. after it was shared); the agent picks up the new
    one with its next heartbeat."""
    db = get_database()
    agent = await _agent_or_404(db, agent_id)
    old_version = (agent.get("uninstallProtection") or {}).get("version", 0)
    protection = _new_protection(old_version + 1, getattr(current_user, "username", "unknown"))
    await db.agents.update_one({"id": agent_id}, {"$set": {"uninstallProtection": protection}})
    await _audit(db, "ROTATE_UNINSTALL_CODE", agent, current_user, version=protection["version"])
    return _reveal(agent, protection)


@router.post("/{agent_id}/uninstall-report")
async def report_uninstall(
    agent_id: str,
    body: Dict[str, Any] = Body(default={}),
    current_user=Depends(get_current_user_or_agent),
):
    """The agent's uninstaller reports that it is removing the agent. A valid
    code marks the removal authorized; anything else is reported as tampering."""
    if getattr(current_user, "role", "") != "agent" or getattr(current_user, "username", None) != agent_id:
        raise HTTPException(status_code=403, detail="Only the agent itself can report its uninstall")
    db = get_database()
    agent = await _agent_or_404(db, agent_id)
    protection = agent.get("uninstallProtection")
    code = body.get("code") or ""
    authorized = bool(
        protection and code
        and hmac.compare_digest(hash_code(code, protection["salt"], protection["iterations"]), protection["hash"])
    )
    now = datetime.now(timezone.utc).isoformat()
    update: Dict[str, Any] = {
        "status": "Uninstalled",
        "uninstalledAt": now,
        "uninstallAuthorized": authorized,
        "uninstallMethod": str(body.get("method") or "unknown")[:64],
    }
    if authorized:  # single use: the next install or a failed uninstall needs a fresh code
        update["uninstallProtection"] = _new_protection(protection["version"] + 1, "system")
    await db.agents.update_one({"id": agent_id}, {"$set": update})
    if agent.get("status") not in licensing.NON_SEAT_STATUSES:
        await licensing.release_seats(db, agent["tenantId"])  # an uninstalled agent holds no seat
    await _audit(db, "AGENT_UNINSTALLED", agent, current_user, authorized=authorized, method=update["uninstallMethod"])

    from ueba_service import persist_security_alert
    host = agent.get("hostname") or agent_id
    await persist_security_alert(
        db,
        alert_type="agent_uninstalled" if authorized else "agent_tamper",
        severity="low" if authorized else "high",
        title=f"Agent uninstalled on {host}" if authorized else f"Agent removed without a valid uninstall code on {host}",
        description=("The agent was removed with an administrator-issued uninstall code."
                     if authorized else
                     "The agent reported its removal without a valid uninstall code."),
        metadata={"agent_id": agent_id, "hostname": host, "tenantId": agent.get("tenantId"),
                  "authorized": authorized, "method": update["uninstallMethod"]},
    )
    return {"success": True, "authorized": authorized}
