import dataclasses
import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from weasyprint import HTML, CSS

    WEASYPRINT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency for measurement
    HTML = None
    CSS = None
    WEASYPRINT_AVAILABLE = False

LOGGER = logging.getLogger(__name__)
CSS_PX_TO_PT = 72.0 / 96.0


@dataclasses.dataclass(frozen=True)
class LayoutConfig:
    page_width_pt: float = 612.0
    page_height_pt: float = 792.0
    content_left_pt: float = 85.1
    content_width_pt: float = 444.0
    default_intro_top_pt: float = 122.18
    default_content_top_pt: float = 150.0
    continuation_content_top_pt: float = 110.0
    header_title_top_pt: float = 73.7
    header_subtitle_top_pt: float = 90.77
    header_title_left_pt: float = 94.7
    header_title_width_pt: float = 430.0
    header_subtitle_left_pt: float = 260.8
    header_subtitle_width_pt: float = 220.0
    header_logo_top_pt: float = 13.95
    header_logo_height_pt: float = 36.75
    header_banner_height_pt: float = 79.5
    header_title_min_top_pt: float = 100.0
    footer_contact_bottom_pt: float = 32.0
    footer_page_bottom_pt: float = 134.0
    footer_meta_bottom_pt: float = 70.0
    footer_meta_gap_pt: float = 6.0
    header_gap_pt: float = 6.0
    intro_gap_pt: float = 12.0
    header_subtitle_gap_pt: float = 2.0
    safety_pad_pt: float = 6.0
    min_content_height_pt: float = 48.0

    def to_template(self) -> Dict[str, float]:
        return {
            "content_top": self.default_content_top_pt,
            "intro_top": self.default_intro_top_pt,
        }


@dataclasses.dataclass
class PageLayoutState:
    intro_top_pt: float
    content_top_pt: float
    content_height_base_pt: float
    content_height_meta_pt: float
    reserved_base_pt: float
    footer_meta_bottom_pt: float


@dataclasses.dataclass
class BlockItem:
    data: Dict[str, Any]
    height_pt: float
    keep_with_next: bool = False
    refs: List[str] = dataclasses.field(default_factory=list)
    notes: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class PageBuild:
    blocks: List[BlockItem]
    height_pt: float
    refs: List[str]
    notes: List[str]


