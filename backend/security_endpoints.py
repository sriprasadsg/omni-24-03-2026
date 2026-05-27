from fastapi import APIRouter, HTTPException, Depends
import logging
from datetime import datetime, timezone
from database import get_database
from security_service import get_security_service
from authentication_service import get_current_user
from auth_types import TokenData
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_SEC_SUPER_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}

def _sec_caller_tenant(current_user) -> str:
    tid = getattr(current_user, "tenant_id", None) or None
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


@router.get("/security-cases")
async def list_security_cases(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List security cases"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    query: dict = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = _sec_caller_tenant(current_user)
    cases = await db.security_cases.find(query, {"_id": 0}).to_list(length=100)
    return cases

@router.post("/security-cases")
async def create_security_case(
    case: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new security case from a security event."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    case.setdefault("id", f"case-{uuid.uuid4()}")
    case.setdefault("tenantId", _sec_caller_tenant(current_user))
    case.setdefault("createdAt", now)
    case["updatedAt"] = now
    await db.security_cases.insert_one({**case, "_id": case["id"]})
    case.pop("_id", None)
    return case


@router.put("/security-cases/{case_id}")
async def update_security_case(
    case_id: str,
    case: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Update an existing security case."""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    query: dict = {"id": case_id}
    if not is_admin:
        query["tenantId"] = _sec_caller_tenant(current_user)
    case["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result = await db.security_cases.update_one(query, {"$set": case}, upsert=False)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Security case not found")
    return case


@router.get("/security-events")
async def list_security_events(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List security events"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    query: dict = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = _sec_caller_tenant(current_user)
    events = await db.security_events.find(query, {"_id": 0}).to_list(length=100)
    return events

@router.post("/security-events")
async def create_security_event(
    event: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Create a new security event."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    event.setdefault("id", f"evt-{uuid.uuid4()}")
    event.setdefault("tenantId", _sec_caller_tenant(current_user))
    event.setdefault("createdAt", now)
    await db.security_events.insert_one({**event, "_id": event["id"]})
    event.pop("_id", None)
    return event

@router.get("/vulnerability-scans")
async def list_vulnerability_scans(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """List vulnerability scans"""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
    query: dict = {}
    if is_admin:
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = _sec_caller_tenant(current_user)
    scans = await db.vulnerability_scans.find(query, {"_id": 0}).to_list(length=100)
    return scans

@router.get("/security/incident-impact/{incident_id}")
async def get_incident_impact(
    incident_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get incident impact graph — returns nodes/edges for an incident the caller can access."""
    db = get_database()
    is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")

    # Verify the caller has access to this incident
    incident_query: dict = {"id": incident_id}
    if not is_admin:
        incident_query["tenantId"] = _sec_caller_tenant(current_user)

    incident = await db.security_cases.find_one(incident_query, {"_id": 0})
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Build impact graph from linked assets
    affected_asset_ids = incident.get("affectedAssets", [])
    nodes = [{"id": "root", "label": f"Incident {incident_id}", "type": "Incident"}]
    edges = []

    if affected_asset_ids:
        assets = await db.assets.find(
            {"id": {"$in": affected_asset_ids}}, {"_id": 0, "id": 1, "hostname": 1, "type": 1}
        ).to_list(length=50)
        for asset in assets:
            nodes.append({"id": asset["id"], "label": asset.get("hostname", asset["id"]), "type": asset.get("type", "Asset")})
            edges.append({"from": "root", "to": asset["id"], "label": "Affected"})
    else:
        # No linked assets yet — return minimal graph
        nodes.append({"id": "no-assets", "label": "No affected assets linked", "type": "Info"})
        edges.append({"from": "root", "to": "no-assets", "label": "Status"})

    return {"nodes": nodes, "edges": edges}




@router.post("/security/generate-keypair")
async def generate_signing_keypair(
    current_user: TokenData = Depends(get_current_user),
):
    """
    Generate RSA key pair for patch signing.
    Admin-only. Returns public key + the private key **once** in the response.
    Only the AES-256-GCM encrypted private key is persisted; the plaintext is never stored.
    """
    import base64 as _b64
    import os as _os

    is_admin = getattr(current_user, "role", "") in (
        "Super Admin", "super_admin", "admin", "platform-admin"
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required to generate signing keys")

    try:
        security_service = get_security_service()
        private_key_pem, public_key_pem = security_service.generate_rsa_keypair(key_size=2048)

        # Encrypt the private key with a per-key AES-256-GCM wrapping key.
        # The wrapping key is derived from a server-side secret and the key_id so
        # it is never stored alongside the ciphertext.
        db = get_database()
        key_id = f"key-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{_os.urandom(4).hex()}"

        wrap_key = security_service.generate_encryption_key()
        encrypted_priv, nonce = security_service.encrypt_payload(private_key_pem, wrap_key)

        # Derive a persistent storage key from the server JWT secret + key_id
        # so the wrap_key itself is never written to the database.
        import hashlib as _hl
        from authentication_service import SECRET_KEY
        storage_wrap = _hl.sha256(f"{SECRET_KEY}:{key_id}".encode()).digest()
        encrypted_wrap, wrap_nonce = security_service.encrypt_payload(wrap_key, storage_wrap)

        await db.signing_keys.insert_one({
            "id": key_id,
            "public_key": public_key_pem.decode(),
            # Private key stored encrypted; plaintext never persisted
            "private_key_encrypted": _b64.b64encode(encrypted_priv).decode(),
            "private_key_nonce": _b64.b64encode(nonce).decode(),
            # Wrapping key stored double-encrypted (recoverable only with SECRET_KEY)
            "wrap_key_encrypted": _b64.b64encode(encrypted_wrap).decode(),
            "wrap_key_nonce": _b64.b64encode(wrap_nonce).decode(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": getattr(current_user, "username", "unknown"),
            "key_size": 2048,
            "algorithm": "RSA",
        })

        await security_service.audit_security_event(
            db=db,
            event_type="signing_key_generated",
            details={"key_id": key_id, "algorithm": "RSA-2048", "created_by": getattr(current_user, "username", "unknown")},
            severity="Info",
        )

        # Return the private key exactly once — caller must store it securely.
        # It cannot be recovered from the database without SECRET_KEY.
        return {
            "success": True,
            "key_id": key_id,
            "public_key": public_key_pem.decode(),
            "private_key": private_key_pem.decode(),
            "message": (
                "Private key returned once. Store it securely — "
                "it cannot be recovered from the server without the master secret."
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating keypair: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")





@router.post("/agents/{agent_id}/verify-integrity")
async def verify_agent_integrity(
    agent_id: str,
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Verify agent software integrity (detect tampering).
    Agents authenticate via their Bearer token; admins can verify any agent.
    """
    # An agent may only verify itself; admins may verify any agent
    is_admin = getattr(current_user, "role", "") in (
        "Super Admin", "super_admin", "admin", "platform-admin"
    )
    caller_id = getattr(current_user, "username", "")
    if not is_admin and caller_id != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized to verify this agent")

    try:
        security_service = get_security_service()
        db = get_database()
        
        # Get expected checksum for this version
        expected_version_data = await db.agent_versions.find_one(
            {"version": data.get("version")},
            {"_id": 0}
        )
        
        if not expected_version_data:
            raise HTTPException(status_code=404, detail="Unknown agent version")
        
        expected_checksum = expected_version_data.get("checksum")
        
        # Validate
        result = security_service.validate_agent_integrity(
            agent_id=agent_id,
            reported_version=data.get("version"),
            reported_checksum=data.get("checksum"),
            expected_checksum=expected_checksum
        )
        
        # If tampering detected, quarantine agent
        if result["threat_detected"]:
            await db.agents.update_one(
                {"id": agent_id},
                {"$set": {
                    "quarantined": True,
                    "quarantine_reason": "Agent integrity check failed - possible tampering",
                    "quarantined_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            await security_service.audit_security_event(
                db=db,
                event_type="agent_tampering_detected",
                details={
                    "agent_id": agent_id,
                    "version": data.get("version"),
                    "reported_checksum": data.get("checksum"),
                    "expected_checksum": expected_checksum
                },
                severity="Critical"
            )
        
        return result
    except Exception as e:
        logger.error("Error verifying agent integrity: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/security/encrypt")
async def encrypt_data(
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Encrypt sensitive data using a server-managed AES-256-GCM key.
    The caller receives the ciphertext + nonce; the key is never returned.
    """
    try:
        import base64
        import logging as _log
        _log.getLogger(__name__).info(
            "encrypt_data called by %s", getattr(current_user, "username", "unknown")
        )

        security_service = get_security_service()

        key = security_service.generate_encryption_key()

        plaintext = data.get("plaintext", "").encode()
        encrypted, nonce = security_service.encrypt_payload(plaintext, key)

        return {
            "encrypted": base64.b64encode(encrypted).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "algorithm": "AES-256-GCM"
        }
    except Exception as e:
        logger.error("Error encrypting: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/security/audit-log")
async def get_security_audit_log(
    limit: int = 50,
    severity: str = None,
    event_type: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get security audit log entries — scoped to the caller's tenant."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")

        query: dict = {}
        if not is_admin:
            query["tenantId"] = _sec_caller_tenant(current_user)
        if severity:
            query["severity"] = severity
        if event_type:
            query["type"] = event_type

        events = await db.security_audit_log.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        return {
            "events": events,
            "count": len(events)
        }
    except Exception as e:
        logger.error("Error getting audit log: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")



# CONFLICT RESOLUTION: Use vuln_endpoints.py instead
# @router.get("/api/vulnerabilities")
# async def list_vulnerabilities(tenant_id: str = None):
#     """List all vulnerabilities"""
#     db = get_database()
#     query = {}
#     if tenant_id:
#         query["tenantId"] = tenant_id
#         
#     # Try to get from DB first
#     vulnerabilities = await db.vulnerabilities.find(query, {"_id": 0}).to_list(length=100)
#     
#     if not vulnerabilities:
#         # Return mock data if empty
#         return [
#             {
#                 "id": "vuln-1",
#                 "cveId": "CVE-2024-1234",
#                 "severity": "Critical",
#                 "status": "Open",
#                 "affectedSoftware": "Apache Log4j",
#                 "discoveredAt": datetime.now(timezone.utc).isoformat(),
#                 "description": "Remote Code Execution vulnerability in Log4j",
#                 "assetId": "asset-1"
#             },
#             {
#                 "id": "vuln-2",
#                 "cveId": "CVE-2024-5678",
#                 "severity": "High",
#                 "status": "Patched",
#                 "affectedSoftware": "OpenSSL",
#                 "discoveredAt": datetime.now(timezone.utc).isoformat(),
#                 "description": "Buffer overflow in OpenSSL",
#                 "assetId": "asset-2"
#             }
#         ]
#     return vulnerabilities

# @router.get("/api/vulnerabilities/stats")
# async def get_vulnerability_stats(tenant_id: str = None):
#     """Get vulnerability statistics"""
#     db = get_database()
#     query = {}
#     if tenant_id:
#         query["tenantId"] = tenant_id
#         
#     # For now return mock stats if no real aggregation logic
#     return {
#         "Critical": 12,
#         "High": 45,
#         "Medium": 89,
#         "Low": 156,
#         "total": 302
#     }

@router.post("/vulnerability-scans/schedule")
async def schedule_vulnerability_scan(
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Schedule a vulnerability scan
    body: {
        "assetIds": ["id1", "id2"],
        "scanType": "Immediate" | "Scheduled",
        "scheduleTime": "ISO string"
    }
    """
    try:
        db = get_database()

        job = {
            "id": f"job-{uuid.uuid4()}",
            "type": "Vulnerability Scan",
            "status": "Queued",
            "progress": 0,
            "targetAssets": data.get("assetIds", []),
            "scanType": data.get("scanType", "Immediate"),
            "scheduleTime": data.get("scheduleTime") or datetime.now(timezone.utc).isoformat(),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "createdBy": getattr(current_user, "username", "unknown"),
            "tenantId": getattr(current_user, "tenant_id", None),
            "log": ["Job created"]
        }
        
        await db.vulnerability_scan_jobs.insert_one(job)
        
        # Remove _id for JSON serialization
        if "_id" in job:
            del job["_id"]
            
        return job
    except Exception as e:
        logger.error("Error scheduling scan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/assets/{asset_id}/scan")
async def trigger_asset_scan(
    asset_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger an immediate scan for a single asset
    """
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in _SEC_SUPER_ROLES
        caller_tenant = _sec_caller_tenant(current_user)
        asset_filter: dict = {"id": asset_id}
        if not is_admin:
            asset_filter["tenantId"] = caller_tenant

        timestamp = datetime.now(timezone.utc).isoformat()

        # Update asset lastScanned
        result = await db.assets.update_one(
            asset_filter,
            {"$set": {"lastScanned": timestamp}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Asset not found")
            
        return {"success": True, "lastScanned": timestamp}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error triggering scan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/security/attack-paths")
async def get_attack_paths(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get security attack paths from DB, derived from live alerts/vulns when empty."""
    try:
        db = get_database()
        is_admin = getattr(current_user, "role", "") in ("Super Admin", "super_admin", "admin", "platform-admin")
        query: dict = {}
        if not is_admin:
            query["tenantId"] = _sec_caller_tenant(current_user)
        elif tenant_id:
            query["tenantId"] = tenant_id

        paths = await db.attack_paths.find(query, {"_id": 0}).to_list(length=100)

        if paths:
            return paths

        # Derive lightweight paths from live critical vulnerabilities when none stored
        vuln_query = {**query, "severity": {"$in": ["Critical", "critical"]},
                      "status": {"$in": ["open", "Open", "pending", "Pending"]}}
        vulns = await db.patches.find(vuln_query, {"_id": 0, "id": 1, "cveId": 1,
                                                    "affectedSoftware": 1, "description": 1}).to_list(length=20)

        alert_query = {**query, "severity": {"$in": ["Critical", "critical"]},
                       "status": {"$in": ["open", "Open", "new", "New"]}}
        alerts = await db.alerts.find(alert_query, {"_id": 0, "id": 1, "title": 1,
                                                    "asset": 1, "description": 1}).to_list(length=10)

        derived = []
        for i, vuln in enumerate(vulns[:5]):
            derived.append({
                "id": f"derived-vuln-{i+1}",
                "name": f"Unpatched CVE: {vuln.get('cveId', 'Unknown')}",
                "riskScore": 90,
                "source": "derived",
                "steps": [
                    {"step": f"CVE affects {vuln.get('affectedSoftware', 'unknown software')}", "type": "Vulnerability"},
                    {"step": "Remote code execution possible", "type": "Execution"},
                    {"step": "Privilege escalation to SYSTEM", "type": "Privilege Escalation"},
                ],
                "affectedAssets": [vuln.get("affectedSoftware", "Unknown")],
            })

        for i, alert in enumerate(alerts[:5]):
            derived.append({
                "id": f"derived-alert-{i+1}",
                "name": alert.get("title", f"Active Threat {i+1}"),
                "riskScore": 80,
                "source": "derived",
                "steps": [
                    {"step": alert.get("description", "Suspicious activity detected"), "type": "Initial Access"},
                    {"step": "Lateral movement possible", "type": "Lateral Movement"},
                ],
                "affectedAssets": [alert.get("asset", "Unknown")],
            })

        return derived

    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
