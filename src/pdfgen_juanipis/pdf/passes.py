"""Post-layout passes: render, measure, adjust the HTML, render again.

WeasyPrint is the layout engine; these passes only read the boxes it laid
out and nudge the HTML where a typesetter would:

* **Footnotes on their marker's page.** Each note is injected right after
  its ``<sup>`` marker as a CSS footnote (``float: footnote``). When a
  note still lands on a later page than its marker, the paragraph (or the
  heading right above it) is pushed to the next page — unless the marker
  sits high on its page, where the push would blank most of it.
* **Figure gaps.** A figure kept whole that does not fit jumps to the next
  page and leaves a hole. The prose right after it (never across a
  heading, never text announcing a later figure) moves into the hole, or
  the figure's image shrinks a little to fit it. Every layout tried is
  scored and the least wasteful one wins.
* **Lonely breaks.** A forced section break after a page holding a couple
  of lines is dropped when that makes the document shorter.

Every function takes a ``render`` callable (HTML string → WeasyPrint
``Document``) so it can be tested with plain WeasyPrint documents.
A pass that fails is skipped with a warning: layout polish never breaks
a render.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("pdfgen_juanipis.pdf.passes")

Render = Callable[[str], Any]

#: Fix a cross-page footnote only when its marker sits in the bottom band
#: of the page: pushing a paragraph that starts higher wastes more page
#: than the cross-page note it cures.
FOOTNOTE_FIX_MIN_PAGE_FRACTION = 0.62

#: A page may end this empty (fraction of the text area) before the figure
#: that jumped to the next one, before the text after it is pulled up.
FIGURE_GAP_MIN_FRACTION = 0.15
FIGURE_GAP_PASSES = 4
#: The most a figure's image may shrink to fit the hole above it, and the
#: height (pt) it may never go below.
FIGURE_GAP_MAX_SHRINK = 0.35
FIGURE_GAP_MIN_HEIGHT_PT = 240.0

#: A page filled less than this before a section that forces a new page
#: is the stranded tail of the section before it.
LONELY_PAGE_MAX_FILL = 0.25
FORCED_BREAK = 'class="section-title" style="break-before:page"'


# ───────────────────────── footnotes ─────────────────────────────────────


def separate_numbers_from_markers(payload: Dict[str, Any]) -> None:
    """A hair space between a figure and the note call that follows it.

    On the page «49.872¹²» reads fine, but in the PDF text layer the
    superscript is just two more digits («49.87212»): anyone copying the
    number gets a different one. U+200A is invisible at print size and
    extracts as a separator.
    """
    for page in payload.get("pages") or []:
        for block in page.get("blocks") or []:
            block_html = block.get("html", "")
            if block_html and "<sup" in block_html:
                block["html"] = re.sub(r"(\d)(<sup\b)", "\\1\u200a\\2", block_html)


def _ref_marker(ref_text: Any) -> Optional[str]:
    match = re.match(r"^\s*([A-Za-z]*\d+)\s", str(ref_text))
    return match.group(1) if match else None


def inject_inline_footnotes(payload: Dict[str, Any]) -> None:
    """Put each footnote right after its ``<sup>`` marker as a CSS footnote.

    ``float: footnote`` places a note at the bottom of the page where it
    appears in the flow, so injecting it right after the marker lands it
    on the marker's page even when a paragraph splits across pages. Refs
    are collected page-wide first: a definition attached to a sibling
    block still finds its marker.
    """
    for page in payload.get("pages") or []:
        ref_map: Dict[str, str] = {}
        for block in page.get("blocks") or []:
            for ref_text in block.get("refs") or []:
                marker = _ref_marker(ref_text)
                if marker:
                    ref_map[marker] = str(ref_text)
        if not ref_map:
            continue

        for block in page.get("blocks") or []:
            block_html = block.get("html", "")
            if not block_html or "<sup" not in block_html:
                continue

            def _inject(match: "re.Match[str]", _refs: Dict[str, str] = ref_map) -> str:
                # A joined marker («<sup>2,3,4</sup>») places every note.
                numbers = [n.strip() for n in match.group(1).split(",")]
                notes = [n for n in numbers if n in _refs]
                if not notes:
                    return match.group(0)
                spans = "".join(f'<span class="fn-note">{_refs.pop(n)}</span>' for n in notes)
                return f'<sup>{",".join(numbers)}</sup>{spans}'

            block["html"] = re.sub(
                r"<sup[^>]*>\s*(\d+(?:\s*,\s*\d+)*)\s*</sup>", _inject, block_html,
            )

        # Drop consumed refs from every block (the template would print a
        # leftover ref a second time); unconsumed ones stay as a fallback.
        for block in page.get("blocks") or []:
            block["refs"] = [
                ref_text for ref_text in block.get("refs") or []
                if _ref_marker(ref_text) is None or _ref_marker(ref_text) in ref_map
            ]


def add_footnote_tracking_ids(payload: Dict[str, Any]) -> None:
    """``id="sup-N"`` / ``id="fn-N"`` so the page of each can be measured."""
    for page in payload.get("pages") or []:
        for block in page.get("blocks") or []:
            block_html = block.get("html", "")
            if "<sup" not in block_html:
                continue
            block_html = re.sub(
                r'<sup(?![^>]*\bid=)([^>]*)>(\s*\d+\s*)</sup>',
                lambda m: f'<sup{m.group(1)} id="sup-{m.group(2).strip()}">{m.group(2)}</sup>',
                block_html,
            )
            block_html = re.sub(
                r'<span class="fn-note"(?![^>]*\bid=)>(\d+)\s',
                lambda m: f'<span class="fn-note" id="fn-{m.group(1)}">{m.group(1)} ',
                block_html,
            )
            block["html"] = block_html


def detect_footnote_mismatches(document: Any) -> List[Tuple[str, int, int, float]]:
    """``(marker, marker_page, note_page, marker_page_fraction)`` for every
    note laid out on a later page than its marker."""

    def _find_ids(box: Any, found: Dict[str, float]) -> None:
        element = getattr(box, "element", None)
        if element is not None and hasattr(element, "get"):
            eid = element.get("id")
            if eid and eid not in found:
                found[eid] = float(getattr(box, "position_y", 0.0) or 0.0)
        for child in getattr(box, "children", []):
            _find_ids(child, found)

    sup_page: Dict[str, int] = {}
    sup_frac: Dict[str, float] = {}
    fn_page: Dict[str, int] = {}
    for page_idx, page in enumerate(document.pages):
        ids: Dict[str, float] = {}
        _find_ids(page._page_box, ids)
        page_h = float(
            getattr(page, "height", 0.0) or getattr(page._page_box, "height", 0.0) or 0.0
        )
        for eid, pos_y in ids.items():
            if eid.startswith("sup-"):
                sup_page[eid[4:]] = page_idx
                # 1.0 when the geometry is unknown: fix by default.
                sup_frac[eid[4:]] = (pos_y / page_h) if page_h > 0 else 1.0
            elif eid.startswith("fn-"):
                fn_page[eid[3:]] = page_idx

    mismatches: List[Tuple[str, int, int, float]] = []
    for marker, sp in sup_page.items():
        fp = fn_page.get(marker)
        if fp is not None and fp > sp:
            mismatches.append((marker, sp, fp, sup_frac.get(marker, 1.0)))
    return mismatches


def heading_block_start_before(html_str: str, p_start: int) -> Optional[int]:
    """Start of a heading block immediately before ``p_start``, if any.

    Forcing a break before the first paragraph after a heading would strand
    the heading at the bottom of the previous page; the break goes on the
    heading's block instead so both travel together.
    """
    region = html_str[:p_start]
    m_wrapper = re.search(r'<div\s+class="content-block"[^>]*>\s*$', region)
    head_region = region[: m_wrapper.start()] if m_wrapper else region
    tail = head_region[-1200:]
    m_heading = re.search(
        r'<div\s+class="content-block"[^>]*>\s*'
        r'(?:<div\s+class="(?:section-title|section-subtitle)[^"]*"[^>]*>'
        r'[\s\S]*?</div>|<h[1-3][\s\S]*?</h[1-3]>)'
        r'\s*</div>\s*$',
        tail,
    )
    if not m_heading:
        return None
    return len(head_region) - len(tail) + m_heading.start()


def fix_footnote_mismatches(html_str: str, mismatches: List[Tuple[Any, ...]]) -> str:
    """Push the paragraph holding each mismatched marker to the next page."""
    for item in mismatches:
        marker = item[0]
        frac = float(item[3]) if len(item) > 3 else 1.0
        if frac < FOOTNOTE_FIX_MIN_PAGE_FRACTION:
            logger.info(
                "footnote %s: marker at %.0f%% of its page — accepting a cross-page "
                "note instead of a wasteful break", marker, frac * 100,
            )
            continue
        idx = html_str.find(f'id="sup-{marker}"')
        if idx == -1:
            continue
        # Only a real <p>: a bare "<p" prefix also matches SVG tags
        # (<path>, <polygon>) when the marker follows an inline chart.
        p_matches = list(re.finditer(r"<p(?=[\s>])", html_str[:idx]))
        if not p_matches:
            continue
        p_start = p_matches[-1].start()
        target_start = heading_block_start_before(html_str, p_start)
        if target_start is None:
            target_start = p_start
        tag_end = html_str.index(">", target_start)
        tag = html_str[target_start: tag_end + 1]
        if "break-before" in tag:
            continue  # already fixed in a previous pass
        if "style=" in tag:
            new_tag = tag.replace('style="', 'style="break-before:page;')
        else:
            new_tag = re.sub(r"^<(\w+)", r'<\1 style="break-before:page"', tag, count=1)
        html_str = html_str[:target_start] + new_tag + html_str[tag_end + 1:]
    return html_str


# ───────────────────────── figure gaps ───────────────────────────────────

_GID_RE = re.compile(r"<(p|figure|ul)(?=[\s>])")

#: One unit of prose right after a figure: a bare ``<p>``/``<ul>``, or the
#: template's ``content-block`` wrapper holding only those. Anything else
#: (a heading, a table, another figure) ends the run.
_TEXT_UNIT_RE = re.compile(
    r'\s*(?:<div class="content-block">\s*'
    r'((?:<(?:p|ul) data-gid="g\d+"[^>]*>.*?</(?:p|ul)>\s*)+)</div>'
    r'|(<p data-gid="g\d+"[^>]*>.*?</p>)'
    r'|(<ul data-gid="g\d+"[^>]*>.*?</ul>))',
    re.DOTALL,
)


def layout_waste(document: Any) -> float:
    """Blank past the tolerated fraction, summed over every page but the last."""
    waste = 0.0
    for page in document.pages[:-1]:
        box = page._page_box
        bottoms: List[float] = []

        def _walk(node: Any, bottoms: List[float] = bottoms) -> None:
            element = getattr(node, "element", None)
            if element is not None and hasattr(element, "get") and element.get("data-gid"):
                bottoms.append(float(node.position_y) + float(node.margin_height()))
                return
            for child in getattr(node, "children", None) or []:
                _walk(child, bottoms)

        _walk(box)
        if not bottoms:
            continue
        top, height = float(box.content_box_y()), float(box.height)
        blank = (top + height - max(bottoms)) / height if height else 0.0
        waste += max(0.0, blank - FIGURE_GAP_MIN_FRACTION)
    return waste


def _figure_span(html_str: str, figure_gid: str) -> Optional[Tuple[int, int]]:
    """Where the figure's own unit starts (its wrapper, if any) and ends."""
    at = html_str.find(f'<figure data-gid="{figure_gid}"')
    end = html_str.find("</figure>", at)
    if at < 0 or end < 0:
        return None
    end += len("</figure>")
    opener = html_str.rfind('<div class="content-block">', 0, at)
    if opener >= 0 and not html_str[opener + len('<div class="content-block">'): at].strip():
        close = re.match(r"\s*</div>", html_str[end:])
        if close:
            return opener, end + close.end()
    return at, end


