"""
Runtime Security Capability
Detects and monitors for malicious runtime behavior
"""
from .base import BaseCapability
import psutil
from typing import Dict, Any, List
from datetime import datetime

class RuntimeSecurityCapability(BaseCapability):
    
    def __init__(self, config=None):
        super().__init__(config)
        self.baseline_processes = set()
        self.suspicious_processes = []
    
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
                        "threads": pinfo['num_threads']
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
        
        return {
            "processes": process_list,
            "connections": connection_list,
            "suspicious_activities": suspicious,
            "process_count": len(process_list),
            "connection_count": len(connection_list),
            "scan_time": datetime.now().isoformat()
        }
    
    def _detect_suspicious_patterns(self, processes: List, new_procs: List) -> List[Dict[str, Any]]:
        """Detect suspicious patterns in process behavior"""
        suspicious = []
        
        # Flag processes with suspicious names
        suspicious_keywords = ['mimikatz', 'nc.exe', 'netcat', 'psexec', 'powershell -enc']
        
        for proc in new_procs:
            name = proc.get('name', '').lower()
            if any(keyword in name for keyword in suspicious_keywords):
                suspicious.append({
                    "type": "Suspicious Process Name",
                    "description": f"New process '{proc.get('name')}' contains keywords associated with penetration testing tools.",
                    "severity": "critical",
                    "timestamp": datetime.now().isoformat()
                })
        
        # Flag unusual thread counts
        for proc in new_procs:
            if proc.get('threads', 0) > 100:
                suspicious.append({
                    "type": "Unusual Thread Count",
                    "description": f"Process '{proc.get('name')}' has an unusually high thread count ({proc.get('threads')}).",
                    "severity": "medium",
                    "timestamp": datetime.now().isoformat()
                })

        # Flag high resource usage
        for proc in processes:
            if proc['cpu_percent'] > 90:
                 suspicious.append({
                    "type": "High CPU Usage",
                    "description": f"Process '{proc['name']}' (PID {proc['pid']}) is consuming {proc['cpu_percent']}% CPU.",
                    "severity": "low",
                    "timestamp": datetime.now().isoformat()
                })
        
        return suspicious
