"""Offline label-rendering primitives for ITAM-CAT-05 (Phase 58).

This module deliberately imports neither FastAPI nor `database` — every
function here is unit-testable without an app or a DB. `generate_label_sheet_pdf`
sits alongside `generate_qr_png` and `generate_barcode_png`, keeping the same
pure-function contract.
"""
import io

import barcode
import qrcode
from barcode.errors import BarcodeError
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

# Same values backend/mfa_service.py's generate_qr_base64 uses.
QR_BOX_SIZE = 10
QR_BORDER = 4

# Code128 (not EAN/UPC) because it is alphanumeric-safe and accepts the
# codebase's real IT-0001-shaped asset tag; the numeric-only EAN/UPC
# symbologies would reject that shape outright.
BARCODE_SYMBOLOGY = "code128"


class LabelEncodingError(ValueError):
    """Raised when a value cannot be rendered into a label image.

    The single typed error this module raises, so the endpoint layer has one
    thing to catch and map to 400 rather than catching bare Exception.
    """


def generate_qr_png(asset_tag: str) -> bytes:
    """Render `asset_tag` as a PNG QR code and return the raw bytes.

    Per D-02, the QR payload is the bare `asset_tag` string exactly as given
    — no URL prefix, no JSON wrapper, no tenant or asset id mixed in.

    Unlike mfa_service.generate_qr_base64, this function never swallows an
    exception and returns an empty result — a failed render has to be
    visible to the caller, because a silently blank PNG would be printed
    and stuck on hardware.
    """
    if not asset_tag or not isinstance(asset_tag, str):
        raise LabelEncodingError("asset_tag must be a non-empty string")

    qr = qrcode.QRCode(version=1, box_size=QR_BOX_SIZE, border=QR_BORDER)
    qr.add_data(asset_tag)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_barcode_png(asset_tag: str) -> bytes:
    """Render `asset_tag` as a Code128 1D barcode PNG and return the raw bytes.

    Symmetric with generate_qr_png per D-02 — the payload is the bare
    `asset_tag` string exactly as stored, no prefix, no separator, no case
    folding, no Unicode normalization, so both codes on a label round-trip
    to the same lookup key.

    `write_text` is off because the human-readable tag/name/model text
    required by D-01 is drawn by the PDF layout layer in Plan 04, which
    positions it deliberately within the Avery cell; letting the writer
    draw its own caption would double it up there.

    Never returns a placeholder, blank, or partially-rendered image on
    failure — an image that looks like a valid label but carries no
    scannable payload gets printed and stuck onto hardware before anyone
    finds out, which is strictly worse than an error the caller sees
    immediately.
    """
    if not asset_tag or not isinstance(asset_tag, str):
        raise LabelEncodingError("asset_tag must be a non-empty string")

    try:
        code128_cls = barcode.get_barcode_class(BARCODE_SYMBOLOGY)
        barcode_obj = code128_cls(asset_tag, writer=ImageWriter(format="PNG"))
        buf = io.BytesIO()
        barcode_obj.write(buf, options={"write_text": False})
    except (BarcodeError, ValueError, TypeError) as exc:
        raise LabelEncodingError(f"asset_tag could not be encoded as Code128: {exc}") from exc

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Avery 5160 label sheet (Phase 58-04, ITAM-CAT-05). Figures per the Avery
# 5160 published spec: 3 columns x 10 rows of 2.625in x 1.0in labels on US
# Letter, 0.5in top margin, no vertical gutter between rows (ROW_PITCH ==
# LABEL_H). The outer LEFT_MARGIN is the arithmetically reconciled
# (8.5 - 3 * 2.625) / 2 = 0.3125in — Avery's published figures agree on
# label size and grid but not on a single stated outer-margin number, and
# COL_PITCH is set equal to LABEL_W (edge-to-edge columns, no horizontal
# gutter) so this margin is internally consistent with the printable page
# width rather than mixing a reconciled margin with the vendor's separately
# published (and, paired with this margin, page-overflowing) 2.75in gutter
# pitch. Confirming the reconciled margin to better than a sixteenth of an
# inch requires printing onto real label stock — logged as this phase's one
# manual-only verification (see 58-VALIDATION.md).
PAGE_W, PAGE_H = letter
LABEL_W = 2.625 * inch
LABEL_H = 1.0 * inch
COLS = 3
ROWS = 10
LABELS_PER_PAGE = COLS * ROWS
TOP_MARGIN = 0.5 * inch
LEFT_MARGIN = 0.3125 * inch
COL_PITCH = LABEL_W
ROW_PITCH = LABEL_H

