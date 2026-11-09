"""Bundled fonts and the fontconfig set-up around a render.

The library ships only open-source fonts (see ``assets/fonts/FONTS.md``).
Body text defaults to Carlito, a metric-compatible replacement for
Calibri. A template package can bring its own faces (``fonts:`` in its
``package.yml``) and choose the body family (``font_family:``).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

PACKAGE_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

#: Body family of the default stylesheet.
DEFAULT_FONT_FAMILY = "Carlito"
#: What the stylesheet falls back to after the chosen family.
FALLBACK_STACK = "'Carlito', 'DejaVu Sans', 'Liberation Sans', sans-serif"

#: Metric-compatible pairs: open font → proprietary font it replaces.
#: The Word exporter declares the right-hand side as the substitute, so a
#: reader without the open font keeps every line break.
METRIC_COMPATIBLE: dict = {
    "Carlito": "Calibri",
    "TeX Gyre Adventor": "Century Gothic",
    "Selawik": "Segoe UI",
    "Liberation Serif": "Times New Roman",
}


def font_family_css_value(family: Optional[str]) -> str:
    """CSS ``font-family`` value with the library's fallbacks after ``family``."""
    name = str(family or "").strip().strip("'\"")
    if not name or name == DEFAULT_FONT_FAMILY:
        return FALLBACK_STACK
    return f"'{name}', {FALLBACK_STACK}"


def fontconfig_file(font_dirs: Iterable[Path]) -> Path:
    """A fontconfig file that knows ONLY ``font_dirs`` (scanned recursively).

    Isolating fontconfig is what makes a render reproducible: with the
    system configuration, the same HTML lays out differently on a machine
    that happens to have another font installed under the same name.
    """
    dirs: List[str] = []
    for directory in font_dirs:
        path = str(Path(directory).resolve())
        if path not in dirs and Path(path).is_dir():
            dirs.append(path)
    body = "".join(f"  <dir>{d}</dir>\n" for d in dirs)
    content = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        f"{body}"
        "</fontconfig>\n"
    )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    target = Path(tempfile.gettempdir()) / "pdfgen_juanipis" / f"fonts_{digest}.conf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="utf-8") != content:
        target.write_text(content, encoding="utf-8")
    return target


@contextlib.contextmanager
def isolated_fontconfig(font_dirs: Iterable[Path], *, enabled: bool = True) -> Iterator[Optional[Path]]:
    """Point ``FONTCONFIG_FILE`` at ``font_dirs`` for the duration of a render.

    WeasyPrint reads the variable when it creates a ``FontConfiguration``,
    so it must be set before that and is restored afterwards. Not
    thread-safe: the variable is process-wide.
    """
    if not enabled:
        yield None
        return
    conf = fontconfig_file(font_dirs)
    previous = os.environ.get("FONTCONFIG_FILE")
    os.environ["FONTCONFIG_FILE"] = str(conf)
    try:
        yield conf
    finally:
        if previous is None:
            os.environ.pop("FONTCONFIG_FILE", None)
        else:
            os.environ["FONTCONFIG_FILE"] = previous


__all__ = [
    "ASSETS_DIR",
    "DEFAULT_FONT_FAMILY",
    "FALLBACK_STACK",
    "FONTS_DIR",
    "METRIC_COMPATIBLE",
    "font_family_css_value",
    "fontconfig_file",
    "isolated_fontconfig",
]