def _caption_label_and_number(figure_html: str, fallback_label: str) -> Tuple[str, Optional[int]]:
    """The figure's own label and number, read off its caption («Figura 3.»)."""
    caption = re.search(r'class="figure-title">\s*([^\W\d_]+)\s+(\d+)', figure_html)
    if caption:
        return caption.group(1), int(caption.group(2))
    if fallback_label:
        caption = re.search(
            rf"<figcaption[^>]*>(?:\s*<[^>]+>)*\s*({re.escape(fallback_label)})\s+(\d+)",
            figure_html,
        )
        if caption:
            return caption.group(1), int(caption.group(2))
    return "", None


def text_units_after(
    html_str: str,
    figure_gid: str,
    home: Optional[Dict[str, Optional[str]]] = None,
    *,
    figure_label: str = "",
) -> List[List[str]]:
    """The prose units that directly follow a figure AND belong to it."""
    span = _figure_span(html_str, figure_gid)
    if span is None:
        return []
    cursor, out = span[1], []
    label, number = _caption_label_and_number(html_str[span[0]: span[1]], figure_label)
    while True:
        match = _TEXT_UNIT_RE.match(html_str, cursor)
        if not match or "data-page-break" in match.group(0):
            return out
        gids = re.findall(r'<(?:p|ul) data-gid="(g\d+)"', match.group(0))
        if home is not None and any(home.get(g) != figure_gid for g in gids):
            return out
        # Text announcing a LATER figure stays below this one.
        if number is not None and any(
            int(n) > number
            for n in re.findall(rf"(?<!\w){re.escape(label)}\s+(\d+)", match.group(0))
        ):
            return out
        out.append(gids)
        cursor = match.end()