# Inner-cell layout constants for label_draw_boxes. Not part of the Avery
# spec — purely this module's own drawing geometry.
_CELL_PAD = 0.05 * inch
_INNER_GAP = 0.03 * inch
_QR_SIZE = 0.85 * inch
_BARCODE_H = 0.35 * inch


def label_cell_origin(index_on_page: int) -> tuple:
    """Return the bottom-left (x, y) origin, in reportlab's bottom-left
    coordinate space, of cell `index_on_page` (0-based, 0 to
    LABELS_PER_PAGE - 1) on an Avery 5160 sheet.

    This is the single place the grid arithmetic exists — both
    generate_label_sheet_pdf and its geometry test read this function, so
    the test cannot pass against arithmetic the renderer does not use.
    """
    if not 0 <= index_on_page < LABELS_PER_PAGE:
        raise ValueError(
            f"index_on_page must be 0..{LABELS_PER_PAGE - 1}, got {index_on_page}"
        )
    col = index_on_page % COLS
    row = index_on_page // COLS
    x = LEFT_MARGIN + col * COL_PITCH
    y = PAGE_H - TOP_MARGIN - (row + 1) * ROW_PITCH
    return (x, y)


def label_draw_boxes(x: float, y: float) -> dict:
    """Return `(x, y, width, height)` rectangles keyed qr/barcode/tag/name/model
    for a cell anchored at `(x, y)` (bottom-left origin). Every returned
    rectangle lies fully inside the cell — that is the property the geometry
    test asserts, and it is the mitigation (T-58-02) that stops an unusually
    long asset name from bleeding into the adjacent label.

    Layout: a square QR code on the left, vertically centered; a barcode in
    the upper right of the remaining width; three stacked text bands (tag,
    name, model) beneath the barcode.
    """
    inner_x0 = x + _CELL_PAD
    inner_y0 = y + _CELL_PAD
    inner_x1 = x + LABEL_W - _CELL_PAD
    inner_y1 = y + LABEL_H - _CELL_PAD
    inner_w = inner_x1 - inner_x0
    inner_h = inner_y1 - inner_y0

    qr_x = inner_x0
    qr_y = inner_y0 + (inner_h - _QR_SIZE) / 2
    qr_box = (qr_x, qr_y, _QR_SIZE, _QR_SIZE)

    right_x0 = inner_x0 + _QR_SIZE + _INNER_GAP
    right_w = inner_x1 - right_x0

    barcode_y = inner_y1 - _BARCODE_H
    barcode_box = (right_x0, barcode_y, right_w, _BARCODE_H)

    text_top = barcode_y - _INNER_GAP
    text_h = text_top - inner_y0
    band_h = text_h / 3

    tag_box = (right_x0, text_top - band_h, right_w, band_h)
    name_box = (right_x0, text_top - 2 * band_h, right_w, band_h)
    model_box = (right_x0, text_top - 3 * band_h, right_w, band_h)

    return {
        "qr": qr_box,
        "barcode": barcode_box,
        "tag": tag_box,
        "name": name_box,
        "model": model_box,
    }


