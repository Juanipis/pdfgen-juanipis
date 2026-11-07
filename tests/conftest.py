import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


import pytest  # noqa: E402


def _png(path: pathlib.Path, size=(2448, 420), color=(30, 90, 160)) -> pathlib.Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


@pytest.fixture
def make_package(tmp_path):
    """Build a template package directory on the fly (neutral test data)."""

    def _make(name="letterhead", *, root=None, manifest=None, band=True, css=None):
        import yaml

        base = (root or tmp_path / "packages") / name
        base.mkdir(parents=True, exist_ok=True)
        data = {
            "label": f"Test {name}",
            "description": "Neutral test letterhead.",
            "theme": {
                "footer_site": "example.org",
                "footer_phone": "+1 555 0100",
                "footer_address": "1 Main St",
                "footer_email": "hello@example.org",
                "footer_city": "Springfield",
            },
        }
        if band:
            _png(base / "assets" / "band.png")
            data["theme"]["header_complete_path"] = "band.png"
        if css:
            (base / "letterhead.css").write_text(css, encoding="utf-8")
            data["css"] = "letterhead.css"
        data.update(manifest or {})
        (base / "package.yml").write_text(yaml.safe_dump(data), encoding="utf-8")
        return base

    return _make
