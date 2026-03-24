"""
Log Collection Capability
Gathers and forwards logs from the host system
"""
from .base import BaseCapability
import platform
import subprocess
from typing import Dict, Any, List

class LogsCapability(BaseCapability):
    
    @property
    def capability_id(self) -> str:
        return "log_collection"
    
    @property
    def capability_name(self) -> str:
        return "Log Collection"
    
    def collect(self) -> Dict[str, Any]:
        """Collect recent system logs"""
        system = platform.system()
        logs = []
        
        try:
            if system == "Windows":
                logs = self._collect_windows_logs()
            elif system == "Linux":
                logs = self._collect_linux_logs()
            else:
                logs = [{"message": f"Log collection not supported on {system}", "level": "INFO"}]
        except Exception as e:
            logs = [{"message": f"Log collection error: {e}", "level": "ERROR"}]
        
        return {"logs": logs, "count": len(logs)}
    
    def _collect_windows_logs(self) -> List[Dict[str, Any]]:
        """Collect Windows Event Logs (System + IIS)"""
        logs = []
        try:
            # System Logs
            result = subprocess.run(
                ['powershell', '-Command', 
                 'Get-EventLog -LogName System -Newest 10 | Select-Object TimeGenerated, EntryType, Message | ConvertTo-Json'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout:
                import json
                logs_data = json.loads(result.stdout)
                if not isinstance(logs_data, list):
                    logs_data = [logs_data]
                for log in logs_data:
                    logs.append({
                        "timestamp": log.get("TimeGenerated", ""),
                        "level": log.get("EntryType", "INFO"),
                        "source": "EventLog:System",
                        "message": log.get("Message", "")[:200]
                    })
            
            # IIS Logs (via Application Log or custom W3SVC if available)
            iis_cmd = 'Get-WinEvent -LogName "Microsoft-IIS-Configuration/Operational" -MaxEvents 5 -ErrorAction SilentlyContinue | Select-Object TimeCreated, LevelDisplayName, Message | ConvertTo-Json'
            result_iis = subprocess.run(['powershell', '-Command', iis_cmd], capture_output=True, text=True, timeout=5)
            if result_iis.returncode == 0 and result_iis.stdout.strip():
                import json
                iis_data = json.loads(result_iis.stdout)
                if not isinstance(iis_data, list):
                    iis_data = [iis_data]
                for log in iis_data:
                    logs.append({
                        "timestamp": log.get("TimeCreated", ""),
                        "level": log.get("LevelDisplayName", "INFO"),
                        "source": "IIS:Operational",
                        "message": log.get("Message", "")[:200]
                    })
                    
        except Exception as e:
            logs.append({"message": f"Windows log error: {e}", "level": "ERROR"})
        
        return logs
    
    def _collect_linux_logs(self) -> List[Dict[str, Any]]:
        """Collect Linux system logs and web service logs"""
        logs = []
        try:
            # System logs via journalctl
            result = subprocess.run(
                ['journalctl', '-n', '10', '--output=json'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import json
                for line in result.stdout.strip().split('\n'):
                    if line:
                        log = json.loads(line)
                        logs.append({
                            "timestamp": log.get("__REALTIME_TIMESTAMP", ""),
                            "level": log.get("PRIORITY", "INFO"),
                            "source": "journal",
                            "message": log.get("MESSAGE", "")[:200]
                        })
            
            # Web Service logs (Nginx/Apache)
            web_log_paths = [
                "/var/log/nginx/access.log",
                "/var/log/nginx/error.log",
                "/var/log/apache2/access.log",
                "/var/log/apache2/error.log"
            ]
            import os
            for path in web_log_paths:
                if os.path.exists(path):
                    try:
                        with open(path, 'r') as f:
                            all_lines = f.readlines()
                            last_lines = all_lines[-5:]
                            for line in last_lines:
                                logs.append({
                                    "timestamp": datetime.now().isoformat(),
                                    "level": "INFO",
                                    "source": f"web_log:{os.path.basename(path)}",
                                    "message": line.strip()[:200]
                                })
                    except Exception as e:
                        logger.warning(f"Failed to read log {path}: {e}")
            
            return logs
        except Exception as e:
            return [{"message": f"Linux log error: {e}", "level": "ERROR"}]
        return []
