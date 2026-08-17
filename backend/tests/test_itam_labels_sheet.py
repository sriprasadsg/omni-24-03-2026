"""ITAM Labels sheet tests — Phase 58 Plan 04.

Avery-5160 grid arithmetic, PDF page assembly, and D-01 label content
(generate_label_sheet_pdf), plus (Task 2) the POST /api/assets/labels/sheet
route's no-silent-drop contract.

Shared mock DB/fixtures live in itam_label_test_support.py.
"""
import base64
import re
import sys
import os
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import itam_label_service as s
from itam_label_service import LabelEncodingError, generate_label_sheet_pdf


def extract_pdf_text(pdf: bytes) -> bytes:
    """Decode every content stream in `pdf` and return the concatenated
    plaintext bytes.

    reportlab writes page content streams with `/Filter [ /ASCII85Decode
    /FlateDecode ]` and `rl_config.pageCompression` defaults to 1 in the
    installed reportlab 5.0.0, so drawn text is NOT present as plain bytes
    in the PDF and a direct membership check on the raw bytes silently
    returns False. This decodes each `stream ... endstream` blob, trying
    ASCII85+Flate, then plain Flate, then plain ASCII85, skipping blobs
    that fail all three. The trailing `~>` sits immediately before
    `endstream` with no newline between it and the tag, which is why the
    closing regex must not require one. Standard library only — no
    PDF-parsing dependency is added.
    """
    out = b""
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        blob = m.group(1).strip()
        for decoder in (
            lambda b: zlib.decompress(base64.a85decode(b, adobe=True)),
            lambda b: zlib.decompress(b),
            lambda b: base64.a85decode(b),
        ):
            try:
                out += decoder(blob)
                break
            except Exception:
                continue
    return out


def pdf_page_count(pdf: bytes) -> int:
    """Return the integer from the single `/Count (\\d+)` match in the
    document's Pages object."""
    matches = re.findall(rb"/Count (\d+)", pdf)
    return int(matches[0])


def _asset(i, **overrides):
    doc = {
        "id": f"asset-{i}",
        "assetTag": f"IT-{i:04d}",
        "name": f"Laptop {i}",
        "model": "ThinkPad T14",
    }
    doc.update(overrides)
    return doc


class TestSheetGeometry:
    """Unit, no app: cell and box containment across all 30 indices, plus
    the out-of-range ValueError."""

    def test_index_0_is_top_left_index_29_is_bottom_right(self):
        x0, y0 = s.label_cell_origin(0)
        x29, y29 = s.label_cell_origin(29)
        assert y0 > y29  # top row has a larger y (bottom-left coordinate space)
        assert x0 < x29  # left column has a smaller x

    def test_all_30_origins_distinct(self):
        origins = [s.label_cell_origin(i) for i in range(s.LABELS_PER_PAGE)]
        assert len(set(origins)) == 30

    def test_all_30_cells_lie_inside_us_letter_page(self):
        tol = 1e-6
        for i in range(s.LABELS_PER_PAGE):
            x, y = s.label_cell_origin(i)
            assert x >= s.LEFT_MARGIN - tol
            assert x + s.LABEL_W <= s.PAGE_W - s.LEFT_MARGIN + tol
            assert y >= 0 - tol
            assert y + s.LABEL_H <= s.PAGE_H - s.TOP_MARGIN + tol

    def test_cells_do_not_overlap(self):
        rects = [s.label_cell_origin(i) for i in range(s.LABELS_PER_PAGE)]
        for i, (x1, y1) in enumerate(rects):
            for j, (x2, y2) in enumerate(rects):
                if i == j:
                    continue
                # Overlap only if intervals on both axes have positive
                # intersection (touching edges are fine, not overlap).
                x_overlap = min(x1 + s.LABEL_W, x2 + s.LABEL_W) - max(x1, x2)
                y_overlap = min(y1 + s.LABEL_H, y2 + s.LABEL_H) - max(y1, y2)
                assert not (x_overlap > 1e-6 and y_overlap > 1e-6), (i, j)

    def test_out_of_range_index_raises_value_error(self):
        with pytest.raises(ValueError):
            s.label_cell_origin(-1)
        with pytest.raises(ValueError):
            s.label_cell_origin(30)

    def test_all_draw_boxes_lie_inside_their_cell(self):
        tol = 1e-6
        for i in range(s.LABELS_PER_PAGE):
            x, y = s.label_cell_origin(i)
            boxes = s.label_draw_boxes(x, y)
            for name, (bx, by, bw, bh) in boxes.items():
                assert bx >= x - tol, name
                assert by >= y - tol, name
                assert bx + bw <= x + s.LABEL_W + tol, name
                assert by + bh <= y + s.LABEL_H + tol, name


class TestSheetPagination:
    """Selectable with -k sheet_pagination."""

    @pytest.mark.parametrize(
        "count,expected_pages",
        [(1, 1), (29, 1), (30, 1), (31, 2), (60, 2), (61, 3)],
    )
    def test_sheet_pagination_page_counts(self, count, expected_pages):
        assets = [_asset(i) for i in range(count)]
        pdf = generate_label_sheet_pdf(assets)
        assert pdf.startswith(b"%PDF-")
        assert pdf_page_count(pdf) == expected_pages

    def test_sheet_pagination_no_blank_leading_page(self):
        assets = [_asset(i) for i in range(31)]
        pdf = generate_label_sheet_pdf(assets)
        text = extract_pdf_text(pdf)
        # The first asset's tag must appear — a blank leading page would
        # push content onto page 2 without removing it from the stream, so
        # this alone doesn't prove no blank page, but combined with the
        # exact page counts above (31 -> 2, not 3) it does.
        assert assets[0]["assetTag"].encode() in text


class TestLabelContent:
    """Selectable with -k label_content."""

    def test_label_content_tag_name_model_present_for_every_asset(self):
        assets = [_asset(i) for i in range(3)]
        pdf = generate_label_sheet_pdf(assets)
        text = extract_pdf_text(pdf)
        for a in assets:
            assert a["assetTag"].encode() in text
            assert a["name"].encode() in text
            assert a["model"].encode() in text

    def test_label_content_raw_bytes_do_not_contain_tag(self):
        # This is what makes the decoding helper necessary — a naive check
        # against the raw undecoded bytes would otherwise vacuously pass.
        assets = [_asset(0)]
        pdf = generate_label_sheet_pdf(assets)
        assert assets[0]["assetTag"].encode() not in pdf

    def test_label_content_missing_name_and_model_renders_without_literal_none(self):
        pdf = generate_label_sheet_pdf([{"id": "a", "assetTag": "IT-0001"}])
        text = extract_pdf_text(pdf)
        assert b"None" not in text
        assert b"IT-0001" in text

    def test_label_content_long_name_is_truncated(self):
        long_name = "A" * 200
        pdf = generate_label_sheet_pdf(
            [{"id": "a", "assetTag": "IT-0001", "name": long_name, "model": "M"}]
        )
        text = extract_pdf_text(pdf)
        assert long_name.encode() not in text
        assert b"..." in text


class TestSheetInputGuards:
    def test_sheet_input_guards_empty_list_raises(self):
        with pytest.raises(LabelEncodingError):
            generate_label_sheet_pdf([])

    def test_sheet_input_guards_missing_asset_tag_raises(self):
        with pytest.raises(LabelEncodingError):
            generate_label_sheet_pdf([{"id": "no-tag"}])
