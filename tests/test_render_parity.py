"""PDF ↔ DOCX render parity on one HTML.

Everything that reaches the reader — prose, headings, figures and their
captions, footnote markers and definitions, page breaks, tables — must
survive BOTH exporters identically. Compared as normalised invariants:
the PDF side is read from the renderer's block payload (what WeasyPrint
lays out), the Word side from the generated .docx, and both against the
source HTML so neither can "pass" by dropping the same thing.
"""

from __future__ import annotations

import copy
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

docx = pytest.importorskip("docx")

from docx.oxml.ns import qn  # noqa: E402
from docx.table import Table  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402
from lxml import html as lxml_html  # noqa: E402

from pdfgen_juanipis.docx_export import DocxRenderer  # noqa: E402
from pdfgen_juanipis.options import RenderOptions  # noqa: E402
from pdfgen_juanipis.pdf.renderer import HtmlRenderer  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "report_fixture.html"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_ROMAN_PREFIX = re.compile(r"^\s*[IVXLCDM]+\.\s*", re.IGNORECASE)
_CHROME_STYLES = {"Document Title", "Document Subtitle"}
_DOC_HEADING_CLASSES = {"document-title", "document-subtitle"}


def _norm(text: str) -> str:
    return " ".join(str(text or "").replace(" ", " ").split())


def _strip_numeral(text: str) -> str:
    return _ROMAN_PREFIX.sub("", _norm(text)).strip()


def _text_without_markers(elem: Any) -> str:
    clone = copy.deepcopy(elem)
    for sup in clone.findall(".//sup"):
        sup.text = None
        for child in list(sup):
            sup.remove(child)
    for note in clone.xpath(".//*[contains(@class, 'fn-note')]"):
        note.getparent().remove(note)
    if isinstance(getattr(clone, "tag", None), str) and clone.tag.lower() == "sup":
        return ""
    return _norm(clone.text_content())


@dataclass
class Outline:
    prose: List[str] = field(default_factory=list)
    headings: List[Tuple[int, str]] = field(default_factory=list)
    numbered_headings: List[str] = field(default_factory=list)
    figures: int = 0
    figure_captions: List[str] = field(default_factory=list)
    footnote_markers: int = 0
    footnote_defs: List[str] = field(default_factory=list)
    page_breaks: int = 0
    tables: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def prose_text(self) -> str:
        return _norm(" ".join(self.prose))


def _is_doc_heading(elem: Any) -> bool:
    return bool(_DOC_HEADING_CLASSES & set((elem.get("class") or "").split()))


def _html_outline(html_content: str) -> Outline:
    out = Outline()
    tree = lxml_html.fragment_fromstring(html_content, create_parent="div")
    for elem in tree.iter():
        tag = getattr(elem, "tag", None)
        if not isinstance(tag, str) or _is_doc_heading(elem):
            continue
        classes = (elem.get("class") or "").split()
        if str(elem.get("data-page-break") or "").lower() == "before":
            out.page_breaks += 1
        if tag in ("h1", "h2", "h3", "h4"):
            out.headings.append((int(tag[1]), _strip_numeral(elem.text_content())))
        elif tag == "figure":
            out.figures += 1
            caption = elem.find(".//figcaption")
            if caption is not None:
                out.figure_captions.append(_norm(caption.text_content()))
        elif tag == "p" and "footnote" in classes:
            sup = elem.find("sup")
            marker = _norm(sup.text_content()) if sup is not None else ""
            body = _norm(elem.text_content())
            out.footnote_defs.append(body[len(marker):].strip() if body.startswith(marker) else body)
        elif tag == "sup":
            parent = elem.getparent()
            if "footnote" not in ((parent.get("class") or "").split() if parent is not None else []):
                out.footnote_markers += len(_norm(elem.text_content()).split(","))
        elif tag == "table":
            header_rows = elem.xpath("./thead/tr")
            body_rows = elem.xpath("./tbody/tr") or elem.xpath("./tr")
            out.tables.append({
                "header_rows": len(header_rows),
                "body_rows": len(body_rows),
                "cols": max(len(r.xpath("./th|./td")) for r in list(header_rows) + list(body_rows)),
                "first_col": [_norm(r.xpath("./th|./td")[0].text_content()) for r in body_rows],
            })
    for elem in tree.iter():
        tag = getattr(elem, "tag", None)
        if not isinstance(tag, str) or tag not in ("p", "li", "h1", "h2", "h3", "h4", "figcaption"):
            continue
        if _is_doc_heading(elem) or (tag == "p" and "footnote" in (elem.get("class") or "").split()):
            continue
        if any(isinstance(a.tag, str) and a.tag.lower() == "table" for a in elem.iterancestors()):
            continue
        if tag == "p" and "section-subtitle" in (elem.get("class") or "").split():
            continue  # printed as the section subtitle, compared via headings below
        text = _text_without_markers(elem)
        if text:
            out.prose.append(_strip_numeral(text) if tag.startswith("h") else text)
    return out


