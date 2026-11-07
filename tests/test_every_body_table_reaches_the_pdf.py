"""Every table in the HTML reaches the block list, exactly once.

Folding a table's source line (``div.table-caption``) into its block used
to REMOVE the div while the body walk iterated that very tree, and lxml's
iterator then skipped the element after the gap: tables vanished.
"""

from __future__ import annotations

import inspect

from lxml import html as lxml_html

from pdfgen_juanipis.pdf import parsing
from pdfgen_juanipis.pdf.parsing import HtmlParser


def _table(n, *, with_source=True):
    source = f'<div class="table-caption">Fuente: elaboración propia {n}.</div>' if with_source else ""
    return (f'<table class="body-table"><caption>Tabla {n}. Título {n}.</caption>'
            f"<thead><tr><th>A</th><th>B</th></tr></thead>"
            f"<tbody><tr><td>x{n}</td><td>{n}</td></tr></tbody></table>{source}")


def _blocks(html_text):
    parser = HtmlParser()
    root = lxml_html.fragment_fromstring(html_text, create_parent="div")
    content: list = []
    text_buffer: list = []
    for child in list(root):
        parser.consume_element(child, content=content, text_buffer=text_buffer,
                               title_node=None, footnotes=[])
    if text_buffer:
        content.append({"type": "text", "text": list(text_buffer)})
    return content


def _prose_of(blocks):
    out = []
    for block in blocks:
        if block.get("type") == "html":
            out.append(block.get("html") or "")
        elif block.get("type") == "text":
            out.extend(block.get("text") or [])
    return " ".join(out)


def test_three_tables_with_sources_all_survive():
    tables = [b for b in _blocks("".join(_table(n) for n in (1, 2, 3))) if b["type"] == "table"]
    assert [t["table"]["title"] for t in tables] == [
        "Tabla 1. Título 1.", "Tabla 2. Título 2.", "Tabla 3. Título 3."]


def test_paragraphs_between_tables_survive_too():
    blocks = _blocks(_table(1) + "<p>Entre una y otra.</p>" + _table(2) + "<p>Después.</p>" + _table(3))
    assert len([b for b in blocks if b["type"] == "table"]) == 3
    prose = _prose_of(blocks)
    assert "Entre una y otra." in prose and "Después." in prose


def test_a_table_without_a_source_line_is_unaffected():
    tables = [b for b in _blocks(_table(1, with_source=False) + _table(2)) if b["type"] == "table"]
    assert len(tables) == 2 and tables[0]["table"]["caption"] == ""


def test_the_source_line_lands_on_its_table_and_not_in_the_prose():
    blocks = _blocks(_table(1))
    assert [b for b in blocks if b["type"] == "table"][0]["table"]["caption"] == \
        "Fuente: elaboración propia 1."
    assert "Fuente: elaboración propia" not in _prose_of(blocks)


def test_a_loose_caption_div_with_no_table_is_still_printed():
    assert "Nota suelta." in _prose_of(_blocks('<div class="table-caption">Nota suelta.</div>'))


def test_the_parser_never_removes_a_node_it_did_not_create():
    source = inspect.getsource(parsing.HtmlParser.table_block)
    assert ".remove(" not in source and "CONSUMED_ATTR" in source
