"""HTML → sections, cover, tables and content blocks.

The parser turns an editable HTML document into the block payload the
template lays out. It is structural only: it reads tags, classes and the
render-contract attributes, never the words.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from lxml import etree, html
from lxml.html import HtmlElement

from pdfgen_juanipis.contract import (
    TEXT_WIDTH_PT,
    body_table_widths,
    is_body_table,
    is_document_heading,
    wants_keep_with_next,
    wants_page_break_before,
)
from pdfgen_juanipis.options import Labels
from pdfgen_juanipis.pdf.images import fit_image_src_for_pdf, read_image_bytes
from pdfgen_juanipis.security import ResourcePolicy
from pdfgen_juanipis.pdf.visual_layout import (
    ResolvedPDFVisualLayoutConfig,
    classify_aspect_ratio,
    compute_target_height_pt,
    extract_chart_type_from_meta,
    image_dimensions_from_bytes,
    infer_layout_key,
    parse_chart_meta_json,
    resolve_pdf_visual_layout_config,
)

#: Marks a node a block builder already folded into its own output, so the
#: body walk does not print it again. A flag rather than a removal: the
#: walk iterates the tree, and deleting a sibling from under lxml's
#: iterator skips the next element (two tables once vanished that way).
CONSUMED_ATTR = "data-consumed-by-block"

#: Rows above which a data grid may break across pages. A grid taller
#: than a page cannot honour ``page-break-inside: avoid``, and the layout
#: engine resolves the impossible by pushing it whole, leaving blank pages
#: behind its headings. Rows stay whole and the header repeats.
LONG_TABLE_ROWS = 30

#: Width of a data grid's first (label) column, in points.
LABEL_COLUMN_WIDTH_PT = 120.0


def first_text(root: HtmlElement, xpaths: List[str]) -> str:
    for xpath in xpaths:
        node = root.xpath(xpath)
        if not node:
            continue
        value = node[0].text_content().strip()
        if value:
            return value
    return ""


def _contract_attrs(element: HtmlElement) -> str:
    """The render-contract attributes ``element`` carries, ready to splice."""
    parts: List[str] = []
    if wants_page_break_before(element):
        parts.append('data-page-break="before"')
    if wants_keep_with_next(element):
        parts.append('data-keep-with-next="true"')
    return (" " + " ".join(parts)) if parts else ""


def _append_css_class(node: HtmlElement, class_name: str) -> None:
    classes = [part for part in (node.attrib.get("class") or "").split() if part]
    if class_name not in classes:
        classes.append(class_name)
    node.attrib["class"] = " ".join(classes)


def _nearest_visual_container(img: HtmlElement) -> Optional[HtmlElement]:
    node = img.getparent()
    while isinstance(node, HtmlElement):
        tag = (node.tag or "").lower()
        class_attr = f" {(node.attrib.get('class') or '').lower()} "
        if tag == "figure":
            return node
        if tag == "div" and " chart " in class_attr:
            return node
        node = node.getparent()
    return None


def _read_chart_meta(container: HtmlElement) -> Optional[Dict[str, Any]]:
    for script in container.xpath(
        ".//script[contains(concat(' ', normalize-space(@class), ' '), ' chart-meta ')]"
    ):
        payload = (script.text or "").strip()
        if not payload:
            continue
        parsed = parse_chart_meta_json(payload)
        if parsed:
            return parsed
        try:
            fallback = json.loads(payload)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(fallback, dict):
            return fallback
    return None


class HtmlParser:
    """Parse editable HTML into the renderer's section / block model."""

    def __init__(
        self,
        *,
        labels: Optional[Labels] = None,
        visual_layout: Any = None,
        source_dir: Optional[Path] = None,
        text_width_pt: float = TEXT_WIDTH_PT,
        policy: Optional[ResourcePolicy] = None,
    ) -> None:
        self.labels = labels or Labels()
        self.visual_layout: ResolvedPDFVisualLayoutConfig = (
            visual_layout
            if isinstance(visual_layout, ResolvedPDFVisualLayoutConfig)
            else resolve_pdf_visual_layout_config(visual_layout)
        )
        self.source_dir = source_dir
        # What an <img src> may load. Without one: data: URIs and files
        # under source_dir only.
        self.policy = policy or ResourcePolicy.build([source_dir] if source_dir else [])
        self.text_width_pt = text_width_pt

    # ── document level ──────────────────────────────────────────────
    def extract_sections(self, root: HtmlElement) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        section_nodes = root.xpath("//section")
        if section_nodes:
            for node in section_nodes:
                class_name = (node.attrib.get("class") or "").lower()
                section_type = (node.attrib.get("data-section-type") or "").lower()
                if section_type == "cover" or "cover-section" in class_name:
                    continue
                section = self.build_section(node, section_type=section_type)
                if section:
                    sections.append(section)
            return sections

        body = root.xpath("//body")
        container = body[0] if body else root

        # Without <section> wrappers, split the top-level flow by <h2> so
        # the document does not become one giant untitled section.
        flow_children = [
            c for c in container
            if isinstance(getattr(c, "tag", None), str) and not is_document_heading(c)
        ]
        if len(flow_children) == 1 and flow_children[0].tag.lower() in {"div", "main", "article"}:
            wrapped = [c for c in flow_children[0] if isinstance(getattr(c, "tag", None), str)]
            if wrapped:
                flow_children = wrapped
        if flow_children:
            # Only <h2> opens a numbered top-level section; <h3>/<h4> are
            # sub-headings within one.
            groups: List[List[HtmlElement]] = []
            current: List[HtmlElement] = []
            for child in flow_children:
                if child.tag.lower() == "h2" and current:
                    groups.append(current)
                    current = [child]
                else:
                    current.append(child)
            if current:
                groups.append(current)

            if len(groups) > 1:
                sections = []
                for idx, group in enumerate(groups):
                    pseudo = html.Element("section")
                    for node in group:
                        pseudo.append(node)
                    # A leading group with no <h2> is the preamble: it
                    # renders unnumbered and untitled instead of stealing
                    # numeral «I.» from the first real section.
                    leads_without_heading = idx == 0 and not (
                        group and str(group[0].tag).lower() == "h2"
                    )
                    if leads_without_heading:
                        built = self.build_section(pseudo, section_type="intro")
                    else:
                        built = self.build_section(
                            pseudo, fallback_title=f"{self.labels.untitled_section} {idx + 1}",
                        )
                    if built:
                        sections.append(built)
                if sections:
                    return sections

        fallback = self.build_section(container, fallback_title=self.labels.untitled_section)
        return [fallback] if fallback else []

    def build_section(
        self,
        node: HtmlElement,
        *,
        fallback_title: str = "",
        section_type: str = "",
    ) -> Optional[Dict[str, Any]]:
        section_title = ""
        title_node = None
        is_intro = section_type == "intro" or "intro-section" in (node.attrib.get("class") or "").lower()

        if not is_intro:
            for heading_tag in ("h2", "h3", "h1"):
                headings = [h for h in node.xpath(f"./{heading_tag}") if not is_document_heading(h)]
                if headings:
                    raw = html.tostring(headings[0], encoding="unicode")
                    inner = re.sub(
                        rf"^\s*<{heading_tag}[^>]*>(.*)</{heading_tag}>\s*$",
                        r"\1", raw, flags=re.DOTALL | re.IGNORECASE,
                    ).strip()
                    section_title = inner or headings[0].text_content().strip()
                    title_node = headings[0]
                    break

        # The section subtitle is printed under the title; flag it so the
        # body walk does not print it a second time as a paragraph.
        subtitle = ""
        subtitle_nodes = node.xpath("./p[contains(@class, 'section-subtitle')]")
        if subtitle_nodes:
            subtitle = subtitle_nodes[0].text_content().strip()
            if subtitle:
                subtitle_nodes[0].set(CONSUMED_ATTR, "1")

        content: List[Dict[str, Any]] = []
        text_buffer: List[str] = []
        footnotes: List[str] = []
        # A materialised list: a consumer touching the tree cannot make
        # this loop skip a sibling.
        for child in list(node):
            if is_document_heading(child):
                continue
            self.consume_element(
                child, content=content, text_buffer=text_buffer,
                title_node=title_node, footnotes=footnotes,
            )
        if text_buffer:
            content.append({"type": "text", "text": text_buffer[:]})

        if not content:
            plain_text = " ".join(node.text_content().split())
            if plain_text and plain_text != " ".join((section_title or "").split()):
                content.append({"type": "text", "text": [escape(plain_text, quote=False)]})
        if not content:
            return None

        final_title = "" if is_intro else (section_title or fallback_title or self.labels.untitled_section)
        section: Dict[str, Any] = {"title": final_title, "content": content}
        if is_intro:
            section["is_intro"] = True
        if title_node is not None and wants_page_break_before(title_node):
            section["page_break_before"] = True
        if footnotes:
            section["footnotes"] = footnotes
        if subtitle:
            section["subtitle"] = subtitle
        return section

    def extract_cover(
        self, root: HtmlElement, *, fallback_title: str, fallback_subtitle: str,
    ) -> Optional[Dict[str, Any]]:
        cover_nodes = root.xpath(
            "//section[@data-section-type='cover' or contains(@class, 'cover-section')]"
        )
        if not cover_nodes:
            return None
        node = cover_nodes[0]
        title_nodes = node.xpath(".//*[contains(@class, 'cover-title')]")
        subtitle_nodes = node.xpath(".//*[contains(@class, 'cover-subtitle')]")
        line_nodes = node.xpath(".//*[contains(@class, 'cover-line')]")

        def _text(n: HtmlElement) -> str:
            return " ".join(n.text_content().split())

        cover_title = _text(title_nodes[0]) if title_nodes else fallback_title
        cover_subtitle = _text(subtitle_nodes[0]) if subtitle_nodes else fallback_subtitle
        return {
            "cover_title": cover_title or fallback_title,
            "cover_subtitle": cover_subtitle or fallback_subtitle or "",
            "cover_lines": [_text(item) for item in line_nodes if _text(item)],
        }

    # ── element level ───────────────────────────────────────────────
    def consume_element(
        self,
        element: HtmlElement,
        *,
        content: List[Dict[str, Any]],
        text_buffer: List[str],
        title_node: Optional[HtmlElement],
        footnotes: Optional[List[str]] = None,
    ) -> None:
        if not isinstance(element.tag, str):
            return
        tag = element.tag.lower()
        if tag in {"script", "style"} or element.get(CONSUMED_ATTR):
            return
        if tag in {"h1", "h2", "h3"} and element is title_node:
            return

        def _flush() -> None:
            if text_buffer:
                content.append({"type": "text", "text": text_buffer[:]})
                text_buffer.clear()

        if tag in {"h1", "h2", "h3"}:
            _flush()
            heading_text = " ".join(element.text_content().split())
            # Inline headings are re-emitted from their text, so the
            # contract attributes have to be carried over explicitly.
            content.append({
                "type": "html",
                "html": f"<{tag}{_contract_attrs(element)}>{escape(heading_text, quote=False)}</{tag}>",
            })
            return

        if tag == "table":
            _flush()
            table = self.table_block(element)
            if table:
                content.append(table)
            return

        if tag == "p":
            class_name = (element.attrib.get("class") or "").lower()
            if "footnote" in class_name.split() and footnotes is not None:
                footnote_text = element.text_content().strip()
                if footnote_text:
                    footnotes.append(footnote_text)
                return
            _flush()
            normalized = self.normalize_html_fragment(html.tostring(element, encoding="unicode"))
            if normalized.strip():
                content.append({"type": "html", "html": normalized})
            return

        if tag == "li":
            normalized = self.normalize_html_fragment(html.tostring(element, encoding="unicode"))
            if normalized.strip():
                text_buffer.append(normalized)
            return

        if tag in {"ul", "ol"}:
            _flush()
            normalized = self.normalize_html_fragment(html.tostring(element, encoding="unicode"))
            if normalized.strip():
                content.append({"type": "html", "html": normalized})
            return

        # Any class mentioning "chart" marks a chart container (``chart``,
        # ``chart-block`` ...): kept whole like a figure.
        if tag == "figure" or (
            tag == "div" and "chart" in (element.attrib.get("class") or "").lower()
        ):
            _flush()
            normalized = self.normalize_html_fragment(html.tostring(element, encoding="unicode"))
            if normalized.strip():
                content.append({"type": "html", "html": normalized, "_keep_together": True})
            return

        if tag in {"div", "section", "article", "main"} and len(element):
            lead_text = " ".join((element.text or "").split())
            if lead_text:
                text_buffer.append(escape(lead_text, quote=False))
            for child in element:
                self.consume_element(
                    child, content=content, text_buffer=text_buffer,
                    title_node=title_node, footnotes=footnotes,
                )
            return

        _flush()
        fragment = html.tostring(element, encoding="unicode")
        content.append({"type": "html", "html": self.normalize_html_fragment(fragment)})

    def table_block(self, table_node: HtmlElement) -> Optional[Dict[str, Any]]:
        rows = table_node.xpath("./tbody/tr") or table_node.xpath("./tr")
        if not rows:
            return None

        groups: List[Dict[str, Any]] = []
        #: Single-tier header cells after the first column (exclusive
        #: with ``groups``; the template renders whichever is set).
        headers: List[str] = []
        header_rows = table_node.xpath("./thead/tr")
        first_header = self.labels.first_column_header
        # The <caption> is the table's NAME, printed above the grid; the
        # source line travels in the `div.table-caption` after the table
        # and is printed under it.
        caption_nodes = table_node.xpath("./caption")
        title = " ".join(caption_nodes[0].text_content().split()) if caption_nodes else ""
        caption = ""
        following = table_node.getnext()
        if following is not None and str(following.tag).lower() == "div":
            if "table-caption" in (following.get("class") or "").split():
                caption = " ".join(following.text_content().split())
                following.set(CONSUMED_ATTR, "1")

        if len(header_rows) >= 2:
            top_cells = header_rows[0].xpath("./th|./td")
            if top_cells:
                first_header = " ".join(top_cells[0].text_content().split()) or first_header
            group_titles = top_cells[1:]
            sub_cells = [" ".join(c.text_content().split()) for c in header_rows[1].xpath("./th|./td")]
            expected = sum(int(c.attrib.get("colspan", "1")) for c in group_titles)
            if len(sub_cells) == expected + 1:
                sub_cells = sub_cells[1:]
            index = 0
            for group_cell in group_titles:
                span = int(group_cell.attrib.get("colspan", "1"))
                groups.append({
                    "title": " ".join(group_cell.text_content().split()),
                    "months": sub_cells[index: index + span],
                })
                index += span
        elif len(header_rows) == 1:
            # One tier, rendered as one tier.
            flat = [" ".join(c.text_content().split()) for c in header_rows[0].xpath("./th|./td")]
            if flat:
                first_header = flat[0] or first_header
                headers = [h or f"C{i + 1}" for i, h in enumerate(flat[1:])]

        body_rows: List[Dict[str, Any]] = []
        for tr in rows:
            cells = tr.xpath("./th|./td")
            if len(cells) < 2:
                continue
            label = " ".join(cells[0].text_content().split())
            vals = [" ".join(cell.text_content().split()) for cell in cells[1:]]
            # Emphasis survives the flattening: a row set in bold in the
            # markup (a total, a highlighted entity) stays bold.
            emphasised = any(
                node.tag in ("b", "strong")
                for cell in cells for node in cell.iter() if node is not cell
            )
            body_rows.append({"dep": label, "vals": vals, "emphasised": emphasised})
        if not body_rows:
            return None

        show_header = bool(groups or headers)
        if not show_header:
            max_cols = max(len(row["vals"]) for row in body_rows)
            headers = [f"C{i + 1}" for i in range(max_cols)]

        expected_cols = len(headers) if headers else sum(len(g.get("months", [])) for g in groups)
        for row in body_rows:
            vals = row["vals"]
            if len(vals) < expected_cols:
                row["vals"] = vals + [""] * (expected_cols - len(vals))
            elif len(vals) > expected_cols:
                row["vals"] = vals[:expected_cols]

        # A BODY table is prose in a grid: left aligned, widths by
        # content, and allowed to break across pages.
        is_body = is_body_table(table_node)
        widths = body_table_widths(
            [[first_header, *headers], *[[row["dep"], *row["vals"]] for row in body_rows]]
        ) if is_body else []
        return {
            "type": "table",
            "table": {
                "breakable": len(body_rows) > LONG_TABLE_ROWS,
                "total_width": self.text_width_pt,
                "column_widths": [w * self.text_width_pt for w in widths],
                "dep_width": None if is_body else LABEL_COLUMN_WIDTH_PT,
                "dep_header": first_header,
                "show_header": show_header,
                "title": title,
                "caption": caption,
                "groups": groups,
                "headers": headers,
                "variant": "body" if is_body else "reference",
                "rows": body_rows,
            },
        }

    def normalize_html_fragment(self, fragment_html: str) -> str:
        """Resolve and down-scale images, cap their height, drop scripts."""
        try:
            # huge_tree: an inline chart is a multi-MB data URL, and
            # libxml2's default 10 MB cap silently truncates the rest.
            nodes = html.fragments_fromstring(
                fragment_html, parser=html.HTMLParser(huge_tree=True),
            )
        except etree.ParserError:
            return fragment_html

        parts: List[str] = []
        for node in nodes:
            if isinstance(node, str):
                parts.append(node)
                continue
            # descendant-or-self: a bare top-level <img> IS the node.
            for img in node.xpath("descendant-or-self::img"):
                src = (img.attrib.get("src") or "").strip()
                if not src:
                    continue
                # Responsive-safe dimensions regardless of editor-injected
                # width/height.
                img.attrib.pop("width", None)
                img.attrib.pop("height", None)
                style = (img.attrib.get("style") or "").strip()
                if style:
                    for prop in ("width", "height", "max-width", "max-height"):
                        style = re.sub(rf"(?i)(?<![-\w]){prop}\s*:[^;]+;?", "", style)
                    style = re.sub(r"\s{2,}", " ", style).strip(" ;")
                normalized_src = self.policy.resolve_src(src, self.source_dir)
                if not normalized_src:
                    # Refused (and logged): the image is dropped, never
                    # handed to WeasyPrint to fetch on its own.
                    img.attrib.pop("src", None)
                    continue
                final_src = fit_image_src_for_pdf(normalized_src) or normalized_src
                img.attrib["src"] = final_src
                responsive = "max-width:100%;height:auto;object-fit:contain;"
                max_height_pt = self._visual_max_height_for_img(img, final_src)
                if max_height_pt:
                    responsive += f"max-height:{int(max_height_pt)}pt;"
                img.attrib["style"] = f"{style};{responsive}" if style else responsive
            for script in node.xpath(".//script"):
                parent = script.getparent()
                if parent is not None:
                    parent.remove(script)
            parts.append(html.tostring(node, encoding="unicode"))
        return "".join(parts)

    def _visual_max_height_for_img(self, img: HtmlElement, final_src: str) -> Optional[int]:
        cfg = self.visual_layout
        if cfg is None or not cfg.enabled:
            return None
        container = _nearest_visual_container(img)
        if container is None:
            return None
        layout_key = infer_layout_key(container.attrib.get("class", ""))
        chart_type = extract_chart_type_from_meta(_read_chart_meta(container))
        try:
            image_bytes = read_image_bytes(final_src)
        except Exception:  # noqa: BLE001
            image_bytes = None
        dims = image_dimensions_from_bytes(image_bytes)
        aspect_ratio = (float(dims[0]) / float(dims[1])) if dims and dims[1] else None
        ratio_bucket = classify_aspect_ratio(aspect_ratio)
        target = compute_target_height_pt(
            cfg=cfg, layout_key=layout_key, chart_type=chart_type,
            aspect_ratio=aspect_ratio, text_width_pt=self.text_width_pt,
        )
        if not target:
            return None
        _append_css_class(img, "pdf-heuristic-applied")
        if chart_type:
            img.attrib["data-pdf-chart-type"] = str(chart_type)
        if ratio_bucket:
            img.attrib["data-pdf-ratio-bucket"] = str(ratio_bucket)
        img.attrib["data-pdf-layout"] = str(layout_key)
        img.attrib["data-pdf-max-height-pt"] = str(int(target))
        return int(target)


__all__ = ["CONSUMED_ATTR", "HtmlParser", "LONG_TABLE_ROWS", "first_text"]
