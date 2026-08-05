"""Offline label-rendering primitives for ITAM-CAT-05 (Phase 58).

This module deliberately imports neither FastAPI nor `database` — every
function here is unit-testable without an app or a DB. Later plans in this
phase (02-04) add `generate_barcode_png` and `generate_label_sheet_pdf`
alongside this module's `generate_qr_png`, keeping the same pure-function
contract.
"""
import io

import qrcode

# Same values backend/mfa_service.py's generate_qr_base64 uses.
QR_BOX_SIZE = 10
QR_BORDER = 4


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
