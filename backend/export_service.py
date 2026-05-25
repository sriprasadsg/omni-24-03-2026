import csv
import io
import re
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from database import get_database


class ExportService:
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

    # ── PDF ───────────────────────────────────────────────────────────────────

    # Column width hints (inches) for known fields
    _COL_WIDTHS = {
        "Hostname":            1.1,
        "IP Address":          1.1,
        "OS Type":             0.9,
        "OS Version":          1.4,
        "Status":              0.7,
        "CPU Cores":           0.7,
        "CPU Model":           1.6,
        "Total Memory":        0.9,
        "Disks":               2.0,
        "Installed Software":  1.8,
        "Critical Files":      0.8,
        "Last Seen":           1.1,
        "Tenant ID":           1.2,
        # patches
        "Patch ID":            0.9,
        "Title":               2.0,
        "Severity":            0.7,
        "CVE":                 1.2,
        "Released":            1.0,
        "Applied":             1.0,
        # alerts / security events
        "Alert ID":            1.0,
        "Source":              1.0,
        "Timestamp":           1.2,
        # AI risks
        "Risk ID":             0.9,
        "Description":         2.5,
        "Owner":               1.0,
        "System":              1.2,
        # vulnerabilities
        "Vuln ID":             0.9,
        "CVSS Score":          0.8,
        "Component":           1.2,
        "Version":             0.8,
        "Fixed Version":       0.9,
        "Detected":            1.1,
        "Asset":               1.1,
        # threat intel
        "Scan ID":             1.0,
        "Artifact":            1.8,
        "Type":                0.8,
        "Verdict":             0.8,
        "Malicious":           0.7,
        "Suspicious":          0.8,
        "Harmless":            0.8,
        "Scanned At":          1.1,
        # SBOM
        "SBOM ID":             1.0,
        "Name":                1.6,
        "Format":              0.8,
        "Total Components":    1.0,
        "Critical Vulns":      0.9,
        "High Vulns":          0.8,
        "License Issues":      0.9,
        "Generated At":        1.1,
        # secrets
        "Secret ID":           1.0,
        "Environment":         0.9,
        "Rotation Due":        1.1,
        "Last Rotated":        1.1,
        "Tags":                1.2,
        # EDR alerts
        "Rule":                1.8,
        "Category":            1.0,
        "MITRE Tactic":        1.0,
        "MITRE Technique":     1.2,
        "Agent ID":            1.0,
        "Process":             1.2,
        "Acknowledged":        0.8,
        # response tasks
        "Task ID":             1.0,
        "Priority":            0.7,
        "Assigned To":         1.0,
        "Alert ID":            1.0,
        "Created":             1.1,
        "Completed":           1.1,
        "Notes":               2.0,
    }

    # PDF columns to include per report type (ordered, human-readable)
    _PDF_COLS = {
        "Asset Inventory": [
            "Hostname", "IP Address", "OS Type", "Status",
            "CPU Cores", "Total Memory", "Disks", "Installed Software", "Last Seen",
        ],
        "Patch Management": [
            "Patch ID", "Title", "Severity", "Status", "Asset", "CVE", "Released",
        ],
        "Security Events": [
            "Alert ID", "Title", "Severity", "Status", "Source", "Asset", "Timestamp",
        ],
        "AI Risk Register": [
            "Risk ID", "Description", "Severity", "Status", "Owner", "System",
        ],
        "Vulnerability": [
            "Vuln ID", "Title", "CVE", "Severity", "CVSS Score",
            "Status", "Asset", "Component", "Version", "Fixed Version",
        ],
        "Threat Intelligence": [
            "Artifact", "Type", "Verdict", "Malicious", "Suspicious", "Harmless", "Scanned At",
        ],
        "SBOM": [
            "SBOM ID", "Name", "Version", "Format", "Asset",
            "Total Components", "Critical Vulns", "High Vulns", "License Issues", "Generated At",
        ],
        "Secrets Management": [
            "Secret ID", "Name", "Type", "Environment", "Status",
            "Rotation Due", "Last Rotated", "Owner",
        ],
        "EDR Alerts": [
            "Alert ID", "Rule", "Severity", "Category", "MITRE Tactic",
            "MITRE Technique", "Agent ID", "Process", "Acknowledged", "Timestamp",
        ],
        "Incident Response": [
            "Task ID", "Type", "Status", "Priority", "Asset",
            "Assigned To", "Created", "Completed", "Notes",
        ],
    }

    def _generate_pdf(self, data, title):
        output = io.BytesIO()
        doc = SimpleDocTemplate(
            output,
            pagesize=landscape(letter),
            leftMargin=0.5 * inch,
            rightMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch,
        )
        elements = []
        styles = getSampleStyleSheet()
        cell_style = ParagraphStyle(
            "cell", parent=styles["Normal"], fontSize=7, leading=9, wordWrap='CJK'
        )
        header_style = ParagraphStyle(
            "header", parent=styles["Normal"], fontSize=7, leading=9,
            fontName="Helvetica-Bold", textColor=colors.whitesmoke
        )

        elements.append(Paragraph(f"{title} Report", styles["Title"]))
        elements.append(Paragraph(
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"]
        ))
        elements.append(Spacer(1, 14))

        if not data:
            elements.append(Paragraph("No data available.", styles["Normal"]))
        else:
            # Choose columns
            desired = self._PDF_COLS.get(title, list(data[0].keys()))
            headers = [h for h in desired if h in data[0]]
            if not headers:
                headers = list(data[0].keys())[:10]

            # Column widths
            page_w = landscape(letter)[0] - inch  # usable width
            col_w = [self._COL_WIDTHS.get(h, 1.0) * inch for h in headers]
            total_w = sum(col_w)
            if total_w > page_w:
                scale = page_w / total_w
                col_w = [w * scale for w in col_w]

            # Build table rows with wrapped paragraphs
            header_row = [Paragraph(h, header_style) for h in headers]
            table_data = [header_row]
            for row in data:
                cells = []
                for h in headers:
                    val = str(row.get(h, "—"))
                    cells.append(Paragraph(val, cell_style))
                table_data.append(cells)

            t = Table(table_data, colWidths=col_w, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#2d3748")),
                ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.whitesmoke),
                ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, 0),  7),
                ("BOTTOMPADDING", (0, 0), (-1, 0),  6),
                ("TOPPADDING",    (0, 0), (-1, 0),  6),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
                ("FONTSIZE",      (0, 1), (-1, -1), 7),
                ("TOPPADDING",    (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e0")),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ]))
            elements.append(t)

        doc.build(elements)
        return output.getvalue()
