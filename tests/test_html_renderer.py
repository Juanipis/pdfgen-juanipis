"""End to end: HTML in, a paginated PDF with the right fonts and words out."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

pytest.importorskip("weasyprint")
pypdf = pytest.importorskip("pypdf")

from pdfgen_juanipis import HtmlRenderer, Labels, RenderOptions, render_formats  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "report_fixture.html"


def _reader(data: bytes):
    return pypdf.PdfReader(io.BytesIO(data))


def _fonts(reader) -> set:
    names = set()
    for page in reader.pages:
        fonts = (page.get("/Resources") or {}).get("/Font") or {}
        for ref in fonts.values():
            names.add(str(ref.get_object().get("/BaseFont")))
    return names


@pytest.fixture(scope="module")
def fixture_pdf(tmp_path_factory):
    out = tmp_path_factory.mktemp("render") / "fixture.pdf"
    result = HtmlRenderer(options=RenderOptions(show_page_numbers=True)).render(
        FIXTURE.read_text(encoding="utf-8"), out,
    )
    return result, out.read_bytes()


def test_the_fixture_paginates(fixture_pdf):
    result, data = fixture_pdf
    reader = _reader(data)
    assert result.pages == len(reader.pages) >= 3
    assert result.unsupported_directives == []
    assert result.package == "plain"


def test_body_text_is_set_in_the_bundled_open_font(fixture_pdf):
    _result, data = fixture_pdf
    fonts = _fonts(_reader(data))
    assert any("Carlito" in f for f in fonts), fonts
    assert not any("Calibri" in f for f in fonts)


def test_footnotes_land_on_their_marker_page(fixture_pdf):
    result, data = fixture_pdf
    assert result.footnote_mismatches == []
    reader = _reader(data)
    first = reader.pages[0].extract_text()
    assert "Nota metodológica de ejemplo" in first


def test_the_text_layer_keeps_the_words(fixture_pdf):
    _result, data = fixture_pdf
    text = " ".join(p.extract_text() for p in _reader(data).pages)
    for words in ("Informe de ejemplo", "Indicador A", "Detalle por categoría", "Total"):
        assert words in text


def test_the_annex_starts_on_a_fresh_page(fixture_pdf):
    _result, data = fixture_pdf
    reader = _reader(data)
    starts = [p.extract_text().split("\n")[0] for p in reader.pages]
    assert any("Anexo" in s for s in starts)


def test_page_number_label_is_an_option(tmp_path):
    html = "<h2>Uno</h2>" + "<p>texto de relleno.</p>" * 5
    plain = _reader(HtmlRenderer(options=RenderOptions(show_page_numbers=True)).render_bytes(html))
    labelled = _reader(HtmlRenderer(options=RenderOptions(
        show_page_numbers=True, page_number_label=True, labels=Labels(page="Page"))).render_bytes(html))
    assert "Page 1" in labelled.pages[0].extract_text()
    assert "Page" not in plain.pages[0].extract_text()


def test_the_language_reaches_the_document(tmp_path):
    html = HtmlRenderer(options=RenderOptions(language="en-US")).build_html("<p>x</p>")
    assert '<html lang="en">' in html


def test_render_formats_fans_one_options_object_out(tmp_path):
    pytest.importorskip("docx")
    result = render_formats(
        "<h2>Uno</h2><p>texto<sup>1</sup></p><p class='footnote'><sup>1</sup> Nota.</p>",
        RenderOptions(title="Informe"), output_dir=tmp_path, basename="doc",
    )
    assert result.errors == {}
    assert result.pdf_path.exists() and result.docx_path.exists()
    assert result.docx.footnotes_attached == 1


def test_importing_the_package_does_not_load_weasyprint():
    import subprocess

    code = ("import sys, pdfgen_juanipis; "
            "assert 'weasyprint' not in sys.modules; assert 'docx' not in sys.modules; "
            "pdfgen_juanipis.RenderOptions; assert 'weasyprint' not in sys.modules")
    src = str(Path(__file__).resolve().parents[1] / "src")
    subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {src!r}); {code}"], check=True)
