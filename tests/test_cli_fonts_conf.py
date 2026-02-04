import pathlib

from pdfgen_juanipis.cli import _build_fonts_conf


def test_build_fonts_conf(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    conf = _build_fonts_conf(fonts_dir)
    content = pathlib.Path(conf).read_text(encoding="utf-8")
    assert str(fonts_dir.resolve()) in content
