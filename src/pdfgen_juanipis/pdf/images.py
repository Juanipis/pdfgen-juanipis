"""Image loading and down-scaling for the PDF.

Images are resized to what the text column can actually show (at 2× for
sharp print) and re-embedded as PNG data URLs, so a 6000 px photograph
does not bloat the PDF.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from PIL import Image

#: Content-area width images are fitted to, in points.
CONTENT_WIDTH_PT = 444.0
#: Tall enough for a figure grown to the text width (see
#: ``visual_layout.compute_target_height_pt``).
MAX_IMAGE_HEIGHT_PT = 420.0
#: 2× resolution for sharp print.
IMAGE_RESOLUTION_SCALE = 2.0
CSS_PX_PER_PT = 96.0 / 72.0
MAX_IMAGE_WIDTH_PX = int(CONTENT_WIDTH_PT * CSS_PX_PER_PT * IMAGE_RESOLUTION_SCALE)
MAX_IMAGE_HEIGHT_PX = int(MAX_IMAGE_HEIGHT_PT * CSS_PX_PER_PT * IMAGE_RESOLUTION_SCALE)


def read_image_bytes(src: str) -> Optional[bytes]:
    """Bytes of a ``data:`` URL, a ``file://`` URL or a local path."""
    if src.startswith("data:image/"):
        try:
            header, b64 = src.split(",", 1)
        except ValueError:
            return None
        if ";base64" not in header.lower():
            return None
        try:
            return base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            return None

    parsed = urlparse(src)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path))
        if path.exists():
            try:
                return path.read_bytes()
            except Exception:  # noqa: BLE001
                return None

    path = Path(src)
    try:
        if path.exists():
            return path.read_bytes()
    except (OSError, ValueError):
        return None
    return None


def fit_image_bytes(data: bytes) -> Optional[bytes]:
    """Down-scale a raster image to the content area; ``None`` if unreadable."""
    try:
        with Image.open(BytesIO(data)) as im:
            im = im.convert("RGBA")
            w, h = im.size
            if w <= 0 or h <= 0:
                return None
            scale = min(1.0, MAX_IMAGE_WIDTH_PX / float(w), MAX_IMAGE_HEIGHT_PX / float(h))
            if scale < 1.0:
                new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                im = im.resize(new_size, Image.Resampling.LANCZOS)
            out = BytesIO()
            im.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except Exception:  # noqa: BLE001 - SVG and friends are left untouched
        return None


def fit_image_src_for_pdf(src: str) -> Optional[str]:
    """A PNG data URL of the image fitted to the content area, or ``None``."""
    image_bytes = read_image_bytes(src)
    if not image_bytes:
        return None
    fitted = fit_image_bytes(image_bytes)
    if not fitted:
        return None
    return "data:image/png;base64," + base64.b64encode(fitted).decode("ascii")


__all__ = [
    "CONTENT_WIDTH_PT",
    "MAX_IMAGE_HEIGHT_PT",
    "fit_image_bytes",
    "fit_image_src_for_pdf",
    "read_image_bytes",
]
