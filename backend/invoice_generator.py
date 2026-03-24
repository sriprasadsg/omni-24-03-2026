"""
Invoice PDF Generator — Phase 7
Generates professional PDF invoices using reportlab.
"""
import io
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def generate_invoice_pdf(invoice: Dict[str, Any], tenant: Dict[str, Any]) -> bytes:
    """
    Generate a professional PDF invoice.
    Returns bytes of the PDF.
    """
    if not REPORTLAB_AVAILABLE:
        raise Exception("reportlab is not installed. Run: pip install reportlab")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#4F46E5")
    light_gray = colors.HexColor("#F8F9FA")
    dark_gray = colors.HexColor("#374151")

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Normal"],
        fontSize=28,
        textColor=primary_color,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )
    header_style = ParagraphStyle(
        "Header",
        parent=styles["Normal"],
        fontSize=11,
        textColor=dark_gray,
        fontName="Helvetica-Bold",
    )
    normal_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        textColor=dark_gray,
    )
    right_style = ParagraphStyle(
        "Right",
        parent=styles["Normal"],
        fontSize=10,
        textColor=dark_gray,
        alignment=TA_RIGHT,
    )

    story = []

    # ── Header: Company + Invoice Title ─────────────────────────────────────
    header_table = Table([
        [
            Paragraph("Omni-Agent Platform", title_style),
            Paragraph("INVOICE", ParagraphStyle("inv", parent=title_style, fontSize=22, alignment=TA_RIGHT))
        ]
    ], colWidths=[3 * inch, 3 * inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=2, color=primary_color))
    story.append(Spacer(1, 16))

    # ── Invoice Meta ─────────────────────────────────────────────────────────
    invoice_id = invoice.get("id", "INV-XXXX")
    invoice_date = invoice.get("generated_at", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    due_date = invoice.get("due_date", "On receipt")

    meta_table = Table([
        [
            Paragraph(f"<b>Bill To:</b><br/>"
                      f"{tenant.get('name', 'N/A')}<br/>"
                      f"{tenant.get('contact_email', '')}<br/>"
                      f"{tenant.get('address', '')}", normal_style),
            Paragraph(
                f"<b>Invoice #:</b> {invoice_id}<br/>"
                f"<b>Invoice Date:</b> {invoice_date}<br/>"
                f"<b>Due Date:</b> {due_date}<br/>"
                f"<b>Status:</b> {invoice.get('status', 'Pending').upper()}",
                right_style
            )
        ]
    ], colWidths=[3.5 * inch, 3 * inch])
    meta_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(meta_table)
    story.append(Spacer(1, 20))

    # ── Line Items ───────────────────────────────────────────────────────────
    items = invoice.get("items", [
        {"description": invoice.get("plan", "Platform Subscription"), "qty": 1,
         "unit_price": invoice.get("amount", 0), "total": invoice.get("amount", 0)}
    ])

    header_row = ["Description", "Qty", "Unit Price", "Total"]
    item_rows = []
    for item in items:
        item_rows.append([
            Paragraph(str(item.get("description", "")), normal_style),
            str(item.get("qty", 1)),
            f"${item.get('unit_price', 0):.2f}",
            f"${item.get('total', 0):.2f}",
        ])

    subtotal = invoice.get("subtotal", invoice.get("amount", 0))
    tax = invoice.get("tax", 0)
    tax_rate = invoice.get("tax_rate", 0)
    total = invoice.get("total", subtotal + tax)

    items_table_data = [header_row] + item_rows + [
        ["", "", "Subtotal:", f"${subtotal:.2f}"],
        ["", "", f"Tax ({tax_rate}%):", f"${tax:.2f}"],
        ["", "", Paragraph("<b>Total Due:</b>", normal_style), Paragraph(f"<b>${total:.2f}</b>", normal_style)],
    ]

    items_table = Table(items_table_data, colWidths=[3.5 * inch, 0.7 * inch, 1.3 * inch, 1 * inch])
    items_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), primary_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -4), [colors.white, light_gray]),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        # Total section
        ("LINEABOVE", (2, -3), (-1, -3), 0.5, colors.gray),
        ("LINEABOVE", (2, -1), (-1, -1), 1.5, primary_color),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 24))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.gray))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Thank you for your business! For questions about this invoice, contact billing@omni-agent.ai",
        ParagraphStyle("Footer", parent=normal_style, fontSize=9, textColor=colors.gray, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()


def generate_compliance_report_pdf(report: Dict[str, Any], tenant_name: str) -> bytes:
    """Generate a PDF compliance report."""
    if not REPORTLAB_AVAILABLE:
        raise Exception("reportlab is not installed")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    primary = colors.HexColor("#4F46E5")
    story = []

    story.append(Paragraph(f"Compliance Report — {tenant_name}", styles["Title"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 16))

    framework = report.get("framework", "N/A")
    score = report.get("compliance_score", 0)
    story.append(Paragraph(f"<b>Framework:</b> {framework}", styles["Normal"]))
    story.append(Paragraph(f"<b>Compliance Score:</b> {score}%", styles["Normal"]))
    story.append(Spacer(1, 12))

    controls = report.get("controls", [])
    if controls:
        header = ["Control", "Status", "Evidence"]
        rows = [[c.get("name", ""), c.get("status", ""), c.get("evidence", "")] for c in controls[:20]]
        table = Table([header] + rows, colWidths=[2 * inch, 1.5 * inch, 3 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

    doc.build(story)
    return buffer.getvalue()
