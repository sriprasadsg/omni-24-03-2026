import logging
import platform
import os
import sys
import subprocess
import requests
import shutil
import time

logger = logging.getLogger(__name__)

class AgentUpdateCapability:
    """
    Checks for updates and performs self-update with integrity verification.
    """
    capability_name = "agent_update"

    def __init__(self):
        # Current version
        self.current_version = "2.0.0"
        try:
            # Try to import version from main agent module
            import agent
            self.current_version = getattr(agent, "AGENT_VERSION", "2.0.0")
        except ImportError:
            pass
            
        self.system_platform = platform.system().lower()
        if not getattr(sys, 'frozen', False):
            self.system_platform = "python"
            
    def should_run(self, interval: int) -> bool:
        return True # logic handled by manager interval

    def verify_file_hash(self, filepath: str, expected_hash: str) -> bool:
        """Verify SHA256 hash of the downloaded file"""
        if not expected_hash:
            logger.warning("No expected hash provided. Skipping integrity check.")
            return True
            
        try:
            import hashlib
            sha256_hash = hashlib.sha256()
            with open(filepath, "rb") as f:
                # Read and update hash string value in blocks of 4K
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            calculated = sha256_hash.hexdigest()
            if calculated.lower() == expected_hash.lower():
                logger.info("✅ Integrity Check Passed.")
                return True
            else:
                logger.error(f"❌ Hash Mismatch! Expected: {expected_hash}, Got: {calculated}")
                return False
        except Exception as e:
            logger.error(f"Integrity check error: {e}")
            return False

    def execute(self):
        """Check and Update."""
        try:
            # Temporary Fix: Read config file directly
            import yaml
            from pathlib import Path
            cfg_path = Path(__file__).parent.parent / "config.yaml"
            if cfg_path.exists():
                try:
                    # Check if encrypted config
                    content = cfg_path.read_text(encoding="utf-8")
                    if content.strip().startswith("{") and "api_base_url" not in content:
                        # Simple heuristic for now: assume we can't read it easily without manager
                        # But wait, we imported SecurityManager in agent.py
                        # Let's assume we can fallback to os.environ or just try plain load
                         cfg = yaml.safe_load(content) # This might fail if encrypted
                    else:
                        cfg = yaml.safe_load(content)
                        
                    base_url = cfg.get("api_base_url", "http://localhost:5000").rstrip('/')
                except:
                    # If config is encrypted and we can't read it here easily without key,
                    # we fail gracefully. In real app, capability gets config from agent.
                    return {"status": "error", "reason": "Config encrypted/unreadable"}
            else:
                return {"status": "skipped", "reason": "No config found"}

            update_url = f"{base_url}/api/agent-updates/latest?platform={self.system_platform}"
            
            resp = requests.get(update_url, timeout=10)
            if resp.status_code != 200:
                logger.debug(f"Update check: {resp.status_code}")
                return {"status": "success", "message": "No update info"}
                
            data = resp.json()
            latest_version = data.get("version")
            download_url = data.get("url")
            expected_hash = data.get("sha256")
            
            if not latest_version or not download_url:
                return {"status": "success", "message": "No updates available"}

            # Compare versions
            if latest_version != self.current_version and latest_version > self.current_version:
                logger.info(f"Update available: {self.current_version} -> {latest_version}")
                return self.perform_update(download_url, data.get("filename"), expected_hash)
            
            return {"status": "success", "message": "Agent is up to date"}
            
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return {"status": "error", "error": str(e)}

    def perform_update(self, url: str, filename: str, expected_hash: str = None):
        """Download, Verify, Backup, Replace, Restart"""
        backup_path = None
        target_path = None
        
        try:
            # 1. Download
            local_filename = filename if filename else "omni-agent.new"
            logger.info(f"Downloading update from {url}...")
            
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            # 2. Verify Integrity
            if not self.verify_file_hash(local_filename, expected_hash):
                os.remove(local_filename)
                return {"status": "error", "error": "Integrity Check Failed. Update Aborted."}

            logger.info("Download verified.")
            
            # 3. Identify Target
            if getattr(sys, 'frozen', False):
                target_path = sys.executable
            else:
                # Script mode update
                target_path = os.path.abspath(sys.argv[0])
                if not target_path.endswith(".py"): 
                    target_path = os.path.join(os.getcwd(), "agent.py")

            backup_path = target_path + ".bak"
            
            # 4. Create Backup
            if os.path.exists(target_path):
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(target_path, backup_path)
                logger.info(f"Created backup at {backup_path}")
            
            # 5. Move New File
            shutil.move(local_filename, target_path)
            logger.info(f"Applied update to {target_path}")
            
            # 6. Restart
            logger.info("Restarting agent...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
            
        except Exception as e:
            logger.error(f"Update failed: {e}")
            
            # ROLLBACK
            if backup_path and os.path.exists(backup_path):
                logger.warning("Rolling back to previous version...")
                try:
                    if target_path and os.path.exists(target_path):
                        os.remove(target_path)
                    os.rename(backup_path, target_path)
                    logger.info("Rollback successful.")
                except Exception as rb_e:
                    logger.critical(f"Rollback FAILED: {rb_e}")
            
            return {"status": "error", "error": str(e)}
