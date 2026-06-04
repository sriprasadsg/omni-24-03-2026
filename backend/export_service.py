import csv
import io
import re
from datetime import datetime
from database import get_database
from export_service_pdf import ExportServicePDFMixin


class ExportService(ExportServicePDFMixin):
    async def generate_report(self, report_type: str, fmt: str, tenant_id: str = None):
        data = await self._fetch_data(report_type, tenant_id)
        filename = f"{report_type.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"

        if fmt == 'csv':
            content = self._generate_csv(data)
            return content, f"{filename}.csv", "text/csv"
        elif fmt == 'pdf':
            content = self._generate_pdf(data, report_type)
            return content, f"{filename}.pdf", "application/pdf"
        else:
            raise ValueError("Unsupported format")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _fmt_bytes(self, b) -> str:
        try:
            b = int(b)
        except (TypeError, ValueError):
            return "—"
        if b == 0:
            return "—"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    def _clean_cpu(self, model: str) -> str:
        if not model:
            return "—"
        m = re.search(r'(Intel|AMD|ARM|Apple)\s+\S+(?:\s+\S+){0,4}', model)
        return m.group(0).strip() if m else model[:40]

    def _format_asset(self, asset: dict) -> dict:
        # Disks
        disks = asset.get("disks", [])
        if isinstance(disks, list) and disks:
            parts = []
            for d in disks:
                if not isinstance(d, dict):
                    continue
                mp = d.get("mountpoint") or d.get("device") or "?"
                total = self._fmt_bytes(d.get("total", 0))
                fs = d.get("fstype") or d.get("type") or ""
                parts.append(f"{mp} {total} {fs}".strip())
            disk_str = "; ".join(parts) if parts else "—"
        else:
            disk_str = "—"

        # Installed software
        software = asset.get("installedSoftware") or asset.get("installed_software") or []
        if isinstance(software, list):
            sw_count = len(software)
            names = [s.get("name", "") for s in software[:5] if isinstance(s, dict) and s.get("name")]
            sw_str = f"{sw_count} packages" + (f" ({', '.join(names)})" if names else "")
        else:
            sw_str = "—"

        # Critical files
        cf = asset.get("criticalFiles") or asset.get("critical_files") or []
        cf_str = str(len(cf)) + " files" if isinstance(cf, list) else "—"

        # Last seen — normalise timestamp formats
        last_seen = asset.get("lastSeen") or asset.get("last_seen") or ""
        if last_seen and isinstance(last_seen, (int, float)):
            try:
                last_seen = datetime.utcfromtimestamp(last_seen).strftime("%Y-%m-%d %H:%M")
            except Exception:
                last_seen = str(last_seen)

        return {
            "Hostname":          asset.get("hostname") or "—",
            "IP Address":        asset.get("ipAddress") or asset.get("ip_address") or "—",
            "OS Type":           asset.get("osType") or asset.get("os_type") or "—",
            "OS Version":        (asset.get("osVersion") or asset.get("os_version") or "—")[:40],
            "Status":            asset.get("status") or "unknown",
            "CPU Cores":         str(asset.get("cpuCores") or asset.get("cpu_cores") or "—"),
            "CPU Model":         self._clean_cpu(asset.get("cpuModel") or asset.get("cpu_model") or ""),
            "Total Memory":      self._fmt_bytes(asset.get("totalMemory") or asset.get("total_memory") or 0),
            "Disks":             disk_str,
            "Installed Software": sw_str,
            "Critical Files":    cf_str,
            "Last Seen":         str(last_seen) or "—",
            "Tenant ID":         asset.get("tenantId") or asset.get("tenant_id") or "—",
        }

    def _format_patch(self, patch: dict) -> dict:
        return {
            "Patch ID":      patch.get("id") or patch.get("patchId") or "—",
            "Title":         patch.get("title") or patch.get("name") or "—",
            "Severity":      patch.get("severity") or "—",
            "Status":        patch.get("status") or "—",
            "Asset":         patch.get("hostname") or patch.get("assetId") or "—",
            "CVE":           ", ".join(patch.get("cves") or []) or patch.get("cve") or "—",
            "Released":      str(patch.get("releaseDate") or patch.get("released") or "—"),
            "Applied":       str(patch.get("appliedAt") or patch.get("applied") or "—"),
            "Tenant ID":     patch.get("tenantId") or "—",
        }

    def _format_alert(self, alert: dict) -> dict:
        return {
            "Alert ID":      alert.get("id") or str(alert.get("_id", ""))[:12],
            "Title":         alert.get("title") or alert.get("name") or "—",
            "Severity":      alert.get("severity") or "—",
            "Status":        alert.get("status") or "—",
            "Source":        alert.get("source") or alert.get("type") or "—",
            "Asset":         alert.get("hostname") or alert.get("assetId") or "—",
            "Timestamp":     str(alert.get("timestamp") or alert.get("created_at") or "—"),
            "Tenant ID":     alert.get("tenantId") or "—",
        }

    def _format_vulnerability(self, v: dict) -> dict:
        cves = v.get("cves") or v.get("cve_ids") or []
        if isinstance(cves, list):
            cves = ", ".join(cves)
        return {
            "Vuln ID":       v.get("id") or str(v.get("_id", ""))[:12],
            "Title":         v.get("title") or v.get("name") or "—",
            "CVE":           cves or v.get("cve") or "—",
            "Severity":      v.get("severity") or "—",
            "CVSS Score":    str(v.get("cvssScore") or v.get("cvss_score") or "—"),
            "Status":        v.get("status") or "—",
            "Asset":         v.get("hostname") or v.get("assetId") or v.get("asset_id") or "—",
            "Component":     v.get("component") or v.get("package") or "—",
            "Version":       v.get("version") or "—",
            "Fixed Version": v.get("fixedVersion") or v.get("fixed_version") or "—",
            "Detected":      str(v.get("detectedAt") or v.get("created_at") or "—"),
            "Tenant ID":     v.get("tenantId") or "—",
        }

    def _format_threat_intel(self, t: dict) -> dict:
        stats = t.get("stats") or {}
        return {
            "Scan ID":       t.get("id") or str(t.get("_id", ""))[:12],
            "Artifact":      t.get("artifact") or t.get("indicator") or "—",
            "Type":          t.get("artifact_type") or t.get("type") or "—",
            "Verdict":       t.get("verdict") or "—",
            "Malicious":     str(stats.get("malicious", t.get("malicious", "—"))),
            "Suspicious":    str(stats.get("suspicious", t.get("suspicious", "—"))),
            "Harmless":      str(stats.get("harmless", t.get("harmless", "—"))),
            "Source":        t.get("source") or "VirusTotal",
            "Scanned At":    str(t.get("created_at") or t.get("scanned_at") or "—"),
            "Tenant ID":     t.get("tenantId") or "—",
        }

    def _format_sbom(self, s: dict) -> dict:
        components = s.get("components") or []
        return {
            "SBOM ID":       s.get("id") or str(s.get("_id", ""))[:12],
            "Name":          s.get("name") or "—",
            "Version":       s.get("version") or "—",
            "Format":        s.get("format") or s.get("sbom_format") or "—",
            "Asset":         s.get("assetId") or s.get("asset_id") or s.get("hostname") or "—",
            "Total Components": str(s.get("componentCount") or len(components)),
            "Critical Vulns": str(s.get("criticalVulns") or s.get("critical_vulns") or 0),
            "High Vulns":    str(s.get("highVulns") or s.get("high_vulns") or 0),
            "License Issues": str(s.get("licenseIssues") or s.get("license_issues") or 0),
            "Generated At":  str(s.get("generatedAt") or s.get("created_at") or "—"),
            "Tenant ID":     s.get("tenantId") or "—",
        }

    def _format_secret(self, s: dict) -> dict:
        return {
            "Secret ID":     s.get("id") or str(s.get("_id", ""))[:12],
            "Name":          s.get("name") or "—",
            "Type":          s.get("type") or s.get("secret_type") or "—",
            "Environment":   s.get("environment") or "—",
            "Rotation Due":  str(s.get("rotationDue") or s.get("rotation_due") or s.get("expiresAt") or "—"),
            "Last Rotated":  str(s.get("lastRotated") or s.get("last_rotated") or "—"),
            "Status":        s.get("status") or "—",
            "Owner":         s.get("owner") or s.get("createdBy") or "—",
            "Tags":          ", ".join(s.get("tags") or []) or "—",
            "Tenant ID":     s.get("tenantId") or "—",
        }

    def _format_edr_alert(self, a: dict) -> dict:
        return {
            "Alert ID":      a.get("id") or str(a.get("_id", ""))[:12],
            "Rule":          a.get("rule_name") or a.get("title") or "—",
            "Severity":      a.get("severity") or "—",
            "Category":      a.get("category") or a.get("tactic") or "—",
            "MITRE Tactic":  a.get("mitre_tactic") or a.get("tactic") or "—",
            "MITRE Technique": a.get("mitre_technique") or a.get("technique") or "—",
            "Agent ID":      a.get("agent_id") or "—",
            "Process":       a.get("process_name") or a.get("process") or "—",
            "Acknowledged":  "Yes" if a.get("acknowledged") else "No",
            "Timestamp":     str(a.get("timestamp") or a.get("created_at") or a.get("ingested_at") or "—"),
            "Tenant ID":     a.get("tenantId") or "—",
        }

    def _format_response_task(self, t: dict) -> dict:
        return {
            "Task ID":       t.get("task_id") or str(t.get("_id", ""))[:12],
            "Type":          t.get("task_type") or t.get("type") or "—",
            "Status":        t.get("status") or "—",
            "Priority":      t.get("priority") or "—",
            "Asset":         t.get("asset_id") or t.get("hostname") or "—",
            "Assigned To":   t.get("assigned_to") or "—",
            "Alert ID":      t.get("alert_id") or "—",
            "Created":       str(t.get("created_at") or "—"),
            "Completed":     str(t.get("completed_at") or "—"),
            "Notes":         (t.get("notes") or "")[:80] or "—",
            "Tenant ID":     t.get("tenantId") or "—",
        }

    # ── new format methods ────────────────────────────────────────────────────

    def _format_change(self, c: dict) -> dict:
        votes = c.get("cab_votes") or []
        approved = sum(1 for v in votes if isinstance(v, dict) and v.get("vote") == "approve")
        return {
            "Change ID":         c.get("id") or str(c.get("_id", ""))[:12],
            "Title":             c.get("title") or "—",
            "Type":              c.get("change_type") or "—",
            "Status":            c.get("status") or "—",
            "Risk Level":        c.get("risk_level") or "—",
            "Impact Level":      c.get("impact_level") or "—",
            "Assignee":          c.get("assignee") or "—",
            "Reporter":          c.get("reporter") or "—",
            "Required Approvals": str(c.get("required_approvals") or 0),
            "CAB Votes":         f"{approved}/{len(votes)}",
            "Has Rollback Plan": "Yes" if c.get("rollback_plan") else "No",
            "Scheduled Start":   str(c.get("scheduled_start") or "—"),
            "Scheduled End":     str(c.get("scheduled_end") or "—"),
            "Created At":        str(c.get("created_at") or "—"),
            "Tenant ID":         c.get("tenantId") or c.get("tenant_id") or "—",
        }

    def _format_agent_health(self, a: dict) -> dict:
        caps = a.get("capabilities") or []
        return {
            "Agent ID":       a.get("id") or str(a.get("_id", ""))[:12],
            "Hostname":       a.get("hostname") or "—",
            "IP Address":     a.get("ipAddress") or a.get("ip_address") or "—",
            "Platform":       a.get("platform") or "—",
            "OS Type":        a.get("osType") or a.get("os_type") or "—",
            "OS Version":     (a.get("osVersion") or a.get("os_version") or "—")[:40],
            "Status":         a.get("status") or "—",
            "Agent Version":  a.get("version") or a.get("agentVersion") or "—",
            "Last Seen":      str(a.get("lastSeen") or a.get("last_seen") or "—"),
            "Capabilities":   ", ".join(caps) if isinstance(caps, list) else str(caps or "—"),
            "Tenant ID":      a.get("tenantId") or a.get("tenant_id") or "—",
        }

    def _format_support_chat(self, c: dict) -> dict:
        msgs = c.get("messages") or []
        return {
            "Conversation ID":  c.get("id") or "—",
            "Subject":          c.get("subject") or "—",
            "Chat Type":        c.get("chat_type") or "—",
            "Status":           c.get("status") or "—",
            "Initiator Name":   c.get("initiator_name") or c.get("initiator_id") or "—",
            "Initiator Email":  c.get("initiator_email") or "—",
            "Initiator Role":   c.get("initiator_role") or "—",
            "Target User":      c.get("target_user_name") or c.get("target_user_id") or "—",
            "Message Count":    str(c.get("message_count") or len(msgs)),
            "Escalated":        "Yes" if c.get("escalated") else "No",
            "Escalated By":     c.get("escalated_by") or "—",
            "Created At":       str(c.get("created_at") or "—"),
            "Resolved At":      str(c.get("resolved_at") or "—"),
            "Tenant ID":        c.get("tenant_id") or "—",
        }

    def _format_endpoint_chat(self, s: dict) -> dict:
        msgs = s.get("messages") or []
        return {
            "Session ID":      s.get("id") or "—",
            "Agent Hostname":  s.get("agent_hostname") or "—",
            "Subject":         s.get("subject") or "—",
            "Status":          s.get("status") or "—",
            "Initiator ID":    s.get("initiator_id") or "—",
            "Initiator Type":  s.get("initiator_type") or "admin",
            "Message Count":   str(s.get("message_count") or len(msgs)),
            "Escalated":       "Yes" if s.get("escalated") else "No",
            "Escalated By":    s.get("escalated_by") or "—",
            "Escalation Note": (s.get("escalation_note") or "")[:120] or "—",
            "Created At":      str(s.get("created_at") or "—"),
            "Tenant ID":       s.get("tenant_id") or "—",
        }

    def _format_audit_log(self, e: dict) -> dict:
        return {
            "Event ID":      e.get("id") or str(e.get("_id", ""))[:12],
            "Action":        e.get("action") or e.get("event_type") or "—",
            "Actor":         e.get("user") or e.get("actor") or e.get("username") or "—",
            "Resource Type": e.get("resource_type") or e.get("resourceType") or "—",
            "Resource ID":   str(e.get("resource_id") or e.get("resourceId") or "—"),
            "Outcome":       e.get("outcome") or e.get("status") or "—",
            "IP Address":    e.get("ip_address") or e.get("ipAddress") or "—",
            "Tenant ID":     e.get("tenantId") or e.get("tenant_id") or "—",
            "Timestamp":     str(e.get("timestamp") or e.get("created_at") or "—"),
        }

    def _format_user_activity(self, u: dict) -> dict:
        return {
            "User ID":    u.get("id") or str(u.get("_id", ""))[:12],
            "Name":       u.get("name") or "—",
            "Email":      u.get("email") or "—",
            "Role":       u.get("role") or "—",
            "Status":     u.get("status") or "—",
            "Tenant ID":  u.get("tenantId") or "—",
            "Last Login": str(u.get("lastLogin") or u.get("last_login") or "—"),
            "Created At": str(u.get("createdAt") or u.get("created_at") or "—"),
        }

    def _format_automation(self, p: dict) -> dict:
        actions = p.get("actions") or []
        return {
            "Policy ID":    p.get("id") or str(p.get("_id", ""))[:12],
            "Name":         p.get("name") or "—",
            "Trigger Type": p.get("trigger") or p.get("trigger_type") or p.get("triggerType") or "—",
            "Actions Count": str(len(actions) if isinstance(actions, list) else 0),
            "Enabled":      "Yes" if p.get("enabled") else "No",
            "Last Run":     str(p.get("last_run") or p.get("lastRun") or "—"),
            "Run Count":    str(p.get("run_count") or p.get("runCount") or 0),
            "Created At":   str(p.get("created_at") or p.get("createdAt") or "—"),
            "Tenant ID":    p.get("tenantId") or p.get("tenant_id") or "—",
        }

    def _format_cspm(self, f: dict) -> dict:
        return {
            "Finding ID":    f.get("id") or str(f.get("_id", ""))[:12],
            "Cloud Provider": f.get("provider") or f.get("cloud_provider") or f.get("cloudProvider") or "—",
            "Account ID":    f.get("accountId") or f.get("account_id") or "—",
            "Region":        f.get("region") or "—",
            "Severity":      f.get("severity") or "—",
            "Resource Type": f.get("resourceType") or f.get("resource_type") or "—",
            "Resource ID":   f.get("resourceId") or f.get("resource_id") or "—",
            "Rule ID":       f.get("ruleId") or f.get("rule_id") or f.get("checkId") or "—",
            "Status":        f.get("status") or "—",
            "Detected At":   str(f.get("detectedAt") or f.get("detected_at") or f.get("createdAt") or "—"),
            "Remediated At": str(f.get("remediatedAt") or f.get("remediated_at") or "—"),
            "Tenant ID":     f.get("tenantId") or f.get("tenant_id") or "—",
        }

    # ── data fetching ─────────────────────────────────────────────────────────

    async def _fetch_data(self, report_type, tenant_id=None):
        db = get_database()
        query = {}
        if tenant_id:
            query["tenantId"] = tenant_id

        if report_type == 'Asset Inventory':
            cursor = db.assets.find(query, {"_id": 0})
            raw = await cursor.to_list(length=1000)
            return [self._format_asset(a) for a in raw]

        elif report_type == 'Patch Management':
            cursor = db.patches.find(query, {"_id": 0})
            raw = await cursor.to_list(length=1000)
            return [self._format_patch(p) for p in raw]

        elif report_type == 'Security Events':
            cursor = db.alerts.find(query, {"_id": 0}).limit(200)
            raw = await cursor.to_list(length=200)
            return [self._format_alert(a) for a in raw]

        elif report_type == 'AI Risk Register':
            cursor = db.risks.find(query, {"_id": 0})
            risks = await cursor.to_list(length=1000)
            if not risks:
                cursor = db.ai_systems.find(query, {"_id": 0})
                systems = await cursor.to_list(length=1000)
                risks = [
                    {
                        "Risk ID":     s.get("id", ""),
                        "Description": s.get("riskDescription") or f"Risk for AI system: {s.get('name', '')}",
                        "Severity":    s.get("riskLevel") or s.get("risk_level", "Medium"),
                        "Status":      s.get("status", "Open"),
                        "Owner":       s.get("owner", ""),
                        "System":      s.get("name", ""),
                    }
                    for s in systems
                ]
            return risks

        elif report_type == 'Vulnerability':
            cursor = db.vulnerabilities.find(query, {"_id": 0}).sort("severity", 1).limit(2000)
            raw = await cursor.to_list(length=2000)
            return [self._format_vulnerability(v) for v in raw]

        elif report_type == 'Threat Intelligence':
            cursor = db.threat_intel_scans.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
            raw = await cursor.to_list(length=500)
            return [self._format_threat_intel(t) for t in raw]

        elif report_type == 'SBOM':
            cursor = db.sboms.find(query, {"_id": 0}).sort("generatedAt", -1).limit(500)
            raw = await cursor.to_list(length=500)
            return [self._format_sbom(s) for s in raw]

        elif report_type == 'Secrets Management':
            cursor = db.secrets.find(query, {"_id": 0}).limit(500)
            raw = await cursor.to_list(length=500)
            return [self._format_secret(s) for s in raw]

        elif report_type == 'EDR Alerts':
            cursor = db.edr_alerts.find({}, {"_id": 0}).sort("timestamp", -1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_edr_alert(a) for a in raw]

        elif report_type == 'Incident Response':
            cursor = db.response_tasks.find(query, {"_id": 0}).sort("created_at", -1).limit(500)
            raw = await cursor.to_list(length=500)
            return [self._format_response_task(t) for t in raw]

        # ── New modules ───────────────────────────────────────────────────────

        elif report_type == 'Change Management':
            cursor = db.change_requests.find(query, {"_id": 0}).sort("created_at", -1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_change(c) for c in raw] or [{"Note": "No data available"}]

        elif report_type == 'Agent Health':
            cursor = db.agents.find(query, {"_id": 0}).sort("lastSeen", -1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_agent_health(a) for a in raw] or [{"Note": "No data available"}]

        elif report_type == 'Support Chat':
            cursor = db.support_conversations.find(query, {"_id": 0}).sort("created_at", -1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_support_chat(c) for c in raw] or [{"Note": "No data available"}]

        elif report_type == 'Endpoint Chat':
            cursor = db.agent_chat_sessions.find(query, {"_id": 0}).sort("created_at", -1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_endpoint_chat(s) for s in raw] or [{"Note": "No data available"}]

        elif report_type == 'Audit Log':
            q_audit = {"tenantId": tenant_id} if tenant_id else {}
            cursor = db.audit_logs.find(q_audit, {"_id": 0}).sort("timestamp", -1).limit(2000)
            raw = await cursor.to_list(length=2000)
            return [self._format_audit_log(e) for e in raw] or [{"Note": "No data available"}]

        elif report_type == 'User Activity':
            q_user = {"tenantId": tenant_id} if tenant_id else {}
            cursor = db._db.users.find(q_user, {"_id": 0}).sort("name", 1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_user_activity(u) for u in raw] or [{"Note": "No data available"}]

        elif report_type == 'Automation Policies':
            cursor = db.automation_policies.find(query, {"_id": 0}).sort("name", 1).limit(1000)
            raw = await cursor.to_list(length=1000)
            return [self._format_automation(p) for p in raw] or [{"Note": "No data available"}]

        elif report_type == 'Cloud Security':
            cursor = db.cspm_findings.find(query, {"_id": 0}).sort("detectedAt", -1).limit(2000)
            raw = await cursor.to_list(length=2000)
            return [self._format_cspm(f) for f in raw] or [{"Note": "No data available"}]

        return []

    # ── CSV ───────────────────────────────────────────────────────────────────

    def _generate_csv(self, data):
        if not data:
            return ""

        output = io.StringIO()
        if isinstance(data[0], dict):
            all_keys = list(dict.fromkeys(k for row in data for k in row.keys()))
            writer = csv.DictWriter(output, fieldnames=all_keys, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data)
        else:
            writer = csv.writer(output)
            writer.writerows(data)

        return output.getvalue()

