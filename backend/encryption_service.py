import os
from cryptography.fernet import Fernet


class EncryptionService:
    """Service for encrypting and decrypting sensitive data like API keys"""
    
    def __init__(self):
        # Get encryption key from environment variable
        key = os.getenv('PAYMENT_ENCRYPTION_KEY')
        
        if not key:
            # Generate a new key if not set (for development only)
            key = Fernet.generate_key().decode()
            print(f"WARNING: No PAYMENT_ENCRYPTION_KEY found. Generated temporary key: {key}")
            print("Please set this in your .env file for production use!")
        
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
