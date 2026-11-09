"""A number followed by a note call keeps its value in the PDF text layer.

«49.872¹²» reads fine on the page but extracts as «49.87212»: the
superscript is just two more digits. A hair space separates them.
"""

from __future__ import annotations

import io
import re

import pytest

from pdfgen_juanipis.pdf import passes


def _run(html: str) -> str:
    payload = {"pages": [{"blocks": [{"html": html}]}]}
    passes.separate_numbers_from_markers(payload)
    return payload["pages"][0]["blocks"][0]["html"]


def _numbers(text: str) -> set:
    return set(re.findall(r"(?<![\d.])\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d)|\d+(?:,\d+)?", text))


def test_a_number_glued_to_a_call_gets_a_hair_space():
    assert _run("<p>de 49.872<sup>12</sup>.</p>") == "<p>de 49.872 <sup>12</sup>.</p>"


@pytest.mark.parametrize("html", [
    "<p>un texto<sup>4</sup>.</p>",
    "<p>de 5 <sup>3</sup>.</p>",
    "<p>sin llamadas 49.872.</p>",
])
def test_nothing_else_changes(html):
    assert _run(html) == html


def test_the_pdf_text_layer_keeps_the_number():
    weasyprint = pytest.importorskip("weasyprint")
    pypdf = pytest.importorskip("pypdf")

    def extract(html: str) -> str:
        buf = io.BytesIO()
        weasyprint.HTML(string=f"<html><body>{html}</body></html>").write_pdf(buf)
        buf.seek(0)
        return pypdf.PdfReader(buf).pages[0].extract_text()

    glued = extract("<p>del total de 49.872<sup>12</sup>.</p>")
    fixed = extract(_run("<p>del total de 49.872<sup>12</sup>.</p>"))
    assert "49.872" not in _numbers(glued)   # the defect is real
    assert "49.872" in _numbers(fixed)       # and this repairs it
