"""Every bundled font is open source, documented and licensed in place."""

from __future__ import annotations

from pathlib import Path

from pdfgen_juanipis.fonts import FONTS_DIR

#: Families whose redistribution the library cannot grant.
_PROPRIETARY = ("calibri", "segoe", "century", "times new roman", "timesnewroman", "aptos")


def _font_files():
    return sorted(p for p in FONTS_DIR.rglob("*") if p.suffix.lower() in (".ttf", ".otf"))


def test_no_proprietary_font_is_bundled():
    for path in _font_files():
        assert not any(name in path.name.lower() for name in _PROPRIETARY), path
    from fontTools.ttLib import TTFont

    for path in _font_files():
        family = TTFont(str(path), lazy=True)["name"].getDebugName(1).lower()
        assert not any(name in family for name in _PROPRIETARY), (path, family)


def test_every_family_ships_its_license_and_is_documented():
    doc = (FONTS_DIR / "FONTS.md").read_text(encoding="utf-8")
    families = {p.parent for p in _font_files()}
    assert families
    for directory in families:
        licenses = [p for p in directory.iterdir() if p.suffix == ".txt"]
        assert licenses, f"{directory.name} has no license file next to its fonts"
        assert f"`{directory.name}/`" in doc
    assert all(path.parent != FONTS_DIR for path in _font_files()), "fonts live in per-family dirs"


def test_both_stylesheets_reference_existing_font_files():
    import re

    package = Path(FONTS_DIR).parents[1]
    for css in (package / "templates" / "report.css", package / "legacy" / "templates" / "boletin.css"):
        text = css.read_text(encoding="utf-8")
        urls = re.findall(r"url\('([^']+\.(?:ttf|otf))'\)", text)
        assert urls, css
        for url in urls:
            assert (css.parent / url).resolve().exists(), (css.name, url)
