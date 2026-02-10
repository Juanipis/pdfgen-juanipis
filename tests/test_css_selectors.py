"""Verify that boletin.css contains rules for all HTML elements used by
the bulletin pipeline (sup, figure, figcaption, lists, footnotes)."""

import pathlib

CSS_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src"
    / "pdfgen_juanipis"
    / "templates"
    / "boletin.css"
)


def _css_content() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def test_sup_selector():
    css = _css_content()
    assert "sup" in css, "CSS should contain a rule for <sup> elements"


def test_figure_element_selector():
    css = _css_content()
    # Must style the <figure> HTML element (not only the .figure class)
    assert "figure {" in css or "figure{" in css, (
        "CSS should contain a rule for the <figure> element"
    )


def test_figcaption_selector():
    css = _css_content()
    assert "figcaption" in css, "CSS should contain a rule for <figcaption>"


def test_list_selectors():
    css = _css_content()
    assert "ul" in css, "CSS should contain a rule for <ul>"
    assert "ol" in css, "CSS should contain a rule for <ol>"
    assert "li" in css, "CSS should contain a rule for <li>"


def test_footnote_paragraph_selector():
    css = _css_content()
    assert "p.footnote" in css, "CSS should contain a rule for p.footnote"


def test_figure_layout_variants():
    css = _css_content()
    assert "figure.figure-full" in css
    assert "figure.figure-left" in css
    assert "figure.figure-right" in css
