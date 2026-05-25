from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from auth_types import TokenData
from datetime import datetime, timezone

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
            except:
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
