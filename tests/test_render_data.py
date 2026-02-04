from pdfgen_juanipis.render import build_sample_data, _build_pages_from_sections


def test_sample_data_structure():
    data = build_sample_data()
    assert "theme" in data
    assert "sections" in data
    assert data["sections"], "Expected at least one section"


def test_pages_built_from_sections():
    data = build_sample_data()
    built = _build_pages_from_sections(data)
    assert "pages" in built
    assert built["pages"], "Expected pages to be created"
    page = built["pages"][0]
    assert "blocks" in page
    assert isinstance(page["blocks"], list)
