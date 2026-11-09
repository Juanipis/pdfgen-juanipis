"""The render contract is closed, documented and implemented on both sides."""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest
from lxml import html as lxml_html

from pdfgen_juanipis import contract
from pdfgen_juanipis.contract import (
    DIRECTIVES_BY_KEY,
    PAGE_SIDE_MARGIN_PT,
    PAGE_WIDTH_PT,
    RENDER_DIRECTIVES,
    TEXT_WIDTH_PT,
    RenderDirective,
    RenderTextError,
    body_table_widths,
    format_section_title,
    register_directive,
    scan_directives,
    strip_leading_numeral,
    to_roman,
    validate_render_text,
)
from pdfgen_juanipis.options import RenderOptions
from pdfgen_juanipis.pdf.parsing import HtmlParser

PACKAGE = Path(contract.__file__).resolve().parent
CSS = (PACKAGE / "templates" / "report.css").read_text(encoding="utf-8")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "report_fixture.html"


def test_every_emitted_directive_is_implemented_in_both_renderers():
    orphans = [d.key for d in RENDER_DIRECTIVES if d.emitted and not d.supported]
    assert not orphans


def test_directive_keys_are_unique():
    keys = [d.key for d in RENDER_DIRECTIVES]
    assert len(keys) == len(set(keys))


def test_partially_implemented_directives_are_documented_and_not_emitted():
    for directive in RENDER_DIRECTIVES:
        if not directive.supported:
            assert directive.semantics and not directive.emitted


def test_every_directive_has_a_rule_or_a_reader_in_the_pdf_side():
    """Attribute directives the stylesheet implements must appear in it."""
    for key in ("data-page-break", "data-keep-with-next"):
        assert key in CSS


def test_scan_counts_known_directives():
    scan = scan_directives(
        '<h2 data-page-break="before">A</h2>'
        '<p class="footnote"><sup>1</sup> Fuente.</p>'
        '<figure class="figure-full"><figcaption>'
        '<span class="figure-title">Figura 1.</span>'
        '<span class="figure-subcaption"> Nota.</span></figcaption></figure>'
    )
    for key in ("data-page-break", "footnote", "figure-full", "figure-title", "figure-subcaption"):
        assert scan.counts[key] == 1
    assert scan.unsupported == []


def test_scan_flags_unknown_data_attribute():
    assert any("data-shadow" in u for u in scan_directives('<p data-shadow="x">x</p>').unsupported)


def test_scan_flags_unknown_attribute_value():
    assert scan_directives('<h2 data-page-break="after">x</h2>').unsupported


def test_scan_flags_directive_missing_on_one_side():
    html = '<section data-section-type="cover">x</section>'
    assert scan_directives(html).unsupported
    assert scan_directives(html, target="pdf").unsupported == []


def test_scan_ignores_cosmetic_classes_and_internal_attributes():
    assert scan_directives('<p class="lead" data-pdf-keep="x">x</p>').unsupported == []


def test_a_consumer_can_register_its_own_marker():
    key = "data-test-marker"
    assert scan_directives(f'<table {key}="Tabla 1"></table>').unsupported
    register_directive(RenderDirective(
        key=key, kind="attribute", applies_to="<table>", semantics="test marker",
        pdf="not read", docx="not read",
    ))
    try:
        assert scan_directives(f'<table {key}="Tabla 1"></table>').unsupported == []
        with pytest.raises(ValueError):
            register_directive(DIRECTIVES_BY_KEY[key])
    finally:
        RENDER_DIRECTIVES[:] = [d for d in RENDER_DIRECTIVES if d.key != key]
        DIRECTIVES_BY_KEY.pop(key, None)


def test_the_fixture_carries_no_unsupported_directive():
    scan = scan_directives(FIXTURE.read_text(encoding="utf-8"))
    assert scan.unsupported == [] and scan.counts


# ── options ───────────────────────────────────────────────────────────────


def test_options_normalize_invalid_alignment():
    assert RenderOptions(text_align="diagonal").text_align == "justify"


def test_options_reject_unknown_numbering():
    with pytest.raises(ValueError):
        RenderOptions(section_numbering="arabic")


def test_options_merge_ignores_none():
    merged = RenderOptions(title="T", show_page_numbers=True).merged(title=None, text_align="left")
    assert (merged.title, merged.show_page_numbers, merged.text_align) == ("T", True, "left")


def test_figure_cap_applies_to_every_container():
    layout = RenderOptions(figure_max_height_pt=300).resolved_visual_layout()
    assert layout["max_height_pt"] == 300
    assert set(layout["layout_max_height_pt"].values()) == {300}
    assert RenderOptions().resolved_visual_layout() is None


