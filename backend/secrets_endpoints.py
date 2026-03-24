"""
Secrets Management API Endpoints

Provides API for centralized secrets management, rotation, and auditing.
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from secrets_service import get_secrets_service, SecretType, SecretStatus
from rbac_utils import require_permission

router = APIRouter(prefix="/api/secrets", tags=["Secrets Management"])

def _get(user, key, default=None):
    if isinstance(user, dict): return user.get(key, default)
    return getattr(user, key, default)



# Request/Response Models
class CreateSecretRequest(BaseModel):
    name: str
    value: str
    secret_type: str
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    rotation_enabled: bool = True


class UpdateSecretRequest(BaseModel):
    name: str
    new_value: str


class RotateSecretRequest(BaseModel):
    name: str


class RevokeSecretRequest(BaseModel):
    name: str


# Endpoints

@router.post("/create")
async def create_secret(
    request: CreateSecretRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:secrets"))
):
    """
    Create a new secret
    
    Secret types:
    - api_key: API keys and tokens
    - database_password: Database credentials
    - encryption_key: Encryption keys
    - certificate: SSL/TLS certificates
    - ssh_key: SSH private keys
    - oauth_token: OAuth tokens
    - webhook_secret: Webhook secrets
    """
    secrets_service = get_secrets_service(db)
    tenant_id = current_user.get("tenantId")
    
    try:
        secret = await secrets_service.create_secret(
            name=request.name,
            value=request.value,
            secret_type=request.secret_type,
            tenant_id=tenant_id,
            description=request.description,
            metadata=request.metadata,
            rotation_enabled=request.rotation_enabled
        )
        
        return secret
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create secret: {str(e)}")


@router.get("/list")
async def list_secrets(
    status: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:secrets"))
):
    """
    List all secrets (without values)
    
    Filter by status: active, rotating, deprecated, revoked
    """
    secrets_service = get_secrets_service(db)
    tenant_id = _get(current_user, "tenantId")
    
    try:
        secrets = await secrets_service.list_secrets(
            tenant_id=tenant_id,
            status=status
        )
        return secrets
    except Exception as e:
        return []


@router.get("/{name}")
async def get_secret_metadata(
    name: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:secrets"))
):
    """
    Get secret metadata (without the actual value)
    """
    tenant_id = _get(current_user, "tenantId")
    
    secret = await db.secrets.find_one({
        "name": name,
        "tenant_id": tenant_id
    })
    
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    
    # Remove encrypted value
    secret.pop("encrypted_value", None)
    secret["id"] = str(secret.pop("_id"))
    
    return secret


@router.get("/{name}/value")
async def get_secret_value(
    name: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("read:secrets"))
):
    """
    Get secret value (decrypted)
    
    WARNING: This returns the actual secret value. Use with caution.
    All access is logged for audit purposes.
    """
    secrets_service = get_secrets_service(db)
    tenant_id = current_user.get("tenantId")
    user = current_user.get("email", "unknown")
    
    try:
        value = await secrets_service.get_secret(
            name=name,
            tenant_id=tenant_id,
            user=user
        )
        
        return {"name": name, "value": value}
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get secret: {str(e)}")


@router.put("/update")
async def update_secret(
    request: UpdateSecretRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:secrets"))
):
    """
    Update a secret value (creates a new version)
    
    Old versions are archived and can be retrieved if needed.
    """
    secrets_service = get_secrets_service(db)
    tenant_id = current_user.get("tenantId")
    user = current_user.get("email", "unknown")
    
    try:
        result = await secrets_service.update_secret(
            name=request.name,
            new_value=request.new_value,
            tenant_id=tenant_id,
            user=user
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update secret: {str(e)}")


@router.post("/rotate")
async def rotate_secret(
    request: RotateSecretRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:secrets"))
):
    """
    Rotate a secret (generate new value)
    
    For API keys and tokens, automatically generates a new random value.
    For passwords and other types, requires manual update.
    """
    secrets_service = get_secrets_service(db)
    tenant_id = _get(current_user, "tenantId")
    user = _get(current_user, "email", "unknown")
    
    try:
        result = await secrets_service.rotate_secret(
            name=request.name,
            tenant_id=tenant_id,
            user=user
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rotate secret: {str(e)}")


@router.post("/revoke")
async def revoke_secret(
    request: RevokeSecretRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:secrets"))
):
    """
    Revoke a secret (mark as revoked, cannot be used)
    
    Revoked secrets cannot be accessed or used.
    """
    secrets_service = get_secrets_service(db)
    tenant_id = current_user.get("tenantId")
    user = current_user.get("email", "unknown")
    
    try:
        result = await secrets_service.revoke_secret(
            name=request.name,
            tenant_id=tenant_id,
            user=user
        )
        
        return result
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke secret: {str(e)}")


@router.get("/rotation/check")
async def check_rotation_needed(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:secrets"))
):
    """
    Check which secrets need rotation
    
    Returns list of secrets that have passed their rotation date.
    """
    secrets_service = get_secrets_service(db)
    
    try:
        secrets_to_rotate = await secrets_service.check_rotation_needed()
        
        return {
            "count": len(secrets_to_rotate),
            "secrets": secrets_to_rotate
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check rotation: {str(e)}")


@router.post("/scan")
async def scan_code_for_secrets(
    file: UploadFile = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:secrets"))
):
    """
    Scan code file for hardcoded secrets
    
    Detects:
    - API keys
    - Passwords
    - Tokens
    - Private keys
    - AWS keys
    """
    secrets_service = get_secrets_service(db)
    
    try:
        # Read file content
        content = await file.read()
        code = content.decode('utf-8')
        
        # Scan for secrets
        findings = await secrets_service.scan_for_hardcoded_secrets(
            code=code,
            file_path=file.filename
        )
        
        return {
            "file": file.filename,
            "findings_count": len(findings),
            "findings": findings
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to scan file: {str(e)}")


@router.get("/audit-log")
async def get_audit_log(
    secret_name: Optional[str] = None,
    limit: int = 100,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:secrets"))
):
    """
    Get secret access audit log
    
    Shows all access, updates, rotations, and revocations.
    """
    secrets_service = get_secrets_service(db)
    tenant_id = current_user.get("tenantId")
    
    try:
        logs = await secrets_service.get_secret_access_log(
            secret_name=secret_name,
            tenant_id=tenant_id,
            limit=limit
        )
        
        return logs
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audit log: {str(e)}")


@router.get("/stats")
async def get_secrets_stats(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:secrets"))
):
    """
    Get secrets management statistics
    """
    tenant_id = current_user.get("tenantId")
    
    # Count secrets by status
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }
        }
    ]
    
    cursor = db.secrets.aggregate(pipeline)
    status_counts = {}
    
    async for result in cursor:
        status_counts[result["_id"]] = result["count"]
    
    # Count secrets by type
    pipeline = [
        {"$match": {"tenant_id": tenant_id, "status": SecretStatus.ACTIVE}},
        {
            "$group": {
                "_id": "$secret_type",
                "count": {"$sum": 1}
            }
        }
    ]
    
    cursor = db.secrets.aggregate(pipeline)
    type_counts = {}
    
    async for result in cursor:
        type_counts[result["_id"]] = result["count"]
    
    # Check rotation needed
    secrets_service = get_secrets_service(db)
    rotation_needed = await secrets_service.check_rotation_needed()
    
    return {
        "total_secrets": sum(status_counts.values()),
        "by_status": status_counts,
        "by_type": type_counts,
        "rotation_needed": len(rotation_needed)
    }
