import pathlib
import textwrap

from pdfgen_juanipis.cli import _load_data


def test_load_yaml(tmp_path):
    p = tmp_path / "data.yaml"
    p.write_text(textwrap.dedent("""
        title: Demo
        theme:
          footer_site: example.org
        sections:
          - title: Intro
            content:
              - type: text
                text: "Hola"
    """), encoding="utf-8")
    data = _load_data(p)
    assert data["title"] == "Demo"
    assert data["sections"][0]["content"][0]["text"] == "Hola"
