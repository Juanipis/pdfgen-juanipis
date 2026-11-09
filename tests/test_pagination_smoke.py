from pdfgen_juanipis.pagination import (
    LayoutConfig,
    Paginator,
    split_html_into_chunks,
    _needs_keep_with_next,
    _split_single_element_by_words,
)


def test_split_html_chunks():
    html = "<p>Uno</p><p>Dos</p><p>Tres</p>"
    chunks = split_html_into_chunks(html)
    assert len(chunks) >= 2


def test_split_html_chunks_long_paragraph():
    html = "<p>" + "Frase. " * 120 + "</p>"
    chunks = split_html_into_chunks(html)
    assert len(chunks) > 1


def test_split_single_element_by_words_basic():
    """A single <p> with many words should be split into multiple <p> tags."""
    html = "<p>" + " yes" * 300 + "</p>"
    chunks = _split_single_element_by_words(html, target_words=80)
    assert len(chunks) >= 3
    # First chunk keeps original tag; continuation chunks get margin-reset style.
    assert chunks[0].startswith("<p>")
    for chunk in chunks[1:]:
        assert chunk.startswith("<p ")
        assert "margin:0" in chunk
    for chunk in chunks:
        assert chunk.endswith("</p>")


def test_split_single_element_preserves_inline_tags():
    """Inline tags like <strong> and <em> should be preserved in chunks."""
    html = "<p>" + " word" * 50 + " <strong>bold</strong>" + " word" * 50 + "</p>"
    chunks = _split_single_element_by_words(html, target_words=40)
    assert len(chunks) >= 2
    combined = "".join(chunks)
    assert "<strong>bold</strong>" in combined


def test_split_single_element_preserves_attributes():
    """The opening tag attributes (class, style, etc.) should be preserved."""
    html = '<p class="intro" style="color:red;">' + " word" * 200 + "</p>"
    chunks = _split_single_element_by_words(html, target_words=80)
    assert len(chunks) >= 2
    # First chunk keeps original style; continuations prepend margin reset.
    assert chunks[0].startswith('<p class="intro" style="color:red;">')
    for chunk in chunks[1:]:
        assert 'class="intro"' in chunk
        assert "margin:0" in chunk
        assert "color:red" in chunk
    for chunk in chunks:
        assert chunk.endswith("</p>")


def test_split_chunks_fallback_to_word_split():
    """split_html_into_chunks should use word splitting as last resort for
    single-element HTML without sentences (no periods)."""
    html = "<p>" + " yes" * 500 + "</p>"
    chunks = split_html_into_chunks(html)
    assert len(chunks) > 1, "Expected word-based fallback to split the block"


def test_split_short_paragraph_not_split():
    """A short paragraph should not be split."""
    html = "<p>Short text.</p>"
    chunks = _split_single_element_by_words(html, target_words=80)
    assert len(chunks) == 1


def test_keep_with_next_detects_titles():
    assert _needs_keep_with_next('<div class="section-title">X</div>') is True
    assert _needs_keep_with_next('<div class="section-subtitle">X</div>') is True
    assert _needs_keep_with_next('<p>normal</p>') is False


def test_paginator_smoke(tmp_path):
    layout = LayoutConfig()
    css_path = tmp_path / "dummy.css"
    css_path.write_text(".content { font-size: 12pt; }")
    paginator = Paginator(layout, str(css_path), str(tmp_path))

    pages = [
        {
            "header_banner_path": "banner.png",
            "header_logo_path": "logo.png",
            "title_line1": "Titulo",
            "title_line2": "Subtitulo",
            "footer_site": "abaco.org.co",
            "footer_phone": "Telefono: 313 245 79 78",
            "show_header_titles": False,
            "blocks": [
                {"type": "html", "html": "<p>Texto de prueba</p>"},
                {"type": "html", "html": "<p>Otro parrafo</p>"},
            ],
            "refs": [],
            "footer_notes": [],
            "page_number": "1",
        }
    ]

    paginated = paginator.paginate(pages)
    assert paginated
    assert paginated[0]["blocks"], "Expected blocks to be preserved"
