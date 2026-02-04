import pathlib

from pdfgen.api import PDFGenConfig


def test_config_from_root():
    root = pathlib.Path.cwd()
    config = PDFGenConfig.from_root(root)
    assert config.template_dir == root / "template"
    assert config.css_path == root / "template" / "boletin.css"
    assert config.fonts_conf == root / "fonts.conf"
