"""A tall figure grows to the text width instead of printing at half of it."""

from __future__ import annotations

from pdfgen_juanipis.contract import TEXT_WIDTH_PT
from pdfgen_juanipis.pdf.visual_layout import (
    ResolvedPDFVisualLayoutConfig,
    compute_target_height_pt,
    image_dimensions_from_bytes,
)

_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="740" height="700"></svg>'


def _height(w, h, **cfg):
    return compute_target_height_pt(
        cfg=ResolvedPDFVisualLayoutConfig(**cfg), layout_key="full", chart_type=None,
        aspect_ratio=w / h, text_width_pt=TEXT_WIDTH_PT,
    )


def test_svg_dimensions_are_read():
    assert image_dimensions_from_bytes(_SVG) == (740, 700)
    assert image_dimensions_from_bytes(
        b'<svg viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg"></svg>') == (800, 400)


def test_a_tall_chart_grows_until_it_fills_the_column():
    height = _height(740, 700)
    assert height > 240 and height * 740 / 700 >= 0.95 * TEXT_WIDTH_PT


def test_growth_stops_at_the_ceiling():
    assert _height(740, 1400) == 400
    assert _height(740, 1400, fit_width_max_height_pt=300) == 300


def test_a_wide_chart_keeps_its_size_and_fills_the_column():
    height = _height(740, 360)
    assert height <= 240 and height * 740 / 360 >= TEXT_WIDTH_PT


def test_without_the_column_width_nothing_changes():
    cfg = ResolvedPDFVisualLayoutConfig()
    assert compute_target_height_pt(cfg=cfg, layout_key="full", chart_type=None,
                                    aspect_ratio=740 / 700) <= cfg.max_height_pt
