"""The activity export as a PDF (Phase 86, ACTV-06, D-11).

Page one is the summary: the organization, when it was made (UTC), what the file holds, the counts, the per-rule
table for the same period, the time saved written as an estimate with how it is worked out, and the cap sentence
when older rows were left out. A page break follows, then the rows table (the nine CSV columns) with its header
repeated on every page.

Every string passes through ``xml.sax.saxutils.escape`` before it reaches a ``Paragraph``, so markup or an
ampersand in a ticket title or a target is printed as written and never changes or breaks the page (T-86-12).
"""
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .export import CSV_HEADER
from .stats import format_minutes

METHOD_SENTENCE = (
    "This is an estimate, not a measurement. Each action that really ran and was not undone counts a fixed number "
    "of minutes for its kind, for example 15 minutes to isolate a host or 8 minutes to answer a ticket. Simulated "
    "and undone actions are not counted. These minutes are fixed in the product and can't be changed.")
RULE_HEADER = ("Rule", "Fired", "Done", "Approved", "Denied", "Undone", "Failed", "Refused", "Would have done (simulation)")
RULE_KEYS = ("fired", "done", "approved", "denied", "undone", "failed", "refused", "wouldHaveDone")
COUNT_HEADER = ("Decisions", "Done", "Undone", "Would have done (simulation)")
COUNT_KEYS = ("fired", "done", "undone", "wouldHaveDone")
ROW_WIDTHS = (1.1, 0.7, 1.3, 1.4, 1.0, 1.6, 1.3, 0.9, 1.7)
_HEAD_BG, _GRID, _ZEBRA = colors.HexColor("#2d3748"), colors.HexColor("#cbd5e0"), colors.HexColor("#f7fafc")


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape("" if value is None else str(value)), style)


def _table(data: List[List[Any]], widths: List[float], *, repeat: int = 1) -> Table:
    table = Table(data, colWidths=widths, repeatRows=repeat)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _HEAD_BG), ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ZEBRA]),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _scaled(widths, page_width: float) -> List[float]:
    wide = [w * inch for w in widths]
    return [w * page_width / sum(wide) for w in wide] if sum(wide) > page_width else wide


def render_pdf(*, organization: str, generated_at: datetime, filter_line: str, summary: Dict[str, int],
               rules: List[Dict[str, Any]], time_saved: Dict[str, Any], rows: List[List[str]],
               cap_note: Optional[str], compress: bool = True) -> bytes:
    """The PDF bytes. ``summary`` is the totals of ``stats.fold``, ``rules`` its per-rule rows and ``time_saved``
    the ``stats.time_saved`` result; ``rows`` are the CSV rows (nine text cells each)."""
    page = landscape(letter)
    page_width = page[0] - inch
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=page, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch, pageCompression=1 if compress else 0)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7, leading=9, wordWrap="CJK")
    head = ParagraphStyle("head", parent=styles["Normal"], fontSize=7, leading=9, fontName="Helvetica-Bold",
                          textColor=colors.whitesmoke)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#4a5568"))
    stamp = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=timezone.utc)

    out: List[Any] = [_p(f"Autonomous Ops activity: {organization}", styles["Title"]),
                      _p(f"Generated {stamp.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC", styles["Normal"]),
                      _p(filter_line, styles["Normal"]), Spacer(1, 10)]
    counts = [[_p(h, head) for h in COUNT_HEADER], [str(int(summary.get(k) or 0)) for k in COUNT_KEYS]]
    out += [_table(counts, _scaled((1.5, 1.5, 1.5, 2.2), page_width)), Spacer(1, 10),
            _p(f"Time saved (estimate): {format_minutes(time_saved.get('minutes') or 0)}", styles["Heading3"]),
            _p(METHOD_SENTENCE, small)]
    if cap_note:
        out += [Spacer(1, 6), _p(cap_note, styles["Normal"])]
    out.append(Spacer(1, 12))
    if rules:
        body = [[_p(h, head) for h in RULE_HEADER]]
        body += [[_p(rule.get("name") or rule.get("id"), cell)] + [str(int(rule.get(k) or 0)) for k in RULE_KEYS]
                 for rule in rules]
        out.append(_table(body, _scaled((3.0,) + (0.8,) * 8, page_width)))
    else:
        out.append(_p("No decisions in this period.", styles["Normal"]))
    out.append(PageBreak())
    table = [[_p(h, head) for h in CSV_HEADER]] + [[_p(c, cell) for c in row] for row in rows]
    out.append(_table(table, _scaled(ROW_WIDTHS, page_width)))
    doc.build(out)
    return output.getvalue()
