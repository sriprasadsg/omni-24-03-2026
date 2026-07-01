"""
Raw Log Shipper Capability
Collects raw OS logs (Syslog and Windows Event Logs) and forwards them to the backend SIEM engine.
"""
from .base import BaseCapability
import platform
import os
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

    # Security log needs SeSecurityPrivilege / admin; System and Application do not.
    _WIN_LOG_PRIORITY = ["Security", "System", "Application"]

    def _collect_windows_event_logs(self) -> List[Dict[str, Any]]:
        """
        Collect Windows Event Log entries.  Attempts Security first; if access is denied
        (error 1314 – privilege not held, or 5 – access denied) falls back to
        System + Application so the agent still ships useful logs without admin rights.
        Fallback: if pywin32 is unavailable, uses PowerShell Get-WinEvent.
        """
        logs = []
        try:
            import win32evtlog
            import win32evtlogutil

            server = "localhost"
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

            accessible = []
            denied = []
            for logtype in self._WIN_LOG_PRIORITY:
                try:
                    hand = win32evtlog.OpenEventLog(server, logtype)
                    events = win32evtlog.ReadEventLog(hand, flags, 0)
                    win32evtlog.CloseEventLog(hand)
                    accessible.append((logtype, events))
                except Exception as open_err:
                    # winerror 5 = Access Denied, 1314 = Privilege not held
                    # winerror 6 = Invalid Handle (transient ReadEventLog issue — treat as soft skip)
                    winerr = getattr(open_err, "winerror", None)
                    if winerr in (5, 6, 1314):
                        denied.append(logtype)
                        print(f"[LogShipper] {logtype} log access denied (need admin) – skipping")
                    else:
                        print(f"[LogShipper] Could not open {logtype} log: {open_err}")

            for logtype, events in accessible:
                for ev in events[:50]:
                    try:
                        msg = win32evtlogutil.SafeFormatMessage(ev, logtype)
                    except Exception:
                        msg = "Could not format message"
                    logs.append({
                        "source": f"windows_event_log_{logtype.lower()}",
                        "event_id": ev.EventID & 0xFFFF,
                        "event_category": ev.EventCategory,
                        "event_type": ev.EventType,
                        "raw_message": str(msg),
                        "computer_name": ev.ComputerName,
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                    })

            if denied and not accessible:
                # All logs denied — try PowerShell fallback (non-Security only)
                logs.extend(self._collect_windows_logs_powershell())
            elif denied:
                logs.append({
                    "source": "log_shipper_meta",
                    "raw_message": (
                        f"[LogShipper] Logs collected from: {[l for l,_ in accessible]}. "
                        f"Skipped (needs admin): {denied}"
                    ),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })

        except ImportError:
            # pywin32 not available — use PowerShell
            logs.extend(self._collect_windows_logs_powershell())
        except Exception as e:
            print(f"[LogShipper] Unexpected error reading Windows event logs: {e}")

        return logs

    def _collect_windows_logs_powershell(self) -> List[Dict[str, Any]]:
        """Fallback: use PowerShell Get-WinEvent to read System + Application logs."""
        logs = []
        try:
            import subprocess, json as _json
            script = (
                "Get-WinEvent -FilterHashtable @{LogName='System','Application'; "
                "StartTime=(Get-Date).AddHours(-1)} -MaxEvents 100 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message "
                "| ConvertTo-Json -Compress"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=20,
            )
            events = _json.loads(r.stdout.strip()) if r.stdout.strip() else []
            if isinstance(events, dict):
                events = [events]
            for ev in events:
                logs.append({
                    "source": "windows_event_log_ps_fallback",
                    "event_id": ev.get("Id"),
                    "raw_message": str(ev.get("Message", ""))[:500],
                    "provider": ev.get("ProviderName"),
                    "level": ev.get("LevelDisplayName"),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            print(f"[LogShipper] PowerShell fallback failed: {e}")
        return logs

    # ── Local buffer (disk-backed, survives process restart) ──────────────────

    def _buffer_path(self) -> str:
        import os, tempfile
        agent_id = self.config.get("agent_id", "unknown")
        return os.path.join(tempfile.gettempdir(), f"log_buffer_{agent_id}.jsonl")

    def _write_to_buffer(self, logs: List[Dict[str, Any]]) -> None:
        import json
        try:
            with open(self._buffer_path(), "a", encoding="utf-8") as fh:
                for entry in logs:
                    fh.write(json.dumps(entry) + "\n")
            print(f"[LogShipper] Buffered {len(logs)} log(s) to disk for later retry.")
        except Exception as exc:
            print(f"[LogShipper] Could not write to local buffer: {exc}")

    def _flush_buffer(self) -> List[Dict[str, Any]]:
        """Read and clear the local buffer; returns buffered logs."""
        import json, os
        path = self._buffer_path()
        if not os.path.exists(path):
            return []
        buffered = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            buffered.append(json.loads(line))
                        except Exception:
                            pass
            os.remove(path)
        except Exception as exc:
            print(f"[LogShipper] Could not read local buffer: {exc}")
        return buffered

    # ── Shipping ──────────────────────────────────────────────────────────────

    def _post_logs(self, logs: List[Dict[str, Any]]) -> bool:
        """Low-level POST to backend; returns True on success."""
        import requests as _req
        backend_url = self.config.get("api_base_url", "http://localhost:5000")
        api_key = self.config.get("api_key", "")
        agent_id = self.config.get("agent_id", "unknown")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = _req.post(
            f"{backend_url.rstrip('/')}/api/agents/{agent_id}/logs/raw",
            json={"logs": logs, "agent_id": agent_id},
            headers=headers,
            timeout=10,
        )
        if resp.status_code not in (200, 201, 204):
            print(f"[LogShipper] Backend returned {resp.status_code}")
            return False
        return True

    def _ship_logs_to_backend(self, logs: List[Dict[str, Any]]) -> bool:
        """
        POST collected logs to the backend SIEM.
        On failure: writes to a local disk buffer so logs are not lost.
        On next successful call: flushes buffered logs first.
        """
        if not logs:
            return True

        # Try to flush any previously buffered logs first
        buffered = self._flush_buffer()
        all_logs = buffered + logs

        try:
            success = self._post_logs(all_logs)
            if not success:
                self._write_to_buffer(all_logs)
            return success
        except Exception as exc:
            print(f"[LogShipper] Failed to ship logs: {exc}")
            self._write_to_buffer(all_logs)
            return False

    def collect(self) -> Dict[str, Any]:
        """Collect raw OS logs and ship them to the backend SIEM."""
        logs: List[Dict[str, Any]] = []
        if self.os_type == 'windows':
            logs = self._collect_windows_event_logs()
        elif self.os_type in ['linux', 'darwin']:
            logs = self._collect_linux_syslog()

        shipped = self._ship_logs_to_backend(logs)
        return {
            "status": "active",
            "logs_shipped": len(logs) if shipped else 0,
            "ship_success": shipped,
            "raw_logs": logs,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
