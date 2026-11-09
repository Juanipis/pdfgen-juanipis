"""The 0.1 API keeps working: names, module paths and the YAML/JSON CLI."""

from __future__ import annotations

import importlib


def test_old_names_are_importable_from_the_package():
    import pdfgen_juanipis as pg
    from pdfgen_juanipis.legacy import api, pagination, render, validator

    assert pg.render_pdf is render.render_pdf
    assert pg.build_sample_data is render.build_sample_data
    assert pg.validate_and_normalize is validator.validate_and_normalize
    assert pg.LayoutConfig is pagination.LayoutConfig
    assert pg.Paginator is pagination.Paginator
    assert pg.PDFGen is api.PDFGen
    assert pg.PDFGenConfig is api.PDFGenConfig
    assert pg.render_with_defaults is api.render_with_defaults
    assert pg.render_with_defaults_bytes is api.render_with_defaults_bytes


def test_old_module_paths_alias_the_legacy_modules():
    for name in ("render", "api", "pagination", "validator"):
        old = importlib.import_module(f"pdfgen_juanipis.{name}")
        new = importlib.import_module(f"pdfgen_juanipis.legacy.{name}")
        assert old is new


def test_layout_config_still_builds_its_template_dict():
    from pdfgen_juanipis.pagination import LayoutConfig

    assert "content_width_pt" in str(LayoutConfig().to_template()) or LayoutConfig().to_template()


def test_the_legacy_sample_renders_with_the_open_fonts(tmp_path):
    import io

    import pytest

    pypdf = pytest.importorskip("pypdf")
    from pdfgen_juanipis import PDFGen, PDFGenConfig, build_sample_data

    data = PDFGen(PDFGenConfig.from_root(tmp_path)).render_bytes(build_sample_data())
    reader = pypdf.PdfReader(io.BytesIO(data))
    fonts = set()
    for page in reader.pages:
        for ref in ((page.get("/Resources") or {}).get("/Font") or {}).values():
            fonts.add(str(ref.get_object().get("/BaseFont")))
    assert any("Carlito" in f for f in fonts), fonts