class BlockMeasurer:
    def __init__(self, css_path: str, base_url: str, layout: LayoutConfig):
        self.css_path = css_path
        self.base_url = base_url
        self.layout = layout
        self._height_cache: Dict[Tuple[Any, ...], float] = {}

    def measure_html(self, html_fragment: str) -> float:
        key = ("html", html_fragment)
        cached = self._height_cache.get(key)
        if cached is not None:
            return cached

        height = self._measure_with_weasyprint(
            f"<div class=\"content\"><div id=\"probe\">{html_fragment}</div></div>",
            "probe",
        )
        if height is None:
            height = self._estimate_html_height(html_fragment)
        self._height_cache[key] = height
        return height

    def measure_text_block(self, text: str, class_name: str) -> float:
        key = ("text", class_name, text)
        cached = self._height_cache.get(key)
        if cached is not None:
            return cached

        html = f"<div id=\"probe\" class=\"{class_name}\">{text}</div>"
        height = self._measure_with_weasyprint(html, "probe")
        if height is None:
            height = self._estimate_text_height(text, class_name)
        self._height_cache[key] = height
        return height

    def measure_table(self, table: Dict[str, Any], show_header: bool) -> float:
        rows_key = tuple(tuple(row.get("vals", [])) + (row.get("dep", ""),) for row in table["rows"])
        key = ("table", show_header, rows_key)
        cached = self._height_cache.get(key)
        if cached is not None:
            return cached

        html = build_table_html(table, show_header=show_header)
        content_width = table.get("total_width") or self.layout.content_width_pt
        height = self._measure_with_weasyprint(html, "probe-table", content_width=content_width)
        if height is None:
            height = self._estimate_table_height(table, show_header)
        self._height_cache[key] = height
        return height

    def measure_footer_meta(self, refs: List[str], notes: List[str]) -> float:
        if not refs and not notes:
            return 0.0
        refs_html = "".join(f"<div class=\"refs-text\">{ref}</div>" for ref in refs)
        notes_html = "".join(f"<div>{note}</div>" for note in notes)
        html = """
        <div id=\"probe\" class=\"footer-meta\">
          {refs_block}
          {notes_block}
        </div>
        """.format(
            refs_block=(
                f"<div class=\"refs\"><div class=\"refs-line\"></div>{refs_html}</div>"
                if refs
                else ""
            ),
            notes_block=(f"<div class=\"footer-notes\">{notes_html}</div>" if notes else ""),
        )
        height = self._measure_with_weasyprint(html, "probe")
        if height is None:
            height = self._estimate_refs_height(refs) + self._estimate_notes_height(notes)
        return height

    def measure_footer_contact(self, site: str, phone: str) -> float:
        html = f"<div id=\"probe\" class=\"footer-contact\"><div>{site}</div><div>{phone}</div></div>"
        height = self._measure_with_weasyprint(html, "probe")
        if height is None:
            height = 22.0
        return height

    def measure_footer_page(self, page_number: str) -> float:
        if not page_number:
            return 0.0
        html = f"<div id=\"probe\" class=\"footer-page\">{page_number}</div>"
        height = self._measure_with_weasyprint(html, "probe")
        if height is None:
            height = 8.0
        return height

    def _measure_with_weasyprint(
        self, body_html: str, probe_id: str, content_width: Optional[float] = None
    ) -> Optional[float]:
        if not WEASYPRINT_AVAILABLE:
            return None

        if content_width is None:
            content_width = self.layout.content_width_pt
        measure_css = MEASURE_CSS.format(content_width=content_width)
        full_html = f"""
<!DOCTYPE html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\" />
</head>
<body>
  <div class=\"measure-root\">{body_html}</div>
</body>
</html>
"""
        try:
            document = HTML(string=full_html, base_url=self.base_url).render(
                stylesheets=[
                    CSS(filename=str(self.css_path)),
                    CSS(string=measure_css),
                ]
            )
        except Exception as exc:  # pragma: no cover - runtime dependency may fail
            LOGGER.warning("WeasyPrint measurement failed: %s", exc)
            return None

        if not document.pages:
            return None

        box = _find_box_by_id(document.pages[0], probe_id)
        if box is None:
            return None

        height = getattr(box, "height", 0.0) or 0.0
        height += getattr(box, "margin_top", 0.0) or 0.0
        height += getattr(box, "margin_bottom", 0.0) or 0.0
        height += getattr(box, "padding_top", 0.0) or 0.0
        height += getattr(box, "padding_bottom", 0.0) or 0.0
        return float(height) * CSS_PX_TO_PT

    def _estimate_html_height(self, html_fragment: str) -> float:
        lines = (
            html_fragment.count("<br")
            + html_fragment.count("</p>")
            + html_fragment.count("</div>")
        )
        if "section-title" in html_fragment:
            return 20 + lines * 14
        return lines * 14 + 10

    def _estimate_text_height(self, text: str, class_name: str) -> float:
        chars_per_line = 80
        if class_name in {"header-title", "header-subtitle"}:
            chars_per_line = 45
        elif class_name == "intro":
            chars_per_line = 70
        lines = max(1, math.ceil(len(text) / chars_per_line))
        font_size = 12.0
        if class_name in {"header-title", "header-subtitle"}:
            font_size = 14.0
        line_height = 1.05 if class_name in {"header-title", "header-subtitle"} else 1.1
        return lines * font_size * line_height

    def _estimate_table_height(self, table: Dict[str, Any], show_header: bool) -> float:
        num_rows = len(table["rows"])
        header_height = 40 if show_header else 0
        row_height = 16
        return header_height + (num_rows * row_height) + 16

    def _estimate_refs_height(self, refs: List[str]) -> float:
        if not refs:
            return 0.0
        line_height = 8.0 * 1.1
        return 6.0 + len(refs) * line_height

    def _estimate_notes_height(self, notes: List[str]) -> float:
        if not notes:
            return 0.0
        line_height = 8.0 * 1.1
        return len(notes) * line_height


