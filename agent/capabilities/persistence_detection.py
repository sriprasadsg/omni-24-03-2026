"""
Persistence Detection Capability
Scans for common persistence mechanisms on Windows and Linux.
"""
import os
import sys
import logging
import subprocess
from typing import Dict, Any, List
from .base import BaseCapability

logger = logging.getLogger(__name__)

# Commands that suggest malicious persistence when found in a scheduled/startup entry
_SUSPICIOUS_KEYWORDS = [
    "powershell", "cmd.exe", "wscript", "cscript", "mshta", "rundll32",
    "regsvr32", "certutil", "bitsadmin", "curl", "wget", "nc ", "ncat",
    "python", "perl", "ruby", "base64", "encodedcommand", "-enc ",
    "/tmp/", "\\temp\\", "\\appdata\\local\\temp\\",
]

def _risk_score(command: str) -> str:
    cmd_lower = (command or "").lower()
    hits = sum(1 for kw in _SUSPICIOUS_KEYWORDS if kw in cmd_lower)
    if hits >= 2:
        return "Critical"
    if hits == 1:
        return "High"
    if "appdata" in cmd_lower or "temp" in cmd_lower:
        return "Medium"
    return "Low"


class PersistenceDetectionCapability(BaseCapability):

    @property
    def capability_id(self) -> str:
        return "persistence_detection"

    @property
    def capability_name(self) -> str:
        return "Persistence Detection"

    def collect(self) -> Dict[str, Any]:
        findings = []
        try:
            if os.name == "nt":
                findings = self._scan_windows()
            else:
                findings = self._scan_linux()
        except Exception as e:
            logger.error("Persistence scan failed: %s", e)
            return {"error": str(e), "findings": []}

        critical = sum(1 for f in findings if f["severity"] == "Critical")
        high     = sum(1 for f in findings if f["severity"] == "High")
        return {
            "findings": findings,
            "count": len(findings),
            "critical_count": critical,
            "high_count": high,
            "platform": os.name,
        }

    # ── Windows ───────────────────────────────────────────────────────────────

    def _scan_windows(self) -> List[Dict[str, Any]]:
        findings = []
        try:
            import winreg
        except ImportError:
            return findings

        run_keys = [
            (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_CURRENT_USER,  r"Software\Microsoft\Windows\CurrentVersion\RunServices"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunServices"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows NT\CurrentVersion\Winlogon"),
            (winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Services"),
            # WOW64 variants
            (winreg.HKEY_CURRENT_USER,  r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run"),
        ]

        for hkey, path in run_keys:
            hive = "HKCU" if hkey == winreg.HKEY_CURRENT_USER else "HKLM"
            try:
                with winreg.OpenKey(hkey, path) as key:
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            severity = _risk_score(value)
                            findings.append({
                                "type": "Registry Run Key",
                                "location": f"{hive}\\{path}",
                                "name": name,
                                "command": value,
                                "severity": severity,
                            })
                            i += 1
                        except OSError:
                            break
            except Exception:
                continue

        # Startup folders
        startup_paths = [
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup",
        ]
        for path in startup_paths:
            if os.path.isdir(path):
                for item in os.listdir(path):
                    full = os.path.join(path, item)
                    findings.append({
                        "type": "Startup Folder",
                        "location": path,
                        "name": item,
                        "command": full,
                        "severity": _risk_score(item),
                    })

        # Scheduled tasks via schtasks
        findings.extend(self._scan_schtasks())

        return findings

    def _scan_schtasks(self) -> List[Dict[str, Any]]:
        findings = []
        try:
            output = subprocess.check_output(
                ["schtasks", "/query", "/fo", "CSV", "/v"],
                stderr=subprocess.DEVNULL,
                timeout=30,
            ).decode(errors="replace")
            for line in output.splitlines():
                if "Run As User" in line or "Task To Run" not in line:
                    continue
                parts = line.split(",")
                if len(parts) >= 9:
                    task_name = parts[0].strip().strip('"')
                    task_cmd  = parts[8].strip().strip('"')
                    if task_name and task_cmd and task_cmd.upper() != "TASK TO RUN":
                        severity = _risk_score(task_cmd)
                        if severity in ("Critical", "High", "Medium"):
                            findings.append({
                                "type": "Scheduled Task",
                                "location": "Windows Task Scheduler",
                                "name": task_name,
                                "command": task_cmd,
                                "severity": severity,
                            })
        except Exception as e:
            logger.debug("schtasks scan failed: %s", e)
        return findings

    # ── Linux ─────────────────────────────────────────────────────────────────

    def _scan_linux(self) -> List[Dict[str, Any]]:
        findings = []

        # systemd services
        for systemd_dir in ["/etc/systemd/system", "/lib/systemd/system", "/usr/lib/systemd/system"]:
            if os.path.isdir(systemd_dir):
                for item in os.listdir(systemd_dir):
                    if item.endswith(".service"):
                        full = os.path.join(systemd_dir, item)
                        cmd_line = self._read_service_exec(full)
                        findings.append({
                            "type": "systemd Service",
                            "location": full,
                            "name": item,
                            "command": cmd_line,
                            "severity": _risk_score(cmd_line),
                        })

        # user crontab
        try:
            output = subprocess.check_output(["crontab", "-l"], stderr=subprocess.STDOUT, timeout=5).decode()
            for line in output.splitlines():
                if line.strip() and not line.startswith("#"):
                    findings.append({
                        "type": "Crontab Entry",
                        "location": "User Crontab",
                        "name": "Cron Job",
                        "command": line.strip(),
                        "severity": _risk_score(line),
                    })
        except Exception:
            pass

        # /etc/cron.d/ and /etc/cron.* directories
        for cron_dir in ["/etc/cron.d", "/etc/cron.hourly", "/etc/cron.daily",
                         "/etc/cron.weekly", "/etc/cron.monthly"]:
            if os.path.isdir(cron_dir):
                for item in os.listdir(cron_dir):
                    full = os.path.join(cron_dir, item)
                    if os.path.isfile(full):
                        try:
                            content = open(full).read()
                            for line in content.splitlines():
                                if line.strip() and not line.startswith("#"):
                                    findings.append({
                                        "type": "Cron File",
                                        "location": full,
                                        "name": item,
                                        "command": line.strip(),
                                        "severity": _risk_score(line),
                                    })
                        except Exception:
                            pass

        # /etc/profile.d/ scripts
        if os.path.isdir("/etc/profile.d"):
            for item in os.listdir("/etc/profile.d"):
                full = os.path.join("/etc/profile.d", item)
                if os.path.isfile(full):
                    findings.append({
                        "type": "Profile Script",
                        "location": full,
                        "name": item,
                        "command": f"(loaded at login)",
                        "severity": "Low",
                    })

        # User shell config files
        for shell_file in [
            os.path.expanduser("~/.bashrc"),
            os.path.expanduser("~/.bash_profile"),
            os.path.expanduser("~/.profile"),
            os.path.expanduser("~/.zshrc"),
            "/root/.bashrc",
            "/root/.bash_profile",
        ]:
            if os.path.isfile(shell_file):
                try:
                    for line in open(shell_file):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            sev = _risk_score(stripped)
                            if sev in ("Critical", "High"):
                                findings.append({
                                    "type": "Shell Config",
                                    "location": shell_file,
                                    "name": os.path.basename(shell_file),
                                    "command": stripped,
                                    "severity": sev,
                                })
                except Exception:
                    pass

        # /etc/ld.so.preload — library injection
        if os.path.isfile("/etc/ld.so.preload"):
            try:
                content = open("/etc/ld.so.preload").read().strip()
                if content:
                    findings.append({
                        "type": "LD_PRELOAD Hijack",
                        "location": "/etc/ld.so.preload",
                        "name": "ld.so.preload",
                        "command": content,
                        "severity": "Critical",
                    })
            except Exception:
                pass

        return findings

    def _read_service_exec(self, path: str) -> str:
        try:
            for line in open(path):
                if line.strip().startswith("ExecStart="):
                    return line.strip()[len("ExecStart="):]
        except Exception:
            pass
        return "N/A"
