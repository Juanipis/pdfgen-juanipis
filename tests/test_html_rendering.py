from pdfgen.render import _blocks_from_section


def test_text_allows_inline_html():
    section = {
        "title": "",
        "content": [
            {"type": "text", "text": "Texto con <strong>negrita</strong> y <u>subrayado</u>."}
        ],
    }
    blocks = _blocks_from_section(section)
    assert blocks
    html = blocks[0]["html"]
    assert "<strong>negrita</strong>" in html
    assert "<u>subrayado</u>" in html


def test_html_block_passthrough():
    section = {
        "title": "",
        "content": [
            {"type": "html", "html": "<p>Texto <s>tachado</s></p>"}
        ],
    }
    blocks = _blocks_from_section(section)
    assert blocks
    assert blocks[0]["html"] == "<p>Texto <s>tachado</s></p>"