def move_before(html_str: str, figure_gid: str, paragraph_gids: List[str]) -> str:
    span = _figure_span(html_str, figure_gid)
    if span is None:
        return html_str
    wanted = set(paragraph_gids)
    cursor, moved = span[1], []
    while wanted:
        match = _TEXT_UNIT_RE.match(html_str, cursor)
        if not match:
            break
        gids = set(re.findall(r'<(?:p|ul) data-gid="(g\d+)"', match.group(0)))
        if not gids & wanted:
            break
        moved.append(match.group(0))
        wanted -= gids
        cursor = match.end()
    if not moved:
        return html_str
    return html_str[: span[0]] + "".join(moved) + html_str[span[0]: span[1]] + html_str[cursor:]


def _page_bottom(box: Any) -> float:
    bottom = float(box.content_box_y()) + float(box.height)
    footnotes = getattr(box, "footnote_area", None)
    if footnotes is not None and getattr(footnotes, "children", None):
        bottom = min(bottom, float(footnotes.position_y))
    return bottom


def figure_gap_moves(
    document: Any,
    html_str: str,
    home: Optional[Dict[str, Optional[str]]] = None,
    *,
    figure_label: str = "",
) -> List[Tuple[str, List[str]]]:
    """``(figure, paragraphs to move above it)`` for every hole worth filling."""
    pages: List[Dict[str, Any]] = []
    for page in document.pages:
        box = page._page_box
        blocks: Dict[str, Tuple[float, float, str]] = {}

        def _walk(node: Any, blocks: Dict[str, Tuple[float, float, str]] = blocks) -> None:
            element = getattr(node, "element", None)
            gid = element.get("data-gid") if element is not None and hasattr(element, "get") else None
            if gid and gid not in blocks:
                blocks[gid] = (float(node.position_y), float(node.margin_height()), str(element.tag))
            for child in getattr(node, "children", None) or []:
                _walk(child, blocks)

        _walk(box)
        pages.append({"blocks": blocks, "bottom": _page_bottom(box), "height": float(box.height)})

    heights: Dict[str, float] = {}
    for page in pages:
        for gid, (_y, h, _tag) in page["blocks"].items():
            heights[gid] = heights.get(gid, 0.0) + h

    moves: List[Tuple[str, List[str]]] = []
    for current, following in zip(pages, pages[1:]):
        if not following["blocks"] or not current["blocks"]:
            continue
        first_gid, (_y, _h, tag) = min(following["blocks"].items(), key=lambda kv: kv[1][0])
        if tag != "figure":
            continue
        used = max(y + h for y, h, _t in current["blocks"].values())
        hole = current["bottom"] - used
        if hole < FIGURE_GAP_MIN_FRACTION * current["height"]:
            continue
        # Whole units while they fit; the first that does not still moves
        # and splits: it starts in the hole and ends above the figure.
        chosen: List[str] = []
        budget = hole * 0.95
        for unit_gids in text_units_after(html_str, first_gid, home, figure_label=figure_label):
            chosen.extend(unit_gids)
            budget -= sum(heights.get(g, budget + 1) for g in unit_gids)
            if budget <= 0:
                break
        if chosen:
            moves.append((first_gid, chosen))
    return moves


