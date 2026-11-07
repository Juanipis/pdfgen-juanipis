"""The Word file must be the same DOCUMENT as the PDF, not just the same words.

The stylesheet is the reference: the exporter's typography is compared to
``report.css`` itself, so a value that drifts fails here.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

docx = pytest.importorskip("docx")

from docx.shared import Pt  # noqa: E402

from pdfgen_juanipis import docx_export as dx  # noqa: E402
from pdfgen_juanipis.docx_export import DocxRenderer  # noqa: E402
from pdfgen_juanipis.options import Labels, RenderOptions  # noqa: E402
from pdfgen_juanipis.packages import PackageRegistry  # noqa: E402
from pdfgen_juanipis.pdf.renderer import STYLESHEET  # noqa: E402

_CSS = STYLESHEET.read_text(encoding="utf-8")


def _declaration(selector: str, prop: str) -> str:
    """One declaration from the stylesheet, scanning EVERY rule for the selector."""
    for match in re.finditer(rf"(?:^|[\s,}}]){re.escape(selector)}\s*\{{(.*?)\}}", _CSS, flags=re.DOTALL):
        found = re.search(rf"(?<![-\w]){re.escape(prop)}\s*:\s*([^;]+);", match.group(1))
        if found:
            return found.group(1).strip()
    return ""


def _hex(colour: Any) -> str:
    return str(colour).lstrip("#").lower()


class TestTheStylesheetIsTheReference:
    def test_the_css_declarations_this_test_reads_still_exist(self):
        for selector, prop in ((".content p", "font-size"), (".content p", "margin"),
                               (".content p", "line-height"), (".content h3", "font-size"),
                               (".content h3", "color")):
            assert _declaration(selector, prop), (selector, prop)

    def test_body_font_size_gap_and_line_spacing(self):
        assert Pt(float(_declaration(".content p", "font-size")[:-2])) == dx._BODY_FONT_SIZE
        margin = _declaration(".content p", "margin").split()
        assert Pt(float(margin[2][:-2])) == dx._BODY_SPACE_AFTER
        assert float(_declaration(".content p", "line-height")) == pytest.approx(dx._BODY_LINE_SPACING)

    def test_h3_matches(self):
        assert Pt(float(_declaration(".content h3", "font-size")[:-2])) == dx._H3_FONT_SIZE
        assert _hex(dx._H3_COLOR) == _hex(_declaration(".content h3", "color"))

    def test_footer_sizes_and_colours_match(self):
        assert Pt(float(_declaration(".footer-line-primary", "font-size")[:-2])) == dx._FOOTER_PRIMARY_SIZE
        assert Pt(float(_declaration(".footer-line-secondary", "font-size")[:-2])) == dx._FOOTER_SECONDARY_SIZE
        assert _hex(dx._FOOTER_PRIMARY_COLOR) == _hex(_declaration(".footer-line-primary", "color"))
        assert _hex(dx._FOOTER_SITE_COLOR) == _hex(_declaration(".footer-site", "color"))

    def test_palette_defaults_match_the_stylesheet_variables(self):
        from pdfgen_juanipis.packages import PALETTE_DEFAULTS

        assert f"--pdfgen-title-color: {PALETTE_DEFAULTS['title']}" in _CSS
        assert f"--pdfgen-accent-color: {PALETTE_DEFAULTS['accent']}" in _CSS

    def test_the_table_header_fill_matches(self):
        assert _hex(dx._TABLE_HEADER_FILL) == _hex(_declaration(".pdfgen-table thead th", "background"))


def _render(tmp_path, html, **kwargs):
    options = kwargs.pop("options", RenderOptions(title="T"))
    out = DocxRenderer(options=options, **kwargs).render(html, tmp_path / "b.docx")
    return out, docx.Document(str(out.output_path))


class TestTheRenderedFileCarriesThem:
    def test_normal_and_heading_three(self, tmp_path):
        _out, doc = _render(tmp_path, "<h2>I. Sección</h2><p>Texto.</p><h3>Grupo</h3>")
        normal = doc.styles["Normal"]
        assert normal.font.size == dx._BODY_FONT_SIZE
        assert normal.paragraph_format.space_after == dx._BODY_SPACE_AFTER
        h3 = doc.styles["Heading 3"]
        assert _hex(h3.font.color.rgb) == _hex(dx._H3_COLOR) != "4f81bd"
        assert h3.font.name == "Carlito"

    def test_the_title_colour_comes_from_the_package_palette(self, tmp_path, make_package):
        registry = PackageRegistry()
        registry.register(make_package("blue", manifest={"palette": {"title": "#112233"}}))
        _out, doc = _render(tmp_path, "<h2>Uno</h2><p>x</p>", package="blue", registry=registry)
        assert _hex(doc.styles["Heading 2"].font.color.rgb) == "112233"


def _footer_lines(path: Path) -> list:
    xml = zipfile.ZipFile(path).read("word/footer1.xml").decode()
    out = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.DOTALL):
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.DOTALL))
        if text.strip():
            out.append(text)
    return out


class TestTheFooterIsTheWholeContactBlock:
    @pytest.fixture
    def registry(self, make_package):
        registry = PackageRegistry()
        registry.register(make_package("brand"), default="brand")
        return registry

    def test_every_line_the_letterhead_declares_is_printed(self, tmp_path, registry):
        out, _doc = _render(tmp_path, "<p>x</p>", registry=registry)
        lines = _footer_lines(out.output_path)
        blob = " ".join(lines)
        for value in ("example.org", "+1 555 0100", "1 Main St", "hello@example.org", "Springfield"):
            assert value in blob
        assert len(lines) == 3

    def test_the_options_override_the_letterhead(self, tmp_path, registry):
        out, _doc = _render(tmp_path, "<p>x</p>", registry=registry, options=RenderOptions(
            footer_site="otro.org", footer_phone="+1 555 0199", theme={"footer_city": "Shelbyville"}))
        blob = " ".join(_footer_lines(out.output_path))
        assert "otro.org" in blob and "+1 555 0199" in blob and "Shelbyville" in blob
        assert "1 Main St" in blob

    def test_the_phone_label_is_an_option(self, tmp_path, registry):
        out, _doc = _render(tmp_path, "<p>x</p>", registry=registry,
                            options=RenderOptions(labels=Labels(phone="Tel.")))
        assert "Tel. +1 555 0100" in " ".join(_footer_lines(out.output_path))

    def test_the_page_number_does_not_replace_a_contact_line(self, tmp_path, registry):
        out, _doc = _render(tmp_path, "<p>x</p>", registry=registry,
                            options=RenderOptions(show_page_numbers=True))
        assert "PAGE" in zipfile.ZipFile(out.output_path).read("word/footer1.xml").decode()
        assert len(_footer_lines(out.output_path)) == 3


class TestTheFontSurvivesAMachineWithoutIt:
    def test_the_document_font_is_declared_with_a_metric_compatible_substitute(self, tmp_path):
        out, _doc = _render(tmp_path, "<p>x</p>")
        table = zipfile.ZipFile(out.output_path).read("word/fontTable.xml").decode()
        entry = re.search(r'<w:font w:name="Carlito">.*?</w:font>', table, flags=re.DOTALL)
        assert entry and 'w:altName w:val="Calibri"' in entry.group(0)
        assert table.count('<w:font w:name="Carlito">') == 1


class TestTheTableHeaderSurvivesAPageBreak:
    _HTML = ("<p>x</p><table><thead><tr><th>Grupo</th><th>Valor</th></tr></thead><tbody>"
             + "".join(f"<tr><td>G{i}</td><td>{i}</td></tr>" for i in range(40))
             + "</tbody></table>")

    def test_the_header_row_repeats_with_the_stylesheet_fill(self, tmp_path):
        _out, doc = _render(tmp_path, self._HTML)
        xml = doc.tables[0]._tbl.xml
        assert xml.count("<w:tblHeader") == 1
        assert f'w:fill="{dx._TABLE_HEADER_FILL}"' in xml

    def test_a_table_without_a_header_row_gets_no_repeat(self, tmp_path):
        _out, doc = _render(tmp_path, "<table><tbody><tr><td>a</td><td>b</td></tr></tbody></table>")
        assert "<w:tblHeader" not in doc.tables[0]._tbl.xml


def test_section_numbering_none_is_honoured_in_word(tmp_path):
    _out, doc = _render(tmp_path, "<h2>Uno</h2><p>a</p><h2>Dos</h2><p>b</p>",
                        options=RenderOptions(section_numbering="none"))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert headings == ["Uno", "Dos"]
