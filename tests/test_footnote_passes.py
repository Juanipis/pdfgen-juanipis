"""The two-pass footnote machinery, section numbering and the intro.

No document is laid out here: the passes operate on payload dicts, HTML
strings and a duck-typed document, so they are exercised directly.
"""

from __future__ import annotations

from lxml import html

from pdfgen_juanipis.pdf import passes
from pdfgen_juanipis.pdf.pages import build_pages, format_section_title_html
from pdfgen_juanipis.pdf.parsing import HtmlParser


def _payload(blocks):
    return {"pages": [{"blocks": [
        {"html": block_html, "refs": list(block_refs)} for block_html, block_refs in blocks
    ]}]}


class TestInjectInlineFootnotes:
    def test_ref_from_sibling_block_lands_next_to_marker(self):
        payload = _payload([
            ("<p>texto<sup>1</sup></p>", []),
            ("<p>otro bloque</p>", ["1 Fuente: ejemplo. 2026."]),
        ])
        passes.inject_inline_footnotes(payload)
        blocks = payload["pages"][0]["blocks"]
        assert '<span class="fn-note">1 Fuente: ejemplo. 2026.</span>' in blocks[0]["html"]
        assert blocks[0]["refs"] == [] and blocks[1]["refs"] == []

    def test_marker_without_ref_left_untouched(self):
        payload = _payload([("<p>x<sup>7</sup></p>", ["1 Fuente: X."])])
        passes.inject_inline_footnotes(payload)
        block = payload["pages"][0]["blocks"][0]
        assert "<sup>7</sup>" in block["html"] and "fn-note" not in block["html"]
        assert block["refs"] == ["1 Fuente: X."]  # unconsumed refs stay as fallback

    def test_each_ref_consumed_once(self):
        payload = _payload([("<p>a<sup>1</sup> y b<sup>1</sup></p>", ["1 Fuente: X."])])
        passes.inject_inline_footnotes(payload)
        assert payload["pages"][0]["blocks"][0]["html"].count("fn-note") == 1

    def test_a_joined_marker_places_every_note(self):
        payload = _payload([("<p>palabra<sup>2,3</sup></p>", ["2 Nota dos.", "3 Nota tres."])])
        passes.inject_inline_footnotes(payload)
        out = payload["pages"][0]["blocks"][0]["html"]
        assert "<sup>2,3</sup>" in out
        assert out.count('class="fn-note"') == 2


class TestTrackingIds:
    def test_ids_added_to_sup_and_fn_note(self):
        payload = _payload([('<p>x<sup>2</sup><span class="fn-note">2 Fuente.</span></p>', [])])
        passes.add_footnote_tracking_ids(payload)
        out = payload["pages"][0]["blocks"][0]["html"]
        assert '<sup id="sup-2">2</sup>' in out
        assert '<span class="fn-note" id="fn-2">2 ' in out

    def test_idempotent_on_existing_ids(self):
        payload = _payload([('<p>x<sup id="sup-2">2</sup></p>', [])])
        passes.add_footnote_tracking_ids(payload)
        assert payload["pages"][0]["blocks"][0]["html"].count("sup-2") == 1


class _Box:
    def __init__(self, ident, children=()):
        class _El(dict):
            def get(self, k, default=None):
                return dict.get(self, k, default)

        self.element = _El(id=ident) if ident else None
        self.children = list(children)


class _Page:
    def __init__(self, *ids):
        self._page_box = _Box(None, [_Box(i) for i in ids])


class _Doc:
    def __init__(self, *pages):
        self.pages = list(pages)


class TestDetectAndFix:
    def test_detects_note_on_later_page_than_marker(self):
        doc = _Doc(_Page("sup-3"), _Page("fn-3"))
        # No geometry → fraction 1.0 (fix by default).
        assert passes.detect_footnote_mismatches(doc) == [("3", 0, 1, 1.0)]

    def test_same_page_is_not_a_mismatch(self):
        assert passes.detect_footnote_mismatches(_Doc(_Page("sup-3", "fn-3"))) == []

    def test_fix_adds_break_before_to_owning_paragraph(self):
        source = '<p>uno</p><p>dos <sup id="sup-3">3</sup></p>'
        fixed = passes.fix_footnote_mismatches(source, [("3", 0, 1)])
        assert '<p style="break-before:page">dos <sup id="sup-3">3</sup></p>' in fixed
        assert fixed.startswith("<p>uno</p>")

    def test_fix_skips_svg_path_tags(self):
        source = '<p>intro</p><svg><path d="M0 0"/></svg> <sup id="sup-4">4</sup>'
        fixed = passes.fix_footnote_mismatches(source, [("4", 0, 1)])
        assert "path style=" not in fixed
        assert '<p style="break-before:page">intro</p>' in fixed

    def test_fix_is_idempotent(self):
        source = '<p style="break-before:page">x <sup id="sup-5">5</sup></p>'
        assert passes.fix_footnote_mismatches(source, [("5", 0, 1)]) == source

    def test_fix_skipped_when_marker_high_on_page(self):
        source = '<p>alto <sup id="sup-6">6</sup></p>'
        assert passes.fix_footnote_mismatches(source, [("6", 0, 1, 0.30)]) == source

    def test_fix_applies_when_marker_low_on_page(self):
        source = '<p>bajo <sup id="sup-7">7</sup></p>'
        assert "break-before:page" in passes.fix_footnote_mismatches(source, [("7", 0, 1, 0.85)])


