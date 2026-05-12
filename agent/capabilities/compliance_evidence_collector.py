"""
Compliance Evidence Collector

Fills the gap between infrastructure checks (ComplianceEnforcementCapability)
and the full evidence set required for:
  - SOC 2 Type II  (CC6.x, CC7.x, CC9.2)
  - ISO 27001:2022  (A.8.2, A.8.5, A.8.15, A.8.16, A.5.10, A.5.33)
  - PCI DSS 4.0     (7.x, 8.x, 10.x)
  - HIPAA           (164.312(a)(1), 164.312(b), 164.308(a)(1))
  - NIST 800-53     (AC-2, AC-3, AU-9, AU-11, CM-3, CM-6, CP-9)
  - GDPR            (Art.5(1)(b)/(e), Art.25, Art.32)
  - FedRAMP         (AC-2, AU-11, CM-6, CP-9)
  - DORA            (Art.9, Art.12)

Evidence gaps addressed (not covered elsewhere in the agent):
  1. User access logs (logon/logoff/failed auth, account changes)
  2. Privileged account usage monitoring
  3. Log retention policy verification
  4. Backup existence & schedule verification
  5. Configuration change management
  6. Account lifecycle hygiene (dormant/orphaned/locked)
  7. Network firewall rules enumeration
"""

from .base import BaseCapability
import platform
import subprocess
import json
import os
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Compliance framework control mapping for evidence types
CONTROL_MAPPINGS = {
    "access_logs":          ["SOC2:CC6.2", "ISO27001:A.8.15", "PCI-DSS:10.2", "HIPAA:164.312(b)", "NIST:AU-2", "FedRAMP:AU-2"],
    "failed_logins":        ["SOC2:CC6.1", "ISO27001:A.8.5",  "PCI-DSS:10.2.4", "HIPAA:164.312(b)", "NIST:AC-7", "GDPR:Art.32"],
    "privileged_access":    ["SOC2:CC6.3", "ISO27001:A.8.2",  "PCI-DSS:7.1",  "HIPAA:164.312(a)(1)", "NIST:AC-3", "FedRAMP:AC-3"],
    "account_changes":      ["SOC2:CC6.2", "ISO27001:A.5.18", "PCI-DSS:8.2",  "HIPAA:164.312(a)(2)", "NIST:AC-2"],
    "log_retention":        ["SOC2:CC7.2", "ISO27001:A.8.15", "PCI-DSS:10.7", "HIPAA:164.312(b)", "NIST:AU-11", "FedRAMP:AU-11"],
    "backup_status":        ["SOC2:A1.2",  "ISO27001:A.8.13", "PCI-DSS:12.3", "HIPAA:164.308(a)(7)", "NIST:CP-9", "DORA:Art.12"],
    "config_change_log":    ["SOC2:CC8.1", "ISO27001:A.8.32", "PCI-DSS:6.5",  "HIPAA:164.312(b)", "NIST:CM-3", "FedRAMP:CM-3"],
    "account_lifecycle":    ["SOC2:CC6.2", "ISO27001:A.5.18", "PCI-DSS:8.2",  "HIPAA:164.312(a)(1)", "NIST:AC-2", "GDPR:Art.5(1)(e)"],
    "firewall_rules":       ["SOC2:CC6.6", "ISO27001:A.8.20", "PCI-DSS:1.3",  "HIPAA:164.312(e)(1)", "NIST:AC-17", "FedRAMP:AC-17"],
}


