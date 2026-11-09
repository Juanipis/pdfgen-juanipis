"""The document's own title and subtitle never become section «I.»."""

from __future__ import annotations

import re

import pytest

from pdfgen_juanipis.pdf.renderer import HtmlRenderer

_COMPLETE = (
    "<h1 class='document-title'>Informe</h1>"
    "<h2 class='document-subtitle'>Primer semestre</h2>"
    "<p>Introducción sin encabezado.</p>"
    "<h2>Precios</h2><p>a</p>"
    "<h2>Consumo</h2><p>b</p>"
)


@pytest.mark.parametrize("html", [_COMPLETE, _COMPLETE.replace("document-", "bulletin-")])
def test_the_pdf_prints_them_above_the_body_and_numbers_the_first_section_i(html):
    payload = HtmlRenderer().build_payload(html)
    page = payload["pages"][0]
    assert (page["title_line1"], page["title_line2"]) == ("Informe", "Primer semestre")
    assert page["show_header_titles"] is True
    body = " ".join(re.sub(r"<[^>]+>", " ", b.get("html") or "") for b in page["blocks"])
    assert "Primer semestre" not in body
    assert re.search(r"\bI\.\s+Precios", body) and re.search(r"\bII\.\s+Consumo", body)


def test_the_docx_prints_them_as_document_chrome_without_a_number(tmp_path):
    docx = pytest.importorskip("docx")
    from pdfgen_juanipis.docx_export import DocxRenderer

    out = DocxRenderer().render(_COMPLETE, tmp_path / "b.docx")
    paragraphs = docx.Document(str(out.output_path)).paragraphs
    styles = {p.text: p.style.name for p in paragraphs if p.text.strip()}
    assert styles["Informe"] == "Document Title"
    assert styles["Primer semestre"] == "Document Subtitle"
    headings = [p.text for p in paragraphs if p.style.name.startswith("Heading")]
    assert headings[:2] == ["I. Precios", "II. Consumo"]


def test_the_docx_does_not_print_the_title_twice(tmp_path):
    docx = pytest.importorskip("docx")
    from pdfgen_juanipis.docx_export import DocxRenderer
    from pdfgen_juanipis.options import RenderOptions

    out = DocxRenderer(options=RenderOptions(title="Informe", subtitle="Primer semestre")).render(
        _COMPLETE, tmp_path / "b.docx")
    texts = [p.text for p in docx.Document(str(out.output_path)).paragraphs]
    assert texts.count("Informe") == 1 and texts.count("Primer semestre") == 1
