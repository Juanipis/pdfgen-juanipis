"""What an editor writes reaches the Word file, not only the PDF.

Measured against a rich-text editor (TipTap) and documents pasted from
Word, Google Docs and the web (ABACO, 2026-11-12): the PDF printed every
format, the Word file lost italics inside bold, bold inside a coloured
``<span>`` (how Docs pastes), every underline, colour, highlight and link,
the formatting of list items, the restart of numbered lists, blockquotes,
and every JPEG photo. One assertion per thing that was lost.
"""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import pytest

docx = pytest.importorskip("docx")

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from pdfgen_juanipis.contract import scan_directives  # noqa: E402
from pdfgen_juanipis.docx_export import render_docx  # noqa: E402


def _render(tmp_path: Path, html: str):
    out = tmp_path / "x.docx"
    result = render_docx(html, out)
    return Document(str(out)), result, out


def _runs(document):
    return [r for p in document.paragraphs for r in p.runs]


def _run(document, text):
    found = [r for r in _runs(document) if text in r.text]
    assert found, f"no run with «{text}»: {[r.text for r in _runs(document)]}"
    return found[0]


def _shade(run):
    shd = run._r.rPr.find(qn("w:shd")) if run._r.rPr is not None else None
    return None if shd is None else shd.get(qn("w:fill"))


class TestNestedFormatting:
    def test_italics_inside_bold_are_both(self, tmp_path):
        d, *_ = _render(tmp_path, "<p><strong>negrita <em>AMBAS</em></strong> fin</p>")
        run = _run(d, "AMBAS")
        assert run.bold and run.italic
        assert _run(d, "negrita").bold and not _run(d, "negrita").italic

    def test_bold_inside_a_coloured_span_as_google_docs_pastes(self, tmp_path):
        d, *_ = _render(tmp_path, '<p><span style="color:#1F3864"><strong>DOCS</strong></span> resto</p>')
        run = _run(d, "DOCS")
        assert run.bold
        assert str(run.font.color.rgb) == "1F3864"

    def test_span_styles_say_bold_italic_and_underline(self, tmp_path):
        html = ('<p><span style="font-weight:700">PESO</span> <span style="font-style:italic">INCL</span> '
                '<span style="text-decoration: underline">SUBR</span></p>')
        d, *_ = _render(tmp_path, html)
        assert _run(d, "PESO").bold and _run(d, "INCL").italic and _run(d, "SUBR").underline

    def test_underline_strike_subscript_and_code(self, tmp_path):
        d, *_ = _render(tmp_path, "<p><u>SUB</u> <s>TACH</s> H<sub>2</sub>O <code>CODIGO</code></p>")
        assert _run(d, "SUB").underline
        assert _run(d, "TACH").font.strike
        assert _run(d, "2").font.subscript
        assert _run(d, "CODIGO").font.name == "Courier New"

    def test_rgb_colour_and_whitespace_like_html(self, tmp_path):
        d, *_ = _render(tmp_path, '<p>\n   uno   <span style="color: rgb(192, 0, 0)">ROJO</span>\n  dos</p>')
        assert str(_run(d, "ROJO").font.color.rgb) == "C00000"
        assert d.paragraphs[0].text == "uno ROJO dos"


class TestHighlightAndLinks:
    def test_a_mark_is_shaded_with_its_colour_or_yellow(self, tmp_path):
        html = ('<p><mark data-color="#f8e08e" style="background-color: #f8e08e; color: inherit">RES</mark> '
                "<mark>AMARILLO</mark></p>")
        d, *_ = _render(tmp_path, html)
        assert _shade(_run(d, "RES")) == "F8E08E"
        assert _shade(_run(d, "AMARILLO")) == "FFFF00"

    def test_data_color_on_a_mark_is_part_of_the_contract(self):
        assert scan_directives('<p><mark data-color="#f8e08e">x</mark></p>').unsupported == []

    def test_a_link_is_a_word_hyperlink_and_a_javascript_one_is_text(self, tmp_path):
        html = ('<p>Ver <a href="https://www.minsalud.gov.co">el <strong>sitio</strong></a> y '
                '<a href="javascript:alert(1)">malo</a>.</p>')
        d, _result, out = _render(tmp_path, html)
        links = d.paragraphs[0]._p.findall(qn("w:hyperlink"))
        assert len(links) == 1
        rel = d.part.rels[links[0].get(qn("r:id"))]
        assert rel.target_ref == "https://www.minsalud.gov.co"
        texts = "".join(t.text for t in links[0].iter(qn("w:t")))
        assert texts == "el sitio"
        assert "javascript" not in zipfile.ZipFile(out).read("word/_rels/document.xml.rels").decode()
        assert "malo" in d.paragraphs[0].text


