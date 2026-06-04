"""ExportServicePDFMixin: PDF column metadata and generation for ExportService."""

import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


class ExportServicePDFMixin:
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
        "Created":             1.1,
        "Completed":           1.1,
        "Notes":               2.0,
    }

    # PDF columns to include per report type (ordered)
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
            desired = self._PDF_COLS.get(title, list(data[0].keys()))
            headers = [h for h in desired if h in data[0]]
            if not headers:
                headers = list(data[0].keys())[:10]

            page_w = landscape(letter)[0] - inch
            col_w = [self._COL_WIDTHS.get(h, 1.0) * inch for h in headers]
            total_w = sum(col_w)
            if total_w > page_w:
                scale = page_w / total_w
                col_w = [w * scale for w in col_w]

            header_row = [Paragraph(h, header_style) for h in headers]
            table_data = [header_row]
            for row in data:
                cells = [Paragraph(str(row.get(h, "—")), cell_style) for h in headers]
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