class ComplianceEvidenceCollectorCapability(BaseCapability):
    """
    Collects compliance evidence for access control, account lifecycle,
    log retention, backup verification, config change management, and network rules.
    """

    @property
    def capability_id(self) -> str:
        return "compliance_evidence_collector"

    @property
    def capability_name(self) -> str:
        return "Compliance Evidence Collector"

    def collect(self) -> Dict[str, Any]:
        system = platform.system()
        evidence: Dict[str, Any] = {
            "collected_at": datetime.utcnow().isoformat() + "Z",
            "platform": system,
            "controls_mapped": CONTROL_MAPPINGS,
        }

        if system == "Windows":
            evidence["access_logs"]       = self._windows_access_logs()
            evidence["failed_logins"]     = self._windows_failed_logins()
            evidence["privileged_access"] = self._windows_privileged_access()
            evidence["account_changes"]   = self._windows_account_changes()
            evidence["log_retention"]     = self._windows_log_retention()
            evidence["backup_status"]     = self._windows_backup_status()
            evidence["config_change_log"] = self._windows_config_change_log()
            evidence["account_lifecycle"] = self._windows_account_lifecycle()
            evidence["firewall_rules"]    = self._windows_firewall_rules()
        elif system == "Linux":
            evidence["access_logs"]       = self._linux_access_logs()
            evidence["failed_logins"]     = self._linux_failed_logins()
            evidence["privileged_access"] = self._linux_privileged_access()
            evidence["account_changes"]   = self._linux_account_changes()
            evidence["log_retention"]     = self._linux_log_retention()
            evidence["backup_status"]     = self._linux_backup_status()
            evidence["config_change_log"] = self._linux_config_change_log()
            evidence["account_lifecycle"] = self._linux_account_lifecycle()
            evidence["firewall_rules"]    = self._linux_firewall_rules()

        # Summary: how many evidence domains have data
        populated = sum(1 for k, v in evidence.items()
                        if k not in ("collected_at", "platform", "controls_mapped")
                        and isinstance(v, dict) and v.get("status") == "collected")
        total_domains = len(CONTROL_MAPPINGS)
        evidence["summary"] = {
            "domains_collected": populated,
            "domains_total": total_domains,
            "coverage_pct": round(populated / total_domains * 100, 1),
        }
        return evidence

    # ──────────────────────────────────────────────────────────────────────────
    # WINDOWS COLLECTORS
    # ──────────────────────────────────────────────────────────────────────────

    def _ps(self, script: str, timeout: int = 15) -> Optional[str]:
        """Run a PowerShell snippet and return stdout, or None on error."""
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=timeout
            )
            return r.stdout.strip() if r.stdout.strip() else None
        except Exception as e:
            logger.debug("PowerShell error: %s", e)
            return None

    def _ps_json(self, script: str, timeout: int = 15) -> Any:
        """Run PowerShell and parse JSON output."""
        raw = self._ps(f"{script} | ConvertTo-Json -Depth 4 -Compress", timeout)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _windows_access_logs(self) -> Dict[str, Any]:
        """
        Security Event Log: successful logons (4624) and logoffs (4634).
        Evidence for: SOC2 CC6.2, ISO27001 A.8.15, PCI-DSS 10.2.1, HIPAA 164.312(b)
        """
        try:
            script = (
                "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4624,4634; "
                "StartTime=(Get-Date).AddHours(-24)} -MaxEvents 200 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, Id, "
                "@{N='User';E={$_.Properties[5].Value}}, "
                "@{N='LogonType';E={$_.Properties[8].Value}}, "
                "@{N='WorkstationName';E={$_.Properties[11].Value}}, "
                "@{N='IpAddress';E={$_.Properties[18].Value}}"
            )
            data = self._ps_json(script)
            if data is None:
                data = []
            if isinstance(data, dict):
                data = [data]
            return {
                "status": "collected",
                "window_hours": 24,
                "event_count": len(data),
                "events": data[:100],   # cap payload
                "note": "EventID 4624=Logon, 4634=Logoff",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _windows_failed_logins(self) -> Dict[str, Any]:
        """
        Security Event Log: failed logon attempts (4625).
        Evidence for: SOC2 CC6.1, PCI-DSS 10.2.4, NIST AC-7
        """
        try:
            script = (
                "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; "
                "StartTime=(Get-Date).AddHours(-24)} -MaxEvents 500 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, "
                "@{N='TargetUser';E={$_.Properties[5].Value}}, "
                "@{N='FailureReason';E={$_.Properties[9].Value}}, "
                "@{N='IpAddress';E={$_.Properties[19].Value}}"
            )
            data = self._ps_json(script) or []
            if isinstance(data, dict):
                data = [data]
            # Group by user to highlight brute-force candidates
            by_user: Dict[str, int] = {}
            for e in data:
                u = str(e.get("TargetUser", "unknown"))
                by_user[u] = by_user.get(u, 0) + 1
            top_targets = sorted(by_user.items(), key=lambda x: -x[1])[:10]
            return {
                "status": "collected",
                "window_hours": 24,
                "total_failures": len(data),
                "unique_accounts_targeted": len(by_user),
                "top_targeted_accounts": [{"user": u, "count": c} for u, c in top_targets],
                "high_volume_threshold": 10,
                "high_volume_accounts": [u for u, c in top_targets if c >= 10],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _windows_privileged_access(self) -> Dict[str, Any]:
        """
        Track explicit admin/privileged logons (4648, 4672) and admin group membership.
        Evidence for: SOC2 CC6.3, ISO27001 A.8.2, PCI-DSS 7.1, HIPAA 164.312(a)(1)
        """
        try:
            # Special privilege assigned to new logon (4672) + explicit cred use (4648)
            priv_script = (
                "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4648,4672; "
                "StartTime=(Get-Date).AddHours(-24)} -MaxEvents 200 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, Id, "
                "@{N='SubjectUser';E={$_.Properties[1].Value}}, "
                "@{N='TargetUser';E={if($_.Id -eq 4648){$_.Properties[5].Value}else{'N/A'}}}"
            )
            priv_events = self._ps_json(priv_script) or []
            if isinstance(priv_events, dict):
                priv_events = [priv_events]

            # Local Administrators group members
            admins_script = (
                "net localgroup Administrators 2>&1 | "
                "Select-String -Pattern '^(?!-|Alias|Comment|Members|The command|$)' | "
                "ForEach-Object { $_.Line.Trim() }"
            )
            admins_raw = self._ps(admins_script) or ""
            admin_accounts = [line for line in admins_raw.splitlines() if line.strip()]

            return {
                "status": "collected",
                "window_hours": 24,
                "privileged_events_count": len(priv_events),
                "privileged_events": priv_events[:50],
                "local_admin_accounts": admin_accounts,
                "admin_count": len(admin_accounts),
                "note": "EventID 4672=Special Privileges Assigned, 4648=Explicit Credentials Used",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _windows_account_changes(self) -> Dict[str, Any]:
        """
        Account create/modify/delete/enable/disable (4720-4726, 4738, 4781).
        Evidence for: SOC2 CC6.2, PCI-DSS 8.2, NIST AC-2
        """
        try:
            script = (
                "Get-WinEvent -FilterHashtable @{LogName='Security'; "
                "Id=4720,4722,4723,4724,4725,4726,4738,4781; "
                "StartTime=(Get-Date).AddDays(-30)} -MaxEvents 500 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, Id, "
                "@{N='SubjectUser';E={$_.Properties[4].Value}}, "
                "@{N='TargetUser';E={$_.Properties[0].Value}}"
            )
            events = self._ps_json(script) or []
            if isinstance(events, dict):
                events = [events]
            event_labels = {
                4720: "Account Created",     4722: "Account Enabled",
                4723: "Password Changed",    4724: "Password Reset",
                4725: "Account Disabled",    4726: "Account Deleted",
                4738: "Account Modified",    4781: "Account Renamed",
            }
            summary: Dict[str, int] = {}
            for ev in events:
                label = event_labels.get(ev.get("Id", 0), "Unknown")
                summary[label] = summary.get(label, 0) + 1
            return {
                "status": "collected",
                "window_days": 30,
                "total_changes": len(events),
                "change_summary": summary,
                "events": events[:100],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _windows_log_retention(self) -> Dict[str, Any]:
        """
        Verify Security, System, and Application log retention settings.
        PCI-DSS 10.7 requires 12 months; most frameworks require at least 90 days.
        Evidence for: SOC2 CC7.2, PCI-DSS 10.7, NIST AU-11, FedRAMP AU-11
        """
        MINIMUM_BYTES = 200 * 1024 * 1024   # 200 MB ≈ ~90 days on typical system
        PCI_MINIMUM   = 500 * 1024 * 1024   # 500 MB target for PCI

        results = []
        for log_name in ("Security", "System", "Application"):
            try:
                script = (
                    f"$l = Get-WinEvent -ListLog '{log_name}'; "
                    f"[PSCustomObject]@{{Name='{log_name}'; "
                    f"MaxSizeBytes=$l.MaximumSizeInBytes; "
                    f"RecordCount=$l.RecordCount; "
                    f"OldestRecord=$l.OldestRecordNumber; "
                    f"Retention=$l.LogMode}}"
                )
                info = self._ps_json(script)
                if not info:
                    continue
                size_mb = round((info.get("MaxSizeBytes") or 0) / (1024 * 1024), 1)
                max_bytes = info.get("MaxSizeBytes") or 0
                results.append({
                    "log": log_name,
                    "max_size_mb": size_mb,
                    "record_count": info.get("RecordCount"),
                    "retention_mode": info.get("Retention"),
                    "meets_90day_minimum": max_bytes >= MINIMUM_BYTES,
                    "meets_pci_minimum": max_bytes >= PCI_MINIMUM,
                })
            except Exception as e:
                results.append({"log": log_name, "error": str(e)})

        all_meet_min = all(r.get("meets_90day_minimum", False) for r in results if "error" not in r)
        return {
            "status": "collected",
            "logs_checked": results,
            "all_meet_90day_minimum": all_meet_min,
            "recommendation": None if all_meet_min else "Increase Security log size to ≥200MB for 90-day retention",
        }

    def _windows_backup_status(self) -> Dict[str, Any]:
        """
        Check Windows Server Backup / wbadmin last backup status and scheduled tasks.
        Evidence for: SOC2 A1.2, ISO27001 A.8.13, NIST CP-9, DORA Art.12
        """
        results: Dict[str, Any] = {}

        # wbadmin last backup status
        try:
            raw = self._ps("wbadmin get status 2>&1 | Out-String")
            if raw:
                results["wbadmin_last_status"] = raw[:2000]
        except Exception as e:
            results["wbadmin_error"] = str(e)

        # Volume Shadow Copies (VSS) — quick count
        try:
            vss = self._ps_json(
                "Get-WmiObject Win32_ShadowCopy "
                "| Select-Object ID, VolumeName, InstallDate, ClientAccessible"
            )
            if isinstance(vss, dict):
                vss = [vss]
            results["vss_snapshot_count"] = len(vss) if vss else 0
            if vss:
                results["vss_latest"] = vss[0]
        except Exception as e:
            results["vss_error"] = str(e)

        # Scheduled backup tasks
        try:
            tasks = self._ps_json(
                "Get-ScheduledTask | Where-Object {$_.TaskName -match 'backup|vss|shadow'} "
                "| Select-Object TaskName, State, @{N='LastRun';E={(Get-ScheduledTaskInfo $_.TaskName).LastRunTime}}"
            )
            if isinstance(tasks, dict):
                tasks = [tasks]
            results["backup_scheduled_tasks"] = tasks or []
        except Exception as e:
            results["scheduled_tasks_error"] = str(e)

        results["status"] = "collected"
        results["evidence_note"] = (
            "VSS snapshots + wbadmin status + scheduled backup tasks. "
            "Manual test of restore procedure must supplement this automated evidence."
        )
        return results

    def _windows_config_change_log(self) -> Dict[str, Any]:
        """
        System configuration changes via Event IDs 4657 (registry value modified)
        and 4719 (audit policy changed) over the last 7 days.
        Evidence for: SOC2 CC8.1, ISO27001 A.8.32, PCI-DSS 6.5, NIST CM-3
        """
        try:
            script = (
                "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4657,4719; "
                "StartTime=(Get-Date).AddDays(-7)} -MaxEvents 500 -ErrorAction SilentlyContinue "
                "| Select-Object TimeCreated, Id, "
                "@{N='SubjectUser';E={$_.Properties[1].Value}}, "
                "@{N='ObjectName';E={$_.Properties[6].Value}}, "
                "@{N='OldValue';E={$_.Properties[10].Value}}, "
                "@{N='NewValue';E={$_.Properties[11].Value}}"
            )
            events = self._ps_json(script) or []
            if isinstance(events, dict):
                events = [events]
            by_type = {4657: 0, 4719: 0}
            for ev in events:
                eid = ev.get("Id", 0)
                if eid in by_type:
                    by_type[eid] += 1
            return {
                "status": "collected",
                "window_days": 7,
                "total_config_changes": len(events),
                "registry_changes_4657": by_type[4657],
                "audit_policy_changes_4719": by_type[4719],
                "changes": events[:100],
                "note": "4657=Registry Modified, 4719=Audit Policy Changed",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _windows_account_lifecycle(self) -> Dict[str, Any]:
        """
        Identify dormant (>90 days no login), locked, and disabled accounts.
        Evidence for: SOC2 CC6.2, ISO27001 A.5.18, PCI-DSS 8.2.6, GDPR Art.5(1)(e)
        """
        try:
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
            all_script = (
                "Get-LocalUser | Select-Object Name, Enabled, "
                "LastLogon, PasswordLastSet, "
                "@{N='PasswordNeverExpires';E={$_.PasswordNeverExpires}}, "
                "@{N='AccountLocked';E={try{(Get-LocalUser $_.Name).AccountExpires -and "
                "(Get-LocalUser $_.Name).AccountExpires -lt (Get-Date)}catch{$false}}}"
            )
            users = self._ps_json(all_script) or []
            if isinstance(users, dict):
                users = [users]

            dormant, disabled, never_expires = [], [], []
            for u in users:
                last = u.get("LastLogon")
                if u.get("Enabled") is False:
                    disabled.append(u.get("Name"))
                elif last and last < cutoff:
                    dormant.append(u.get("Name"))
                if u.get("PasswordNeverExpires"):
                    never_expires.append(u.get("Name"))

            return {
                "status": "collected",
                "total_accounts": len(users),
                "disabled_accounts": disabled,
                "dormant_accounts_90d": dormant,
                "password_never_expires": never_expires,
                "dormant_count": len(dormant),
                "disabled_count": len(disabled),
                "risk_flag": len(dormant) > 0 or len(never_expires) > 0,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _windows_firewall_rules(self) -> Dict[str, Any]:
        """
        Enumerate all enabled inbound firewall rules and flag any rules that
        allow * (any) remote address on sensitive ports.
        Evidence for: SOC2 CC6.6, ISO27001 A.8.20, PCI-DSS 1.3, NIST AC-17
        """
        SENSITIVE_PORTS = {21, 22, 23, 25, 53, 80, 135, 139, 443, 445, 1433, 3306, 3389, 5432, 5900, 8080, 8443}
        try:
            script = (
                "Get-NetFirewallRule -Enabled True -Direction Inbound "
                "| Select-Object Name, DisplayName, Action, Profile, "
                "@{N='Protocol';E={(Get-NetFirewallPortFilter -AssociatedNetFirewallRule $_).Protocol}}, "
                "@{N='LocalPort';E={(Get-NetFirewallPortFilter -AssociatedNetFirewallRule $_).LocalPort}}, "
                "@{N='RemoteAddress';E={(Get-NetFirewallAddressFilter -AssociatedNetFirewallRule $_).RemoteAddress}}"
            )
            rules = self._ps_json(script) or []
            if isinstance(rules, dict):
                rules = [rules]

            risky_rules = []
            for r in rules:
                remote = str(r.get("RemoteAddress", ""))
                port_str = str(r.get("LocalPort", ""))
                is_any_remote = remote.lower() in ("any", "*", "")
                try:
                    port_nums = {int(p) for p in re.findall(r"\d+", port_str)}
                except Exception:
                    port_nums = set()
                if is_any_remote and r.get("Action") == "Allow" and port_nums & SENSITIVE_PORTS:
                    risky_rules.append({
                        "name": r.get("DisplayName"),
                        "port": port_str,
                        "remote_address": remote,
                        "risk": "Sensitive port open to any remote address",
                    })

            return {
                "status": "collected",
                "total_inbound_enabled": len(rules),
                "risky_rules_count": len(risky_rules),
                "risky_rules": risky_rules,
                "all_rules": rules[:200],
                "sensitive_ports_checked": sorted(SENSITIVE_PORTS),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ──────────────────────────────────────────────────────────────────────────
    # LINUX COLLECTORS
    # ──────────────────────────────────────────────────────────────────────────

    def _sh(self, cmd: str, timeout: int = 15) -> Optional[str]:
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip() or None
        except Exception as e:
            logger.debug("Shell error: %s", e)
            return None

    def _linux_access_logs(self) -> Dict[str, Any]:
        """
        Parse /var/log/auth.log or /var/log/secure for successful logins.
        Evidence for: SOC2 CC6.2, ISO27001 A.8.15, PCI-DSS 10.2.1
        """
        log_candidates = ["/var/log/auth.log", "/var/log/secure"]
        log_file = next((f for f in log_candidates if os.path.exists(f)), None)
        if not log_file:
            return {"status": "unavailable", "reason": "No auth log found"}
        try:
            raw = self._sh(f"grep -a 'Accepted' {log_file} | tail -200")
            lines = (raw or "").splitlines()
            entries = []
            pattern = re.compile(r"(\w+\s+\d+\s+[\d:]+)\s+\S+\s+sshd\[.*?Accepted\s+(\w+)\s+for\s+(\S+)\s+from\s+([\d.]+)")
            for line in lines:
                m = pattern.search(line)
                if m:
                    entries.append({"time": m.group(1), "method": m.group(2), "user": m.group(3), "source_ip": m.group(4)})
            return {
                "status": "collected",
                "log_file": log_file,
                "successful_logins": len(entries),
                "entries": entries[-100:],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _linux_failed_logins(self) -> Dict[str, Any]:
        """
        Parse auth log for failed login attempts.
        Evidence for: SOC2 CC6.1, PCI-DSS 10.2.4, NIST AC-7
        """
        log_candidates = ["/var/log/auth.log", "/var/log/secure"]
        log_file = next((f for f in log_candidates if os.path.exists(f)), None)
        if not log_file:
            return {"status": "unavailable", "reason": "No auth log found"}
        try:
            raw = self._sh(f"grep -a 'Failed password' {log_file} | tail -500")
            lines = (raw or "").splitlines()
            by_user: Dict[str, int] = {}
            by_ip: Dict[str, int] = {}
            for line in lines:
                um = re.search(r"for\s+(\S+)\s+from", line)
                im = re.search(r"from\s+([\d.]+)", line)
                if um:
                    by_user[um.group(1)] = by_user.get(um.group(1), 0) + 1
                if im:
                    by_ip[im.group(1)] = by_ip.get(im.group(1), 0) + 1
            top_ips = sorted(by_ip.items(), key=lambda x: -x[1])[:10]
            return {
                "status": "collected",
                "total_failures": len(lines),
                "unique_accounts_targeted": len(by_user),
                "top_source_ips": [{"ip": ip, "count": c} for ip, c in top_ips],
                "high_volume_ips": [ip for ip, c in top_ips if c >= 20],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _linux_privileged_access(self) -> Dict[str, Any]:
        """
        Track sudo usage from auth log and list sudoers.
        Evidence for: SOC2 CC6.3, ISO27001 A.8.2, PCI-DSS 7.1
        """
        try:
            log_candidates = ["/var/log/auth.log", "/var/log/secure"]
            log_file = next((f for f in log_candidates if os.path.exists(f)), None)
            sudo_events = []
            if log_file:
                raw = self._sh(f"grep -a 'sudo:' {log_file} | tail -200") or ""
                sudo_events = raw.splitlines()
            sudoers = self._sh("getent group sudo wheel 2>/dev/null | awk -F: '{print $4}' | tr ',' '\\n'") or ""
            return {
                "status": "collected",
                "sudo_events_count": len(sudo_events),
                "sudo_events_sample": sudo_events[-50:],
                "sudoers_members": [u for u in sudoers.splitlines() if u],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _linux_account_changes(self) -> Dict[str, Any]:
        """
        Detect account creations/deletions/modifications from auth log and /etc/passwd mtime.
        Evidence for: SOC2 CC6.2, PCI-DSS 8.2, NIST AC-2
        """
        try:
            log_candidates = ["/var/log/auth.log", "/var/log/secure"]
            log_file = next((f for f in log_candidates if os.path.exists(f)), None)
            changes = []
            if log_file:
                raw = self._sh(f"grep -aE 'useradd|userdel|usermod|groupadd|passwd' {log_file} | tail -200") or ""
                changes = raw.splitlines()
            passwd_mtime = None
            if os.path.exists("/etc/passwd"):
                ts = os.path.getmtime("/etc/passwd")
                passwd_mtime = datetime.fromtimestamp(ts).isoformat()
            return {
                "status": "collected",
                "account_change_events": len(changes),
                "events_sample": changes[-50:],
                "etc_passwd_last_modified": passwd_mtime,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _linux_log_retention(self) -> Dict[str, Any]:
        """
        Check rsyslog/journald retention configuration.
        Evidence for: PCI-DSS 10.7, NIST AU-11, FedRAMP AU-11
        """
        results: Dict[str, Any] = {"status": "collected"}
        # journald retention
        for cfg in ("/etc/systemd/journald.conf", "/etc/systemd/journald.conf.d"):
            if os.path.exists(cfg):
                raw = self._sh(f"grep -r 'MaxRetentionSec\\|MaxFileSec\\|SystemMaxUse\\|SystemKeepFree' {cfg} 2>/dev/null")
                results["journald_retention_config"] = raw or "default (no explicit retention set)"
                break
        # rsyslog rotation
        for cfg in ("/etc/logrotate.d/syslog", "/etc/logrotate.d/rsyslog", "/etc/logrotate.conf"):
            if os.path.exists(cfg):
                raw = self._sh(f"cat {cfg}")
                results["logrotate_config"] = (raw or "")[:1000]
                break
        # journal disk usage
        raw = self._sh("journalctl --disk-usage 2>/dev/null")
        results["journal_disk_usage"] = raw
        results["recommendation"] = (
            "Ensure SystemMaxUse is unset or large enough for 90+ days, "
            "or forward logs to a SIEM/central log server."
        )
        return results

    def _linux_backup_status(self) -> Dict[str, Any]:
        """
        Check for cron-based backup jobs and presence of common backup tools.
        Evidence for: SOC2 A1.2, NIST CP-9, DORA Art.12
        """
        results: Dict[str, Any] = {"status": "collected"}
        backup_tools = ["rsync", "duplicati", "bacula", "amanda", "borgbackup", "restic", "tar"]
        installed = []
        for tool in backup_tools:
            if self._sh(f"which {tool} 2>/dev/null"):
                installed.append(tool)
        results["backup_tools_found"] = installed

        # Cron-based backups
        cron_sources = ["/etc/crontab", "/etc/cron.d", "/var/spool/cron/crontabs"]
        backup_crons = []
        for src in cron_sources:
            raw = self._sh(f"grep -rla 'rsync\\|backup\\|dump\\|tar\\|restic\\|borg' {src} 2>/dev/null")
            if raw:
                backup_crons.extend(raw.splitlines())
        results["backup_cron_files"] = list(set(backup_crons))
        results["has_backup_schedule"] = bool(backup_crons or installed)
        return results

    def _linux_config_change_log(self) -> Dict[str, Any]:
        """
        Use auditd logs (if available) to detect config file changes.
        Evidence for: SOC2 CC8.1, ISO27001 A.8.32, NIST CM-3
        """
        try:
            ausearch = self._sh("which ausearch 2>/dev/null")
            if ausearch:
                raw = self._sh("ausearch -ts today -k config_change 2>/dev/null | tail -200") or ""
                events = [l for l in raw.splitlines() if l.startswith("type=")]
                return {
                    "status": "collected",
                    "source": "auditd",
                    "config_change_events": len(events),
                    "events_sample": events[-50:],
                }
            # Fallback: recently modified /etc files
            raw = self._sh("find /etc -maxdepth 2 -newer /etc/passwd -type f 2>/dev/null | head -50") or ""
            return {
                "status": "collected",
                "source": "find /etc -newer /etc/passwd",
                "recently_modified_configs": raw.splitlines(),
                "note": "Install auditd for full config-change audit trail",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _linux_account_lifecycle(self) -> Dict[str, Any]:
        """
        Dormant, locked, and passwordless accounts on Linux.
        Evidence for: SOC2 CC6.2, PCI-DSS 8.2.6, GDPR Art.5(1)(e)
        """
        try:
            # All users with login shell
            raw_passwd = self._sh("getent passwd | awk -F: '$7 ~ /bash|sh|zsh|fish/ {print $1\"|\"$3\"|\"$7}'") or ""
            users = []
            for line in raw_passwd.splitlines():
                parts = line.split("|")
                if len(parts) == 3:
                    users.append({"name": parts[0], "uid": parts[1], "shell": parts[2]})

            # Last login times
            lastlog_raw = self._sh("lastlog -b 90 2>/dev/null | tail -n +2") or ""
            dormant = [line.split()[0] for line in lastlog_raw.splitlines() if "Never logged in" not in line and line.strip()]

            # Locked accounts
            locked_raw = self._sh("passwd -S -a 2>/dev/null | awk '$2==\"L\"{print $1}'") or ""
            locked = [l for l in locked_raw.splitlines() if l]

            # Passwordless accounts (dangerous)
            nopass_raw = self._sh("awk -F: '($2==\"\" || $2==\"!\"){print $1}' /etc/shadow 2>/dev/null") or ""
            passwordless = [l for l in nopass_raw.splitlines() if l]

            return {
                "status": "collected",
                "total_shell_users": len(users),
                "dormant_accounts_90d": dormant,
                "locked_accounts": locked,
                "passwordless_accounts": passwordless,
                "risk_flag": bool(passwordless),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _linux_firewall_rules(self) -> Dict[str, Any]:
        """
        Enumerate iptables/nftables/ufw rules and flag open sensitive ports.
        Evidence for: SOC2 CC6.6, ISO27001 A.8.20, PCI-DSS 1.3, NIST AC-17
        """
        SENSITIVE_PORTS = {21, 22, 23, 25, 53, 80, 135, 139, 443, 445, 1433, 3306, 3389, 5432, 5900}
        results: Dict[str, Any] = {"status": "collected"}
        try:
            ufw_raw = self._sh("ufw status verbose 2>/dev/null")
            if ufw_raw:
                results["ufw_status"] = ufw_raw[:3000]

            iptables_raw = self._sh("iptables -L INPUT -n --line-numbers 2>/dev/null")
            if iptables_raw:
                results["iptables_input_rules"] = iptables_raw[:3000]

            nft_raw = self._sh("nft list ruleset 2>/dev/null | head -100")
            if nft_raw:
                results["nftables_ruleset_sample"] = nft_raw

            # ss-based open ports
            ss_raw = self._sh("ss -tlnp 2>/dev/null") or ""
            open_ports: List[int] = []
            for line in ss_raw.splitlines()[1:]:
                m = re.search(r":(\d+)\s", line)
                if m:
                    open_ports.append(int(m.group(1)))
            open_ports = sorted(set(open_ports))
            risky_open = sorted(set(open_ports) & SENSITIVE_PORTS)
            results["open_listening_ports"] = open_ports
            results["risky_open_ports"] = risky_open
            results["risk_flag"] = bool(risky_open - {22, 80, 443})
        except Exception as e:
            results["error"] = str(e)
        return results