def figure_gap_shrinks(document: Any) -> Dict[str, float]:
    """``{figure: image max-height in pt}`` for jumped figures that fit the
    hole they left once their image is a little smaller."""

    def _tagged(node: Any, sink: List[Any]) -> None:
        element = getattr(node, "element", None)
        if element is not None and hasattr(element, "get") and element.get("data-gid"):
            sink.append(node)
            return
        for child in getattr(node, "children", None) or []:
            _tagged(child, sink)

    def _images(node: Any, sink: List[Any]) -> None:
        element = getattr(node, "element", None)
        if element is not None and str(getattr(element, "tag", "")) == "img":
            sink.append(node)
            return
        for child in getattr(node, "children", None) or []:
            _images(child, sink)

    out: Dict[str, float] = {}
    pages = list(document.pages)
    for current, following in zip(pages, pages[1:]):
        cbox, fbox = current._page_box, following._page_box
        here: List[Any] = []
        there: List[Any] = []
        _tagged(cbox, here)
        _tagged(fbox, there)
        if not here or not there:
            continue
        figure = min(there, key=lambda node: float(node.position_y))
        if str(figure.element.tag) != "figure":
            continue
        hole = _page_bottom(cbox) - max(float(n.position_y) + float(n.margin_height()) for n in here)
        if hole < FIGURE_GAP_MIN_FRACTION * float(cbox.height):
            continue
        images: List[Any] = []
        _images(figure, images)
        if len(images) != 1:
            continue
        image_h = float(images[0].height)
        excess = float(figure.margin_height()) - hole + 4.0
        if excess <= 0 or image_h <= 0 or excess > FIGURE_GAP_MAX_SHRINK * image_h:
            continue
        if (image_h - excess) * 0.75 < FIGURE_GAP_MIN_HEIGHT_PT:
            continue
        # WeasyPrint lays out in CSS px; the style is written in pt.
        out[str(figure.element.get("data-gid"))] = round((image_h - excess) * 0.75, 1)
    return out


