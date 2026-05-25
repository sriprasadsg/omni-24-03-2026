
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
            if self.key_file.exists():
                try:
                    encrypted_key = self.key_file.read_bytes()
                    if win32crypt and os.name == 'nt':
                        self._key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
                    else:
                        self._key = encrypted_key
                    self._fernet = Fernet(self._key)
                    return
                except Exception as e:
                    logger.error(f"Failed to load existing key: {e}")
                    logger.warning("Key is invalid or corrupted. Deleting and regenerating...")
                    try:
                        self.key_file.unlink()
                    except FileNotFoundError:
                        pass
            
            # Generate new key
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

    @staticmethod
    def _expand_env_vars(obj):
        """Recursively expand ${VAR} and ${VAR:-default} placeholders using os.environ."""
        import re
        pattern = re.compile(r'\$\{([^}]+)\}')

        def _expand(value):
            if not isinstance(value, str):
                return value
            def _replace(match):
                spec = match.group(1)
                if ':-' in spec:
                    var, default = spec.split(':-', 1)
                    return os.environ.get(var.strip(), default)
                return os.environ.get(spec.strip(), match.group(0))
            return pattern.sub(_replace, value)

        if isinstance(obj, dict):
            return {k: SecurityManager._expand_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [SecurityManager._expand_env_vars(i) for i in obj]
        return _expand(obj)

    def load_encrypted_config(self, path: Path) -> dict:
        """Load encrypted configuration, expanding ${ENV_VAR} placeholders."""
        try:
            if not path.exists():
                return {}

            content = path.read_text(encoding="utf-8")

            # Plaintext YAML heuristic
            if content.strip().startswith("{") or "api_base_url:" in content or "${" in content:
                import yaml
                try:
                    raw = yaml.safe_load(content)
                    return self._expand_env_vars(raw) if isinstance(raw, dict) else {}
                except Exception:
                    pass  # not valid YAML — fall through to encrypted path

            decrypted = self.decrypt_data(content)
            raw = json.loads(decrypted)
            return self._expand_env_vars(raw)
        except Exception as e:
            logger.error("Failed to load config: %s", e)
            try:
                import yaml
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                return self._expand_env_vars(raw) if isinstance(raw, dict) else {}
            except Exception:
                return {}

