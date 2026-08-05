"""Offline label-rendering primitives for ITAM-CAT-05 (Phase 58).

This module deliberately imports neither FastAPI nor `database` — every
function here is unit-testable without an app or a DB. Plan 04 adds
`generate_label_sheet_pdf` alongside this module's `generate_qr_png` and
`generate_barcode_png`, keeping the same pure-function contract.
"""
import io

import barcode
import qrcode
from barcode.errors import BarcodeError
from barcode.writer import ImageWriter

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
