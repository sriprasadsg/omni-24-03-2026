"""
Backup & Restore Verification Capability

Collects automated evidence for backup existence, schedule, and restore history.
Frameworks covered:
  - SOC 2    A1.2  (Recovery / Availability)
  - ISO 27001 A.8.13 (Information Backup)
  - PCI DSS  12.3.4 (Hardware / Software Technologies Review)
  - HIPAA    164.308(a)(7) (Contingency Plan – Data Backup Plan)
  - NIST 800-53 CP-9 (System Backup)
  - DORA     Art.12 (ICT Business Continuity)
  - FedRAMP  CP-9   (System Backup)

Evidence collected:
  - Backup software / tools present on the host
  - Last successful backup timestamp (from logs / wbadmin / VSS / backup tool output)
  - Scheduled backup tasks (cron, Task Scheduler)
  - Last restore event (from Windows Backup event log, restore tool logs)
  - Backup destination reachability
  - Recovery Point Objective (RPO) compliance — gap between now and last backup
  - Recovery Time Objective (RTO) compliance — manual upload path also documented
"""

from .base import BaseCapability
import platform
import subprocess
import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# RPO thresholds — backup older than these triggers a risk flag
RPO_THRESHOLDS = {
    "critical": timedelta(hours=4),    # critical systems
    "standard": timedelta(hours=24),   # standard systems
    "archive":  timedelta(days=7),     # archive/low-criticality
}


