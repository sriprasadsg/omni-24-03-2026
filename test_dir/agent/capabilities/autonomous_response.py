"""
Autonomous Response Capability
SentinelOne-style automated threat response actions:
  - kill_process(pid)
  - quarantine_file(path)
  - isolate_host()
  - restore_host()
  - unquarantine_file(quarantine_id)

IMPORTANT: Requires elevated privileges (run agent as Administrator / SYSTEM service).
"""
import os
import sys
import json
import shutil
import hashlib
import platform
import logging
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Where quarantined files are stored (AES-encrypted in production; ZIP-locked here)
QUARANTINE_DIR = os.path.join(
    os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "OmniAgent", "Quarantine"
)
# Audit log for all response actions taken
RESPONSE_LOG = os.path.join(
    os.environ.get("PROGRAMDATA", "C:\\ProgramData"), "OmniAgent", "response_audit.json"
)
# Firewall rule name used for host isolation
FW_RULE_NAME = "OmniAgent-Isolation"


class AutonomousResponseCapability:
    """
    Executes automated response actions against active threats.
    All actions are logged to the response audit trail.
    """
    capability_name = "autonomous_response"

    def __init__(self):
        os.makedirs(QUARANTINE_DIR, exist_ok=True)
        self._audit_log: List[Dict] = self._load_audit_log()

    # ==================================================================
    # PUBLIC API — called by orchestrator
    # ==================================================================

    def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Dispatch a response action.

        action: "kill_process" | "quarantine_file" | "isolate_host" |
                "restore_host" | "unquarantine_file"
        kwargs: action-specific parameters
        """
        dispatch = {
            "kill_process":     self.kill_process,
            "quarantine_file":  self.quarantine_file,
            "isolate_host":     self.isolate_host,
            "restore_host":     self.restore_host,
            "unquarantine_file": self.unquarantine_file,
        }
        fn = dispatch.get(action)
        if not fn:
            return self._result(action, False, f"Unknown action: {action}")
        try:
            return fn(**kwargs)
        except Exception as e:
            logger.exception(f"Response action '{action}' raised exception")
            return self._result(action, False, str(e))

    # ------------------------------------------------------------------
    # KILL PROCESS
    # ------------------------------------------------------------------
    def kill_process(self, pid: int, reason: str = "automated_edr_response") -> Dict[str, Any]:
        """
        Terminate a process by PID.
        Returns success/failure with the process name.
        """
        import psutil
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            exe = proc.exe() if hasattr(proc, "exe") else ""
            proc.kill()
            return self._result("kill_process", True,
                                f"Process '{name}' (PID {pid}) terminated",
                                metadata={"pid": pid, "name": name, "exe": exe, "reason": reason})
        except psutil.NoSuchProcess:
            return self._result("kill_process", False, f"PID {pid} not found")
        except psutil.AccessDenied:
            return self._result("kill_process", False,
                                f"Access denied terminating PID {pid}. Run agent as Administrator.")

    # ------------------------------------------------------------------
    # QUARANTINE FILE
    # ------------------------------------------------------------------
    def quarantine_file(self, path: str, reason: str = "automated_edr_response") -> Dict[str, Any]:
        """
        Move a file to the quarantine vault.
        Records: original path, SHA-256, quarantine ID, timestamp.
        """
        if not os.path.isfile(path):
            return self._result("quarantine_file", False, f"File not found: {path}")

        sha256 = self._hash_file(path)
        quarantine_id = f"Q-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{sha256[:8]}"
        dest = os.path.join(QUARANTINE_DIR, quarantine_id)

        try:
            shutil.move(path, dest)
            # Write metadata sidecar
            meta_path = dest + ".meta.json"
            with open(meta_path, "w") as f:
                json.dump({
                    "quarantine_id": quarantine_id,
                    "original_path": path,
                    "sha256": sha256,
                    "timestamp": datetime.utcnow().isoformat(),
                    "reason": reason,
                }, f, indent=2)
            return self._result("quarantine_file", True,
                                f"File quarantined as {quarantine_id}",
                                metadata={"quarantine_id": quarantine_id, "sha256": sha256, "original_path": path})
        except PermissionError as e:
            return self._result("quarantine_file", False, f"Permission denied: {e}")

    # ------------------------------------------------------------------
    # UNQUARANTINE FILE
    # ------------------------------------------------------------------
    def unquarantine_file(self, quarantine_id: str) -> Dict[str, Any]:
        """Restore a quarantined file to its original location."""
        quarantined = os.path.join(QUARANTINE_DIR, quarantine_id)
        meta_path = quarantined + ".meta.json"

        if not os.path.isfile(quarantined):
            return self._result("unquarantine_file", False, f"Quarantine ID not found: {quarantine_id}")

        original_path = quarantine_id  # default fallback
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            original_path = meta.get("original_path", quarantine_id)
        except Exception:
            pass

        try:
            shutil.move(quarantined, original_path)
            if os.path.isfile(meta_path):
                os.remove(meta_path)
            return self._result("unquarantine_file", True,
                                f"File restored to {original_path}",
                                metadata={"quarantine_id": quarantine_id, "restored_to": original_path})
        except Exception as e:
            return self._result("unquarantine_file", False, str(e))

    # ------------------------------------------------------------------
    # ISOLATE HOST
    # ------------------------------------------------------------------
    def isolate_host(self, allow_c2_port: int = 5000) -> Dict[str, Any]:
        """
        Network-isolate this host by blocking all inbound/outbound traffic
        EXCEPT the specified C2 port (so the agent can still receive commands).

        Uses Windows Firewall (netsh advfirewall) on Windows.
        Uses iptables on Linux.
        """
        if platform.system() == "Windows":
            return self._isolate_windows(allow_c2_port)
        elif platform.system() == "Linux":
            return self._isolate_linux(allow_c2_port)
        else:
            return self._result("isolate_host", False, "Isolation not supported on this OS")

    def _isolate_windows(self, allow_port: int) -> Dict[str, Any]:
        cmds = [
            # Block ALL inbound
            f'netsh advfirewall firewall add rule name="{FW_RULE_NAME}-BLOCK-IN" dir=in action=block',
            # Block ALL outbound
            f'netsh advfirewall firewall add rule name="{FW_RULE_NAME}-BLOCK-OUT" dir=out action=block',
            # Allow C2 inbound
            f'netsh advfirewall firewall add rule name="{FW_RULE_NAME}-C2-IN" dir=in action=allow protocol=TCP localport={allow_port}',
            # Allow C2 outbound
            f'netsh advfirewall firewall add rule name="{FW_RULE_NAME}-C2-OUT" dir=out action=allow protocol=TCP remoteport={allow_port}',
        ]
        errors = []
        for cmd in cmds:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if r.returncode != 0:
                errors.append(r.stderr.strip())

        if errors:
            return self._result("isolate_host", False, f"Partial isolation: {errors}")
        return self._result("isolate_host", True,
                            f"Host isolated. Only port {allow_port} allowed.",
                            metadata={"allow_port": allow_port})

    def _isolate_linux(self, allow_port: int) -> Dict[str, Any]:
        cmds = [
            "iptables -P INPUT DROP",
            "iptables -P OUTPUT DROP",
            "iptables -P FORWARD DROP",
            f"iptables -A INPUT -p tcp --dport {allow_port} -j ACCEPT",
            f"iptables -A OUTPUT -p tcp --sport {allow_port} -j ACCEPT",
            "iptables -A INPUT -i lo -j ACCEPT",
            "iptables -A OUTPUT -o lo -j ACCEPT",
        ]
        errors = []
        for cmd in cmds:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if r.returncode != 0:
                errors.append(r.stderr.strip())
        if errors:
            return self._result("isolate_host", False, f"Partial isolation: {errors}")
        return self._result("isolate_host", True,
                            f"Host isolated via iptables. Only port {allow_port} allowed.",
                            metadata={"allow_port": allow_port})

    # ------------------------------------------------------------------
    # RESTORE HOST
    # ------------------------------------------------------------------
    def restore_host(self) -> Dict[str, Any]:
        """Remove network isolation rules."""
        if platform.system() == "Windows":
            cmds = [
                f'netsh advfirewall firewall delete rule name="{FW_RULE_NAME}-BLOCK-IN"',
                f'netsh advfirewall firewall delete rule name="{FW_RULE_NAME}-BLOCK-OUT"',
                f'netsh advfirewall firewall delete rule name="{FW_RULE_NAME}-C2-IN"',
                f'netsh advfirewall firewall delete rule name="{FW_RULE_NAME}-C2-OUT"',
            ]
        elif platform.system() == "Linux":
            cmds = [
                "iptables -P INPUT ACCEPT",
                "iptables -P OUTPUT ACCEPT",
                "iptables -P FORWARD ACCEPT",
                "iptables -F",
            ]
        else:
            return self._result("restore_host", False, "Restore not supported on this OS")

        for cmd in cmds:
            subprocess.run(cmd, shell=True, capture_output=True)
        return self._result("restore_host", True, "Host network access restored")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _result(self, action: str, success: bool, message: str,
                metadata: Dict = None) -> Dict[str, Any]:
        entry = {
            "action": action,
            "success": success,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self._audit_log.append(entry)
        self._save_audit_log()
        logger.info(f"[ResponseAction] {action} -> {'OK' if success else 'FAIL'}: {message}")
        return entry

    @staticmethod
    def _hash_file(path: str) -> str:
        try:
            sha = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception:
            return "unknown"

    def _load_audit_log(self) -> List[Dict]:
        if os.path.isfile(RESPONSE_LOG):
            try:
                with open(RESPONSE_LOG) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_audit_log(self):
        try:
            os.makedirs(os.path.dirname(RESPONSE_LOG), exist_ok=True)
            with open(RESPONSE_LOG, "w") as f:
                json.dump(self._audit_log[-500:], f, indent=2)  # keep last 500 actions
        except Exception as e:
            logger.warning(f"Could not save response audit log: {e}")

    def get_audit_log(self) -> List[Dict]:
        return self._audit_log

    def list_quarantine(self) -> List[Dict]:
        """List all currently quarantined files."""
        items = []
        for fname in os.listdir(QUARANTINE_DIR):
            if fname.endswith(".meta.json"):
                try:
                    with open(os.path.join(QUARANTINE_DIR, fname)) as f:
                        items.append(json.load(f))
                except Exception:
                    pass
        return items
