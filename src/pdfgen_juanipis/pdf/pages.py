"""Sections → the single flowing page the template lays out.

All blocks go into ONE logical page: WeasyPrint is the layout engine and
paginates the flow itself. This module only decides the blocks, their
section titles (numbered by position) and which block each footnote
definition rides on.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pdfgen_juanipis.contract import strip_leading_numeral, to_roman


def format_section_title_html(title_html: str, section_number: int) -> str:
    """``"IV. Tema"`` at position 2 → ``<span class="roman">II.</span> Tema``.

    Position wins over any hand-written numeral; the Word exporter applies
    the same rule (``contract.format_section_title``).
    """
    raw = (title_html or "").strip()
    if not raw:
        return raw
    if 'class="roman"' in raw or "class='roman'" in raw:
        return raw
    return f'<span class="roman">{to_roman(section_number)}.</span> {strip_leading_numeral(raw)}'


_KEEP_WITH_NEXT_RE = re.compile(
    r"""<[a-z][^>]*\sdata-keep-with-next(?:\s*=\s*(["'])(?!false|0|no)[^"']*\1)?[\s>/]""",
    re.IGNORECASE,
)


def declares_keep_with_next(block_html: str) -> bool:
    """True when the block's opening tag carries ``data-keep-with-next``."""
    return bool(_KEEP_WITH_NEXT_RE.search(block_html[:400]))


def build_pages(
    sections: List[Dict[str, Any]],
    *,
    theme: Dict[str, Any],
    cover: Optional[Dict[str, Any]] = None,
    numbering: str = "roman",
) -> List[Dict[str, Any]]:
    all_blocks: List[Dict[str, Any]] = []
    visible_section_counter = 0

    # Cover lines flow as justified paragraphs at the top of the first page.
    if cover:
        lines_html = "".join(
            f'<p style="text-align:justify;">{line}</p>'
            for line in cover.get("cover_lines", []) if line
        )
        if lines_html:
            all_blocks.append({"type": "html", "html": lines_html})

    for section in sections:
        section_title = (section.get("title") or "").strip()
        section_subtitle = (section.get("subtitle") or "").strip()

        # An intro renders as regular blocks, unnumbered and untitled, so
        # its markup and footnotes survive.
        if section.get("is_intro", False):
            section_title = ""
        else:
            visible_section_counter += 1
            if section_title and numbering == "roman":
                section_title = format_section_title_html(section_title, visible_section_counter)

        title_style = ' style="break-before:page"' if section.get("page_break_before") else ""
        title_html = ""
        if section_title:
            title_html += f'<div class="section-title"{title_style}>{section_title}</div>'
        if section_subtitle:
            title_html += f'<div class="section-subtitle">{section_subtitle}</div>'
        if title_html:
            all_blocks.append({"type": "html", "html": title_html, "keep_with_next": True})

        section_start_idx = len(all_blocks)
        for item in section.get("content", []):
            item_type = item.get("type", "text")
            if item_type == "text":
                paragraphs = item.get("text", [])
                if isinstance(paragraphs, str):
                    paragraphs = [paragraphs]
                for paragraph in paragraphs:
                    text = str(paragraph).strip()
                    if text:
                        all_blocks.append({"type": "html", "html": f"<p>{text}</p>"})
            elif item_type == "table":
                all_blocks.append({"type": "table", "table": item.get("table", {})})
            else:
                item_html = item.get("html", "")
                if not item_html:
                    continue
                block: Dict[str, Any] = {"type": "html", "html": item_html}
                if item.get("_keep_together"):
                    block["keep_with_next"] = False
                if declares_keep_with_next(item_html):
                    block["keep_with_next"] = True
                if re.match(r"^\s*<h[1-3][\s>]", item_html[:60].lower()):
                    # Inline headings never sit alone at a page bottom
                    # (``break-after: avoid`` in the stylesheet). h4 is left
                    # out on purpose: gluing a caption to a long table
                    # strands the caption on a blank page.
                    block["keep_with_next"] = True
                all_blocks.append(block)

        section_footnotes = section.get("footnotes", [])
        if section_footnotes and len(all_blocks) > section_start_idx:
            distribute_footnotes(all_blocks, section_start_idx, section_footnotes)

    if not all_blocks:
        return []
    return [{
        **theme,
        "intro": "",
        "blocks": all_blocks,
        "refs": [],
        "refs_catalog": {},
        "footer_notes": [],
        "page_number": "1",
    }]


def distribute_footnotes(
    all_blocks: List[Dict[str, Any]],
    section_start_idx: int,
    footnotes: List[str],
) -> None:
    """Attach each numbered footnote to the block holding its marker."""
    section_blocks = all_blocks[section_start_idx:]
    if not section_blocks:
        return

    fn_by_marker: Dict[str, str] = {}
    unnumbered: List[str] = []
    for fn in footnotes:
        match = re.match(r"^\s*([A-Za-z]+\d+|\d+)\s", fn)
        if match:
            fn_by_marker[match.group(1)] = fn
        else:
            unnumbered.append(fn)

    if not fn_by_marker:
        section_blocks[-1].setdefault("refs", []).extend(footnotes)
        return

    for marker, fn_text in fn_by_marker.items():
        target = section_blocks[-1]
        for blk in section_blocks:
            # A marker may share its <sup> with others («<sup>2,3,4</sup>»).
            if re.search(
                rf"<sup[^>]*>\s*(?:\d+\s*,\s*)*{re.escape(marker)}(?:\s*,\s*\d+)*\s*</sup>",
                blk.get("html", "") or "",
                re.IGNORECASE,
            ):
                target = blk
                break
        target.setdefault("refs", []).append(fn_text)

    if unnumbered:
        section_blocks[-1].setdefault("refs", []).extend(unnumbered)


__all__ = ["build_pages", "declares_keep_with_next", "distribute_footnotes", "format_section_title_html"]
