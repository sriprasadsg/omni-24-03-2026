import logging
import os
from cryptography.fernet import Fernet

_logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data like API keys"""

    def __init__(self):
        key = os.getenv("PAYMENT_ENCRYPTION_KEY")

        if not key:
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env == "production":
                raise RuntimeError(
                    "PAYMENT_ENCRYPTION_KEY is not set. "
                    "Refusing to start in production without a stable encryption key. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            _logger.warning(
                "PAYMENT_ENCRYPTION_KEY is not set — using ephemeral key (dev only). "
                "All encrypted payment data will be lost on restart. "
                "Set PAYMENT_ENCRYPTION_KEY before going to production."
            )
            key = Fernet.generate_key().decode()

        if isinstance(key, str):
            key = key.encode()

        self.cipher = Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string"""
        if not plaintext:
            return ""
        return self.cipher.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a string"""
        if not ciphertext:
            return ""
        return self.cipher.decrypt(ciphertext.encode()).decode()


# Singleton instance
_encryption_service = None

def get_encryption_service() -> EncryptionService:
    """Get the encryption service singleton"""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service
