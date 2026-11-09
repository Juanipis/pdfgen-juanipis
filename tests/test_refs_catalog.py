from pdfgen_juanipis.pagination import _extract_ref_ids, _refs_from_html


def test_extract_ref_ids_simple():
    html = "Texto [1] y luego [2, 3]"
    assert _extract_ref_ids(html) == ["1", "2", "3"]


def test_extract_ref_ids_range():
    html = "Ver [4-6] y [8–9]"
    assert _extract_ref_ids(html) == ["4", "5", "6", "8", "9"]


def test_refs_from_html_with_catalog():
    catalog = {
        "1": "Fuente 1",
        "2": "Fuente 2",
        "3": "Fuente 3",
    }
    html = "Texto [1,3]"
    assert _refs_from_html(html, catalog) == ["Fuente 1", "Fuente 3"]
