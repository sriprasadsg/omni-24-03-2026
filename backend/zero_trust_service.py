from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from database import get_database
from rbac_utils import require_permission
from auth_types import TokenData
import logging


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Zero Trust & Quantum Security"])

_ZT_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

def _resolve_tenant(user: TokenData) -> Optional[str]:
    role = getattr(user, "role", "")
    if role in _ZT_SUPER_ROLES:
        return None
    return getattr(user, "tenant_id", None)

# --- Models ---
class DeviceTrustFactors(BaseModel):
    osPatched: bool
    antivirusActive: bool
    diskEncrypted: bool
    compliantLocation: bool

class DeviceTrustScore(BaseModel):
    deviceId: str
    score: int
    factors: DeviceTrustFactors
    lastUpdated: Optional[str] = None

class SessionRiskFactors(BaseModel):
    unusualLocation: bool
    unusualTime: bool
    newDevice: bool
    suspiciousActivity: bool

class UserSessionRisk(BaseModel):
    sessionId: str
    userId: str
    authLevel: str
    riskScore: int
    factors: SessionRiskFactors
    timestamp: Optional[str] = None

class CryptographicInventory(BaseModel):
    id: str
    algorithm: str
    usage: str
    quantumVulnerable: bool
    migrationPriority: str  # Critical, High, Medium, Low
    replacementAlgorithm: str


# --- Helper Functions ---
async def ensure_collections_exist(db):
    """Ensure MongoDB collections exist and have initial data"""
    collections = await db.list_collection_names()
    
    # Initialize device_trust_scores collection (kept for backward compatibility)
    # Note: This collection is no longer used as we fetch live data from agents collection
    if "device_trust_scores" not in collections:
        await db.create_collection("device_trust_scores")
        await db.device_trust_scores.create_index("deviceId", unique=True)
    
    
    # Initialize user_sessions collection (will be populated with real user sessions)
    if "user_sessions" not in collections:
        await db.create_collection("user_sessions")
        await db.user_sessions.create_index("sessionId", unique=True)
    
    # Initialize crypto_inventory
    if "crypto_inventory" not in collections:
        await db.create_collection("crypto_inventory")
        await db.crypto_inventory.create_index("id", unique=True)

    initial_crypto = [
        {
            "id": "c1",
            "algorithm": "RSA-2048",
            "usage": "TLS Certificates",
            "quantumVulnerable": True,
            "migrationPriority": "Critical",
            "replacementAlgorithm": "Falcon-1024"
        },
        {
            "id": "c2",
            "algorithm": "ECDSA P-256",
            "usage": "JWT Signing",
            "quantumVulnerable": True,
            "migrationPriority": "High",
            "replacementAlgorithm": "Dilithium3"
        },
        {
            "id": "c3",
            "algorithm": "AES-256",
            "usage": "Data at Rest",
            "quantumVulnerable": False,
            "migrationPriority": "Low",
            "replacementAlgorithm": "N/A (Safe)"
        },
        {
            "id": "c4",
            "algorithm": "SHA-256",
            "usage": "Hashing",
            "quantumVulnerable": False,
            "migrationPriority": "Low",
            "replacementAlgorithm": "N/A (Safe)"
        },
        {
            "id": "c5",
            "algorithm": "Diffie-Hellman",
            "usage": "Key Exchange",
            "quantumVulnerable": True,
            "migrationPriority": "High",
            "replacementAlgorithm": "Kyber-768"
        }
    ]
    for item in initial_crypto:
        await db.crypto_inventory.update_one(
            {"id": item["id"]},
            {"$setOnInsert": item},
            upsert=True
        )


# --- Zero Trust Endpoints ---
@router.get("/zero-trust/device-trust-scores", response_model=List[DeviceTrustScore])
async def get_device_trust_scores(current_user: TokenData = Depends(require_permission("view:security"))):
    """Returns trust scores for fleet devices based on Zero Trust policies using real agents from MongoDB."""
    db = get_database()
    await ensure_collections_exist(db)
    tenant_id = _resolve_tenant(current_user)
    agent_filter = {} if tenant_id is None else {"tenantId": tenant_id}
    # Fetch real agents from the agents collection
    agents = await db.agents.find(agent_filter, {"_id": 0}).to_list(length=100)
    
    # Transform agents to device trust scores
    device_scores = []
    for agent in agents:
        # Determine trust factors based on agent properties
        is_online = agent.get("status") == "Online"
        last_seen = agent.get("lastSeen")
        
        # Calculate if OS is patched (agent is online and recently seen)
        os_patched = is_online
        if last_seen:
            try:
                from datetime import datetime, timezone, timedelta
                last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                time_since_seen = datetime.now(timezone.utc) - last_seen_dt
                # Consider patched if seen within last 24 hours
                os_patched = time_since_seen < timedelta(hours=24)
            except (ValueError, AttributeError):
                os_patched = is_online
        
        # Antivirus active: check agent-reported antivirus status, fall back to online status
        antivirus_active = agent.get("antivirus_active", agent.get("antivirusActive", is_online))

        # Disk encrypted: use agent-reported value if present, else unknown → penalise
        raw_enc = agent.get("disk_encrypted", agent.get("diskEncrypted", None))
        disk_encrypted = bool(raw_enc) if raw_enc is not None else False

        # Compliant location: flag agents on non-RFC1918 (public) IPs as non-compliant
        # unless explicitly approved via allowlisted_public_ip flag
        ip = agent.get("ipAddress", agent.get("ip_address", ""))
        def _is_private(ip_str: str) -> bool:
            try:
                import ipaddress
                return ipaddress.ip_address(ip_str).is_private
            except Exception:
                return True  # unknown → assume private (benefit of doubt)
        compliant_location = (
            _is_private(ip)
            or agent.get("allowlisted_public_ip", False)
            or not ip
        )
        
        # Calculate trust score
        score = 100
        if not os_patched:
            score -= 30
        if not antivirus_active:
            score -= 20
        if not disk_encrypted:
            score -= 20
        if not compliant_location:
            score -= 30
        
        device_scores.append({
            "deviceId": agent.get("hostname", agent.get("id", "Unknown")),
            "score": max(0, score),
            "factors": {
                "osPatched": os_patched,
                "antivirusActive": antivirus_active,
                "diskEncrypted": disk_encrypted,
                "compliantLocation": compliant_location
            },
            "lastUpdated": agent.get("lastSeen", datetime.now(timezone.utc).isoformat())
        })
    
    return device_scores