class BackupVerifierCapability(BaseCapability):

    @property
    def capability_id(self) -> str:
        return "backup_verifier"

    @property
    def capability_name(self) -> str:
        return "Backup & Restore Verifier"

    def collect(self) -> Dict[str, Any]:
        system = platform.system()
        result: Dict[str, Any] = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "platform": system,
        }

        if system == "Windows":
            result["wbadmin"]           = self._windows_wbadmin()
            result["vss_snapshots"]     = self._windows_vss()
            result["scheduled_tasks"]   = self._windows_backup_tasks()
            result["restore_events"]    = self._windows_restore_events()
            result["backup_tools"]      = self._windows_backup_tools()
        elif system == "Linux":
            result["backup_tools"]      = self._linux_backup_tools()
            result["cron_jobs"]         = self._linux_backup_cron()
            result["restore_history"]   = self._linux_restore_history()
            result["systemd_timers"]    = self._linux_systemd_timers()

        result["rpo_assessment"]    = self._rpo_assessment(result)
        result["controls_mapped"]   = {
            "SOC2":     "A1.2",
            "ISO27001": "A.8.13",
            "PCI-DSS":  "12.3.4",
            "HIPAA":    "164.308(a)(7)",
            "NIST":     "CP-9",
            "DORA":     "Art.12",
            "FedRAMP":  "CP-9",
        }
        result["manual_evidence_note"] = (
            "Automated evidence covers backup schedules, last-run timestamps, and VSS/wbadmin output. "
            "Restore testing results (RTO verification) require a human operator to perform and must be "
            "uploaded manually via the Compliance > Evidence Upload interface."
        )
        return result

    # ── Windows ───────────────────────────────────────────────────────────────

    def _ps(self, script: str, timeout: int = 20) -> Optional[str]:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=timeout,
            )
            return r.stdout.strip() or None
        except Exception as e:
            logger.debug("PS error: %s", e)
            return None

    def _ps_json(self, script: str, timeout: int = 20) -> Any:
        raw = self._ps(f"({script}) | ConvertTo-Json -Depth 4 -Compress", timeout)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _windows_wbadmin(self) -> Dict[str, Any]:
        """
        Parse wbadmin get versions to find the most recent backup timestamp and target.
        wbadmin is Windows Server Backup CLI — available on Server and some Pro editions.
        """
        raw = self._ps("wbadmin get versions 2>&1 | Out-String", timeout=30)
        if not raw:
            return {"status": "unavailable", "reason": "wbadmin not installed or no backup configured"}

        # Extract last backup time
        last_time_match = re.search(r"Backup time:\s+(.+)", raw)
        target_match    = re.search(r"Backup target:\s+(.+)", raw)
        versions        = re.findall(r"Backup version identifier:\s+(.+)", raw)

        last_backup_str = last_time_match.group(1).strip() if last_time_match else None

        return {
            "status": "collected",
            "last_backup_time": last_backup_str,
            "backup_target": target_match.group(1).strip() if target_match else None,
            "version_count": len(versions),
            "raw_sample": raw[:1500],
        }

    def _windows_vss(self) -> Dict[str, Any]:
        """
        Volume Shadow Copies — count, latest creation time, and accessible volumes.
        """
        data = self._ps_json(
            "Get-WmiObject Win32_ShadowCopy "
            "| Select-Object ID, VolumeName, InstallDate, ClientAccessible, SetID"
        )
        if data is None:
            return {"status": "unavailable"}
        if isinstance(data, dict):
            data = [data]

        # Sort by InstallDate descending to find newest
        sorted_snaps = sorted(data, key=lambda x: str(x.get("InstallDate") or ""), reverse=True)
        latest = sorted_snaps[0] if sorted_snaps else None

        return {
            "status": "collected",
            "snapshot_count": len(data),
            "latest_snapshot": latest,
            "volumes_protected": list({s.get("VolumeName") for s in data if s.get("VolumeName")}),
        }

    def _windows_backup_tasks(self) -> Dict[str, Any]:
        """
        Enumerate Task Scheduler tasks whose name matches backup/shadow/vss keywords.
        """
        data = self._ps_json(
            "Get-ScheduledTask "
            "| Where-Object {$_.TaskName -match 'backup|vss|shadow|restore|robocopy'} "
            "| ForEach-Object { "
            "  $info = try { Get-ScheduledTaskInfo $_.TaskPath$_.TaskName -ErrorAction Stop } catch { $null }; "
            "  [PSCustomObject]@{ "
            "    Name=$_.TaskName; State=$_.State; "
            "    LastRun=if($info){$info.LastRunTime}else{'N/A'}; "
            "    NextRun=if($info){$info.NextRunTime}else{'N/A'}; "
            "    LastResult=if($info){$info.LastTaskResult}else{$null} "
            "  } "
            "}"
        )
        if isinstance(data, dict):
            data = [data]
        tasks = data or []
        failed = [t for t in tasks if t.get("LastResult") not in (0, None, "N/A", "0")]
        return {
            "status": "collected",
            "backup_tasks": tasks,
            "task_count": len(tasks),
            "failed_last_run": failed,
        }

    def _windows_restore_events(self) -> Dict[str, Any]:
        """
        Check Windows Backup Application event log (Microsoft-Windows-Backup)
        for restore operations (Event ID 4 = Restore Completed).
        Falls back to Application log entries from wbadmin source.
        """
        # Try dedicated Microsoft-Windows-Backup provider
        script = (
            "Get-WinEvent -ProviderName 'Microsoft-Windows-Backup' -MaxEvents 50 "
            "-ErrorAction SilentlyContinue "
            "| Where-Object {$_.Id -in (4, 14, 1)} "
            "| Select-Object TimeCreated, Id, Message"
        )
        data = self._ps_json(script)
        if isinstance(data, dict):
            data = [data]

        # Fallback — search Application log for wbadmin / backup restore mentions
        if not data:
            fb_script = (
                "Get-WinEvent -FilterHashtable @{LogName='Application'; "
                "ProviderName='Microsoft-Windows-Backup'; StartTime=(Get-Date).AddDays(-90)} "
                "-MaxEvents 100 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, Id, Message"
            )
            data = self._ps_json(fb_script) or []
            if isinstance(data, dict):
                data = [data]

        restore_events = [e for e in data if e.get("Id") in (4, 14)]
        last_restore = restore_events[0] if restore_events else None

        return {
            "status": "collected",
            "restore_events_found": len(restore_events),
            "last_restore_event": last_restore,
            "all_backup_events": data[:20],
            "note": "EventID 4=Restore Completed, 14=Backup Completed, 1=Backup Started",
        }

    def _windows_backup_tools(self) -> Dict[str, Any]:
        """Detect third-party backup agents installed on Windows."""
        TOOLS = ["Veeam", "Acronis", "Veritas", "Commvault", "Zerto", "Rubrik",
                 "Cohesity", "Druva", "Bacula", "Amanda", "Backup Exec"]
        raw = self._ps(
            "Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*, "
            "HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* "
            "2>$null | Select-Object -ExpandProperty DisplayName | Where-Object {$_}"
        ) or ""
        detected = [t for t in TOOLS if t.lower() in raw.lower()]
        return {
            "status": "collected",
            "third_party_backup_tools": detected,
            "windows_backup_native": "wbadmin" in (self._ps("Get-Command wbadmin 2>$null") or ""),
        }

    # ── Linux ─────────────────────────────────────────────────────────────────

    def _sh(self, cmd: str, timeout: int = 15) -> Optional[str]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip() or None
        except Exception:
            return None

    def _linux_backup_tools(self) -> Dict[str, Any]:
        """Detect backup tools and check their last-run logs."""
        TOOLS = {
            "restic":       "restic snapshots --no-lock 2>/dev/null | tail -5",
            "borg":         "borg list 2>/dev/null | tail -5",
            "rsync":        "rsync --version 2>/dev/null | head -1",
            "duplicati":    "duplicati-cli list-backups 2>/dev/null | tail -5",
            "bacula-fd":    "bacula-fd --version 2>/dev/null | head -1",
            "amanda":       "amcheck 2>/dev/null | head -3",
            "tar":          "which tar 2>/dev/null",
        }
        detected = []
        for tool, check_cmd in TOOLS.items():
            which = self._sh(f"which {tool} 2>/dev/null")
            if which:
                last_output = self._sh(check_cmd)
                detected.append({
                    "tool": tool,
                    "path": which,
                    "last_output_sample": (last_output or "")[:500],
                })
        return {
            "status": "collected",
            "backup_tools": detected,
            "tool_count": len(detected),
        }

    def _linux_backup_cron(self) -> Dict[str, Any]:
        """Find cron jobs that reference backup tools."""
        sources = ["/etc/crontab", "/etc/cron.d", "/var/spool/cron/crontabs", "/etc/cron.daily"]
        keywords = r"rsync|backup|borg|restic|tar|dump|bak|snapshot"
        found: List[Dict] = []
        for src in sources:
            if not os.path.exists(src):
                continue
            raw = self._sh(f"grep -rn '{keywords}' {src} 2>/dev/null | head -20")
            if raw:
                for line in raw.splitlines():
                    found.append({"source": src, "entry": line.strip()})
        return {
            "status": "collected",
            "backup_cron_entries": found,
            "has_backup_schedule": bool(found),
        }

    def _linux_systemd_timers(self) -> Dict[str, Any]:
        """Detect systemd timers related to backups."""
        raw = self._sh(
            "systemctl list-timers --all 2>/dev/null "
            "| grep -i 'backup\\|restic\\|borg\\|snap\\|vss' | head -20"
        ) or ""
        return {
            "status": "collected",
            "backup_timers": raw.splitlines(),
            "timer_count": len(raw.splitlines()) if raw else 0,
        }

    def _linux_restore_history(self) -> Dict[str, Any]:
        """
        Check backup tool logs for restore operations.
        Checks /var/log/syslog, journald, and tool-specific logs.
        """
        restore_lines: List[str] = []
        keywords = r"restore|recovery|recovered|extraction|extract"

        log_paths = ["/var/log/syslog", "/var/log/messages"]
        for path in log_paths:
            if os.path.exists(path):
                raw = self._sh(f"grep -ai '{keywords}' {path} | tail -20")
                if raw:
                    restore_lines.extend(raw.splitlines())

        # journald
        journal_raw = self._sh(f"journalctl -q --since='30 days ago' 2>/dev/null | grep -i '{keywords}' | tail -20")
        if journal_raw:
            restore_lines.extend(journal_raw.splitlines())

        return {
            "status": "collected",
            "restore_events_found": len(restore_lines),
            "restore_events_sample": restore_lines[-20:],
            "note": "Manual restore tests should be documented and uploaded as evidence artifacts",
        }

    # ── RPO Assessment ────────────────────────────────────────────────────────

    def _rpo_assessment(self, collected: Dict[str, Any]) -> Dict[str, Any]:
        """
        Derive a Recovery Point Objective compliance assessment from collected backup data.
        Compares last known backup timestamp against RPO thresholds.
        """
        last_backup_dt: Optional[datetime] = None

        # Try to parse last backup time from wbadmin
        wbadmin = collected.get("wbadmin", {})
        raw_time = wbadmin.get("last_backup_time")
        if raw_time:
            for fmt in ("%m/%d/%Y %I:%M %p", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %H:%M"):
                try:
                    last_backup_dt = datetime.strptime(raw_time.strip(), fmt)
                    break
                except ValueError:
                    continue

        # Try latest VSS snapshot
        if not last_backup_dt:
            vss = collected.get("vss_snapshots", {})
            latest = vss.get("latest_snapshot") or {}
            install_date = latest.get("InstallDate") or ""
            # WMI date format: "20240115103045.000000+000"
            m = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", install_date)
            if m:
                try:
                    last_backup_dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                              int(m.group(4)), int(m.group(5)), int(m.group(6)))
                except ValueError:
                    pass

        if not last_backup_dt:
            return {
                "status": "unknown",
                "reason": "Could not determine last backup timestamp automatically",
                "recommendation": "Configure wbadmin/VSS or a third-party agent and run as Administrator",
            }

        age = datetime.utcnow() - last_backup_dt
        assessment = {
            "status": "assessed",
            "last_backup_utc": last_backup_dt.isoformat(),
            "backup_age_hours": round(age.total_seconds() / 3600, 1),
            "thresholds": {k: str(v) for k, v in RPO_THRESHOLDS.items()},
        }
        if age <= RPO_THRESHOLDS["critical"]:
            assessment["compliance"] = "meets_critical_rpo"
        elif age <= RPO_THRESHOLDS["standard"]:
            assessment["compliance"] = "meets_standard_rpo"
        elif age <= RPO_THRESHOLDS["archive"]:
            assessment["compliance"] = "meets_archive_rpo_only"
        else:
            assessment["compliance"] = "rpo_breach"
            assessment["risk"] = f"Last backup is {round(age.total_seconds()/3600, 1)}h old — exceeds 7-day archive RPO"

        return assessment
