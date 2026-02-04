import copy
import json
import pathlib
import re
from typing import Any, Dict, List, Tuple


ALLOWED_BLOCK_TYPES = {"text", "table", "figure", "map_grid", "html"}
DEFAULT_TABLE_WIDTH = 532.66
DEFAULT_DEP_WIDTH = 120.0


def validate_and_normalize(data: Dict[str, Any], root_dir: pathlib.Path) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    normalized = copy.deepcopy(data)

    schema_warnings = _validate_schema(normalized, root_dir)
    warnings.extend(schema_warnings)

    theme = normalized.setdefault("theme", {})
    theme.setdefault("footer_site", "")
    theme.setdefault("footer_phone", "")
    theme.setdefault("show_header_titles", False)

    assets_dir = root_dir / "assets"

    refs_catalog = normalized.get("refs_catalog", {})
    if refs_catalog and not isinstance(refs_catalog, dict):
        warnings.append("refs_catalog must be a dict; ignoring invalid value")
        refs_catalog = {}
        normalized["refs_catalog"] = refs_catalog

    if "pages" in normalized:
        _validate_pages(normalized, assets_dir, refs_catalog, warnings)
    elif "sections" in normalized:
        _validate_sections(normalized, assets_dir, refs_catalog, warnings)
    else:
        warnings.append("data must include 'sections' or 'pages'")

    return normalized, warnings


def _validate_pages(
    data: Dict[str, Any],
    assets_dir: pathlib.Path,
    refs_catalog: Dict[str, str],
    warnings: List[str],
) -> None:
    pages = data.get("pages", [])
    if not isinstance(pages, list):
        warnings.append("pages must be a list")
        return

    for page in pages:
        page.setdefault("refs_catalog", refs_catalog)
        _normalize_theme_paths(page, assets_dir, warnings)
        _validate_blocks(page.get("blocks", []), assets_dir, refs_catalog, warnings)


def _validate_sections(
    data: Dict[str, Any],
    assets_dir: pathlib.Path,
    refs_catalog: Dict[str, str],
    warnings: List[str],
) -> None:
    sections = data.get("sections", [])
    if not isinstance(sections, list):
        warnings.append("sections must be a list")
        return

    _normalize_theme_paths(data.get("theme", {}), assets_dir, warnings)

    for section in sections:
        _validate_blocks(section.get("content", []), assets_dir, refs_catalog, warnings)


def _validate_blocks(
    blocks: List[Dict[str, Any]],
    assets_dir: pathlib.Path,
    refs_catalog: Dict[str, str],
    warnings: List[str],
) -> None:
    if not isinstance(blocks, list):
        warnings.append("blocks/content must be a list")
        return

    for block in blocks:
        block_type = block.get("type", "text")
        if block_type not in ALLOWED_BLOCK_TYPES:
            warnings.append(f"Unknown block type: {block_type}")
            continue

        if block_type == "table":
            _validate_table(block.get("table", {}), warnings)
        elif block_type == "figure":
            _normalize_path(block, "path", assets_dir, warnings)
        elif block_type == "map_grid":
            items = block.get("items", [])
            if not isinstance(items, list):
                warnings.append("map_grid.items must be a list")
            else:
                for item in items:
                    _normalize_path(item, "path", assets_dir, warnings)
        elif block_type == "text":
            _validate_text_block(block, refs_catalog, warnings)
        elif block_type == "html":
            _warn_missing_refs(block.get("html", ""), refs_catalog, warnings)


