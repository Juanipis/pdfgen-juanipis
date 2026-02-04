from pdfgen.pagination import LayoutConfig, Paginator, split_html_into_chunks, _needs_keep_with_next


def test_split_html_chunks():
    html = "<p>Uno</p><p>Dos</p><p>Tres</p>"
    chunks = split_html_into_chunks(html)
    assert len(chunks) >= 2


def test_split_html_chunks_long_paragraph():
    html = "<p>" + "Frase. " * 120 + "</p>"
    chunks = split_html_into_chunks(html)
    assert len(chunks) > 1


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
