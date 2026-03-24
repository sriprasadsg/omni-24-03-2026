"""
Raw Log Shipper Capability
Collects raw OS logs (Syslog and Windows Event Logs) and forwards them to the backend SIEM engine.
"""
from .base import BaseCapability
import platform
import os
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

class LogShipperCapability(BaseCapability):
    def __init__(self, config=None):
        super().__init__(config)
        self.os_type = platform.system().lower()
        self.last_run = time.time()
        # Keep track of where we left off (simplified for demo)
        self.pointer = 0 

    @property
    def capability_id(self) -> str:
        return "log_shipper"

    @property
    def capability_name(self) -> str:
        return "Raw OS Log Shipper"

    def _collect_linux_syslog(self) -> List[Dict[str, Any]]:
        logs = []
        try:
            if os.path.exists('/var/log/syslog'):
                path = '/var/log/syslog'
            elif os.path.exists('/var/log/messages'):
                path = '/var/log/messages'
            else:
                return logs

            try:
                # Need elevated privileges for these files
                with open(path, 'r') as f:
                    # Seek to pointer
                    f.seek(0, 2) # End of file
                    current_size = f.tell()
                    
                    if self.pointer == 0 or self.pointer > current_size:
                        # First run or file rotated, just read the last 50 lines
                        self.pointer = max(0, current_size - 5000) 
                        
                    f.seek(self.pointer)
                    lines = f.readlines()
                    self.pointer = f.tell()

                    for line in lines[-50:]: # Send max 50 at a time for demo
                        line_str = line.strip()
                        if line_str:
                            logs.append({
                                "source": "syslog",
                                "raw_message": line_str,
                                "collected_at": datetime.now(timezone.utc).isoformat()
                            })
            except PermissionError:
                logs.append({
                    "source": "syslog_shipper",
                    "raw_message": "ERROR: Agent lacks permission to read /var/log/syslog. Please run as root.",
                    "collected_at": datetime.now(timezone.utc).isoformat()
                })
                
        except Exception as e:
            print(f"[LogShipper] Error reading Linux logs: {e}")
        return logs

    def _collect_windows_event_logs(self) -> List[Dict[str, Any]]:
        logs = []
        try:
            import win32evtlog
            import win32evtlogutil
            
            server = 'localhost'
            logtype = 'Security'
            
            hand = win32evtlog.OpenEventLog(server, logtype)
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            
            # Simplified tailing: Just get the last few events
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            
            for ev in events[:50]: # Max 50 for demo
                try:
                    msg = win32evtlogutil.SafeFormatMessage(ev, logtype)
                except:
                    msg = "Could not format message"
                    
                logs.append({
                    "source": "windows_event_log",
                    "event_id": ev.EventID & 0xFFFF,
                    "event_category": ev.EventCategory,
                    "event_type": ev.EventType,
                    "raw_message": str(msg),
                    "computer_name": ev.ComputerName,
                    "collected_at": datetime.now(timezone.utc).isoformat()
                })
        except ImportError:
            pass # pywin32 not installed
        except Exception as e:
            print(f"[LogShipper] Error reading Windows event logs: {e}")
            
        return logs

    def collect(self) -> Dict[str, Any]:
        """Collect raw logs and ship them"""
        logs = []
        if self.os_type == 'windows':
            logs = self._collect_windows_event_logs()
        elif self.os_type in ['linux', 'darwin']:
            logs = self._collect_linux_syslog()
            
        return {
            "status": "active",
            "logs_shipped": len(logs),
            "raw_logs": logs,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