def _validate_table(table: Dict[str, Any], warnings: List[str]) -> None:
    groups = table.get("groups", [])
    rows = table.get("rows", [])

    if not groups:
        warnings.append("table.groups is empty")
    if not rows:
        warnings.append("table.rows is empty")

    table.setdefault("total_width", DEFAULT_TABLE_WIDTH)
    table.setdefault("dep_width", DEFAULT_DEP_WIDTH)

    num_cols = 0
    for group in groups:
        months = group.get("months", [])
        if not months:
            warnings.append("table group has empty months")
        num_cols += len(months)

    if num_cols == 0:
        return

    for row in rows:
        vals = row.get("vals", [])
        if not isinstance(vals, list):
            warnings.append("table row vals must be a list")
            row["vals"] = []
            vals = row["vals"]
        if len(vals) < num_cols:
            warnings.append(
                f"table row '{row.get('dep', '')}' has {len(vals)} vals; expected {num_cols}. Padding."
            )
            row["vals"] = vals + [""] * (num_cols - len(vals))
        elif len(vals) > num_cols:
            warnings.append(
                f"table row '{row.get('dep', '')}' has {len(vals)} vals; expected {num_cols}. Truncating."
            )
            row["vals"] = vals[:num_cols]


def _validate_text_block(block: Dict[str, Any], refs_catalog: Dict[str, str], warnings: List[str]) -> None:
    text = block.get("text", "")
    if isinstance(text, list):
        for paragraph in text:
            _warn_missing_refs(paragraph, refs_catalog, warnings)
    else:
        _warn_missing_refs(text, refs_catalog, warnings)


def _warn_missing_refs(text: str, refs_catalog: Dict[str, str], warnings: List[str]) -> None:
    if not refs_catalog or not text:
        return
    for ref_id in _extract_ref_ids(str(text)):
        if ref_id not in refs_catalog:
            warnings.append(f"Missing refs_catalog entry for [{ref_id}]")


def _normalize_theme_paths(theme: Dict[str, Any], assets_dir: pathlib.Path, warnings: List[str]) -> None:
    _normalize_path(theme, "header_banner_path", assets_dir, warnings)
    _normalize_path(theme, "header_banner_path_cont", assets_dir, warnings)
    _normalize_path(theme, "header_logo_path", assets_dir, warnings)


def _normalize_path(container: Dict[str, Any], key: str, assets_dir: pathlib.Path, warnings: List[str]) -> None:
    if key not in container:
        return
    value = container.get(key)
    if not value:
        return
    path = pathlib.Path(str(value))
    if path.is_absolute():
        return
    candidate = assets_dir / path
    if candidate.exists():
        container[key] = str(candidate.resolve())
        return

    package_assets = pathlib.Path(__file__).resolve().parent / "assets"
    candidate = package_assets / path
    if candidate.exists():
        container[key] = str(candidate.resolve())
    else:
        warnings.append(f"Asset not found for {key}: {value}")


def _extract_ref_ids(text: str) -> List[str]:
    ids: List[str] = []
    seen = set()
    for match in re.findall(r"\[(.*?)\]", text):
        for token in re.split(r"[;,]\s*", match.strip()):
            token = token.strip()
            if not token:
                continue
            range_match = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", token)
            if range_match:
                start = int(range_match.group(1))
                end = int(range_match.group(2))
                step = 1 if end >= start else -1
                for val in range(start, end + step, step):
                    key = str(val)
                    if key not in seen:
                        ids.append(key)
                        seen.add(key)
                continue
            if re.match(r"^\d+$", token):
                if token not in seen:
                    ids.append(token)
                    seen.add(token)
    return ids


def _validate_schema(data: Dict[str, Any], root_dir: pathlib.Path) -> List[str]:
    warnings: List[str] = []
    schema_path = root_dir / "src" / "pdfgen" / "schema.json"
    if not schema_path.exists():
        schema_path = pathlib.Path(__file__).resolve().parent / "schema.json"
    if not schema_path.exists():
        warnings.append("schema.json not found; skipping schema validation")
        return warnings
    try:
        from jsonschema import Draft7Validator
    except Exception:
        warnings.append("jsonschema not installed; skipping schema validation")
        return warnings

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"Failed to read schema.json: {exc}")
        return warnings

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    for err in errors:
        loc = ".".join(str(p) for p in err.path)
        prefix = f"schema:{loc}" if loc else "schema"
        warnings.append(f"{prefix}: {err.message}")
    return warnings