def _pdf_outline(html_content: str) -> Outline:
    payload = HtmlRenderer().build_payload(html_content)
    blocks = payload["pages"][0]["blocks"]
    out = Outline()
    for block in blocks:
        if block.get("type") == "table":
            table = block["table"]
            out.tables.append({
                "header_rows": 2 if table["groups"] else (1 if table["show_header"] else 0),
                "body_rows": len(table["rows"]),
                "cols": (len(table["headers"]) or sum(len(g["months"]) for g in table["groups"])) + 1,
                "first_col": [_norm(r["dep"]) for r in table["rows"]],
            })
            continue
        node = lxml_html.fragment_fromstring(block.get("html") or "<span></span>", create_parent="div")
        for elem in node.iter():
            tag = getattr(elem, "tag", None)
            if not isinstance(tag, str):
                continue
            classes = (elem.get("class") or "").split()
            if str(elem.get("data-page-break") or "").lower() == "before" or (
                "break-before:page" in (elem.get("style") or "").replace(" ", "")
            ):
                out.page_breaks += 1
            if "section-title" in classes:
                out.headings.append((2, _strip_numeral(elem.text_content())))
                out.numbered_headings.append(_norm(elem.text_content()))
            elif tag in ("h1", "h2", "h3", "h4"):
                out.headings.append((int(tag[1]), _strip_numeral(elem.text_content())))
            elif tag == "figure":
                out.figures += 1
                caption = elem.find(".//figcaption")
                if caption is not None:
                    out.figure_captions.append(_norm(caption.text_content()))
            elif tag == "sup":
                out.footnote_markers += len(_norm(elem.text_content()).split(","))
        for elem in node.iter():
            tag = getattr(elem, "tag", None)
            if not isinstance(tag, str):
                continue
            classes = (elem.get("class") or "").split()
            is_title = "section-title" in classes
            if not is_title and tag not in ("p", "li", "h1", "h2", "h3", "h4", "figcaption"):
                continue
            text = _text_without_markers(elem)
            if text:
                out.prose.append(_strip_numeral(text) if (is_title or tag.startswith("h")) else text)
        for ref in block.get("refs") or []:
            out.footnote_defs.append(re.sub(r"^\d+\s*", "", _norm(ref)))
    return out


