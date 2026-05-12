"""
File Integrity Monitoring Capability
Monitors critical system files for unauthorized changes
"""
from .base import BaseCapability
import os
import json
import hashlib
import logging
import platform
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Persist baseline next to the agent data directory so it survives restarts
_BASELINE_PATH = os.path.join(
    os.environ.get("PROGRAMDATA", os.path.expanduser("~")),
    "OmniAgent", "fim_baseline.json",
)


class FIMCapability(BaseCapability):

    def __init__(self, config=None):
        super().__init__(config)
        self._baseline: Dict[str, str] = self._load_baseline()

    # ------------------------------------------------------------------
    # Baseline persistence helpers
    # ------------------------------------------------------------------
    def _load_baseline(self) -> Dict[str, str]:
        try:
            if os.path.isfile(_BASELINE_PATH):
                with open(_BASELINE_PATH) as f:
                    data = json.load(f)
                logger.info("[FIM] Loaded baseline with %d entries from %s", len(data), _BASELINE_PATH)
                return data
        except Exception as exc:
            logger.warning("[FIM] Could not load baseline: %s — starting fresh", exc)
        return {}

    def _save_baseline(self) -> None:
        try:
            os.makedirs(os.path.dirname(_BASELINE_PATH), exist_ok=True)
            with open(_BASELINE_PATH, "w") as f:
                json.dump(self._baseline, f, indent=2)
        except Exception as exc:
            logger.warning("[FIM] Could not persist baseline: %s", exc)

    @property
    def capability_id(self) -> str:
        return "fim"

    @property
    def capability_name(self) -> str:
        return "File Integrity Monitoring"

    def collect(self) -> Dict[str, Any]:
        """Monitor critical files for changes; detect and report modifications."""
        system = platform.system()
        critical_files = self._get_critical_files(system)
        monitored_files = []
        violations = []

        for filepath in critical_files:
            if os.path.exists(filepath):
                try:
                    checksum = self._calculate_checksum(filepath)
                    stat = os.stat(filepath)
                    prev = self._baseline.get(filepath)
                    changed = prev is not None and prev != checksum

                    if changed:
                        violations.append({
                            "path": filepath,
                            "previous_checksum": prev,
                            "current_checksum": checksum,
                            "severity": "High",
                        })

                    self._baseline[filepath] = checksum
                    monitored_files.append({
                        "path": filepath,
                        "checksum": checksum,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "status": "Modified" if changed else "Monitored",
                    })
                except Exception as e:
                    monitored_files.append({"path": filepath, "status": f"Error: {e}"})

        self._save_baseline()
        return {
            "monitored_files": monitored_files,
            "count": len(monitored_files),
            "violations": violations,
            "violations_count": len(violations),
        }
    
    def _get_critical_files(self, system: str) -> List[str]:
        """Get list of critical files to monitor based on OS"""
        if system == "Windows":
            return [
                r"C:\Windows\System32\drivers\etc\hosts",
                r"C:\Windows\System32\config\SAM",
                r"C:\Windows\System32\config\SYSTEM"
            ]
        elif system == "Linux":
            return [
                "/etc/passwd",
                "/etc/shadow",
                "/etc/sudoers",
                "/etc/hosts",
                "/etc/ssh/sshd_config"
            ]
        return []
    
    def _calculate_checksum(self, filepath: str) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except OSError as exc:
            logger.debug("[FIM] Cannot read %s: %s", filepath, exc)
            return "N/A"
