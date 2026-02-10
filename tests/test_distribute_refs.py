"""Tests for the page-level ref distribution feature.

When page-level refs match ``<sup>N</sup>`` markers inside content blocks,
the paginator should attach those refs to the corresponding blocks so they
appear on the same physical page as the content that references them.
"""

from pdfgen_juanipis.pagination import (
    BlockItem,
    LayoutConfig,
    Paginator,
    _extract_sup_numbers,
    _parse_ref_leading_number,
)


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_extract_sup_numbers_basic():
    html = '<p>Texto con nota<sup>1</sup> y otra<sup>2</sup></p>'
    assert _extract_sup_numbers(html) == ["1", "2"]


def test_extract_sup_numbers_with_attrs():
    html = '<p>Nota<sup class="fn">3</sup> mas</p>'
    assert _extract_sup_numbers(html) == ["3"]


def test_extract_sup_numbers_empty():
    html = "<p>Sin notas al pie</p>"
    assert _extract_sup_numbers(html) == []


def test_extract_sup_numbers_whitespace():
    html = "<p>Nota<sup> 4 </sup></p>"
    assert _extract_sup_numbers(html) == ["4"]


def test_parse_ref_leading_number():
    assert _parse_ref_leading_number("1 DANE. IPC Boletin") == "1"
    assert _parse_ref_leading_number("12 Otra fuente") == "12"
    assert _parse_ref_leading_number("Sin numero") is None
    assert _parse_ref_leading_number("  3 Con espacios") == "3"


# ---------------------------------------------------------------------------
# Unit tests for _distribute_page_refs_to_blocks
# ---------------------------------------------------------------------------


def _make_block(html: str, refs: list | None = None) -> BlockItem:
    return BlockItem(
        data={"type": "html", "html": html},
        height_pt=20.0,
        refs=list(refs) if refs else [],
    )


def test_distribute_assigns_refs_to_matching_blocks(tmp_path):
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Seccion A con nota<sup>1</sup></p>'),
        _make_block('<p>Seccion A continua<sup>2</sup></p>'),
        _make_block('<p>Seccion B con nota<sup>3</sup></p>'),
    ]

    page_refs = [
        "1 Fuente DANE",
        "2 Fuente INS",
        "3 Fuente OMS",
    ]

    remaining = paginator._distribute_page_refs_to_blocks(blocks, page_refs)

    assert remaining == [], "All refs should be distributed"
    assert blocks[0].refs == ["1 Fuente DANE"]
    assert blocks[1].refs == ["2 Fuente INS"]
    assert blocks[2].refs == ["3 Fuente OMS"]


def test_distribute_unmatched_refs_remain(tmp_path):
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Solo tiene nota<sup>1</sup></p>'),
    ]

    page_refs = [
        "1 Fuente DANE",
        "2 Fuente INS sin referencia en bloques",
    ]

    remaining = paginator._distribute_page_refs_to_blocks(blocks, page_refs)

    assert remaining == ["2 Fuente INS sin referencia en bloques"]
    assert blocks[0].refs == ["1 Fuente DANE"]


def test_distribute_empty_page_refs(tmp_path):
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [_make_block("<p>Texto</p>")]
    remaining = paginator._distribute_page_refs_to_blocks(blocks, [])
    assert remaining == []
    assert blocks[0].refs == []


def test_distribute_preserves_existing_block_refs(tmp_path):
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Con nota<sup>2</sup></p>', refs=["Existing ref"]),
    ]

    page_refs = ["2 Nueva fuente"]
    remaining = paginator._distribute_page_refs_to_blocks(blocks, page_refs)

    assert remaining == []
    assert blocks[0].refs == ["Existing ref", "2 Nueva fuente"]


def test_distribute_no_leading_number_stays_page_level(tmp_path):
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [_make_block('<p>Con nota<sup>1</sup></p>')]
    page_refs = [
        "1 Fuente que se distribuye",
        "Fuente sin numero que queda page-level",
    ]

    remaining = paginator._distribute_page_refs_to_blocks(blocks, page_refs)
    assert remaining == ["Fuente sin numero que queda page-level"]
    assert blocks[0].refs == ["1 Fuente que se distribuye"]


def test_distribute_multiple_sups_in_one_block(tmp_path):
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block(
            '<p>Nota<sup>1</sup> y otra<sup>2</sup> en mismo parrafo</p>'
        ),
    ]

    page_refs = ["1 Fuente A", "2 Fuente B"]
    remaining = paginator._distribute_page_refs_to_blocks(blocks, page_refs)

    assert remaining == []
    assert blocks[0].refs == ["1 Fuente A", "2 Fuente B"]


