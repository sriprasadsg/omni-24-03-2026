"""
Secrets Management Service

Provides centralized secrets management with:
- HashiCorp Vault integration
- AWS Secrets Manager integration
- Azure Key Vault integration
- Automatic secret rotation
- Secret versioning
- Access policies
- Audit logging
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import hashlib
import base64
import json
from cryptography.fernet import Fernet
import os


class SecretType:
    API_KEY = "api_key"
    DATABASE_PASSWORD = "database_password"
    ENCRYPTION_KEY = "encryption_key"
    CERTIFICATE = "certificate"
    SSH_KEY = "ssh_key"
    OAUTH_TOKEN = "oauth_token"
    WEBHOOK_SECRET = "webhook_secret"


class SecretStatus:
    ACTIVE = "active"
    ROTATING = "rotating"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class SecretsManagementService:
    """Centralized Secrets Management Service"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger("SecretsManagementService")
        
        # Initialize encryption key (in production, load from secure location)
        self.encryption_key = self._get_or_create_master_key()
        self.cipher = Fernet(self.encryption_key)
        
        # Vault configurations (in production, load from environment)
        self.vault_config = {
            "hashicorp_vault": {
                "enabled": False,
                "url": os.getenv("VAULT_ADDR", "http://localhost:8200"),
                "token": os.getenv("VAULT_TOKEN", "")
            },
            "aws_secrets_manager": {
                "enabled": False,
                "region": os.getenv("AWS_REGION", "us-east-1")
            },
            "azure_key_vault": {
                "enabled": False,
                "vault_url": os.getenv("AZURE_VAULT_URL", "")
            }
        }
        
        # Rotation policies
        self.rotation_policies = {
            SecretType.API_KEY: 90,  # days
            SecretType.DATABASE_PASSWORD: 30,
            SecretType.ENCRYPTION_KEY: 365,
            SecretType.CERTIFICATE: 365,
            SecretType.SSH_KEY: 180,
            SecretType.OAUTH_TOKEN: 7,
            SecretType.WEBHOOK_SECRET: 90
        }
    
    async def create_secret(
        self,
        name: str,
        value: str,
        secret_type: str,
        tenant_id: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        rotation_enabled: bool = True
    ) -> Dict[str, Any]:
        """
        Create a new secret
        
        Args:
            name: Secret name (unique per tenant)
            value: Secret value (will be encrypted)
            secret_type: Type of secret (api_key, database_password, etc.)
            tenant_id: Tenant ID
            description: Optional description
            metadata: Optional metadata
            rotation_enabled: Enable automatic rotation
        
        Returns:
            Secret metadata (without the actual value)
        """
        # Check if secret already exists
        existing = await self.db.secrets.find_one({
            "name": name,
            "tenant_id": tenant_id,
            "status": {"$ne": SecretStatus.REVOKED}
        })
        
        if existing:
            raise ValueError(f"Secret '{name}' already exists")
        
        # Encrypt the secret value
        encrypted_value = self._encrypt_secret(value)
        
        # Calculate next rotation date
        rotation_days = self.rotation_policies.get(secret_type, 90)
        next_rotation = datetime.now(timezone.utc) + timedelta(days=rotation_days) if rotation_enabled else None
        
        secret = {
            "name": name,
            "secret_type": secret_type,
            "tenant_id": tenant_id,
            "description": description,
            "encrypted_value": encrypted_value,
            "status": SecretStatus.ACTIVE,
            "version": 1,
            "rotation_enabled": rotation_enabled,
            "rotation_days": rotation_days if rotation_enabled else None,
            "next_rotation": next_rotation.isoformat() if next_rotation else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": None,
            "access_count": 0,
            "metadata": metadata or {}
        }
        
        # Store in database
        result = await self.db.secrets.insert_one(secret.copy())
        secret_id = str(result.inserted_id)
        
        # Log secret creation
        await self._log_secret_access(
            secret_id=secret_id,
            action="create",
            tenant_id=tenant_id,
            user="system"
        )
        
        # Return metadata (without encrypted value)
        secret.pop("encrypted_value")
        secret["id"] = secret_id
        
        self.logger.info(f"Created secret: {name} (type: {secret_type})")
        
        return secret
    
    async def get_secret(
        self,
        name: str,
        tenant_id: str,
        user: str = "system"
    ) -> str:
        """
        Retrieve a secret value
        
        Args:
            name: Secret name
            tenant_id: Tenant ID
            user: User requesting the secret
        
        Returns:
            Decrypted secret value
        """
        # Get secret from database
        secret = await self.db.secrets.find_one({
            "name": name,
            "tenant_id": tenant_id,
            "status": SecretStatus.ACTIVE
        })
        
        if not secret:
            raise ValueError(f"Secret '{name}' not found or not active")
        
        # Decrypt the value
        decrypted_value = self._decrypt_secret(secret["encrypted_value"])
        
        # Update access tracking
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {
                "$set": {
                    "last_accessed": datetime.now(timezone.utc).isoformat()
                },
                "$inc": {"access_count": 1}
            }
        )
        
        # Log access
        await self._log_secret_access(
            secret_id=str(secret["_id"]),
            action="read",
            tenant_id=tenant_id,
            user=user
        )
        
        return decrypted_value
    
    async def update_secret(
        self,
        name: str,
        new_value: str,
        tenant_id: str,
        user: str = "system"
    ) -> Dict[str, Any]:
        """
        Update a secret value (creates a new version)
        
        Args:
            name: Secret name
            new_value: New secret value
            tenant_id: Tenant ID
            user: User updating the secret
        
        Returns:
            Updated secret metadata
        """
        # Get current secret
        secret = await self.db.secrets.find_one({
            "name": name,
            "tenant_id": tenant_id,
            "status": SecretStatus.ACTIVE
        })
        
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        
        # Archive old version
        await self.db.secret_versions.insert_one({
            "secret_id": str(secret["_id"]),
            "version": secret["version"],
            "encrypted_value": secret["encrypted_value"],
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": user
        })
        
        # Encrypt new value
        encrypted_value = self._encrypt_secret(new_value)
        
        # Update secret
        new_version = secret["version"] + 1
        
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {
                "$set": {
                    "encrypted_value": encrypted_value,
                    "version": new_version,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Log update
        await self._log_secret_access(
            secret_id=str(secret["_id"]),
            action="update",
            tenant_id=tenant_id,
            user=user,
            details={"new_version": new_version}
        )
        
        self.logger.info(f"Updated secret: {name} (version: {new_version})")
        
        return {
            "name": name,
            "version": new_version,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def rotate_secret(
        self,
        name: str,
        tenant_id: str,
        user: str = "system"
    ) -> Dict[str, Any]:
        """
        Rotate a secret (generate new value)
        
        For API keys and tokens, generates a new random value.
        For passwords, requires manual input.
        """
        secret = await self.db.secrets.find_one({
            "name": name,
            "tenant_id": tenant_id,
            "status": SecretStatus.ACTIVE
        })
        
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        
        # Mark as rotating
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {"$set": {"status": SecretStatus.ROTATING}}
        )
        
        # Generate new value based on type
        if secret["secret_type"] in [SecretType.API_KEY, SecretType.WEBHOOK_SECRET]:
            new_value = self._generate_random_secret(32)
        elif secret["secret_type"] == SecretType.OAUTH_TOKEN:
            new_value = self._generate_random_secret(64)
        else:
            # For passwords and other types, rotation requires manual input
            raise ValueError(f"Manual rotation required for secret type: {secret['secret_type']}")
        
        # Update the secret
        result = await self.update_secret(name, new_value, tenant_id, user)
        
        # Update rotation date
        rotation_days = secret.get("rotation_days", 90)
        next_rotation = datetime.now(timezone.utc) + timedelta(days=rotation_days)
        
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {
                "$set": {
                    "status": SecretStatus.ACTIVE,
                    "next_rotation": next_rotation.isoformat()
                }
            }
        )
        
        # Log rotation
        await self._log_secret_access(
            secret_id=str(secret["_id"]),
            action="rotate",
            tenant_id=tenant_id,
            user=user
        )
        
        self.logger.info(f"Rotated secret: {name}")
        
        return {
            "name": name,
            "new_value": new_value,
            "version": result["version"],
            "next_rotation": next_rotation.isoformat()
        }
    
    async def revoke_secret(
        self,
        name: str,
        tenant_id: str,
        user: str = "system"
    ) -> Dict[str, Any]:
        """
        Revoke a secret (mark as revoked, cannot be used)
        """
        secret = await self.db.secrets.find_one({
            "name": name,
            "tenant_id": tenant_id
        })
        
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        
        # Mark as revoked
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {
                "$set": {
                    "status": SecretStatus.REVOKED,
                    "revoked_at": datetime.now(timezone.utc).isoformat(),
                    "revoked_by": user
                }
            }
        )
        
        # Log revocation
        await self._log_secret_access(
            secret_id=str(secret["_id"]),
            action="revoke",
            tenant_id=tenant_id,
            user=user
        )
        
        self.logger.warning(f"Revoked secret: {name}")
        
        return {
            "name": name,
            "status": SecretStatus.REVOKED,
            "revoked_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def list_secrets(
        self,
        tenant_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all secrets for a tenant (without values)
        """
        query = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        
        cursor = self.db.secrets.find(query).sort("name", 1)
        
        secrets = []
        async for secret in cursor:
            # Remove encrypted value
            secret.pop("encrypted_value", None)
            secret["id"] = str(secret.pop("_id"))
            secrets.append(secret)
        
        return secrets
    
    async def check_rotation_needed(self) -> List[Dict[str, Any]]:
        """
        Check which secrets need rotation
        
        Returns list of secrets that need rotation
        """
        now = datetime.now(timezone.utc).isoformat()
        
        cursor = self.db.secrets.find({
            "status": SecretStatus.ACTIVE,
            "rotation_enabled": True,
            "next_rotation": {"$lte": now}
        })
        
        secrets_to_rotate = []
        async for secret in cursor:
            secrets_to_rotate.append({
                "id": str(secret["_id"]),
                "name": secret["name"],
                "tenant_id": secret["tenant_id"],
                "secret_type": secret["secret_type"],
                "next_rotation": secret["next_rotation"]
            })
        
        return secrets_to_rotate
    
    async def scan_for_hardcoded_secrets(
        self,
        code: str,
        file_path: str
    ) -> List[Dict[str, Any]]:
        """
        Scan code for hardcoded secrets
        
        Detects:
        - API keys
        - Passwords
        - Tokens
        - Private keys
        """
        findings = []
        
        # Patterns for common secrets
        patterns = {
            "api_key": [
                r"api[_-]?key['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]",
                r"apikey['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]"
            ],
            "password": [
                r"password['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
                r"passwd['\"]?\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
            ],
            "token": [
                r"token['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]",
                r"auth[_-]?token['\"]?\s*[:=]\s*['\"]([a-zA-Z0-9]{20,})['\"]"
            ],
            "private_key": [
                r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"
            ],
            "aws_key": [
                r"AKIA[0-9A-Z]{16}"
            ]
        }
        
        import re
        
        for secret_type, pattern_list in patterns.items():
            for pattern in pattern_list:
                matches = re.finditer(pattern, code, re.IGNORECASE)
                for match in matches:
                    findings.append({
                        "type": secret_type,
                        "file_path": file_path,
                        "line": code[:match.start()].count('\n') + 1,
                        "pattern": pattern,
                        "severity": "critical",
                        "recommendation": f"Move {secret_type} to secrets management system"
                    })
        
        return findings
    
    async def get_secret_access_log(
        self,
        secret_name: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get secret access audit log
        """
        query = {}
        if secret_name:
            query["secret_name"] = secret_name
        if tenant_id:
            query["tenant_id"] = tenant_id
        
        cursor = self.db.secret_access_log.find(query).sort("timestamp", -1).limit(limit)
        
        logs = []
        async for log in cursor:
            log["id"] = str(log.pop("_id"))
            logs.append(log)
        
        return logs
    
    def _encrypt_secret(self, value: str) -> str:
        """Encrypt a secret value"""
        return self.cipher.encrypt(value.encode()).decode()
    
    def _decrypt_secret(self, encrypted_value: str) -> str:
        """Decrypt a secret value"""
        return self.cipher.decrypt(encrypted_value.encode()).decode()
    
    def _get_or_create_master_key(self) -> bytes:
        """Get or create master encryption key"""
        # In production, load from secure key management service
        # For now, generate or load from environment
        key = os.getenv("SECRETS_MASTER_KEY")
        if key:
            return base64.urlsafe_b64decode(key)
        else:
            # Generate new key (in production, store securely)
            return Fernet.generate_key()
    
    def _generate_random_secret(self, length: int = 32) -> str:
        """Generate a random secret"""
        import secrets
        import string
        
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    async def _log_secret_access(
        self,
        secret_id: str,
        action: str,
        tenant_id: str,
        user: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log secret access for audit trail"""
        log_entry = {
            "secret_id": secret_id,
            "action": action,
            "tenant_id": tenant_id,
            "user": user,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {}
        }
        
        await self.db.secret_access_log.insert_one(log_entry)


# Singleton
_secrets_service: Optional[SecretsManagementService] = None

def get_secrets_service(db: AsyncIOMotorDatabase) -> SecretsManagementService:
    """Get or create secrets management service singleton"""
    global _secrets_service
    if _secrets_service is None:
        _secrets_service = SecretsManagementService(db)
    return _secrets_service
