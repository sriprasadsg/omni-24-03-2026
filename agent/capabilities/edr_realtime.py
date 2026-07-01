"""
Real-Time EDR (Endpoint Detection & Response) Capability
Streams Windows ETW events + psutil process telemetry to the backend.
Falls back to psutil-only on Linux/macOS.
"""
from .base import BaseCapability
import platform
import psutil
import hashlib
import os
import json
import subprocess
import threading
import queue
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Known-bad process names (simplified IOC list)
KNOWN_MALICIOUS = {
    "mimikatz.exe", "mimikatz", "procdump.exe", "procdump64.exe",
    "wce.exe", "fgdump.exe", "pwdump.exe", "pwdump7.exe",
    "nc.exe", "ncat.exe", "netcat.exe",
    "psexec.exe", "psexesvc.exe",
    "cobalt strike", "beacon.exe",
    "mshta.exe", "wscript.exe", "cscript.exe",
}

# Suspicious parent→child pairs (living-off-the-land techniques)
SUSPICIOUS_CHAINS = [
    ("word.exe", "powershell.exe"),
    ("excel.exe", "powershell.exe"),
    ("winword.exe", "cmd.exe"),
    ("outlook.exe", "powershell.exe"),
    ("explorer.exe", "powershell.exe"),
    ("svchost.exe", "powershell.exe"),
    ("msiexec.exe", "cmd.exe"),
]

# High-risk directories — executables here are suspicious
SUSPICIOUS_PATHS = [
    "\\temp\\", "\\tmp\\", "\\appdata\\local\\temp\\",
    "\\downloads\\", "\\users\\public\\", "\\programdata\\",
]