def cap_figure_height(html_str: str, figure_gid: str, max_height_pt: float) -> str:
    """Append a smaller ``max-height`` to the figure's image (last one wins)."""
    at = html_str.find(f'<figure data-gid="{figure_gid}"')
    end = html_str.find("</figure>", at)
    if at < 0 or end < 0:
        return html_str
    capped = re.sub(
        r"""(<img\b[^>]*\bstyle=)(["'])(.*?)\2""",
        lambda m: (f"{m.group(1)}{m.group(2)}{m.group(3).rstrip('; ')};"
                   f"max-height:{max_height_pt}pt{m.group(2)}"),
        html_str[at:end], count=1, flags=re.DOTALL,
    )
    return html_str[:at] + capped + html_str[end:]


def fill_figure_gaps(html_str: str, render: Render, *, figure_label: str = "") -> str:
    """Close the hole a figure leaves when it jumps to the next page."""
    counter = iter(range(1, 1_000_000))
    tagged = _GID_RE.sub(lambda m: f'<{m.group(1)} data-gid="g{next(counter)}"', html_str)
    # Each paragraph's own figure: the last one before it. Text may rise
    # above THAT figure only, never above an earlier one.
    home: Dict[str, Optional[str]] = {}
    current: Optional[str] = None
    for tag, gid in re.findall(r'<(p|figure|ul) data-gid="(g\d+)"', tagged):
        if tag == "figure":
            current = gid
        else:
            home[gid] = current
    # Filling one hole moves every page after it and can open another, so
    # every layout tried is scored (the original included) and the least
    # wasteful one wins.
    best: Optional[Tuple[float, str]] = None
    for pass_num in range(FIGURE_GAP_PASSES + 1):
        try:
            document = render(tagged)
            waste = layout_waste(document)
            if best is None or waste < best[0] - 1e-6:
                best = (waste, tagged)
            if pass_num == FIGURE_GAP_PASSES:
                break
            moves = figure_gap_moves(document, tagged, home, figure_label=figure_label)
            shrinks = figure_gap_shrinks(document)
        except Exception as exc:  # noqa: BLE001 — layout polish never breaks a render
            logger.warning("figure gap filling skipped (%s: %s)", type(exc).__name__, exc)
            break
        moves = [(f, ps) for f, ps in moves if f not in shrinks]
        if not moves and not shrinks:
            break
        for figure_gid, max_height_pt in shrinks.items():
            tagged = cap_figure_height(tagged, figure_gid, max_height_pt)
        for figure_gid, paragraph_gids in moves:
            tagged = move_before(tagged, figure_gid, paragraph_gids)
    chosen = best[1] if best is not None else tagged
    if best is not None and re.sub(r' data-gid="g\d+"', "", chosen) != html_str:
        logger.info("figure gaps: layout with %.2f page(s) of excess blank kept", best[0])
    return re.sub(r' data-gid="g\d+"', "", chosen)


