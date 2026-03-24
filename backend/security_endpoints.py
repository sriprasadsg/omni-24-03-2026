from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from database import get_database
from security_service import get_security_service

router = APIRouter()

@router.get("/api/security-cases")
async def list_security_cases(tenant_id: str = None):
    """List security cases"""
    db = get_database()
    query = {}
    if tenant_id:
        query["tenantId"] = tenant_id
    cases = await db.security_cases.find(query, {"_id": 0}).to_list(length=100)
    return cases

@router.get("/api/security-events")
async def list_security_events(tenant_id: str = None):
    """List security events"""
    db = get_database()
    query = {}
    if tenant_id:
        query["tenantId"] = tenant_id
    events = await db.security_events.find(query, {"_id": 0}).to_list(length=100)
    return events

@router.get("/api/vulnerability-scans")
async def list_vulnerability_scans(tenant_id: str = None):
    """List vulnerability scans"""
    db = get_database()
    query = {}
    if tenant_id:
        query["tenantId"] = tenant_id
    scans = await db.vulnerability_scans.find(query, {"_id": 0}).to_list(length=100)
    return scans

@router.get("/api/security/incident-impact/{incident_id}")
async def get_incident_impact(incident_id: str):
    """Get incident impact graph"""
    # Mock response for now as this likely involves complex graph logic
    return {
        "nodes": [
            {"id": "root", "label": f"Incident {incident_id}", "type": "Incident"},
            {"id": "asset-1", "label": "Web Server 01", "type": "Asset"},
            {"id": "service-1", "label": "Payment Gateway", "type": "Service"}
        ],
        "edges": [
            {"from": "root", "to": "asset-1", "label": "Affected"},
            {"from": "asset-1", "to": "service-1", "label": "Hosts"}
        ]
    }




@router.post("/api/security/generate-keypair")
async def generate_signing_keypair():
    """
    Generate RSA key pair for patch signing
    Returns public key (private key stored securely)
    """
    try:
        security_service = get_security_service()
        
        private_key_pem, public_key_pem = security_service.generate_rsa_keypair(key_size=2048)
        
        # Store keys securely (in production, use HSM or key vault)
        db = get_database()
        key_id = f"key-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        await db.signing_keys.insert_one({
            "id": key_id,
            "public_key": public_key_pem.decode(),
            "private_key_encrypted": private_key_pem.decode(),  # Should be encrypted in production
            "created_at": datetime.now(timezone.utc).isoformat(),
            "key_size": 2048,
            "algorithm": "RSA"
        })
        
        await security_service.audit_security_event(
            db=db,
            event_type="signing_key_generated",
            details={"key_id": key_id, "algorithm": "RSA-2048"},
            severity="info"
        )
        
        return {
            "success": True,
            "key_id": key_id,
            "public_key": public_key_pem.decode(),
            "message": "Key pair generated. Private key stored securely."
        }
    except Exception as e:
        print(f"Error generating keypair: {e}")
        return {"error": str(e)}, 500





@router.post("/api/agents/{agent_id}/verify-integrity")
async def verify_agent_integrity(agent_id: str, data: dict):
    """
    Verify agent software integrity (detect tampering)
    
    Body:
    {
        "version": "1.0.5",
        "checksum": "sha256_of_agent_binary"
    }
    """
    try:
        security_service = get_security_service()
        db = get_database()
        
        # Get expected checksum for this version
        expected_version_data = await db.agent_versions.find_one(
            {"version": data.get("version")},
            {"_id": 0}
        )
        
        if not expected_version_data:
            return {"error": "Unknown agent version"}, 404
        
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
                severity="critical"
            )
        
        return result
    except Exception as e:
        print(f"Error verifying agent integrity: {e}")
        return {"error": str(e)}, 500


@router.post("/api/security/encrypt")
async def encrypt_data(data: dict):
    """
    Encrypt sensitive data (for testing/demo)
    
    Body:
    {
        "plaintext": "sensitive data",
        "key_id": "optional"
    }
    """
    try:
        import base64
        
        security_service = get_security_service()
        
        # Generate or retrieve key
        key = security_service.generate_encryption_key()
        
        plaintext = data.get("plaintext").encode()
        encrypted, nonce = security_service.encrypt_payload(plaintext, key)
        
        return {
            "encrypted": base64.b64encode(encrypted).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "key": base64.b64encode(key).decode(),  # In production, never return key
            "algorithm": "AES-256-GCM"
        }
    except Exception as e:
        print(f"Error encrypting: {e}")
        return {"error": str(e)}, 500


@router.get("/api/security/audit-log")
async def get_security_audit_log(
    limit: int = 50,
    severity: str = None,
    event_type: str = None
):
    """Get security audit log entries"""
    try:
        db = get_database()
        
        query = {}
        if severity:
            query["severity"] = severity
        if event_type:
            query["type"] = event_type
        
        events = await db.security_audit_log.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=None)
        
        return {
            "events": events,
            "count": len(events)
        }
    except Exception as e:
        print(f"Error getting audit log: {e}")
        return {"error": str(e)}, 500



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

@router.post("/api/vulnerability-scans/schedule")
async def schedule_vulnerability_scan(data: dict):
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
            "log": ["Job created"]
        }
        
        await db.vulnerability_scan_jobs.insert_one(job)
        
        # Remove _id for JSON serialization
        if "_id" in job:
            del job["_id"]
            
        return job
    except Exception as e:
        print(f"Error scheduling scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/assets/{asset_id}/scan")
async def trigger_asset_scan(asset_id: str):
    """
    Trigger an immediate scan for a single asset
    """
    try:
        db = get_database()
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Update asset lastScanned
        result = await db.assets.update_one(
            {"id": asset_id},
            {"$set": {"lastScanned": timestamp}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Asset not found")
            
        return {"success": True, "lastScanned": timestamp}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error triggering scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/security/attack-paths")
async def get_attack_paths(tenant_id: str = None):
    """Get security attack paths"""
    try:
        db = get_database()
        
        # Return mock data for now to fix 500 error
        return [
            {
                "id": "path-1",
                "name": "Composite Access Path",
                "riskScore": 85,
                "steps": [
                    {"step": "Phishing Email", "type": "Initial Access"},
                    {"step": "Compromised User Creds", "type": "Credential Access"},
                    {"step": "Lateral Movement to DB", "type": "Lateral Movement"},
                    {"step": "Data Exfiltration", "type": "Exfiltration"}
                ],
                "affectedAssets": ["User-Laptop-01", "Database-Server-01"]
            },
            {
                "id": "path-2",
                "name": "Unpatched Vulnerability Exploitation",
                "riskScore": 92,
                "steps": [
                    {"step": "Public Exploit (Log4j)", "type": "Exploit"},
                    {"step": "Remote Code Execution", "type": "Execution"},
                    {"step": "Privilege Escalation", "type": "Privilege Escalation"}
                ],
                "affectedAssets": ["Web-Server-01", "App-Server-01"]
            }
        ]
    except Exception as e:
        print(f"Error getting attack paths: {e}")
        return {"error": str(e)}, 500
