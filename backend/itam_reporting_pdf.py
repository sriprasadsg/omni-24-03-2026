"""ITAM reporting: PDF renderer (Phase 72, Plan 05, D-11).

Structural clone of compliance_reporting_pdf.py, adapted to consume the
shared {key,title,columns,rows,rowCount,truncated} report dict every ITAM
renderer (csv/pdf/xlsx) reads (build_report_rows's own contract), rather
than compliance's framework/asset_summary/control_rows tuple. Registers
itself into itam_reporting_service.RENDERERS under the "pdf" key.
"""

import html
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table as PDFTable, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from compliance_reporting_data import _sanitize_cell

# ITAM status vocabulary these reports actually emit (warranty_expiring,
# license_utilization, overdue_audits, low_stock_consumables) — a dedicated
# table rather than reusing compliance_reporting_pdf._PDF_STATUS_COLORS,
# since that table's keys (Compliant/Non-Compliant/...) never appear in an
# ITAM report's Status column. Keyed lowercase and matched case-insensitively
# below: itam_finance_service.WARRANTY_STATUS_EXPIRING/_EXPIRED/_ACTIVE are
# lowercase ("expiring"/"expired"/"active"), while
# itam_reporting_prebuilt._build_license_utilization_rows emits Title-case
# ("Active"/"Expired") for the same concept — a pre-existing case
# inconsistency across reports this renderer must tolerate rather than
# silently under-color.
_PDF_STATUS_COLORS = {
    "active":        colors.HexColor("#C6EFCE"),
    "expiring":      colors.HexColor("#FFEB9C"),
    "expired":       colors.HexColor("#FFC7CE"),
    "low stock":     colors.HexColor("#FFEB9C"),
    "overdue":       colors.HexColor("#FFC7CE"),
    "never audited": colors.HexColor("#FFC7CE"),
}


def _find_status_rows(rows_data, col_idx: int):
    """Return BACKGROUND TableStyle commands for status-coloured cells.
    rows_data[0] is the header row; data rows start at index 1."""
    cmds = []
    for i, row in enumerate(rows_data[1:], start=1):
        val = str(row[col_idx]) if col_idx < len(row) else ""
        bg = _PDF_STATUS_COLORS.get(val.strip().lower())
        if bg is not None:
            cmds.append(("BACKGROUND", (col_idx, i), (col_idx, i), bg))
    return cmds


def _status_column_index(columns):
    """Whichever column a report declares as its status column — the
    literal 'Status' header, when present. A report with no such column
    (e.g. checkout_activity, asset_value) simply gets no status coloring."""
    return columns.index("Status") if "Status" in columns else None


async def _generate_pdf(report: dict, reports_dir: str, tenant_id: str = None) -> dict:
    """Renders report['rows'] (a list of {column: value} dicts keyed by
    report['columns']) into a landscape-letter PDF table. Every cell passes
    through _sanitize_cell (CWE-1236 formula-injection defence, T-72-06)
    and is html.escape'd before being wrapped in a reportlab Paragraph
    (T-72-11), matching compliance_reporting_pdf.py's own pattern exactly.
    A zero-row report still builds a document with the header row present.
    """
    columns = report["columns"]
    rows = report["rows"]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"itam_report_{report['key']}_{timestamp}.pdf"
    filepath = os.path.join(reports_dir, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Title"], fontSize=16,
                                  textColor=colors.HexColor("#1F3864"), spaceAfter=4)
    sub_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=9,
                                textColor=colors.HexColor("#555555"), spaceAfter=12)
    cell_style = ParagraphStyle("C", parent=styles["Normal"], fontSize=7, leading=9)
    hdr_style = ParagraphStyle("H", parent=styles["Normal"], fontSize=7, leading=9,
                                fontName="Helvetica-Bold", textColor=colors.whitesmoke)

    page_w = landscape(letter)[0] - inch

    def make_table(headers, rows_plain):
        n = max(len(headers), 1)
        # Column-width hints are expressed in inches and distributed evenly
        # across the printable page width, mirroring
        # compliance_reporting_pdf.py's own page-width-driven scaling
        # mechanics (col_w_hints -> scale -> col_ws) rather than a fixed
        # per-column hint list, since an ITAM report's column count varies
        # by report (6-8 columns) rather than being fixed like the
        # compliance control-details table.
        col_w_hints = [(page_w / inch) / n] * n
        total_hint = sum(col_w_hints)
        scale = page_w / total_hint if total_hint > page_w else 1.0
        col_ws = [w * scale * inch for w in col_w_hints]
        hdr_row = [Paragraph(html.escape(str(h), quote=False), hdr_style) for h in headers]
        table_data = [hdr_row] + [
            [Paragraph(html.escape(str(v), quote=False), cell_style) for v in row]
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
    elements.append(Paragraph(html.escape(str(report["title"]), quote=False), title_style))
    elements.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC "
        f"&nbsp;|&nbsp; Rows: {report['rowCount']}",
        sub_style,
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0")))
    elements.append(Spacer(1, 0.15 * inch))

    # Every cell passes through _sanitize_cell before rendering (T-72-06).
    plain_rows = [
        [_sanitize_cell(row.get(col)) for col in columns]
        for row in rows
    ]
    t, base_cmds = make_table(columns, plain_rows)
    status_idx = _status_column_index(columns)
    if status_idx is not None:
        color_cmds = _find_status_rows([columns] + plain_rows, status_idx)
        t.setStyle(TableStyle(base_cmds + color_cmds))
    else:
        t.setStyle(TableStyle(base_cmds))
    elements.append(t)

    if report.get("truncated"):
        elements.append(Spacer(1, 0.15 * inch))
        elements.append(Paragraph(
            "TRUNCATED — the export ceiling was reached; not every matching "
            "row is shown in this file.",
            sub_style,
        ))

    doc.build(elements)

    return {
        "filename": filename,
        "url": f"/static/reports/{filename}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rowCount": report["rowCount"],
        "truncated": report.get("truncated", False),
    }