class TestLists:
    def test_list_items_keep_their_formatting(self, tmp_path):
        d, *_ = _render(tmp_path, "<ul><li><p>uno <strong>FUERTE</strong></p></li><li><p>dos</p></li></ul>")
        assert _run(d, "FUERTE").bold
        assert [p.style.name for p in d.paragraphs if p.text] == ["List Bullet", "List Bullet"]

    def test_each_numbered_list_starts_at_one(self, tmp_path):
        html = ("<ol><li><p>A1</p></li><li><p>A2</p></li></ol><p>entre</p>"
                "<ol><li><p>B1</p></li><li><p>B2</p></li></ol>")
        d, *_ = _render(tmp_path, html)

        def num_id(text):
            p = next(p for p in d.paragraphs if p.text == text)
            return p._p.pPr.numPr.numId.val

        assert num_id("A1") == num_id("A2")
        assert num_id("B1") == num_id("B2")
        assert num_id("A1") != num_id("B1")

    def test_a_nested_list_goes_one_level_deeper(self, tmp_path):
        d, *_ = _render(tmp_path, "<ul><li><p>padre</p><ul><li><p>HIJO</p></li></ul></li></ul>")
        styles = {p.text: p.style.name for p in d.paragraphs if p.text}
        assert styles == {"padre": "List Bullet", "HIJO": "List Bullet 2"}


def test_a_blockquote_is_indented_and_in_italics(tmp_path):
    d, *_ = _render(tmp_path, "<blockquote><p>CITA textual</p></blockquote>")
    para = next(p for p in d.paragraphs if "CITA" in p.text)
    assert para.paragraph_format.left_indent and para.paragraph_format.left_indent > 0
    assert _run(d, "CITA").italic


class TestImages:
    @staticmethod
    def _data_url(size, fmt="JPEG"):
        from PIL import Image

        out = io.BytesIO()
        Image.new("RGB", size, (29, 144, 145)).save(out, format=fmt)
        mime = "jpeg" if fmt == "JPEG" else fmt.lower()
        return f"data:image/{mime};base64," + base64.b64encode(out.getvalue()).decode("ascii")

    def test_a_jpeg_photo_is_embedded(self, tmp_path):
        d, result, _ = _render(tmp_path, f'<p>Foto:</p><img src="{self._data_url((800, 400))}" alt="foto">')
        assert len(d.inline_shapes) == 1 and result.images_embedded == 1
        assert not result.warnings or not any("skipped" in w for w in result.warnings)

    def test_webp_and_gif_too(self, tmp_path):
        html = f'<img src="{self._data_url((200, 100), "WEBP")}"><img src="{self._data_url((200, 100), "GIF")}">'
        d, result, _ = _render(tmp_path, html)
        assert len(d.inline_shapes) == 2

    def test_a_small_bare_image_keeps_its_size_and_a_figure_fills_the_column(self, tmp_path):
        small = self._data_url((120, 60))
        d, *_ = _render(tmp_path, f'<img src="{small}"><figure class="figure-full"><img src="{small}"></figure>')
        bare, figure = d.inline_shapes
        assert abs(bare.width.inches - 120 / 96) < 0.05
        assert abs(figure.width.inches - 6.0) < 0.05

    def test_an_image_declaring_a_huge_bitmap_is_not_decoded(self, tmp_path):
        d, result, _ = _render(tmp_path, f'<img src="{self._data_url((5000, 4000))}">')
        assert len(d.inline_shapes) == 0 and result.images_skipped == 1
        assert any("exceeds" in w for w in result.warnings), result.warnings

    def test_a_link_to_the_web_is_not_fetched(self, tmp_path):
        d, result, _ = _render(tmp_path, '<img src="https://example.com/x.png">')
        assert len(d.inline_shapes) == 0 and result.images_skipped == 1
