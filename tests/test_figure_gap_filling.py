"""A figure that jumps a page must not leave a third of the page blank,
and a forced section break must not strand a couple of lines on a page."""

from __future__ import annotations

import pytest

pytest.importorskip("weasyprint")

from pdfgen_juanipis.fonts import FONTS_DIR  # noqa: E402
from pdfgen_juanipis.pdf import passes  # noqa: E402

#: The bundled Carlito, so line heights (and so the holes these tests
#: build) are the same on every machine, whatever fonts it has installed.
_FONT_CSS = (
    "@font-face{font-family:T;src:url('"
    + (FONTS_DIR / "carlito" / "Carlito-Regular.ttf").as_uri()
    + "')} body{font-family:T;font-size:12pt;line-height:1.15}"
)


def _render(markup):
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    font_config = FontConfiguration()
    return HTML(string=markup).render(
        stylesheets=[CSS(string=_FONT_CSS, font_config=font_config)], font_config=font_config,
    )


_PARA = "<p style='margin:0 0 8pt 0'>" + "texto de prueba " * 60 + "</p>"


def _doc(before: int, figure_pt: int, after: int) -> str:
    figure = (f"<figure class='figure-full' style='break-inside:avoid;margin:0'>"
              f"<div style='height:{figure_pt}pt;background:#888'></div>"
              "<figcaption>Figura 1.</figcaption></figure>")
    following = "".join(_PARA.replace("texto", f"despues{i}") for i in range(after))
    return ("<html><head><style>@page{size:A4;margin:60pt}</style></head><body>"
            + _PARA * before + figure + following + "<h2>Siguiente sección</h2>" + _PARA
            + "</body></html>")


def _texts(box):
    text = getattr(box, "text", None)
    if text:
        yield text
    for child in getattr(box, "children", None) or []:
        yield from _texts(child)


def _pages_text(markup):
    return ["".join(_texts(page._page_box)) for page in _render(markup).pages]


def test_text_after_a_jumped_figure_fills_the_hole():
    markup = _doc(before=2, figure_pt=600, after=3)
    assert "despues0" not in _pages_text(markup)[0]
    filled = passes.fill_figure_gaps(markup, _render)
    assert "despues0" in _pages_text(filled)[0]
    assert "data-gid" not in filled
    assert filled.index("Figura 1.") < filled.index("Siguiente sección")
    assert filled.index("despues0") < filled.index("Figura 1.")


def test_a_figure_that_fits_leaves_the_order_alone():
    markup = _doc(before=1, figure_pt=200, after=2)
    assert passes.fill_figure_gaps(markup, _render) == markup


def test_text_announcing_a_later_figure_stays_below():
    figure = ("<figure class='figure-full' style='break-inside:avoid;margin:0'>"
              "<div style='height:600pt;background:#888'></div>"
              '<figcaption><span class="figure-title">Figura 1.</span></figcaption></figure>')
    markup = ("<html><head><style>@page{size:A4;margin:60pt}</style></head><body>"
              + _PARA * 3 + figure + "<p>La Figura 2 muestra otra cosa " + "x " * 200 + "</p>"
              + "</body></html>")
    filled = passes.fill_figure_gaps(markup, _render)
    assert filled.index("Figura 1.") < filled.index("La Figura 2")


def test_the_caption_label_is_read_without_a_title_span():
    """With no `.figure-title`, the configured label finds the number."""
    figure_html = '<figure><img src="x"><figcaption>Figure 4. Something.</figcaption></figure>'
    assert passes._caption_label_and_number(figure_html, "Figure") == ("Figure", 4)
    assert passes._caption_label_and_number(figure_html, "") == ("", None)


def _image_doc(before: int, image_pt: int) -> str:
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN"
           "kYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    figure = ("<figure class='figure-full' style='break-inside:avoid;margin:0'>"
              f"<img src='{png}' style='width:100%;height:{image_pt}pt;max-height:{image_pt}pt'>"
              '<figcaption><span class="figure-title">Figura 1.</span></figcaption></figure>')
    # The text after the figure announces the next one, so only shrinking
    # can close the hole.
    return ("<html><head><style>@page{size:A4;margin:60pt}</style></head><body>"
            + _PARA * before + figure + "<p>La Figura 2 muestra " + "x " * 200 + "</p>"
            + "</body></html>")


def _hole_px(markup: str) -> float:
    page = _render(markup).pages[0]._page_box
    bottoms: list = []

    def _walk(node):
        element = getattr(node, "element", None)
        tag = getattr(element, "tag", "") if element is not None else ""
        if tag == "figure":
            return True
        if tag == "p":
            bottoms.append(float(node.position_y) + float(node.margin_height()))
            return False
        return any(_walk(child) for child in getattr(node, "children", None) or [])

    _walk(page)
    return float(page.content_box_y()) + float(page.height) - max(bottoms)


def test_a_figure_slightly_too_tall_shrinks_into_the_hole():
    # Sized off the measured hole so the test does not depend on fonts:
    # 10 % taller than the hole, so it jumps and fits once shrunk.
    image_pt = round(_hole_px(_image_doc(before=2, image_pt=1)) * 1.1 * 0.75)
    markup = _image_doc(before=2, image_pt=image_pt)
    assert "Figura 1." not in _pages_text(markup)[0]
    filled = passes.fill_figure_gaps(markup, _render)
    assert "Figura 1." in _pages_text(filled)[0]
    assert filled.count("max-height") == 2


def test_a_figure_far_too_tall_is_not_crushed():
    filled = passes.fill_figure_gaps(_image_doc(before=3, image_pt=640), _render)
    assert filled.count("max-height") == 1


def test_a_list_after_a_jumped_figure_fills_the_hole_too():
    markup = _doc(before=2, figure_pt=600, after=0).replace(
        "<h2>", "<ul><li>" + "elemento uno " * 30 + "</li><li>" + "elemento dos " * 30
        + "</li></ul><h2>", 1,
    )
    assert "elemento uno" not in _pages_text(markup)[0]
    filled = passes.fill_figure_gaps(markup, _render)
    assert "elemento uno" in _pages_text(filled)[0]
    assert filled.index("elemento uno") < filled.index("Figura 1.")


def _section_doc(lines: int) -> str:
    return ("<html><head><style>@page{size:A4;margin:60pt}</style></head><body>"
            + "".join(f"<p style='margin:0'>linea {i}</p>" for i in range(lines))
            + '<div class="section-title" style="break-before:page">Anexo</div><p>tabla</p>'
            + "</body></html>")


def _lines_per_page() -> int:
    """How many one-line paragraphs fill a page with the fonts at hand."""
    first = _pages_text(_section_doc(200))[0]
    return first.count("linea ")


def test_a_forced_break_after_a_couple_of_lines_is_dropped():
    per_page = _lines_per_page()
    markup = _section_doc(per_page + 2)
    pages = _pages_text(markup)
    assert "Anexo" not in pages[1]
    relaxed = passes.relax_lonely_breaks(markup, _render)
    assert "break-before:page" not in relaxed and "data-lid" not in relaxed
    assert len(_pages_text(relaxed)) == len(pages) - 1


def test_a_forced_break_after_a_full_page_stays():
    markup = _section_doc(_lines_per_page() + 40)
    assert passes.relax_lonely_breaks(markup, _render) == markup