MEASURE_CSS = """
@page {{ size: Letter; margin: 0; }}
html, body {{ margin: 0; padding: 0; }}
.measure-root {{ margin: 0; padding: 0; }}
.page {{ position: static !important; width: auto; height: auto; }}
.content, .intro, .header-title, .header-subtitle, .footer-contact,
.footer-page, .footer-meta, .refs, .footer-notes {{
  position: static !important;
}}
.content, .intro, .footer-meta, .footer-contact {{ width: {content_width}pt; }}
.table-wrap {{ margin-left: 0 !important; }}
"""


def _find_box_by_id(page: Any, element_id: str) -> Optional[Any]:
    root = getattr(page, "_page_box", None)
    if root is None:
        return None

    for box in _iter_boxes(root):
        element = getattr(box, "element", None)
        if element is not None and element.get("id") == element_id:
            return box
    return None


def _iter_boxes(box: Any) -> Iterable[Any]:
    yield box
    for child in getattr(box, "children", []) or []:
        yield from _iter_boxes(child)


def build_table_html(table: Dict[str, Any], show_header: bool = True) -> str:
    total_width = table.get("total_width") or 532.66
    dep_width = table.get("dep_width") or 120.0
    groups = table.get("groups", [])
    num_cols = sum(len(group.get("months", [])) for group in groups)
    num_width = (total_width - dep_width) / (num_cols if num_cols else 1)

    cols = [f"<col style=\"width: {dep_width:.2f}pt;\">"]
    cols.extend([f"<col style=\"width: {num_width:.2f}pt;\">" for _ in range(num_cols)])

    header_html = ""
    if show_header:
        header_top = [
            "<tr>",
            "<th class=\"col-dep\" rowspan=\"2\">Departamento/Mes</th>",
        ]
        for group in groups:
            title = group.get("title", "")
            span = len(group.get("months", []))
            header_top.append(f"<th class=\"col-num\" colspan=\"{span}\">{title}</th>")
        header_top.append("</tr>")

        header_bottom = ["<tr>"]
        for group in groups:
            for month in group.get("months", []):
                header_bottom.append(f"<th class=\"col-num\">{month}</th>")
        header_bottom.append("</tr>")

        header_html = f"<thead>{''.join(header_top)}{''.join(header_bottom)}</thead>"

    body_rows = []
    for row in table.get("rows", []):
        cells = [f"<td class=\"col-dep\">{row.get('dep', '')}</td>"]
        cells.extend(f"<td>{val}</td>" for val in row.get("vals", []))
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    body_html = f"<tbody>{''.join(body_rows)}</tbody>"

    return (
        f"<div class=\"content\" style=\"width: {total_width:.2f}pt;\">"
        f"<div class=\"table-wrap\" style=\"width: {total_width:.2f}pt; margin-left: 0;\">"
        "<table id=\"probe-table\" class=\"tabla-abaco\">"
        f"<colgroup>{''.join(cols)}</colgroup>"
        f"{header_html}"
        f"{body_html}"
        "</table>"
        "</div>"
        "</div>"
    )


