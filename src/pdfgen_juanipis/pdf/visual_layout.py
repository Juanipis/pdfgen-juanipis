"""Figure sizing heuristics: how tall an image may print, given its
container class, its chart type and its aspect ratio."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional at import time
    Image = None  # type: ignore[assignment]


_MODE_RATIO_ADJUSTMENTS = {
    "readability": {"ultra_wide": -10, "wide": -5, "square": 0, "tall": 10},
    "balanced": {"ultra_wide": -20, "wide": -10, "square": 5, "tall": 15},
    "compact": {"ultra_wide": -30, "wide": -15, "square": 5, "tall": 20},
}


@dataclass(frozen=True)
class ResolvedPDFVisualLayoutConfig:
    enabled: bool = True
    mode: str = "balanced"
    min_height_pt: int = 170
    max_height_pt: int = 280
    show_page_numbers: bool = False
    #: How tall a figure may grow to print at the full text width. The
    #: height caps below suit wide charts; a tall one (a bar per category)
    #: would hit the cap first and print at half the column with tiny
    #: labels. See :func:`compute_target_height_pt`.
    fit_width_max_height_pt: int = 400
    layout_max_height_pt: Dict[str, int] = field(
        default_factory=lambda: {
            "full": 240,
            "column": 225,
            "left": 190,
            "right": 190,
        }
    )
    chart_type_max_height_pt: Dict[str, int] = field(
        default_factory=lambda: {
            "line": 220,
            "area": 220,
            "scatter": 220,
            "bar": 245,
            "horizontal_bar": 265,
            "map": 275,
        }
    )


def resolve_pdf_visual_layout_config(raw_cfg: Any) -> ResolvedPDFVisualLayoutConfig:
    defaults = ResolvedPDFVisualLayoutConfig()
    if raw_cfg is None:
        return defaults

    enabled = _bool_attr(raw_cfg, "enabled", defaults.enabled)
    mode = str(_get_attr(raw_cfg, "mode", defaults.mode) or defaults.mode).strip().lower()
    if mode not in _MODE_RATIO_ADJUSTMENTS:
        mode = defaults.mode

    min_height_pt = _int_attr(raw_cfg, "min_height_pt", defaults.min_height_pt)
    max_height_pt = _int_attr(raw_cfg, "max_height_pt", defaults.max_height_pt)
    if min_height_pt <= 0:
        min_height_pt = defaults.min_height_pt
    if max_height_pt <= 0:
        max_height_pt = defaults.max_height_pt
    if min_height_pt > max_height_pt:
        min_height_pt, max_height_pt = defaults.min_height_pt, defaults.max_height_pt

    layout_map = dict(defaults.layout_max_height_pt)
    raw_layout_map = _get_attr(raw_cfg, "layout_max_height_pt", None)
    if isinstance(raw_layout_map, dict):
        for key, value in raw_layout_map.items():
            normalized_key = str(key).strip().lower()
            if normalized_key not in layout_map:
                continue
            try:
                layout_map[normalized_key] = int(value)
            except (TypeError, ValueError):
                continue

    chart_map = dict(defaults.chart_type_max_height_pt)
    raw_chart_map = _get_attr(raw_cfg, "chart_type_max_height_pt", None)
    if isinstance(raw_chart_map, dict):
        for key, value in raw_chart_map.items():
            normalized_key = normalize_chart_type(key)
            if not normalized_key:
                continue
            try:
                chart_map[normalized_key] = int(value)
            except (TypeError, ValueError):
                continue

    show_page_numbers = _bool_attr(raw_cfg, "show_page_numbers", defaults.show_page_numbers)
    fit_width_max_height_pt = _int_attr(
        raw_cfg, "fit_width_max_height_pt", defaults.fit_width_max_height_pt,
    )

    return ResolvedPDFVisualLayoutConfig(
        enabled=enabled,
        mode=mode,
        min_height_pt=min_height_pt,
        max_height_pt=max_height_pt,
        show_page_numbers=show_page_numbers,
        fit_width_max_height_pt=fit_width_max_height_pt,
        layout_max_height_pt=layout_map,
        chart_type_max_height_pt=chart_map,
    )


def parse_chart_meta_json(text: str) -> Optional[Dict[str, Any]]:
    payload = (text or "").strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def normalize_chart_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    normalized = raw.replace("-", "_").replace(" ", "_")
    aliases = {
        "hbar": "horizontal_bar",
        "horizontalbar": "horizontal_bar",
        "barh": "horizontal_bar",
        "choropleth": "map",
        "geo": "map",
        "geographic": "map",
        "mapa": "map",
    }
    return aliases.get(normalized, normalized)


def extract_chart_type_from_meta(meta: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(meta, dict):
        return None
    spec = meta.get("spec")
    if isinstance(spec, dict):
        value = normalize_chart_type(spec.get("chart_type"))
        if value:
            return value
    return normalize_chart_type(meta.get("chart_type"))


def infer_layout_key(container_class: str) -> str:
    classes = {part.strip().lower() for part in str(container_class or "").split() if part.strip()}
    for key in ("left", "right", "column", "full"):
        if f"figure-{key}" in classes:
            return key
    return "full"


def classify_aspect_ratio(ratio: Optional[float]) -> Optional[str]:
    if ratio is None or ratio <= 0:
        return None
    if ratio >= 1.90:
        return "ultra_wide"
    if ratio >= 1.35:
        return "wide"
    if ratio >= 0.85:
        return "square"
    return "tall"


def compute_target_height_pt(
    *,
    cfg: ResolvedPDFVisualLayoutConfig,
    layout_key: str,
    chart_type: Optional[str],
    aspect_ratio: Optional[float],
    text_width_pt: Optional[float] = None,
) -> Optional[int]:
    """The ``max-height`` (pt) a figure's image prints at.

    The caps are height caps, so for a TALL image the height binds before
    the width does: a 740×700 chart printed 240 pt tall is 254 pt wide —
    57 % of the column, with unreadable labels. Given the
    column width, a figure that would print narrower than the text may
    grow to the height that fills it, up to ``fit_width_max_height_pt``.
    Wide figures are bound by the width already and do not change.
    """
    if not cfg.enabled:
        return None

    normalized_layout = str(layout_key or "full").strip().lower()
    if normalized_layout not in cfg.layout_max_height_pt:
        normalized_layout = "full"

    base = int(cfg.layout_max_height_pt.get(normalized_layout, cfg.layout_max_height_pt["full"]))
    normalized_chart_type = normalize_chart_type(chart_type)
    type_cap = (
        int(cfg.chart_type_max_height_pt[normalized_chart_type])
        if normalized_chart_type and normalized_chart_type in cfg.chart_type_max_height_pt
        else None
    )

    if type_cap is not None:
        target = min(base, type_cap) if normalized_layout in {"left", "right"} else type_cap
    else:
        target = base

    ratio_bucket = classify_aspect_ratio(aspect_ratio)
    if ratio_bucket:
        target += int(_MODE_RATIO_ADJUSTMENTS.get(cfg.mode, _MODE_RATIO_ADJUSTMENTS["balanced"]).get(ratio_bucket, 0))

    target = max(int(cfg.min_height_pt), min(int(cfg.max_height_pt), int(target)))
    if text_width_pt and aspect_ratio and aspect_ratio > 0:
        full_width_height = float(text_width_pt) / float(aspect_ratio)
        if full_width_height > target:
            ceiling = max(int(cfg.fit_width_max_height_pt), int(cfg.max_height_pt))
            target = int(min(full_width_height, ceiling))
    return int(target)


def _svg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """``width``/``height`` (or the ``viewBox``) of an SVG's root element."""
    import re

    head = data[:4096].decode("utf-8", "ignore")
    root = re.search(r"<svg\b[^>]*>", head, re.IGNORECASE)
    if not root:
        return None
    tag = root.group(0)
    w = re.search(r'\bwidth="([\d.]+)(?:px)?"', tag)
    h = re.search(r'\bheight="([\d.]+)(?:px)?"', tag)
    if w and h:
        return int(float(w.group(1))), int(float(h.group(1)))
    box = re.search(r'\bviewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', tag)
    if box:
        return int(float(box.group(1))), int(float(box.group(2)))
    return None


def image_dimensions_from_bytes(data: Optional[bytes]) -> Optional[Tuple[int, int]]:
    """Pixel size of a raster image or an SVG.

    PIL cannot read SVG, so without this the aspect-ratio rules never
    applied to SVG charts and every one printed at the same height
    whatever its shape.
    """
    if not data:
        return None
    if data.lstrip()[:5].lower() in (b"<?xml", b"<svg ") or b"<svg" in data[:512]:
        dims = _svg_dimensions(data)
        if dims and dims[0] and dims[1]:
            return dims
        return None
    if Image is None:
        return None
    try:
        with Image.open(BytesIO(data)) as im:
            w, h = im.size
    except Exception:  # noqa: BLE001
        return None
    if not w or not h:
        return None
    return int(w), int(h)


def _get_attr(obj: Any, name: str, default: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int_attr(obj: Any, name: str, default: int) -> int:
    value = _get_attr(obj, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _bool_attr(obj: Any, name: str, default: bool) -> bool:
    value = _get_attr(obj, name, default)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