def test_foreign_script_text_is_refused():
    with pytest.raises(RenderTextError):
        validate_render_text("<p>instiტuciones</p>", RenderOptions())
    validate_render_text("<p>instiტuciones</p>", RenderOptions(validate_text=False))
    validate_render_text("<p>中文</p>", RenderOptions(language="zh"))


# ── numbering ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value,expected", [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (0, "I")])
def test_to_roman(value, expected):
    assert to_roman(value) == expected


def test_position_wins_over_hand_written_numeral():
    assert strip_leading_numeral("IV. Tema") == "Tema"
    assert format_section_title("IV. Tema", 2) == "II. Tema"


# ── body tables ───────────────────────────────────────────────────────────


def test_body_table_shares_sum_to_one_and_follow_content_length():
    rows = [["Indicador", "Meta", "Avance"],
            ["Una descripción larga de una acción con bastante texto", "6,5", "84,48"]]
    shares = body_table_widths(rows)
    assert abs(sum(shares) - 1.0) < 1e-9
    assert shares[0] > shares[1] and shares[0] < 0.7


def test_a_ragged_or_empty_table_does_not_crash():
    assert body_table_widths([]) == []
    assert len(body_table_widths([["a", "b"], ["only one"]])) == 2


class TestATableNeverExceedsTheTextColumn:
    def test_the_constants_describe_the_stylesheets_own_page(self):
        block = re.search(r"@page\s*\{(.*?)\}", CSS, re.DOTALL).group(1)
        assert re.search(r"size:\s*Letter", block)
        margins = re.search(r"margin:\s*([\d.]+)pt\s+([\d.]+)pt", block)
        assert float(margins.group(2)) == PAGE_SIDE_MARGIN_PT
        assert PAGE_WIDTH_PT == 612.0
        assert TEXT_WIDTH_PT == PAGE_WIDTH_PT - 2 * PAGE_SIDE_MARGIN_PT

    def test_no_table_declares_a_width_of_its_own(self):
        assert "532.66" not in CSS and "-45.38pt" not in CSS

    @pytest.mark.parametrize("cls", ["body-table", "tabla-cuerpo"])
    def test_the_column_widths_the_parser_emits_fit_that_width(self, cls):
        markup = (f'<table class="{cls}"><caption>Tabla 1. X</caption><thead><tr>'
                  "<th>Columna de bastante ancho</th><th>Meta</th><th>Avance</th></tr></thead>"
                  "<tbody><tr><td>Una acción descrita</td><td>3,37</td><td>27,0</td></tr></tbody></table>")
        block = HtmlParser().table_block(lxml_html.fromstring(markup))["table"]
        assert block["variant"] == "body"
        assert block["total_width"] == TEXT_WIDTH_PT
        assert abs(sum(block["column_widths"]) - TEXT_WIDTH_PT) < 0.5


class TestTablesShapes:
    def test_a_table_without_header_rows_prints_no_header(self):
        markup = "<table><tbody><tr><td>a</td><td>1</td></tr></tbody></table>"
        block = HtmlParser().table_block(lxml_html.fromstring(markup))["table"]
        assert block["show_header"] is False

    def test_two_tier_headers_become_groups(self):
        markup = ("<table><thead><tr><th>Grupo</th><th colspan='2'>2025</th></tr>"
                  "<tr><th>S1</th><th>S2</th></tr></thead>"
                  "<tbody><tr><td>a</td><td>1</td><td>2</td></tr></tbody></table>")
        block = HtmlParser().table_block(lxml_html.fromstring(markup))["table"]
        assert block["groups"] == [{"title": "2025", "months": ["S1", "S2"]}]
        assert block["dep_header"] == "Grupo"


class TestRowEmphasisSurvives:
    _MARKUP = ("<table><thead><tr><th>Grupo</th><th>2025</th></tr></thead><tbody>"
               "<tr><td>Uno</td><td>1,36</td></tr>"
               "<tr><td><b>Total</b></td><td><b>2,26</b></td></tr></tbody></table>")

    def _rows(self):
        block = HtmlParser().table_block(lxml_html.fromstring(self._MARKUP))["table"]
        return {row["dep"]: row for row in block["rows"]}

    def test_the_parser_flags_the_emphasised_row_only(self):
        rows = self._rows()
        assert rows["Total"]["emphasised"] is True and rows["Uno"]["emphasised"] is False

    def test_the_template_renders_it_as_strong(self):
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PACKAGE / "templates")),
                                 autoescape=True)
        macro = env.get_template("report.html.jinja").module.render_table
        out = str(macro({"headers": ["2025"], "dep_header": "Grupo",
                         "rows": list(self._rows().values()), "variant": "reference"}))
        assert "<strong>Total</strong>" in out and "<strong>2,26</strong>" in out
        assert "<strong>Uno</strong>" not in out
