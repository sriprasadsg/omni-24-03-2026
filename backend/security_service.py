"""
Security Service - Patch Integrity & Encryption
Handles patch verification, signature validation, and encryption
"""

import hashlib
import hmac
import secrets
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature


class SecurityService:
    """Patch security validation and encryption service"""
    
    def __init__(self):
        self.backend = default_backend()
    
    def calculate_sha256(self, data: bytes) -> str:
        """
        Calculate SHA-256 hash of data
        Returns hex digest
        """
        return hashlib.sha256(data).hexdigest()
    
    def verify_sha256(self, data: bytes, expected_hash: str) -> bool:
        """
        Verify data against expected SHA-256 hash
        Returns True if valid, False otherwise
        """
        calculated_hash = self.calculate_sha256(data)
        return hmac.compare_digest(calculated_hash, expected_hash)
    
    def generate_patch_checksum(self, patch_file_path: str) -> Dict[str, str]:
        """
        Generate checksums for a patch file
        Returns dict with SHA-256, SHA-512, and MD5 (for legacy)
        """
        checksums = {
            "sha256": hashlib.sha256(),
            "sha512": hashlib.sha512(),
            "md5": hashlib.md5()
        }
        
        try:
            with open(patch_file_path, 'rb') as f:
                while chunk := f.read(8192):
                    for hash_obj in checksums.values():
                        hash_obj.update(chunk)
            
            return {
                "sha256": checksums["sha256"].hexdigest(),
                "sha512": checksums["sha512"].hexdigest(),
                "md5": checksums["md5"].hexdigest(),
                "algorithm": "SHA-256 (primary)",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            raise ValueError(f"Error generating checksums: {e}")
    
    def verify_patch_integrity(
        self,
        patch_file_path: str,
        expected_checksums: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Verify patch file integrity against expected checksums
        
        Returns:
        {
            "valid": bool,
            "algorithm": str,
            "verified_checksums": list,
            "failed_checksums": list
        }
        """
        calculated = self.generate_patch_checksum(patch_file_path)
        
        verified = []
        failed = []
        
        for algo in ["sha256", "sha512", "md5"]:
            if algo in expected_checksums:
                if hmac.compare_digest(calculated[algo], expected_checksums[algo]):
                    verified.append(algo.upper())
                else:
                    failed.append(algo.upper())
        
        return {
            "valid": len(failed) == 0 and len(verified) > 0,
            "algorithm": "SHA-256",
            "verified_checksums": verified,
            "failed_checksums": failed,
            "calculated": calculated,
            "verified_at": datetime.now(timezone.utc).isoformat()
        }
    
    def generate_rsa_keypair(self, key_size: int = 2048) -> Tuple[bytes, bytes]:
        """
        Generate RSA public/private key pair for patch signing
        
        Returns: (private_key_pem, public_key_pem)
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=self.backend
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return private_pem, public_pem
    
    def sign_patch(
        self,
        patch_data: bytes,
        private_key_pem: bytes
    ) -> bytes:
        """
        Sign patch data with RSA private key
        Returns signature bytes
        """
        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
            backend=self.backend
        )
        
        signature = private_key.sign(
            patch_data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return signature
    
    def verify_patch_signature(
        self,
        patch_data: bytes,
        signature: bytes,
        public_key_pem: bytes
    ) -> Dict[str, Any]:
        """
        Verify patch signature using RSA public key
        
        Returns:
        {
            "valid": bool,
            "algorithm": str,
            "verified_at": str,
            "error": str (if invalid)
        }
        """
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem,
                backend=self.backend
            )
            
            public_key.verify(
                signature,
                patch_data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return {
                "valid": True,
                "algorithm": "RSA-PSS with SHA-256",
                "verified_at": datetime.now(timezone.utc).isoformat()
            }
        
        except InvalidSignature:
            return {
                "valid": False,
                "algorithm": "RSA-PSS with SHA-256",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "error": "Invalid signature - patch may be tampered"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Verification error: {str(e)}"
            }
    
    def generate_secure_token(self, length: int = 32) -> str:
        """
        Generate cryptographically secure random token
        Used for agent registration, API keys, etc.
        """
        return secrets.token_urlsafe(length)
    
    def validate_agent_integrity(
        self,
        agent_id: str,
        reported_version: str,
        reported_checksum: str,
        expected_checksum: str
    ) -> Dict[str, Any]:
        """
        Validate agent software integrity
        Detects tampering or version mismatches
        """
        checksum_valid = hmac.compare_digest(reported_checksum, expected_checksum)
        
        return {
            "agent_id": agent_id,
            "integrity_valid": checksum_valid,
            "version": reported_version,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "action_required": "reinstall_agent" if not checksum_valid else None,
            "threat_detected": not checksum_valid
        }
    
    def encrypt_payload(self, data: bytes, key: bytes) -> Tuple[bytes, bytes]:
        """
        Encrypt data using AES-256-GCM
        
        Returns: (encrypted_data, nonce)
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(key)
        nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
        
        encrypted = aesgcm.encrypt(nonce, data, None)
        
        return encrypted, nonce
    
    def decrypt_payload(
        self,
        encrypted_data: bytes,
        nonce: bytes,
        key: bytes
    ) -> bytes:
        """
        Decrypt AES-256-GCM encrypted data
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, encrypted_data, None)
        
        return decrypted
    
    def generate_encryption_key(self) -> bytes:
        """Generate 256-bit encryption key"""
        return secrets.token_bytes(32)  # 256 bits
    
    async def audit_security_event(
        self,
        db,
        event_type: str,
        details: Dict[str, Any],
        severity: str = "info"
    ) -> None:
        """
        Log security-related events for audit trail
        
        Event types:
        - patch_integrity_verified
        - patch_integrity_failed
        - signature_verified
        - signature_invalid
        - agent_tampering_detected
        - encryption_key_generated
        """
        security_event = {
            "id": f"sec-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}",
            "type": event_type,
            "severity": severity,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await db.security_audit_log.insert_one(security_event)


# Singleton instance
_security_service = None

def get_security_service():
    """Get or create security service singleton"""
    global _security_service
    if _security_service is None:
        _security_service = SecurityService()
    return _security_service
