"""
Runtime Security Capability
Detects and monitors for malicious runtime behavior.
YARA scanning is applied to every new process executable; falls back to
string-pattern matching when yara-python is not installed.
"""
from .base import BaseCapability
import psutil
import logging
from typing import Dict, Any, List
from datetime import datetime
from .yara_scanner import get_yara_scanner

logger = logging.getLogger(__name__)

class RuntimeSecurityCapability(BaseCapability):

    def __init__(self, config=None):
        super().__init__(config)
        self.baseline_processes = set()
        self.suspicious_processes = []
        self._auto_kill = (config or {}).get("auto_kill_critical", True)
        self._yara = get_yara_scanner()
    
    @property
    def capability_id(self) -> str:
        return "runtime_security"
    
    @property
    def capability_name(self) -> str:
        return "Runtime Security"
    
    def collect(self) -> Dict[str, Any]:
        """Monitor processes for suspicious behavior"""
        process_list = []
        connection_list = []
        new_processes = []
        
        # 1. Collect Processes
        for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'num_threads', 'status']):
            try:
                pinfo = proc.info
                name = pinfo['name']

                # Resolve executable path for YARA scanning
                try:
                    exe_path = proc.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    exe_path = None

                process_list.append({
                    "pid": pinfo['pid'],
                    "name": name,
                    "user": pinfo['username'] or "system",
                    "cpu_percent": pinfo['cpu_percent'],
                    "memory_percent": round(pinfo['memory_percent'], 2),
                    "status": pinfo['status']
                })

                # Check for new processes
                if self.baseline_processes and name not in self.baseline_processes:
                    new_processes.append({
                        "name": name,
                        "pid": pinfo['pid'],
                        "threads": pinfo['num_threads'],
                        "exe_path": exe_path,
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Update baseline
        if not self.baseline_processes:
            self.baseline_processes = set([p['name'] for p in process_list])
        
        # 2. Collect Network Connections
        try:
            for conn in psutil.net_connections(kind='inet'):
                try:
                    laddr = f"{conn.laddr.ip}" if conn.laddr else "*"
                    raddr = f"{conn.raddr.ip}" if conn.raddr else "*"
                    connection_list.append({
                        "local_address": laddr,
                        "local_port": conn.laddr.port if conn.laddr else 0,
                        "remote_address": raddr,
                        "remote_port": conn.raddr.port if conn.raddr else 0,
                        "status": conn.status,
                        "pid": conn.pid
                    })
                except Exception:
                    continue
        except (psutil.AccessDenied, Exception):
            # Fallback if net_connections fails due to permissions
            pass

        # 3. Detect suspicious patterns
        suspicious = self._detect_suspicious_patterns(process_list, new_processes)

        # 4. Autonomously kill processes flagged as critical severity
        if self._auto_kill:
            for item in suspicious:
                if item.get("severity") == "critical" and item.get("pid"):
                    pid = item["pid"]
                    try:
                        proc = psutil.Process(pid)
                        proc.kill()
                        item["auto_killed"] = True
                        logger.warning(
                            "[RuntimeSecurity] Auto-killed critical process '%s' PID %d: %s",
                            item.get("name", "?"), pid, item.get("description", ""),
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as _kill_err:
                        logger.warning("[RuntimeSecurity] Could not kill PID %d: %s", pid, _kill_err)

        return {
            "processes": process_list,
            "connections": connection_list,
            "suspicious_activities": suspicious,
            "process_count": len(process_list),
            "connection_count": len(connection_list),
            "scan_time": datetime.now().isoformat()
        }
    
    def _detect_suspicious_patterns(self, processes: List, new_procs: List) -> List[Dict[str, Any]]:
        """Detect suspicious patterns via name heuristics, YARA file scan, and resource thresholds."""
        suspicious = []
        now = datetime.now().isoformat()

        # 1. Name-based heuristics
        suspicious_keywords = ['mimikatz', 'nc.exe', 'netcat', 'psexec', 'powershell -enc']
        for proc in new_procs:
            name = proc.get('name', '').lower()
            if any(keyword in name for keyword in suspicious_keywords):
                suspicious.append({
                    "type": "Suspicious Process Name",
                    "description": f"New process '{proc.get('name')}' matches penetration-testing tool keyword.",
                    "severity": "critical",
                    "pid": proc.get("pid"),
                    "name": proc.get("name"),
                    "timestamp": now,
                })

        # 2. YARA / string-pattern scan of new process executables
        for proc in new_procs:
            name = proc.get("name", "")
            exe_path = proc.get("exe_path")

            # Scan the process name string first (fast, no disk I/O)
            name_hits = self._yara.scan_string(name)
            if name_hits:
                for hit in name_hits:
                    suspicious.append({
                        "type": "YARA Match (process name)",
                        "description": (
                            f"Process '{name}' matched YARA rule '{hit['rule']}' "
                            f"(family: {hit['family']}, MITRE: {hit['mitre']})"
                        ),
                        "severity": hit["severity"],
                        "pid": proc.get("pid"),
                        "name": name,
                        "yara_rule": hit["rule"],
                        "yara_family": hit["family"],
                        "mitre": hit["mitre"],
                        "scan_type": hit["scan_type"],
                        "timestamp": now,
                    })
                continue  # name already flagged — skip file scan

            # Scan the executable binary
            if exe_path:
                file_hits = self._yara.scan_file(exe_path)
                for hit in file_hits:
                    suspicious.append({
                        "type": "YARA Match (executable)",
                        "description": (
                            f"Executable '{exe_path}' matched YARA rule '{hit['rule']}' "
                            f"(family: {hit['family']}, MITRE: {hit['mitre']})"
                        ),
                        "severity": hit["severity"],
                        "pid": proc.get("pid"),
                        "name": name,
                        "exe_path": exe_path,
                        "yara_rule": hit["rule"],
                        "yara_family": hit["family"],
                        "mitre": hit["mitre"],
                        "scan_type": hit["scan_type"],
                        "timestamp": now,
                    })

        # 3. Unusual thread counts
        for proc in new_procs:
            if proc.get('threads', 0) > 100:
                suspicious.append({
                    "type": "Unusual Thread Count",
                    "description": f"Process '{proc.get('name')}' has {proc.get('threads')} threads.",
                    "severity": "medium",
                    "timestamp": now,
                })

        # 4. High CPU usage
        for proc in processes:
            if proc['cpu_percent'] > 90:
                suspicious.append({
                    "type": "High CPU Usage",
                    "description": f"Process '{proc['name']}' (PID {proc['pid']}) using {proc['cpu_percent']}% CPU.",
                    "severity": "low",
                    "timestamp": now,
                })

        return suspicious