class TestFootnoteFixHeadingHoist:
    """The page break must not orphan the heading right above the paragraph."""

    def test_break_hoisted_to_heading_block(self):
        source = (
            '<div class="content-block"><p>previo</p></div>'
            '<div class="content-block"><div class="section-title">II. Sección</div></div>'
            '<div class="content-block"><p>Primer párrafo<sup id="sup-5">5</sup></p></div>'
        )
        out = passes.fix_footnote_mismatches(source, [("5", 2, 3, 0.9)])
        assert out.index("break-before:page") < out.index("II. Sección")
        assert "<p style=" not in out

    def test_break_stays_on_paragraph_without_heading(self):
        source = (
            '<div class="content-block"><p>previo</p></div>'
            '<div class="content-block"><p>Primer párrafo<sup id="sup-5">5</sup></p></div>'
        )
        out = passes.fix_footnote_mismatches(source, [("5", 2, 3, 0.9)])
        assert '<p style="break-before:page">Primer párrafo' in out

    def test_inline_h2_heading_also_hoisted(self):
        source = (
            '<div class="content-block"><p>previo</p></div>'
            '<div class="content-block"><h2>Subtítulo</h2></div>'
            '<div class="content-block"><p>Texto<sup id="sup-3">3</sup></p></div>'
        )
        out = passes.fix_footnote_mismatches(source, [("3", 2, 3, 0.9)])
        assert out.index("break-before:page") < out.index("Subtítulo")


def _all_html(pages):
    return " ".join(b.get("html", "") for b in pages[0]["blocks"])


class TestSectionNumbering:
    def test_position_always_wins_over_declared_numerals(self):
        assert format_section_title_html("Introducción", 1) == '<span class="roman">I.</span> Introducción'
        assert format_section_title_html("I. Precios", 2) == '<span class="roman">II.</span> Precios'
        assert format_section_title_html("V. Tema", 6) == '<span class="roman">VI.</span> Tema'

    def test_already_wrapped_titles_untouched(self):
        wrapped = '<span class="roman">III.</span> Algo'
        assert format_section_title_html(wrapped, 9) == wrapped

    def test_headingless_intro_is_unnumbered(self):
        sample = (
            "<div><h1>Documento</h1><p>Párrafo de contexto.</p><p>Segundo párrafo.</p>"
            "<h2>I. Precios</h2><p>a</p><h2>II. Tema</h2><p>b</p><h2>Cierre</h2><p>c</p></div>"
        )
        sections = HtmlParser().extract_sections(html.fromstring(sample))
        assert sections[0].get("is_intro") is True and sections[0]["title"] == ""
        blob = _all_html(build_pages(sections, theme={}))
        assert "Contenido" not in blob
        assert '<span class="roman">I.</span> Precios' in blob
        assert '<span class="roman">II.</span> Tema' in blob
        assert '<span class="roman">III.</span> Cierre' in blob

    def test_numbering_can_be_turned_off(self):
        sample = "<div><p>intro</p><h2>Precios</h2><p>a</p><h2>Tema</h2><p>b</p></div>"
        sections = HtmlParser().extract_sections(html.fromstring(sample))
        blob = _all_html(build_pages(sections, theme={}, numbering="none"))
        assert "roman" not in blob and ">Precios<" in blob

    def test_intro_keeps_markup_paragraphs_and_footnotes(self):
        sample = (
            "<div><h1>Documento</h1><p>Presentación.</p><p>Definición<sup>1</sup>.</p>"
            "<p class='footnote'><sup>1</sup> Nota metodológica.</p>"
            "<h2>I. Tema</h2><p>cuerpo<sup>2</sup></p>"
            "<p class='footnote'><sup>2</sup> Nota del tema.</p></div>"
        )
        sections = HtmlParser().extract_sections(html.fromstring(sample))
        page = build_pages(sections, theme={})[0]
        assert page["intro"] == ""
        definition = [b for b in page["blocks"] if "Definición<sup>1</sup>" in b.get("html", "")]
        assert definition and definition[0]["refs"] == ["1 Nota metodológica."]
        assert '<span class="roman">I.</span> Tema' in _all_html([page])

    def test_untitled_section_label_is_an_option(self):
        from pdfgen_juanipis.options import Labels

        sample = "<div><p>solo texto</p></div>"
        sections = HtmlParser(labels=Labels(untitled_section="Content")).extract_sections(
            html.fromstring(sample)
        )
        assert sections[0]["title"] == "Content"
