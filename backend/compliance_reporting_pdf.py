"""
Compliance reporting: PDF generation for a single framework.
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table as PDFTable, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from compliance_reporting_data import _build_report_data

_PDF_STATUS_COLORS = {
    "Compliant":           colors.HexColor("#C6EFCE"),
    "Partially Compliant": colors.HexColor("#FFEB9C"),
    "Non-Compliant":       colors.HexColor("#FFC7CE"),
    "Warning":             colors.HexColor("#FFEB9C"),
    "Implemented":         colors.HexColor("#C6EFCE"),
    "Not Implemented":     colors.HexColor("#FFC7CE"),
    "In Progress":         colors.HexColor("#FFEB9C"),
    "—":                   colors.white,
}


def _find_status_rows(rows_data, col_idx: int):
    """Return BACKGROUND TableStyle commands for status-coloured cells."""
    cmds = []
    for i, row in enumerate(rows_data[1:], start=1):
        val = str(row[col_idx]) if col_idx < len(row) else ""
        bg = _PDF_STATUS_COLORS.get(val, colors.white)
        if bg != colors.white:
            cmds.append(("BACKGROUND", (col_idx, i), (col_idx, i), bg))
    return cmds


async def _generate_pdf(framework_id: str, reports_dir: str, tenant_id: str = None) -> dict:
    from database import get_database
    db = get_database()
    tenant_name = tenant_id or "Unknown Tenant"
    if tenant_id:
        tenant_doc = await db.tenants.find_one({"id": tenant_id})
        tenant_name = tenant_doc.get("name", tenant_id) if tenant_doc else tenant_id

    framework, asset_summary, control_rows = await _build_report_data(framework_id, tenant_id)
    fw_name = framework.get("name", framework_id)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"compliance_report_{framework_id}_{timestamp}.pdf"
    filepath = os.path.join(reports_dir, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    title_style   = ParagraphStyle("T", parent=styles["Title"], fontSize=16,
                                    textColor=colors.HexColor("#1F3864"), spaceAfter=4)
    sub_style     = ParagraphStyle("S", parent=styles["Normal"], fontSize=9,
                                    textColor=colors.HexColor("#555555"), spaceAfter=12)
    section_style = ParagraphStyle("SEC", parent=styles["Heading2"], fontSize=11,
                                    textColor=colors.HexColor("#1F3864"),
                                    spaceBefore=14, spaceAfter=6)
    cell_style    = ParagraphStyle("C", parent=styles["Normal"], fontSize=7, leading=9)
    hdr_style     = ParagraphStyle("H", parent=styles["Normal"], fontSize=7, leading=9,
                                    fontName="Helvetica-Bold",
                                    textColor=colors.whitesmoke)

    page_w = landscape(letter)[0] - inch

    def make_table(headers, rows_plain, col_w_hints):
        total_hint = sum(col_w_hints)
        scale = page_w / total_hint if total_hint > page_w else 1.0
        col_ws = [w * scale * inch for w in col_w_hints]
        hdr_row = [Paragraph(h, hdr_style) for h in headers]
        table_data = [hdr_row] + [
            [Paragraph(str(v), cell_style) for v in row]
            for row in rows_plain
        ]
        style_cmds = [
            ("BACKGROUND",     (0, 0), (-1, 0), colors.HexColor("#366092")),
            ("GRID",           (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
            ("VALIGN",         (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",     (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F7FAFC")]),
        ]
        return PDFTable(table_data, colWidths=col_ws, repeatRows=1), style_cmds

    elements = []
    elements.append(Paragraph(f"{fw_name.upper()} Compliance Report", title_style))
    elements.append(Paragraph(
        f"Tenant: {tenant_name} &nbsp;|&nbsp; "
        f"Export Date: {datetime.now().strftime('%Y-%m-%d')} &nbsp;|&nbsp; "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; "
        f"Controls: {len(framework.get('controls', []))} &nbsp;|&nbsp; "
        f"Assets: {len(asset_summary)}",
        sub_style,
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0")))
    elements.append(Paragraph("Asset Compliance Summary", section_style))

    if asset_summary:
        sum_headers = list(asset_summary[0].keys())
        sum_rows = [list(r.values()) for r in asset_summary]
        sum_widths = [1.4, 1.2, 0.9, 0.9, 0.8, 1.0, 0.8, 1.2][:len(sum_headers)]
        t, base_cmds = make_table(sum_headers, sum_rows, sum_widths)
        verdict_idx = sum_headers.index("Overall Status")
        t.setStyle(TableStyle(base_cmds + _find_status_rows(
            [sum_headers] + sum_rows, verdict_idx
        )))
        elements.append(t)
    else:
        elements.append(Paragraph(
            "No asset compliance data available for this framework.", styles["Normal"]
        ))

    elements.append(Spacer(1, 0.2 * inch))
    elements.append(Paragraph("Control Details with Evidence", section_style))

    if control_rows:
        det_headers = list(control_rows[0].keys())
        det_rows = [list(r.values()) for r in control_rows]
        # Columns (in order from _build_report_data):
        # Control ID, Control Name, Category, Control Status, Asset ID, Hostname,
        # Asset Status, Evidence Count, Auto Evidence, Manual Evidence,
        # Evidence Names, Evidence URLs, Evidence Dates, Evidence Desc, Last Reviewed
        det_widths = [0.7, 1.6, 0.9, 0.9, 0.8, 0.9, 0.9, 0.5, 0.6, 0.6, 1.6, 1.4, 0.8, 1.2, 0.8]
        det_widths = det_widths[:len(det_headers)]
        t2, base_cmds2 = make_table(det_headers, det_rows, det_widths)
        ctrl_idx  = det_headers.index("Control Status")
        asset_idx = det_headers.index("Asset Status")
        color_cmds = (
            _find_status_rows([det_headers] + det_rows, ctrl_idx) +
            _find_status_rows([det_headers] + det_rows, asset_idx)
        )
        t2.setStyle(TableStyle(base_cmds2 + color_cmds))
        elements.append(t2)

    doc.build(elements)
    return {
        "filename": filename, "url": f"/static/reports/{filename}",
        "generatedAt": datetime.now().isoformat(), "rowCount": len(control_rows),
    }