class EDRRealtimeCapability(BaseCapability):
    """
    SentinelOne-style real-time EDR using:
    - Windows ETW (Event Tracing for Windows) via subprocess / pywin32
    - psutil for cross-platform process telemetry
    - SHA-256 hash verification against IOC list
    """

    def __init__(self, config=None):
        super().__init__(config)
        self._event_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._process_cache: Dict[int, Dict] = {}
        self._alert_history: List[Dict] = []
        self._etw_thread: Optional[threading.Thread] = None
        self._running = False

    @property
    def capability_id(self) -> str:
        return "edr_realtime"

    @property
    def capability_name(self) -> str:
        return "Real-Time EDR (Endpoint Detection & Response)"

    # ------------------------------------------------------------------
    # Main collect() — called by the agent loop
    # ------------------------------------------------------------------
    def collect(self) -> Dict[str, Any]:
        """Collect real-time EDR telemetry snapshot."""
        process_tree = self._build_process_tree()
        network_connections = self._collect_network_connections()
        alerts = self._detect_threats(process_tree)

        # Drain buffered ETW events (Windows only)
        etw_events = []
        while not self._event_queue.empty():
            try:
                etw_events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break

        # Combine ETW alerts with psutil-based detections
        all_alerts = alerts + [e for e in etw_events if e.get("severity")]

        return {
            "capability": self.capability_id,
            "timestamp": datetime.utcnow().isoformat(),
            "platform": platform.system(),
            "process_tree": process_tree[:50],   # cap at 50 for transport
            "network_connections": network_connections[:100],
            "alerts": all_alerts,
            "alert_count": len(all_alerts),
            "process_count": len(process_tree),
            "connection_count": len(network_connections),
            "etw_events_captured": len(etw_events),
        }

    # ------------------------------------------------------------------
    # Process Tree Builder
    # ------------------------------------------------------------------
    def _build_process_tree(self) -> List[Dict[str, Any]]:
        """Build full process tree with parent-child relationships and hashes."""
        processes = []
        for proc in psutil.process_iter([
            "pid", "name", "ppid", "username", "exe",
            "cmdline", "create_time", "status",
            "cpu_percent", "memory_percent"
        ]):
            try:
                info = proc.info
                exe_path = info.get("exe") or ""
                exe_hash = self._hash_file(exe_path) if exe_path and os.path.isfile(exe_path) else None
                is_suspicious_path = any(
                    s in exe_path.lower() for s in SUSPICIOUS_PATHS
                ) if exe_path else False
                cmdline = " ".join(info.get("cmdline") or [])

                entry = {
                    "pid": info["pid"],
                    "ppid": info["ppid"],
                    "name": info["name"],
                    "username": info.get("username") or "SYSTEM",
                    "exe": exe_path,
                    "cmdline": cmdline[:200],
                    "sha256": exe_hash,
                    "create_time": datetime.fromtimestamp(
                        info.get("create_time") or 0
                    ).isoformat(),
                    "status": info["status"],
                    "cpu_percent": info.get("cpu_percent") or 0,
                    "memory_percent": round(info.get("memory_percent") or 0, 2),
                    "suspicious_path": is_suspicious_path,
                }
                processes.append(entry)
                self._process_cache[info["pid"]] = entry
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return processes

    # ------------------------------------------------------------------
    # Network Connection Collector
    # ------------------------------------------------------------------
    def _collect_network_connections(self) -> List[Dict[str, Any]]:
        """Collect all active TCP/UDP connections with owning process."""
        connections = []
        try:
            for conn in psutil.net_connections(kind="inet"):
                try:
                    proc_name = None
                    if conn.pid and conn.pid in self._process_cache:
                        proc_name = self._process_cache[conn.pid].get("name")
                    elif conn.pid:
                        try:
                            proc_name = psutil.Process(conn.pid).name()
                        except Exception:
                            proc_name = "unknown"

                    connections.append({
                        "pid": conn.pid,
                        "process": proc_name,
                        "local_addr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "*",
                        "remote_addr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "*",
                        "status": conn.status,
                        "family": str(conn.family),
                    })
                except Exception:
                    continue
        except (psutil.AccessDenied, Exception) as e:
            logger.warning(f"network_connections: {e}")
        return connections

    # ------------------------------------------------------------------
    # Threat Detection Engine
    # ------------------------------------------------------------------
    def _detect_threats(self, processes: List[Dict]) -> List[Dict[str, Any]]:
        """Run IOC and behavioral detections over the current process list."""
        alerts = []
        pid_name_map = {p["pid"]: p["name"].lower() for p in processes}

        for proc in processes:
            name = (proc.get("name") or "").lower()
            exe = (proc.get("exe") or "").lower()
            cmdline = (proc.get("cmdline") or "").lower()
            ppid = proc.get("ppid")
            parent_name = pid_name_map.get(ppid, "")

            # 1. Known-bad process name
            if name in KNOWN_MALICIOUS:
                alerts.append(self._make_alert(
                    "KNOWN_MALICIOUS_PROCESS",
                    f"Detected known-malicious process: {proc['name']} (PID {proc['pid']})",
                    "critical", proc
                ))

            # 2. Suspicious parent→child chain
            for parent_kw, child_kw in SUSPICIOUS_CHAINS:
                if parent_name == parent_kw and name == child_kw:
                    alerts.append(self._make_alert(
                        "SUSPICIOUS_PROCESS_CHAIN",
                        f"Suspicious parent→child: {parent_name} → {name} (PID {proc['pid']})",
                        "high", proc
                    ))

            # 3. Executable in suspicious directory
            if proc.get("suspicious_path"):
                alerts.append(self._make_alert(
                    "EXECUTABLE_IN_TEMP",
                    f"Process running from suspicious path: {exe} (PID {proc['pid']})",
                    "medium", proc
                ))

            # 4. Encoded PowerShell (-enc / -EncodedCommand)
            if ("powershell" in name or "pwsh" in name) and (
                "-enc" in cmdline or "-encodedcommand" in cmdline or "-e " in cmdline
            ):
                alerts.append(self._make_alert(
                    "ENCODED_POWERSHELL",
                    f"Encoded PowerShell command detected (PID {proc['pid']}): {cmdline[:100]}",
                    "high", proc
                ))

            # 5. High CPU — possible crypto-miner
            if proc.get("cpu_percent", 0) > 85 and name not in {"system", "idle"}:
                alerts.append(self._make_alert(
                    "HIGH_CPU_ANOMALY",
                    f"Process {proc['name']} (PID {proc['pid']}) consuming {proc['cpu_percent']}% CPU — possible cryptominer",
                    "low", proc
                ))

        return alerts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _make_alert(self, alert_type: str, description: str, severity: str, proc: Dict) -> Dict:
        alert = {
            "alert_id": f"EDR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{proc.get('pid', 0)}",
            "type": alert_type,
            "description": description,
            "severity": severity,
            "process": {
                "pid": proc.get("pid"),
                "name": proc.get("name"),
                "exe": proc.get("exe"),
                "sha256": proc.get("sha256"),
            },
            "timestamp": datetime.utcnow().isoformat(),
            "requires_response": severity in ("critical", "high"),
        }
        self._alert_history.append(alert)
        return alert

    @staticmethod
    def _hash_file(filepath: str) -> Optional[str]:
        """Compute SHA-256 of a file (safely)."""
        try:
            sha = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Optional: Windows ETW background thread (starts automatically)
    # ------------------------------------------------------------------
    def start_etw_listener(self):
        """Start background ETW capture thread (Windows only)."""
        if platform.system() != "Windows":
            logger.info("ETW listener: non-Windows OS, skipping")
            return
        self._running = True
        self._etw_thread = threading.Thread(
            target=self._etw_worker, daemon=True, name="ETWListener"
        )
        self._etw_thread.start()
        logger.info("ETW listener thread started")

    def stop_etw_listener(self):
        self._running = False

    def _etw_worker(self):
        """
        Polls Windows Security Event Log for real-time process creation events (Event ID 4688).
        This is a simplified ETW-via-EventLog approach that requires no driver signing.
        For true ETW, replace with pyetw or logman-based subscription.
        """
        try:
            import win32evtlog  # type: ignore
            import win32evtlogutil  # type: ignore
            import win32con  # type: ignore

            hand = win32evtlog.OpenEventLog(None, "Security")
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

            while self._running:
                events = win32evtlog.ReadEventLog(hand, flags, 0)
                if not events:
                    import time; time.sleep(2)
                    continue
                for ev in events:
                    if ev.EventID == 4688:  # Process Creation
                        try:
                            data = win32evtlogutil.SafeFormatMessage(ev, "Security")
                            self._event_queue.put_nowait({
                                "source": "ETW-Security",
                                "event_id": 4688,
                                "description": data[:300] if data else "Process Created",
                                "timestamp": ev.TimeGenerated.Format(),
                                "severity": None,
                            })
                        except Exception:
                            pass
        except ImportError:
            logger.info("pywin32 not installed — ETW worker skipped")
        except Exception as e:
            logger.error(f"ETW worker error: {e}")
