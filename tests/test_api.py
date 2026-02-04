import pathlib

from pdfgen_juanipis.api import PDFGenConfig
from pdfgen_juanipis.render import build_sample_data
from pdfgen_juanipis.api import PDFGen


def test_config_from_root():
    root = pathlib.Path.cwd()
    config = PDFGenConfig.from_root(root)
    assert config.template_dir in {
        root / "template",
        root / "src" / "pdfgen_juanipis" / "templates",
    }
    assert config.css_path.name == "boletin.css"
    assert config.fonts_conf is None or config.fonts_conf == root / "fonts.conf"


def test_render_bytes_returns_bytes(tmp_path):
    config = PDFGenConfig.from_root(tmp_path)
    # Ensure template exists by pointing to package templates
    data = build_sample_data()
    pdf = PDFGen(config).render_bytes(data)
    assert isinstance(pdf, (bytes, bytearray))
    assert len(pdf) > 1000