def _docx_outline(path: Path) -> Outline:
    doc = docx.Document(str(path))
    out = Outline()
    last_was_figure = False
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:tbl"):
            last_was_figure = False
            rows = [[_norm(c.text) for c in row.cells] for row in Table(child, doc).rows]
            out.tables.append({"rows": rows, "cols": len(rows[0]) if rows else 0})
            continue
        if child.tag != qn("w:p"):
            continue
        para = Paragraph(child, doc)
        style = para.style.name if para.style is not None else ""
        out.page_breaks += sum(1 for br in child.iter(f"{_W}br") if br.get(f"{_W}type") == "page")
        out.figures += len(list(child.iter(f"{_W}drawing")))
        out.footnote_markers += len(list(child.iter(f"{_W}footnoteReference")))
        out.footnote_markers += sum(1 for r in para.runs if r.font.superscript and (r.text or "").strip())
        text = _norm("".join(r.text or "" for r in para.runs if not r.font.superscript))
        follows_figure, last_was_figure = last_was_figure, bool(list(child.iter(f"{_W}drawing")))
        if not text or style in _CHROME_STYLES or style == "Section Subtitle":
            continue
        if style == "Figure Caption" and not follows_figure:
            continue  # a table's name or source line: compared with the tables
        if style.startswith("Heading"):
            level = int(style.split()[-1])
            if level == 2:
                out.numbered_headings.append(text)
            text = _strip_numeral(text)
            out.headings.append((level, text))
        if style == "Figure Caption":
            out.figure_captions.append(text)
        out.prose.append(text)
    from docx.opc.constants import RELATIONSHIP_TYPE
    from lxml import etree

    for rel in doc.part.rels.values():
        if rel.reltype == RELATIONSHIP_TYPE.FOOTNOTES:
            root = etree.fromstring(rel.target_part.blob)
            out.footnote_defs = [_norm("".join(fn.itertext())) for fn in root.findall(f"{_W}footnote")
                                 if int(fn.get(f"{_W}id", "0")) > 0]
    return out


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_outline(fixture_html):
    return _html_outline(fixture_html)


@pytest.fixture(scope="module")
def pdf_outline(fixture_html):
    return _pdf_outline(fixture_html)


@pytest.fixture(scope="module")
def docx_outline(tmp_path_factory, fixture_html):
    out = tmp_path_factory.mktemp("parity") / "document.docx"
    DocxRenderer(options=RenderOptions(title="Informe", subtitle="Paridad")).render(fixture_html, out)
    return _docx_outline(out)


def test_fixture_is_representative(html_outline):
    assert html_outline.figures >= 3
    assert len(html_outline.headings) >= 4
    assert html_outline.footnote_markers >= 5
    assert html_outline.page_breaks >= 1
    assert len(html_outline.tables) >= 2


def test_headings_and_hierarchy_match(pdf_outline, docx_outline, html_outline):
    assert pdf_outline.headings == html_outline.headings
    assert docx_outline.headings == html_outline.headings


def test_section_numbering_matches(pdf_outline, docx_outline):
    assert pdf_outline.numbered_headings
    assert docx_outline.numbered_headings == pdf_outline.numbered_headings
    assert all(re.match(r"^[IVXLCDM]+\. ", h) for h in pdf_outline.numbered_headings)


def test_figure_count_and_captions_match(pdf_outline, docx_outline, html_outline):
    assert pdf_outline.figures == html_outline.figures
    assert pdf_outline.figure_captions == html_outline.figure_captions
    assert docx_outline.figure_captions == html_outline.figure_captions
    if shutil.which("rsvg-convert"):
        assert docx_outline.figures == html_outline.figures


def test_footnote_markers_and_definitions_match(pdf_outline, docx_outline, html_outline):
    assert pdf_outline.footnote_markers == html_outline.footnote_markers
    assert docx_outline.footnote_markers == html_outline.footnote_markers
    assert sorted(pdf_outline.footnote_defs) == sorted(html_outline.footnote_defs)
    assert sorted(docx_outline.footnote_defs) == sorted(html_outline.footnote_defs)


def test_page_breaks_match(pdf_outline, docx_outline, html_outline):
    assert pdf_outline.page_breaks == html_outline.page_breaks
    assert docx_outline.page_breaks == html_outline.page_breaks


def test_prose_text_matches(pdf_outline, docx_outline, html_outline):
    assert pdf_outline.prose_text == html_outline.prose_text
    assert docx_outline.prose_text == html_outline.prose_text


def test_tables_match(pdf_outline, docx_outline, html_outline):
    assert len(pdf_outline.tables) == len(docx_outline.tables) == len(html_outline.tables)
    for src, pdf, word in zip(html_outline.tables, pdf_outline.tables, docx_outline.tables):
        assert pdf == src
        assert word["cols"] == src["cols"]
        assert len(word["rows"]) == src["header_rows"] + src["body_rows"]
        assert [r[0] for r in word["rows"][src["header_rows"]:]] == src["first_col"]
