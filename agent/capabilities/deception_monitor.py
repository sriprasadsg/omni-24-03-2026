"""
Deception Technology Capability
Manages local honeypot files (canary files), fake registry keys, and fake open ports.
Reports any access to these decoys as high-confidence threat indicators.
"""

import os
import platform
import socket
import threading
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseCapability

logger = logging.getLogger(__name__)


class DeceptionMonitorCapability(BaseCapability):
    """
    Lightweight deception layer:
    - Canary files: dummy files in sensitive paths; access = immediate alert
    - Fake credentials file: a file whose name attracts credential harvesters
    - Honeypot TCP listener: low-numbered port that nothing legitimate connects to
    """

    CANARY_FILENAMES = [
        "passwords.txt",
        "credentials.csv",
        "aws_keys.txt",
        "backup_encryption.key",
        ".ssh_backup",
    ]

    @property
    def capability_id(self) -> str:
        return "deception_monitor"

    @property
    def capability_name(self) -> str:
        return "Deception Technology Monitor"

    def __init__(self, config=None):
        super().__init__(config)
        self._canary_dir: Optional[str] = None
        self._canary_paths: List[str] = []
        self._canary_mtimes: Dict[str, float] = {}
        self._honeypot_thread: Optional[threading.Thread] = None
        self._honeypot_socket: Optional[socket.socket] = None
        self._honeypot_port: int = 0
        self._hits: List[Dict[str, Any]] = []
        self._initialized = False

    # ── Initialization ─────────────────────────────────────────────────────────

    def _initialize(self):
        if self._initialized:
            return
        self._canary_dir = self._pick_canary_dir()
        if self._canary_dir:
            self._deploy_canary_files()
        self._start_honeypot_listener()
        self._initialized = True

    def _pick_canary_dir(self) -> Optional[str]:
        if platform.system().lower() == "windows":
            candidates = [
                os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\Public"), "Documents"),
                "C:\\Windows\\Temp",
            ]
        else:
            candidates = ["/tmp", os.path.expanduser("~")]
        for c in candidates:
            if os.path.isdir(c) and os.access(c, os.W_OK):
                return os.path.join(c, ".omni_decoys")
        return None

    def _deploy_canary_files(self):
        try:
            os.makedirs(self._canary_dir, exist_ok=True)
            for fname in self.CANARY_FILENAMES:
                path = os.path.join(self._canary_dir, fname)
                if not os.path.exists(path):
                    with open(path, "w") as fh:
                        fh.write(_canary_content(fname))
                self._canary_paths.append(path)
                self._canary_mtimes[path] = os.path.getatime(path)
            logger.debug("[Deception] Deployed %d canary files in %s", len(self._canary_paths), self._canary_dir)
        except Exception as exc:
            logger.warning("[Deception] Failed to deploy canary files: %s", exc)

    def _start_honeypot_listener(self):
        # Try to bind a fake listener on a high ephemeral port that no service uses
        for candidate_port in (44444, 44445, 44446, 0):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", candidate_port))
                sock.listen(5)
                sock.settimeout(2)
                self._honeypot_socket = sock
                self._honeypot_port = sock.getsockname()[1]
                self._honeypot_thread = threading.Thread(
                    target=self._honeypot_accept_loop, daemon=True
                )
                self._honeypot_thread.start()
                logger.debug("[Deception] Honeypot listener on port %d", self._honeypot_port)
                break
            except Exception:
                continue

    def _honeypot_accept_loop(self):
        while True:
            try:
                if not self._honeypot_socket:
                    break
                conn, addr = self._honeypot_socket.accept()
                try:
                    banner = conn.recv(256)
                except Exception:
                    banner = b""
                conn.close()
                hit = {
                    "type": "honeypot_connection",
                    "remote_ip": addr[0],
                    "remote_port": addr[1],
                    "honeypot_port": self._honeypot_port,
                    "data_sent": banner.decode("utf-8", errors="replace")[:100] if banner else "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "High",
                    "description": f"Connection to honeypot port {self._honeypot_port} from {addr[0]}:{addr[1]}",
                }
                self._hits.append(hit)
                logger.warning("[Deception] HONEYPOT HIT: %s", hit["description"])
            except socket.timeout:
                continue
            except Exception as exc:
                if self._honeypot_socket:
                    logger.debug("[Deception] Honeypot accept error: %s", exc)
                break

    # ── Canary file access detection ───────────────────────────────────────────

    def _check_canary_files(self) -> List[Dict[str, Any]]:
        hits = []
        for path in self._canary_paths:
            if not os.path.exists(path):
                # File deleted — adversary may have exfiltrated or cleaned up
                hit = {
                    "type": "canary_file_deleted",
                    "path": path,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "Critical",
                    "description": f"Canary file DELETED: {path} — possible exfiltration or cleanup",
                }
                hits.append(hit)
                self._hits.append(hit)
                logger.critical("[Deception] CANARY DELETED: %s", path)
                continue

            try:
                current_atime = os.path.getatime(path)
                last_atime = self._canary_mtimes.get(path, 0)
                if current_atime > last_atime + 1:  # 1-second tolerance
                    hit = {
                        "type": "canary_file_accessed",
                        "path": path,
                        "filename": os.path.basename(path),
                        "prev_atime": last_atime,
                        "curr_atime": current_atime,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "severity": "Critical",
                        "description": f"Canary file ACCESSED: {path}",
                    }
                    hits.append(hit)
                    self._hits.append(hit)
                    self._canary_mtimes[path] = current_atime
                    logger.critical("[Deception] CANARY ACCESS: %s", path)

                # Check if modified (content changed = credential harvesting attempt)
                current_mtime = os.path.getmtime(path)
                if current_mtime > last_atime + 1 and current_mtime != current_atime:
                    hit = {
                        "type": "canary_file_modified",
                        "path": path,
                        "filename": os.path.basename(path),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "severity": "Critical",
                        "description": f"Canary file MODIFIED: {path} — possible credential injection",
                    }
                    hits.append(hit)
                    self._hits.append(hit)
                    logger.critical("[Deception] CANARY MODIFIED: %s", path)

            except Exception as exc:
                logger.debug("[Deception] Error checking canary %s: %s", path, exc)

        return hits

    # ── Fake registry key check (Windows only) ────────────────────────────────

    def _check_registry_canaries(self) -> List[Dict[str, Any]]:
        hits = []
        if platform.system().lower() != "windows":
            return hits
        try:
            import winreg
            canary_key_path = r"SOFTWARE\OmniAgent\DecoyCredentials"
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, canary_key_path, 0, winreg.KEY_READ)
                winreg.CloseKey(key)
            except FileNotFoundError:
                # Key doesn't exist yet — create it as a trap
                try:
                    key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, canary_key_path)
                    winreg.SetValueEx(key, "Password", 0, winreg.REG_SZ, "Tr@pP@ssw0rd!")
                    winreg.SetValueEx(key, "Username", 0, winreg.REG_SZ, "admin-backup")
                    winreg.CloseKey(key)
                except PermissionError:
                    pass  # Need admin rights — skip silently
        except ImportError:
            pass
        return hits

    # ── collect() ─────────────────────────────────────────────────────────────

    def collect(self) -> Dict[str, Any]:
        if not self._initialized:
            self._initialize()

        new_hits = self._check_canary_files()
        new_hits += self._check_registry_canaries()

        # Drain honeypot hits that arrived since last collect()
        honeypot_hits = [h for h in self._hits if h.get("type") == "honeypot_connection"]

        all_recent = new_hits + honeypot_hits
        self._hits = [h for h in self._hits if h not in honeypot_hits]

        return {
            "status": "active",
            "canary_files_deployed": len(self._canary_paths),
            "canary_directory": self._canary_dir,
            "honeypot_port": self._honeypot_port,
            "honeypot_running": bool(self._honeypot_thread and self._honeypot_thread.is_alive()),
            "hits_this_cycle": len(all_recent),
            "deception_events": all_recent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def cleanup(self):
        """Remove canary files and close honeypot socket on shutdown."""
        for path in self._canary_paths:
            try:
                os.remove(path)
            except Exception:
                pass
        if self._canary_dir:
            try:
                os.rmdir(self._canary_dir)
            except Exception:
                pass
        if self._honeypot_socket:
            try:
                self._honeypot_socket.close()
            except Exception:
                pass
            self._honeypot_socket = None


def _canary_content(filename: str) -> str:
    templates = {
        "passwords.txt": (
            "# System Credentials - DO NOT SHARE\n"
            "DB_PASSWORD=Tr@pSecure2024!\n"
            "ADMIN_PASSWORD=P@ssw0rd#Canary\n"
            "SSH_PASSPHRASE=FakeKey$ecret99\n"
        ),
        "credentials.csv": (
            "username,password,service\n"
            "admin,CanaryPw!2024,production\n"
            "backup-user,TrapCred$123,backup\n"
        ),
        "aws_keys.txt": (
            "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7CANARY1\n"
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYCANARYKEY\n"
            "AWS_DEFAULT_REGION=us-east-1\n"
        ),
        "backup_encryption.key": (
            "-----BEGIN CANARY KEY-----\n"
            "MIIBOgIBAAJBALRiMLAHudeSA/xKl1oQkFHQGEpFoCQEzHlP1U/FKapkVGl/vIZf\n"
            "-----END CANARY KEY-----\n"
        ),
        ".ssh_backup": (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAAAAAAAAAAAAAABAAAAMwAAAAtzc2gtZWQyNTUxOQAA\n"
            "CANARY_TRAP_KEY_DO_NOT_USE\n"
            "-----END OPENSSH PRIVATE KEY-----\n"
        ),
    }
    return templates.get(filename, f"# Canary file: {filename}\n# Access to this file is monitored\n")
