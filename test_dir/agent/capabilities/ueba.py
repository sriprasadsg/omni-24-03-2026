"""
UEBA (User and Entity Behavior Analytics) Capability
Monitors user and entity behavior for anomalies
"""
from .base import BaseCapability
import platform
import subprocess
from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict

class UEBACapability(BaseCapability):
    
    def __init__(self, config=None):
        super().__init__(config)
        self.login_history = defaultdict(list)
        self.failed_attempts = defaultdict(int)
    
    @property
    def capability_id(self) -> str:
        return "ueba"
    
    @property
    def capability_name(self) -> str:
        return "Behavior Analytics (UEBA)"
    
    def collect(self) -> Dict[str, Any]:
        """Monitor user behavior for anomalies"""
        system = platform.system()
        events = []
        anomalies = []
        
        if system == "Windows":
            events = self._collect_windows_events()
        elif system == "Linux":
            events = self._collect_linux_events()
        
        # Analyze for anomalies
        anomalies = self._analyze_behavior(events)
        
        return {
            "security_events": events[:10],  # Limit to 10 recent events
            "failed_login_attempts": sum(self.failed_attempts.values()),
            "anomalies_detected": anomalies,
            "monitored_users": len(self.login_history)
        }
    
    def _collect_windows_events(self) -> List[Dict[str, Any]]:
        """Collect Windows security events"""
        events = []
        try:
            # Query Security Event Log for logon events (Event ID 4624 = successful, 4625 = failed)
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-EventLog -LogName Security -Newest 20 | Where-Object {$_.EventID -eq 4624 -or $_.EventID -eq 4625} | Select-Object TimeGenerated, EventID, Message | ConvertTo-Json'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0 and result.stdout:
                import json
                logs = json.loads(result.stdout)
                if not isinstance(logs, list):
                    logs = [logs]
                
                for log in logs:
                    event_type = "Login Success" if log.get("EventID") == 4624 else "Login Failed"
                    events.append({
                        "timestamp": log.get("TimeGenerated", ""),
                        "type": event_type,
                        "user": "Unknown",  # Would parse from Message
                        "source": "Windows Security Log"
                    })
                    
                    if event_type == "Login Failed":
                        self.failed_attempts["Unknown"] += 1
        except:
            pass
        
        return events
    
    def _collect_linux_events(self) -> List[Dict[str, Any]]:
        """Collect Linux authentication events"""
        events = []
        try:
            # Read auth.log for authentication events
            result = subprocess.run(
                ['journalctl', '_COMM=sshd', '-n', '20', '--output=json'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                import json
                for line in result.stdout.strip().split('\n'):
                    if line:
                        log = json.loads(line)
                        message = log.get("MESSAGE", "")
                        
                        if "Accepted" in message or "Failed" in message:
                            event_type = "Login Success" if "Accepted" in message else "Login Failed"
                            user = message.split("for ")[1].split(" ")[0] if "for " in message else "Unknown"
                            
                            events.append({
                                "timestamp": log.get("__REALTIME_TIMESTAMP", ""),
                                "type": event_type,
                                "user": user,
                                "source": "SSH"
                            })
                            
                            if event_type == "Login Failed":
                                self.failed_attempts[user] += 1
        except:
            pass
        
        return events
    
    def _analyze_behavior(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze events for behavioral anomalies"""
        anomalies = []
        
        # Check for brute force attempts
        for user, failed_count in self.failed_attempts.items():
            if failed_count > 5:
                anomalies.append({
                    "type": "Potential Brute Force",
                    "user": user,
                    "failed_attempts": failed_count,
                    "severity": "High"
                })
        
        # Check for unusual login times (simplified - would need historical baseline)
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour > 22:
            for event in events:
                if event["type"] == "Login Success":
                    anomalies.append({
                        "type": "Unusual Login Time",
                        "user": event.get("user", "Unknown"),
                        "hour": current_hour,
                        "severity": "Medium"
                    })
                    break
        
        return anomalies