# ---------------------------------------------------------------------------
# Integration: paginator places refs on correct physical pages
# ---------------------------------------------------------------------------


def test_paginator_distributes_refs_across_pages(tmp_path):
    """Page-level refs should appear on the page containing the <sup> marker,
    not all lumped on the last page."""
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    # Build a long document with two sections that each have a footnote.
    # Fill enough text to force multiple physical pages.
    long_text = "<p>" + ("Lorem ipsum. " * 80) + "</p>"

    blocks = [
        {"type": "html", "html": f'<p>Seccion 1 nota<sup>1</sup></p>{long_text}'},
        {"type": "html", "html": f'<p>Seccion 2 nota<sup>2</sup></p>{long_text}'},
    ]

    page_data = {
        "header_banner_path": "banner.png",
        "header_banner_path_cont": "banner.png",
        "header_logo_path": "logo.png",
        "title_line1": "Titulo",
        "title_line2": "Subtitulo",
        "footer_site": "test.org",
        "footer_phone": "",
        "show_header_titles": False,
        "blocks": blocks,
        "refs": [
            "1 Fuente de la seccion 1",
            "2 Fuente de la seccion 2",
        ],
        "footer_notes": [],
        "page_number": "1",
    }

    paginated = paginator.paginate([page_data])

    # We should have multiple pages
    assert len(paginated) >= 2, f"Expected >= 2 pages, got {len(paginated)}"

    # Collect which pages have which refs
    pages_with_ref1 = [
        i for i, p in enumerate(paginated)
        if any("Fuente de la seccion 1" in r for r in p.get("refs", []))
    ]
    pages_with_ref2 = [
        i for i, p in enumerate(paginated)
        if any("Fuente de la seccion 2" in r for r in p.get("refs", []))
    ]

    # Ref 1 should NOT be on the last page (it should be on an earlier page)
    # unless section 1 content happens to land on the last page too.
    # At minimum, refs should not ALL be on the same (last) page.
    all_on_last = (
        pages_with_ref1 == [len(paginated) - 1]
        and pages_with_ref2 == [len(paginated) - 1]
    )
    assert not all_on_last, (
        "Both refs should NOT be lumped on the last page; "
        f"ref1 on pages {pages_with_ref1}, ref2 on pages {pages_with_ref2}"
    )


# ---------------------------------------------------------------------------
# Unit tests for _redistribute_block_refs
# ---------------------------------------------------------------------------


def test_redistribute_moves_refs_to_matching_block(tmp_path):
    """Block-level refs should be moved to the block containing the
    corresponding <sup>N</sup> marker."""
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Parrafo con<sup>1</sup> referencia</p>'),
        _make_block('<p>Parrafo intermedio sin notas</p>'),
        # All refs incorrectly on the last block (simulates old behaviour)
        _make_block(
            '<p>Parrafo con<sup>2</sup> referencia</p>',
            refs=["1 Fuente DANE", "2 Fuente INS"],
        ),
    ]

    paginator._redistribute_block_refs(blocks)

    assert blocks[0].refs == ["1 Fuente DANE"]
    assert blocks[1].refs == []
    assert blocks[2].refs == ["2 Fuente INS"]


def test_redistribute_unmatched_refs_go_to_fallback(tmp_path):
    """Refs that cannot be matched to any <sup> go to the last block that
    originally held refs."""
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Parrafo con<sup>1</sup></p>'),
        _make_block(
            '<p>Texto sin sups</p>',
            refs=["1 Fuente A", "99 Fuente huerfana"],
        ),
    ]

    paginator._redistribute_block_refs(blocks)

    assert blocks[0].refs == ["1 Fuente A"]
    # Unmatched ref stays on the last block that had refs (block index 1)
    assert blocks[1].refs == ["99 Fuente huerfana"]


def test_redistribute_noop_when_no_refs(tmp_path):
    """When no blocks have refs, redistribution is a no-op."""
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Sin refs</p>'),
        _make_block('<p>Tampoco</p>'),
    ]

    paginator._redistribute_block_refs(blocks)

    assert blocks[0].refs == []
    assert blocks[1].refs == []


def test_redistribute_non_numeric_refs_to_fallback(tmp_path):
    """Non-numeric refs go to the fallback block."""
    layout = LayoutConfig()
    css = tmp_path / "dummy.css"
    css.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css), str(tmp_path))

    blocks = [
        _make_block('<p>Con<sup>1</sup></p>'),
        _make_block(
            '<p>Texto</p>',
            refs=["1 Fuente A", "Nota sin numero"],
        ),
    ]

    paginator._redistribute_block_refs(blocks)

    assert blocks[0].refs == ["1 Fuente A"]
    assert blocks[1].refs == ["Nota sin numero"]