class Paginator:
    def __init__(
        self,
        layout: LayoutConfig,
        css_path: str,
        base_url: str,
        fonts_conf_path: Optional[str] = None,
    ):
        if fonts_conf_path:
            os.environ.setdefault("FONTCONFIG_FILE", str(fonts_conf_path))
        self.layout = layout
        self.measurer = BlockMeasurer(css_path, base_url, layout)
        self._header_single_line_height = self.measurer.measure_text_block("X", "header-title")

    def paginate(self, pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result_pages: List[Dict[str, Any]] = []
        for page in pages_data:
            if page.get("cover"):
                page_copy = dict(page)
                page_copy.setdefault("page_number", "")
                page_copy.setdefault("show_header_titles", False)
                result_pages.append(page_copy)
                continue
            result_pages.extend(self._paginate_single_page(page, result_pages))
        return result_pages

    def _paginate_single_page(
        self, page: Dict[str, Any], accumulated_pages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        blocks = page.get("blocks", [])
        refs = page.get("refs", [])
        notes = page.get("footer_notes", [])
        has_meta = bool(refs or notes)

        (
            header_title_top,
            header_subtitle_top,
            header_bottom,
            header_title_style,
            header_subtitle_style,
        ) = self._compute_header_positions(page, show_titles=True)
        (
            header_title_top_other,
            header_subtitle_top_other,
            header_bottom_other,
            header_title_style_other,
            header_subtitle_style_other,
        ) = self._compute_header_positions(page, show_titles=False)
        layout_first = self._compute_layout_state(
            page,
            header_bottom,
            include_intro=True,
            compact_top=False,
        )
        layout_other = self._compute_layout_state(
            page,
            header_bottom_other,
            include_intro=False,
            compact_top=True,
        )

        min_page_height = min(
            layout_first.content_height_base_pt,
            layout_first.content_height_meta_pt,
            layout_other.content_height_base_pt,
            layout_other.content_height_meta_pt,
        )

        normalized_blocks = self._normalize_blocks(blocks, min_page_height)
        pages_build: List[PageBuild] = []
        idx = 0
        page_idx = 0
        while idx < len(normalized_blocks):
            layout_state = layout_first if page_idx == 0 else layout_other
            page_refs: List[str] = []
            page_notes: List[str] = []

            if has_meta:
                remaining_height = sum(block.height_pt for block in normalized_blocks[idx:])
                if remaining_height <= layout_state.content_height_meta_pt:
                    limit = layout_state.content_height_meta_pt
                else:
                    limit = layout_state.content_height_base_pt
            else:
                limit = layout_state.content_height_base_pt
            limit = max(limit, self.layout.min_content_height_pt)

            used = 0.0
            page_blocks: List[BlockItem] = []
            while idx < len(normalized_blocks):
                block = normalized_blocks[idx]
                block_height = block.height_pt
                block_refs = list(block.refs)
                block_notes = list(block.notes)

                if block.keep_with_next and idx + 1 < len(normalized_blocks):
                    next_block = normalized_blocks[idx + 1]
                    next_height = next_block.height_pt
                    if next_block.data.get("type") == "table":
                        available = limit - used - block_height
                        if available <= 0:
                            if page_blocks:
                                break
                        else:
                            next_table = next_block.data.get("table", {})
                            show_header = next_table.get("show_header", True)
                            max_rows = self._max_table_rows_that_fit(
                                next_table,
                                next_table.get("rows", []),
                                available,
                                show_header,
                            )
                            next_height = (
                                self.measurer.measure_table(
                                    {
                                        "groups": next_table.get("groups", []),
                                        "rows": next_table.get("rows", [])[: max_rows or 1],
                                        "total_width": next_table.get("total_width"),
                                        "dep_width": next_table.get("dep_width"),
                                    },
                                    show_header,
                                )
                                if max_rows
                                else next_height
                            )
                    if used + block_height + next_height > limit:
                        if page_blocks:
                            break
                        if page_idx == 0 and page.get("intro"):
                            break

                if block_refs or block_notes:
                    new_limit = min(
                        limit,
                        self._content_height_with_meta(
                            layout_state, page_refs + block_refs, page_notes + block_notes
                        ),
                    )
                    if used > new_limit and page_blocks:
                        break
                    limit = new_limit

                split_table = False
                if block.data.get("type") == "table":
                    available_height = limit - used
                    if available_height <= 0 and page_blocks:
                        break
                    if available_height <= 0:
                        available_height = limit

                    block, split_table = self._split_table_to_fit(
                        normalized_blocks,
                        idx,
                        available_height,
                    )
                    block_height = block.height_pt

                if used + block_height > limit and page_blocks:
                    break

                if used + block_height > limit and not page_blocks:
                    LOGGER.warning(
                        "Block exceeds page height limit (%.2f > %.2f); forcing placement.",
                        block_height,
                        limit,
                    )

                page_blocks.append(block)
                used += block_height
                if block_refs:
                    page_refs.extend(block_refs)
                if block_notes:
                    page_notes.extend(block_notes)
                idx += 1

                if split_table:
                    break

            pages_build.append(PageBuild(blocks=page_blocks, height_pt=used, refs=page_refs, notes=page_notes))
            page_idx += 1

        output_pages: List[Dict[str, Any]] = []
        for build_idx, build in enumerate(pages_build):
            is_first = build_idx == 0
            is_last = build_idx == len(pages_build) - 1
            layout_state = layout_first if is_first else layout_other

            show_header_titles = len(accumulated_pages) == 0 and is_first
            output_pages.append(
                self._build_page_dict(
                    page,
                    build,
                    layout_state,
                    include_intro=is_first,
                    include_meta=(has_meta and is_last),
                    page_number=str(len(accumulated_pages) + len(output_pages) + 1),
                    header_title_top=header_title_top if show_header_titles else header_title_top_other,
                    header_subtitle_top=header_subtitle_top if show_header_titles else header_subtitle_top_other,
                    header_title_style=header_title_style if show_header_titles else header_title_style_other,
                    header_subtitle_style=(
                        header_subtitle_style if show_header_titles else header_subtitle_style_other
                    ),
                    show_header_titles=show_header_titles,
                )
            )

        return output_pages

    def _build_page_dict(
        self,
        source_page: Dict[str, Any],
        build: PageBuild,
        layout_state: PageLayoutState,
        include_intro: bool,
        include_meta: bool,
        page_number: str,
        header_title_top: float,
        header_subtitle_top: float,
        header_title_style: Dict[str, float],
        header_subtitle_style: Dict[str, float],
        show_header_titles: bool,
    ) -> Dict[str, Any]:
        refs = list(build.refs)
        notes = list(build.notes)
        if include_meta:
            refs.extend(source_page.get("refs", []))
            notes.extend(source_page.get("footer_notes", []))

        banner_path = source_page["header_banner_path"]
        banner_path_cont = source_page.get("header_banner_path_cont")
        if not banner_path_cont:
            try:
                banner_file = Path(banner_path)
                candidate = banner_file.with_name(f"{banner_file.stem}-clean{banner_file.suffix}")
                if candidate.exists():
                    banner_path_cont = str(candidate)
            except OSError:
                banner_path_cont = None
        if not banner_path_cont:
            banner_path_cont = banner_path

        # Prefer clean banner for all pages when available to avoid duplicated titles.
        if banner_path_cont and banner_path_cont != banner_path:
            banner_path = banner_path_cont

        page_dict = {
            "header_banner_path": banner_path,
            "header_banner_path_cont": banner_path_cont,
            "header_logo_path": source_page["header_logo_path"],
            "title_line1": source_page["title_line1"],
            "title_line2": source_page["title_line2"],
            "intro": source_page.get("intro", "") if include_intro else "",
            "blocks": [block.data for block in build.blocks],
            "refs": refs,
            "footer_notes": notes,
            "page_number": page_number,
            "footer_site": source_page.get("footer_site", ""),
            "footer_phone": source_page.get("footer_phone", ""),
            "intro_top": layout_state.intro_top_pt,
            "content_top": layout_state.content_top_pt,
            "header_title_top": header_title_top,
            "header_subtitle_top": header_subtitle_top,
            "header_title_left": header_title_style["left"],
            "header_title_width": header_title_style["width"],
            "header_title_align": header_title_style["align"],
            "header_subtitle_left": header_subtitle_style["left"],
            "header_subtitle_width": header_subtitle_style["width"],
            "header_subtitle_align": header_subtitle_style["align"],
            "show_header_titles": show_header_titles,
            "footer_meta_bottom": layout_state.footer_meta_bottom_pt,
        }
        return page_dict

    def _compute_header_positions(
        self, page: Dict[str, Any], show_titles: bool = True
    ) -> Tuple[float, float, float, Dict[str, float], Dict[str, float]]:
        title_text = page.get("title_line1", "") if show_titles else ""
        subtitle_text = page.get("title_line2", "") if show_titles else ""

        title_height = self.measurer.measure_text_block(title_text, "header-title")
        subtitle_height = self.measurer.measure_text_block(subtitle_text, "header-subtitle")

        title_top = max(self.layout.header_title_top_pt, self.layout.header_title_min_top_pt)
        subtitle_top = max(
            self.layout.header_subtitle_top_pt,
            title_top + title_height + self.layout.header_subtitle_gap_pt,
        )

        is_multi_line = title_height > self._header_single_line_height * 1.15
        if is_multi_line:
            title_style = {
                "left": self.layout.content_left_pt,
                "width": self.layout.content_width_pt,
                "align": "center",
            }
            subtitle_style = {
                "left": self.layout.content_left_pt,
                "width": self.layout.content_width_pt,
                "align": "center",
            }
        else:
            title_style = {
                "left": self.layout.header_title_left_pt,
                "width": self.layout.header_title_width_pt,
                "align": "left",
            }
            subtitle_style = {
                "left": self.layout.header_subtitle_left_pt,
                "width": self.layout.header_subtitle_width_pt,
                "align": "left",
            }

        header_bottom = max(
            self.layout.header_banner_height_pt,
            self.layout.header_logo_top_pt + self.layout.header_logo_height_pt,
            title_top + title_height,
            subtitle_top + subtitle_height,
        )
        return title_top, subtitle_top, header_bottom, title_style, subtitle_style

    def _compute_layout_state(
        self,
        page: Dict[str, Any],
        header_bottom: float,
        include_intro: bool,
        compact_top: bool,
    ) -> PageLayoutState:
        intro_text = page.get("intro", "") if include_intro else ""
        intro_height = (
            self.measurer.measure_text_block(intro_text, "intro") if intro_text else 0.0
        )

        intro_top = max(self.layout.default_intro_top_pt, header_bottom + self.layout.header_gap_pt)

        min_content_top = (
            self.layout.continuation_content_top_pt if compact_top else self.layout.default_content_top_pt
        )
        if include_intro and intro_text:
            content_top = max(
                min_content_top,
                intro_top + intro_height + self.layout.intro_gap_pt,
            )
        else:
            content_top = max(min_content_top, header_bottom + self.layout.header_gap_pt)

        footer_contact_height = self.measurer.measure_footer_contact(
            page.get("footer_site", ""),
            page.get("footer_phone", ""),
        )
        footer_page_height = self.measurer.measure_footer_page(page.get("page_number", ""))
        footer_meta_height = self.measurer.measure_footer_meta(
            page.get("refs", []),
            page.get("footer_notes", []),
        )

        reserved_base = max(
            self.layout.footer_contact_bottom_pt + footer_contact_height,
            self.layout.footer_page_bottom_pt + footer_page_height,
        )
        footer_meta_bottom = max(
            self.layout.footer_meta_bottom_pt,
            self.layout.footer_contact_bottom_pt + footer_contact_height + self.layout.footer_meta_gap_pt,
        )
        reserved_meta = max(
            reserved_base,
            footer_meta_bottom + footer_meta_height,
        )

        content_height_base = (
            self.layout.page_height_pt - content_top - reserved_base - self.layout.safety_pad_pt
        )
        content_height_meta = (
            self.layout.page_height_pt - content_top - reserved_meta - self.layout.safety_pad_pt
        )

        if content_height_meta < self.layout.min_content_height_pt:
            LOGGER.warning(
                "Footer/meta area exceeds available page space; clamping content height to %.2fpt.",
                self.layout.min_content_height_pt,
            )

        content_height_base = max(content_height_base, self.layout.min_content_height_pt)
        content_height_meta = max(content_height_meta, self.layout.min_content_height_pt)

        return PageLayoutState(
            intro_top_pt=intro_top,
            content_top_pt=content_top,
            content_height_base_pt=content_height_base,
            content_height_meta_pt=content_height_meta,
            reserved_base_pt=reserved_base,
            footer_meta_bottom_pt=footer_meta_bottom,
        )

    def _normalize_blocks(self, blocks: List[Dict[str, Any]], max_height_pt: float) -> List[BlockItem]:
        normalized: List[BlockItem] = []
        for block in blocks:
            block_refs = block.get("refs", [])
            block_notes = block.get("footer_notes", [])
            if block.get("type") == "table":
                table = block.get("table", {})
                show_header = table.get("show_header", True)
                height = self.measurer.measure_table(table, show_header)
                normalized.append(
                    BlockItem(data=block, height_pt=height, refs=block_refs, notes=block_notes)
                )
            else:
                html = block.get("html", "")
                keep_with_next = _needs_keep_with_next(html)
                split_html = self._split_html_block(html, max_height_pt)
                for idx, chunk in enumerate(split_html):
                    height = self.measurer.measure_html(chunk)
                    normalized.append(
                        BlockItem(
                            data={"type": "html", "html": chunk},
                            height_pt=height,
                            keep_with_next=keep_with_next and idx == 0,
                            refs=block_refs if idx == 0 else [],
                            notes=block_notes if idx == 0 else [],
                        )
                    )
        return normalized

    def _split_table_block(self, block: Dict[str, Any], max_height_pt: float) -> List[Dict[str, Any]]:
        if block.get("type") != "table":
            return [block]

        table = block["table"]
        rows = table.get("rows", [])
        if not rows:
            return [block]

        result_blocks: List[Dict[str, Any]] = []
        start_idx = 0
        first_chunk = True

        while start_idx < len(rows):
            show_header = first_chunk
            max_rows = self._max_table_rows_that_fit(table, rows[start_idx:], max_height_pt, show_header)
            if max_rows < 1:
                max_rows = 1
            chunk_rows = rows[start_idx : start_idx + max_rows]
            result_blocks.append(
                {
                    "type": "table",
                    "table": {
                        "groups": table.get("groups", []),
                        "rows": chunk_rows,
                        "total_width": table.get("total_width"),
                        "dep_width": table.get("dep_width"),
                        "show_header": show_header,
                    },
                }
            )
            start_idx += max_rows
            first_chunk = False

        return result_blocks

    def _split_table_to_fit(
        self,
        blocks: List[BlockItem],
        idx: int,
        max_height_pt: float,
    ) -> Tuple[BlockItem, bool]:
        block = blocks[idx]
        table = block.data.get("table", {})
        rows = table.get("rows", [])
        if not rows:
            return block, False

        show_header = table.get("show_header", True)
        if block.height_pt <= max_height_pt:
            return block, False

        max_rows = self._max_table_rows_that_fit(table, rows, max_height_pt, show_header)
        if max_rows <= 0:
            max_rows = 1

        chunk_rows = rows[:max_rows]
        remainder_rows = rows[max_rows:]

        chunk_block = {
            "type": "table",
            "table": {
                "groups": table.get("groups", []),
                "rows": chunk_rows,
                "total_width": table.get("total_width"),
                "dep_width": table.get("dep_width"),
                "show_header": show_header,
            },
        }

        chunk_height = self.measurer.measure_table(chunk_block["table"], show_header)
        blocks[idx] = BlockItem(
            data=chunk_block,
            height_pt=chunk_height,
            refs=list(block.refs),
            notes=list(block.notes),
        )

        if remainder_rows:
            remainder_show_header = False if show_header else False
            remainder_block = {
                "type": "table",
                "table": {
                    "groups": table.get("groups", []),
                    "rows": remainder_rows,
                    "total_width": table.get("total_width"),
                    "dep_width": table.get("dep_width"),
                    "show_header": remainder_show_header,
                },
            }
            remainder_height = self.measurer.measure_table(
                remainder_block["table"], remainder_show_header
            )
            blocks.insert(
                idx + 1,
                BlockItem(data=remainder_block, height_pt=remainder_height),
            )

        return blocks[idx], bool(remainder_rows)

    def _max_table_rows_that_fit(
        self,
        table: Dict[str, Any],
        remaining_rows: List[Dict[str, Any]],
        max_height_pt: float,
        show_header: bool,
    ) -> int:
        low = 1
        high = len(remaining_rows)
        best = 0
        while low <= high:
            mid = (low + high) // 2
            test_table = {
                "groups": table.get("groups", []),
                "rows": remaining_rows[:mid],
                "total_width": table.get("total_width"),
                "dep_width": table.get("dep_width"),
            }
            height = self.measurer.measure_table(test_table, show_header)
            if height <= max_height_pt:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best

    def _split_html_block(self, html: str, max_height_pt: float) -> List[str]:
        height = self.measurer.measure_html(html)
        if height <= max_height_pt:
            return [html]

        chunks = split_html_into_chunks(html)
        if len(chunks) == 1:
            return [html]

        result: List[str] = []
        buffer: List[str] = []
        for chunk in chunks:
            candidate = "".join(buffer + [chunk])
            candidate_height = self.measurer.measure_html(candidate)
            if candidate_height <= max_height_pt or not buffer:
                buffer.append(chunk)
                continue

            result.append("".join(buffer))
            buffer = [chunk]

        if buffer:
            result.append("".join(buffer))

        return result

    def _content_height_with_meta(
        self, layout_state: PageLayoutState, refs: List[str], notes: List[str]
    ) -> float:
        if not refs and not notes:
            return layout_state.content_height_base_pt

        footer_meta_height = self.measurer.measure_footer_meta(refs, notes)
        reserved_meta = max(
            layout_state.reserved_base_pt,
            layout_state.footer_meta_bottom_pt + footer_meta_height,
        )
        content_height = (
            self.layout.page_height_pt
            - layout_state.content_top_pt
            - reserved_meta
            - self.layout.safety_pad_pt
        )
        if content_height < self.layout.min_content_height_pt:
            LOGGER.warning(
                "Footer/meta area exceeds available page space; clamping content height to %.2fpt.",
                self.layout.min_content_height_pt,
            )
            return self.layout.min_content_height_pt
        return content_height

def split_html_into_chunks(html: str) -> List[str]:
    lowered = html.lower()
    for tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
        close_tag = f"</{tag}>"
        if close_tag in lowered:
            parts = re.split(f"({re.escape(close_tag)})", html, flags=re.IGNORECASE)
            chunks: List[str] = []
            buffer = ""
            for part in parts:
                buffer += part
                if part.lower() == close_tag:
                    if buffer.strip():
                        chunks.append(buffer)
                    buffer = ""
            if buffer.strip():
                chunks.append(buffer)
            if len(chunks) > 1:
                return chunks

    if "<br" in lowered:
        parts = re.split(r"(<br\s*/?>)", html, flags=re.IGNORECASE)
        chunks = []
        buffer = ""
        for part in parts:
            buffer += part
            if part.lower().startswith("<br"):
                chunks.append(buffer)
                buffer = ""
        if buffer.strip():
            chunks.append(buffer)
        if len(chunks) > 1:
            return chunks

    return [html]


def _needs_keep_with_next(html: str) -> bool:
    lowered = html.lower()
    return "section-title" in lowered or "section-title-serif" in lowered or "section-subtitle" in lowered


def _suffix_sums(values: List[float]) -> List[float]:
    suffix = [0.0] * (len(values) + 1)
    for idx in range(len(values) - 1, -1, -1):
        suffix[idx] = suffix[idx + 1] + values[idx]
    return suffix