def _fit_text(text: str, font_name: str, font_size: float, max_width: float) -> str:
    """Return the longest prefix of `text` whose measured width (via
    pdfmetrics.stringWidth) fits `max_width`, appending "..." when
    truncation occurred and re-measuring so the truncated result still
    fits. Measures rather than counting characters, because a fixed
    character budget breaks for wide glyphs — exactly the input a caller
    controls through the asset name (T-58-02).
    """
    if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
        return text

    ellipsis = "..."
    lo, hi = 0, len(text)
    best = ellipsis
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid] + ellipsis
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _label_text_or_blank(value) -> str:
    """Coerce a possibly-missing asset field into label text: a falsy value
    (None, missing, empty string) becomes "", never the literal text
    "None"."""
    return str(value) if value else ""


def generate_label_sheet_pdf(assets: list) -> bytes:
    """Render `assets` (a list of asset dicts) onto an Avery 5160 PDF sheet
    and return the raw PDF bytes.

    Composes generate_qr_png and generate_barcode_png rather than
    re-implementing either, so the D-02 bare-tag payload has exactly one
    definition across the standalone routes and the sheet. Raises
    LabelEncodingError, never a partial/blank render, for: an empty asset
    list, an asset with no assetTag, or a tag either generator cannot
    encode.
    """
    if not assets:
        raise LabelEncodingError("assets must be a non-empty list — nothing to render")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    # One fresh io.BytesIO + ImageReader per image, held alive in this list
    # until after c.save() returns — reportlab reads image data lazily, so a
    # shared or prematurely collected buffer renders blank on later labels
    # rather than failing loudly (T-58-09).
    image_readers = []

    for i, asset in enumerate(assets):
        page_i = i % LABELS_PER_PAGE
        if i > 0 and page_i == 0:
            c.showPage()

        asset_id = asset.get("id", "<unknown>")
        tag = asset.get("assetTag")
        if not tag:
            raise LabelEncodingError(f"asset {asset_id} has no assetTag to encode")

        try:
            qr_png = generate_qr_png(tag)
        except LabelEncodingError as exc:
            raise LabelEncodingError(f"asset {asset_id}: {exc}") from exc

        try:
            barcode_png = generate_barcode_png(tag)
        except LabelEncodingError as exc:
            raise LabelEncodingError(f"asset {asset_id}: {exc}") from exc

        x, y = label_cell_origin(page_i)
        boxes = label_draw_boxes(x, y)

        qr_buf = io.BytesIO(qr_png)
        qr_reader = ImageReader(qr_buf)
        image_readers.append((qr_buf, qr_reader))
        qx, qy, qw, qh = boxes["qr"]
        c.drawImage(qr_reader, qx, qy, width=qw, height=qh, mask="auto")

        bc_buf = io.BytesIO(barcode_png)
        bc_reader = ImageReader(bc_buf)
        image_readers.append((bc_buf, bc_reader))
        bx, by, bw, bh = boxes["barcode"]
        c.drawImage(
            bc_reader, bx, by, width=bw, height=bh, mask="auto", preserveAspectRatio=True
        )

        tag_box = boxes["tag"]
        name_box = boxes["name"]
        model_box = boxes["model"]

        c.setFont("Helvetica-Bold", 7)
        tag_text = _fit_text(str(tag), "Helvetica-Bold", 7, tag_box[2])
        c.drawString(tag_box[0], tag_box[1] + tag_box[3] * 0.3, tag_text)

        c.setFont("Helvetica", 6)
        name_text = _fit_text(_label_text_or_blank(asset.get("name")), "Helvetica", 6, name_box[2])
        c.drawString(name_box[0], name_box[1] + name_box[3] * 0.3, name_text)

        model_text = _fit_text(_label_text_or_blank(asset.get("model")), "Helvetica", 6, model_box[2])
        c.drawString(model_box[0], model_box[1] + model_box[3] * 0.3, model_text)

    c.save()
    return buf.getvalue()
