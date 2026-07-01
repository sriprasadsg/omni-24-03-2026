"""
SecretsManagementService backends mixin: encryption, Vault, AWS Secrets Manager,
key generation, and access audit logging.
"""

import base64
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from cryptography.fernet import Fernet


class SecretsManagementBackendsMixin:
    """Encryption helpers, external vault/cloud backends, and audit logging."""

    def _encrypt_secret(self, value: str) -> str:
        return self.cipher.encrypt(value.encode()).decode()

    def _decrypt_secret(self, encrypted_value: str) -> str:
        return self.cipher.decrypt(encrypted_value.encode()).decode()

    def _get_or_create_master_key(self) -> bytes:
        key = os.getenv("SECRETS_MASTER_KEY")
        if key:
            return base64.urlsafe_b64decode(key)
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env == "production":
            raise RuntimeError(
                "SECRETS_MASTER_KEY is not set. "
                "Refusing to start in production without a stable master key. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; "
                "import base64; print(base64.urlsafe_b64encode(Fernet.generate_key()).decode())\""
            )
        logger = logging.getLogger(self.__class__.__name__)
        logger.warning(
            "SECRETS_MASTER_KEY is not set — using ephemeral key (dev only). "
            "All managed secrets will be unrecoverable after restart. "
            "Set SECRETS_MASTER_KEY before going to production."
        )
        return Fernet.generate_key()

    def _generate_random_secret(self, length: int = 32) -> str:
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
        details: Optional[Dict[str, Any]] = None,
    ):
        await self.db.secret_access_log.insert_one({
            "secret_id": secret_id, "action": action,
            "tenant_id": tenant_id, "user": user,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        })

    async def write_to_vault(self, name: str, value: str, tenant_id: str) -> bool:
        """Write a secret to HashiCorp Vault if configured."""
        vault_cfg = self.vault_config.get("hashicorp_vault", {})
        if not vault_cfg.get("enabled") or not vault_cfg.get("token"):
            return False
        url = vault_cfg["url"].rstrip("/")
        token = vault_cfg["token"]
        path = f"/v1/secret/data/{tenant_id}/{name}"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url + path,
                    headers={"X-Vault-Token": token, "Content-Type": "application/json"},
                    json={"data": {"value": value}},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status in (200, 204):
                        self.logger.info("[Vault] Wrote secret %s/%s", tenant_id, name)
                        return True
                    self.logger.warning("[Vault] Write failed HTTP %s", resp.status)
        except Exception as exc:
            self.logger.warning("[Vault] write_to_vault error: %s", exc)
        return False

    async def read_from_vault(self, name: str, tenant_id: str) -> Optional[str]:
        """Read a secret from HashiCorp Vault."""
        vault_cfg = self.vault_config.get("hashicorp_vault", {})
        if not vault_cfg.get("token"):
            return None
        url = vault_cfg["url"].rstrip("/")
        token = vault_cfg["token"]
        path = f"/v1/secret/data/{tenant_id}/{name}"
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url + path,
                    headers={"X-Vault-Token": token},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("data", {}).get("data", {}).get("value")
        except Exception as exc:
            self.logger.warning("[Vault] read_from_vault error: %s", exc)
        return None

    async def write_to_aws_secrets_manager(self, name: str, value: str, tenant_id: str) -> bool:
        """Write/update a secret in AWS Secrets Manager if boto3 is available."""
        try:
            import boto3
            region = self.vault_config.get("aws_secrets_manager", {}).get("region", "us-east-1")
            client = boto3.client("secretsmanager", region_name=region)
            secret_id = f"omniagent/{tenant_id}/{name}"
            try:
                client.put_secret_value(SecretId=secret_id, SecretString=value)
            except client.exceptions.ResourceNotFoundException:
                client.create_secret(Name=secret_id, SecretString=value)
            self.logger.info("[AWS SM] Stored secret %s", secret_id)
            return True
        except ImportError:
            self.logger.debug("[AWS SM] boto3 not installed; skipping AWS Secrets Manager")
        except Exception as exc:
            self.logger.warning("[AWS SM] write error: %s", exc)
        return False

    async def read_from_aws_secrets_manager(self, name: str, tenant_id: str) -> Optional[str]:
        """Read a secret from AWS Secrets Manager."""
        try:
            import boto3
            region = self.vault_config.get("aws_secrets_manager", {}).get("region", "us-east-1")
            client = boto3.client("secretsmanager", region_name=region)
            secret_id = f"omniagent/{tenant_id}/{name}"
            resp = client.get_secret_value(SecretId=secret_id)
            return resp.get("SecretString")
        except ImportError:
            pass
        except Exception as exc:
            self.logger.warning("[AWS SM] read error: %s", exc)
        return None
