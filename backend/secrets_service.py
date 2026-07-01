"""
Secrets Management Service aggregator.

Backend helpers live in secrets_service_backends.py (encryption, Vault, AWS).
Scanning and audit helpers live in secrets_service_security.py.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from cryptography.fernet import Fernet

from secrets_service_backends import SecretsManagementBackendsMixin
from secrets_service_security import SecretsManagementSecurityMixin


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


class SecretsManagementService(
    SecretsManagementSecurityMixin,
    SecretsManagementBackendsMixin,
):
    """Centralized Secrets Management Service."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.logger = logging.getLogger("SecretsManagementService")
        self.encryption_key = self._get_or_create_master_key()
        self.cipher = Fernet(self.encryption_key)
        self.vault_config = {
            "hashicorp_vault": {
                "enabled": False,
                "url": os.getenv("VAULT_ADDR", "http://localhost:8200"),
                "token": os.getenv("VAULT_TOKEN", ""),
            },
            "aws_secrets_manager": {
                "enabled": False,
                "region": os.getenv("AWS_REGION", "us-east-1"),
            },
            "azure_key_vault": {
                "enabled": False,
                "vault_url": os.getenv("AZURE_VAULT_URL", ""),
            },
        }
        self.rotation_policies = {
            SecretType.API_KEY: 90,
            SecretType.DATABASE_PASSWORD: 30,
            SecretType.ENCRYPTION_KEY: 365,
            SecretType.CERTIFICATE: 365,
            SecretType.SSH_KEY: 180,
            SecretType.OAUTH_TOKEN: 7,
            SecretType.WEBHOOK_SECRET: 90,
        }

    async def create_secret(
        self,
        name: str,
        value: str,
        secret_type: str,
        tenant_id: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        rotation_enabled: bool = True,
    ) -> Dict[str, Any]:
        """Create a new secret (value is stored encrypted)."""
        existing = await self.db.secrets.find_one({
            "name": name, "tenant_id": tenant_id,
            "status": {"$ne": SecretStatus.REVOKED},
        })
        if existing:
            raise ValueError(f"Secret '{name}' already exists")

        encrypted_value = self._encrypt_secret(value)
        rotation_days = self.rotation_policies.get(secret_type, 90)
        next_rotation = (
            datetime.now(timezone.utc) + timedelta(days=rotation_days)
            if rotation_enabled else None
        )
        secret = {
            "name": name, "secret_type": secret_type, "tenant_id": tenant_id,
            "description": description, "encrypted_value": encrypted_value,
            "status": SecretStatus.ACTIVE, "version": 1,
            "rotation_enabled": rotation_enabled,
            "rotation_days": rotation_days if rotation_enabled else None,
            "next_rotation": next_rotation.isoformat() if next_rotation else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": None, "access_count": 0,
            "metadata": metadata or {},
        }
        result = await self.db.secrets.insert_one(secret.copy())
        secret_id = str(result.inserted_id)
        await self._log_secret_access(secret_id, "create", tenant_id, "system")
        asyncio.create_task(self.write_to_vault(name, value, tenant_id))
        asyncio.create_task(self.write_to_aws_secrets_manager(name, value, tenant_id))
        secret.pop("encrypted_value")
        secret["id"] = secret_id
        self.logger.info("Created secret: %s (type: %s)", name, secret_type)
        return secret

    async def get_secret(
        self, name: str, tenant_id: str, user: str = "system"
    ) -> str:
        """Retrieve a decrypted secret value."""
        secret = await self.db.secrets.find_one({
            "name": name, "tenant_id": tenant_id, "status": SecretStatus.ACTIVE,
        })
        if not secret:
            raise ValueError(f"Secret '{name}' not found or not active")
        decrypted_value = self._decrypt_secret(secret["encrypted_value"])
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {"$set": {"last_accessed": datetime.now(timezone.utc).isoformat()},
             "$inc": {"access_count": 1}},
        )
        await self._log_secret_access(str(secret["_id"]), "read", tenant_id, user)
        return decrypted_value

    async def update_secret(
        self, name: str, new_value: str, tenant_id: str, user: str = "system"
    ) -> Dict[str, Any]:
        """Update a secret value (archives the old version)."""
        secret = await self.db.secrets.find_one({
            "name": name, "tenant_id": tenant_id, "status": SecretStatus.ACTIVE,
        })
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        await self.db.secret_versions.insert_one({
            "secret_id": str(secret["_id"]), "version": secret["version"],
            "encrypted_value": secret["encrypted_value"],
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "archived_by": user,
        })
        encrypted_value = self._encrypt_secret(new_value)
        new_version = secret["version"] + 1
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {"$set": {"encrypted_value": encrypted_value, "version": new_version,
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        await self._log_secret_access(
            str(secret["_id"]), "update", tenant_id, user,
            details={"new_version": new_version},
        )
        self.logger.info("Updated secret: %s (version: %d)", name, new_version)
        return {"name": name, "version": new_version,
                "updated_at": datetime.now(timezone.utc).isoformat()}

    async def rotate_secret(
        self, name: str, tenant_id: str, user: str = "system"
    ) -> Dict[str, Any]:
        """Rotate a secret by generating a new random value."""
        secret = await self.db.secrets.find_one({
            "name": name, "tenant_id": tenant_id, "status": SecretStatus.ACTIVE,
        })
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        await self.db.secrets.update_one(
            {"_id": secret["_id"]}, {"$set": {"status": SecretStatus.ROTATING}}
        )
        if secret["secret_type"] in (SecretType.API_KEY, SecretType.WEBHOOK_SECRET):
            new_value = self._generate_random_secret(32)
        elif secret["secret_type"] == SecretType.OAUTH_TOKEN:
            new_value = self._generate_random_secret(64)
        else:
            raise ValueError(
                f"Manual rotation required for secret type: {secret['secret_type']}"
            )
        result = await self.update_secret(name, new_value, tenant_id, user)
        rotation_days = secret.get("rotation_days", 90)
        next_rotation = datetime.now(timezone.utc) + timedelta(days=rotation_days)
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {"$set": {"status": SecretStatus.ACTIVE,
                      "next_rotation": next_rotation.isoformat()}},
        )
        await self._log_secret_access(str(secret["_id"]), "rotate", tenant_id, user)
        self.logger.info("Rotated secret: %s", name)
        return {"name": name, "rotated": True,
                "version": result["version"],
                "next_rotation": next_rotation.isoformat()}

    async def revoke_secret(
        self, name: str, tenant_id: str, user: str = "system"
    ) -> Dict[str, Any]:
        """Revoke a secret (permanently marks it unusable)."""
        secret = await self.db.secrets.find_one({"name": name, "tenant_id": tenant_id})
        if not secret:
            raise ValueError(f"Secret '{name}' not found")
        now = datetime.now(timezone.utc).isoformat()
        await self.db.secrets.update_one(
            {"_id": secret["_id"]},
            {"$set": {"status": SecretStatus.REVOKED, "revoked_at": now, "revoked_by": user}},
        )
        await self._log_secret_access(str(secret["_id"]), "revoke", tenant_id, user)
        self.logger.warning("Revoked secret: %s", name)
        return {"name": name, "status": SecretStatus.REVOKED, "revoked_at": now}

    async def list_secrets(
        self, tenant_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all secrets for a tenant (values omitted)."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        secrets = []
        async for secret in self.db.secrets.find(query).sort("name", 1):
            secret.pop("encrypted_value", None)
            secret["id"] = str(secret.pop("_id"))
            secrets.append(secret)
        return secrets

    async def check_rotation_needed(
        self, tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return secrets that are overdue for rotation."""
        query: Dict[str, Any] = {
            "status": SecretStatus.ACTIVE,
            "rotation_enabled": True,
            "next_rotation": {"$lte": datetime.now(timezone.utc).isoformat()},
        }
        if tenant_id:
            query["tenant_id"] = tenant_id
        result = []
        async for secret in self.db.secrets.find(query):
            result.append({
                "id": str(secret["_id"]), "name": secret["name"],
                "tenant_id": secret["tenant_id"],
                "secret_type": secret["secret_type"],
                "next_rotation": secret["next_rotation"],
            })
        return result


_secrets_service: Optional[SecretsManagementService] = None


def get_secrets_service(db: AsyncIOMotorDatabase) -> SecretsManagementService:
    """Get or create the secrets management service singleton."""
    global _secrets_service
    if _secrets_service is None:
        _secrets_service = SecretsManagementService(db)
    return _secrets_service