# ───────────────────────── lonely breaks ─────────────────────────────────


def relax_lonely_breaks(html_str: str, render: Render) -> str:
    """Drop a forced section break that follows a nearly empty page, when
    the document comes out shorter without it."""
    if FORCED_BREAK not in html_str:
        return html_str
    counter = iter(range(1, 1_000_000))
    tagged = re.sub(
        r"<(p|figure|ul|ol|table|div)(?=[\s>])",
        lambda m: f'<{m.group(1)} data-lid="l{next(counter)}"', html_str,
    )

    def _pages(document: Any) -> List[Tuple[List[str], float]]:
        """Per page: the ids laid out on it (top first) and how full it is."""
        out = []
        for page in document.pages:
            box = page._page_box
            found: Dict[str, Tuple[float, float]] = {}

            def _walk(node: Any, found: Dict[str, Tuple[float, float]] = found) -> None:
                element = getattr(node, "element", None)
                lid = element.get("data-lid") if element is not None and hasattr(element, "get") else None
                if lid and lid not in found:
                    found[lid] = (float(node.position_y), float(node.position_y) + float(node.margin_height()))
                for child in getattr(node, "children", None) or []:
                    _walk(child, found)

            _walk(box)
            top, height = float(box.content_box_y()), float(box.height)
            fill = ((max(b for _t, b in found.values()) - top) / height) if found and height else 1.0
            out.append(([lid for lid, _ in sorted(found.items(), key=lambda kv: kv[1][0])], fill))
        return out

    try:
        document = render(tagged)
        pages = _pages(document)
        for lid in re.findall(r'data-lid="(l\d+)" ' + re.escape(FORCED_BREAK), tagged):
            at = next((i for i, (ids, _f) in enumerate(pages) if lid in ids), None)
            if not at or pages[at - 1][1] >= LONELY_PAGE_MAX_FILL:
                continue
            candidate = tagged.replace(
                f'data-lid="{lid}" {FORCED_BREAK}', f'data-lid="{lid}" class="section-title"', 1,
            )
            trial = render(candidate)
            if len(trial.pages) < len(document.pages):
                logger.info(
                    "lonely page: page %d was %.0f%% full before a forced section break; "
                    "the break was dropped (%d → %d pages)",
                    at, pages[at - 1][1] * 100, len(document.pages), len(trial.pages),
                )
                tagged, document, pages = candidate, trial, _pages(trial)
    except Exception as exc:  # noqa: BLE001 — layout polish never breaks a render
        logger.warning("lonely page relaxation skipped (%s: %s)", type(exc).__name__, exc)
        return html_str
    return re.sub(r' data-lid="l\d+"', "", tagged)


__all__ = [
    "add_footnote_tracking_ids",
    "cap_figure_height",
    "detect_footnote_mismatches",
    "figure_gap_moves",
    "figure_gap_shrinks",
    "fill_figure_gaps",
    "fix_footnote_mismatches",
    "heading_block_start_before",
    "inject_inline_footnotes",
    "layout_waste",
    "move_before",
    "relax_lonely_breaks",
    "separate_numbers_from_markers",
    "text_units_after",
]
