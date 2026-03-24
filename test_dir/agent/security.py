
import os
import sys
import json
import base64
import logging
import platform
import socket
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

try:
    import win32crypt
except ImportError:
    win32crypt = None

logger = logging.getLogger(__name__)

class SecurityManager:
    """
    Manages security primitives for the agent:
    - Unique Device ID generation
    - Derived encryption keys
    - Secure config loading/saving
    """
    
    def __init__(self, base_path=None):
        self.base_path = base_path or Path(".")
        self.key_file = self.base_path / "agent.key"
        self._key = None
        self._fernet = None
        
        self.device_id = self._generate_device_id()
        self._initialize_crypto()

    def _generate_device_id(self) -> str:
        """Generating a stable, machine-specific unique identifier"""
        try:
            # Gather hardware-specific attributes
            system = platform.system()
            node = platform.node()
            machine = platform.machine()
            
            # Simple fingerprint based on stable attributes
            fingerprint = f"{system}-{node}-{machine}"
            
            # Use SHA-256 to create a clean ID
            digest = hashes.Hash(hashes.SHA256())
            digest.update(fingerprint.encode())
            return digest.finalize().hex()[:16] # Return first 16 chars as ID
        except Exception as e:
            logger.error(f"Failed to generate device ID: {e}")
            return "unknown-device"

    def _initialize_crypto(self):
        """Initialize encryption keys, generating if needed (and feasible)"""
        try:
            # In a real enterprise scenario, we might use a TPM or a pre-shared secret.
            # Here, we will use a locally stored key that is generated once.
            # Ideally, we would protect this key with system-level APIs (DPAPI on Windows, Keychain on Mac).
            # For this implementation, we will perform a simple key generation and storage.
            
            if self.key_file.exists():
                try:
                    encrypted_key = self.key_file.read_bytes()
                    if win32crypt and os.name == 'nt':
                        self._key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
                    else:
                        self._key = encrypted_key
                    self._fernet = Fernet(self._key)
                except Exception as e:
                    logger.error(f"Failed to load existing key: {e}")
                    raise
            else:
                self._key = Fernet.generate_key()
                if win32crypt and os.name == 'nt':
                    encrypted_key = win32crypt.CryptProtectData(self._key, "OmniAgent Master Key", None, None, None, 0)
                    self.key_file.write_bytes(encrypted_key)
                else:
                    self.key_file.write_bytes(self._key)
                    # On POSIX, restrict permissions
                    if os.name == 'posix':
                        os.chmod(self.key_file, 0o600)
                
                self._fernet = Fernet(self._key)
                logger.info("Generated new protected encryption key.")
                
        except Exception as e:
            logger.error(f"Crypto init failed: {e}")
            # Fallback for dev environment or catastrophic failure?
            # We raise, because without crypto we can't be secure.
            raise

    def encrypt_data(self, data: str) -> str:
        if not self._fernet: return data
        return self._fernet.encrypt(data.encode()).decode()

    def decrypt_data(self, token: str) -> str:
        if not self._fernet: return token
        return self._fernet.decrypt(token.encode()).decode()

    def save_encrypted_config(self, config: dict, path: Path):
        """Save configuration dictionary as encrypted string"""
        try:
            json_str = json.dumps(config)
            encrypted = self.encrypt_data(json_str)
            path.write_text(encrypted, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save encrypted config: {e}")

    def load_encrypted_config(self, path: Path) -> dict:
        """Load encrypted configuration"""
        try:
            if not path.exists():
                return {}
            
            content = path.read_text(encoding="utf-8")
            
            # Check if it's legacy plaintext YAML first
            if content.strip().startswith("{") or "api_base_url:" in content: 
                # Very rough heuristic for YAML/JSON vs Encrypted
                # Attempt to parse as YAML/JSON directly
                import yaml
                try:
                    return yaml.safe_load(content)
                except:
                    pass # Failed, assume it's encrypted
            
            decrypted = self.decrypt_data(content)
            return json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            # Fallback try plaintext if decryption failed (migration scenario?)
            try:
                import yaml
                return yaml.safe_load(path.read_text(encoding="utf-8"))
            except:
                return {}