@router.get("/zero-trust/session-risks")
async def get_session_risks(current_user: TokenData = Depends(require_permission("view:security"))):
    """Returns real-time risk scoring for active user sessions from MongoDB."""
    db = get_database()
    await ensure_collections_exist(db)
    tenant_id = _resolve_tenant(current_user)
    session_filter = {} if tenant_id is None else {"tenantId": tenant_id}
    sessions = await db.user_sessions.find(session_filter, {"_id": 0}).to_list(length=100)
    return sessions

# --- Quantum Security Endpoints ---
@router.get("/quantum-security/cryptographic-inventory")
async def get_crypto_inventory(current_user: TokenData = Depends(require_permission("view:security"))):
    """
    Returns an inventory of cryptographic algorithms used in the environment from MongoDB,
    flagging those vulnerable to Post-Quantum Cryptography (PQC) attacks.
    """
    db = get_database()
    await ensure_collections_exist(db)
    tenant_id = _resolve_tenant(current_user)
    crypto_filter = {} if tenant_id is None else {"tenantId": tenant_id}
    inventory = await db.crypto_inventory.find(crypto_filter, {"_id": 0}).to_list(length=100)
    return inventory


class ZeroTrustVerifyRequest(BaseModel):
    user_id: str
    resource: str
    action: str
    context: Optional[Dict[str, Any]] = None


@router.post("/zero-trust/verify")
async def verify_zero_trust_access(
    req: ZeroTrustVerifyRequest,
    current_user: TokenData = Depends(require_permission("view:security")),
):
    """
    Evaluate a Zero Trust access decision for a given user, resource, and action.
    Checks: user existence + role, device trust score, explicit deny policies.
    Returns allow/deny with reasons for auditability.
    """
    db = get_database()
    tenant_id = _resolve_tenant(current_user)
    reasons: list[str] = []
    risk_score = 0

    # 1. Verify user exists in this tenant
    user_filter: Dict[str, Any] = {"$or": [{"id": req.user_id}, {"email": req.user_id}]}
    if tenant_id:
        user_filter["tenantId"] = tenant_id
    user_doc = await db.users.find_one(user_filter)
    if not user_doc:
        return {
            "decision": "deny",
            "user_id": req.user_id,
            "resource": req.resource,
            "action": req.action,
            "reasons": ["User not found in tenant"],
            "risk_score": 100,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    # 2. Check for explicit deny policies in the database
    policy_filter: Dict[str, Any] = {
        "resource": {"$regex": req.resource.replace("*", ".*"), "$options": "i"},
        "action": {"$in": [req.action, "*"]},
        "effect": "deny",
    }
    if tenant_id:
        policy_filter["$or"] = [{"tenantId": tenant_id}, {"tenantId": None}]
    deny_policy = await db.zero_trust_policies.find_one(policy_filter)
    if deny_policy:
        reasons.append(f"Explicit deny policy: {deny_policy.get('name', 'unnamed policy')}")
        risk_score += 50

    # 3. Check device trust score for the agent on this user's machine
    agent_filter: Dict[str, Any] = {"assignedUser": req.user_id}
    if tenant_id:
        agent_filter["tenantId"] = tenant_id
    agent = await db.agents.find_one(agent_filter)
    device_trust_score = 100
    if agent:
        device_trust_score = agent.get("deviceTrustScore", 80)
        if device_trust_score < 60:
            reasons.append(f"Device trust score too low ({device_trust_score}/100)")
            risk_score += 30
        elif device_trust_score < 80:
            reasons.append(f"Device trust score below optimal ({device_trust_score}/100)")
            risk_score += 10

    # 4. Check user role permissions
    role_name = user_doc.get("role", "Viewer")
    role_doc = await db.roles.find_one({"name": role_name})
    if role_doc:
        permissions = role_doc.get("permissions", [])
        action_perm = f"{req.action}:{req.resource.split('/')[0]}"
        if "all" not in permissions and action_perm not in permissions:
            has_write = any(p.startswith("manage:") for p in permissions)
            if req.action in ("delete", "write", "modify") and not has_write:
                reasons.append(f"Role '{role_name}' lacks permission for action '{req.action}' on '{req.resource}'")
                risk_score += 40

    # 5. Final decision
    decision = "deny" if (deny_policy or risk_score >= 60) else "allow"
    if not reasons and decision == "allow":
        reasons.append("Access granted — identity verified, device trusted, no deny policies matched")

    # Audit log the decision
    try:
        await db.zero_trust_audit.insert_one({
            "user_id": req.user_id,
            "resource": req.resource,
            "action": req.action,
            "decision": decision,
            "risk_score": risk_score,
            "reasons": reasons,
            "evaluated_by": getattr(current_user, "username", "system"),
            "tenant_id": tenant_id,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    return {
        "decision": decision,
        "user_id": req.user_id,
        "resource": req.resource,
        "action": req.action,
        "reasons": reasons,
        "risk_score": risk_score,
        "device_trust_score": device_trust_score,
        "user_role": user_doc.get("role"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
