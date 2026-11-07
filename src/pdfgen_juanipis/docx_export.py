"""HTML → Word (.docx), sharing the PDF renderer's contract and options.

Requires the ``docx`` extra: ``pip install "pdfgen-juanipis[docx]"``.

The Word file is meant to be the same DOCUMENT as the PDF, not only the
same words: the typography mirrors ``templates/report.css`` (the tests
parse the stylesheet and fail when the two drift), the letterhead comes
from the same template package, and the structural directives of
:mod:`pdfgen_juanipis.contract` are honoured on both sides.

What it emits: the document title/subtitle, numbered section headings
(``<h2>``), paragraphs with inline ``<sup>`` markers, native Word
footnotes lifted from ``<p class="footnote">``, figures (SVG payloads are
rasterized with ``rsvg-convert``; when it is missing a placeholder
paragraph is printed and a warning recorded), tables with a repeating
header row, and the letterhead's band and contact block.

Footnotes: python-docx has no public footnote API, so ``word/footnotes.xml``
and its relationship are built by hand, mirroring what Word itself writes
(Word for Mac flags anything less as unreadable content).
"""

from __future__ import annotations

import base64
import contextvars
import copy
import io
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    from docx import Document
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor
except ImportError as exc:  # pragma: no cover - exercised without the extra
    raise ImportError(
        "The Word exporter needs python-docx: pip install \"pdfgen-juanipis[docx]\""
    ) from exc
from lxml import etree
from lxml import html as lxml_html

from pdfgen_juanipis.contract import (
    body_table_widths,
    element_classes,
    format_section_title,
    inline_text_align,
    is_body_table,
    is_document_heading,
    is_document_subtitle,
    log_unsupported,
    scan_directives,
    validate_render_text,
    wants_keep_with_next,
    wants_page_break_before,
)
from pdfgen_juanipis.fonts import DEFAULT_FONT_FAMILY, METRIC_COMPATIBLE
from pdfgen_juanipis.options import Labels, RenderOptions
from pdfgen_juanipis.packages import (
    PackageRegistry,
    TemplatePackage,
    TemplatePackageError,
    resolve_template_package,
)

logger = logging.getLogger("pdfgen_juanipis.docx")


# ──────────────────────── editorial defaults ─────────────────────────────
# Values mirrored from templates/report.css. Each one names the rule it
# copies, and the presentation-parity tests parse the stylesheet and fail
# when the two drift (python-docx's own template defaults — 11 pt body,
# 10 pt between paragraphs — would otherwise make Word read looser).
_BODY_FONT_SIZE = Pt(12)            # .content p { font-size: 12pt }
_BODY_SPACE_AFTER = Pt(5)           # .content p { margin: 0 0 5pt 0 }
_BODY_LINE_SPACING = 1.15           # .content p { line-height: 1.15 }
_H3_FONT_SIZE = Pt(11.5)            # .content h3 { font-size: 11.5pt }
_HEADING_FONT_SIZE = Pt(14)
_TITLE_FONT_SIZE = Pt(18)
_SUBTITLE_FONT_SIZE = Pt(12)
_FOOTNOTE_FONT_SIZE = Pt(9)
_CAPTION_FONT_SIZE = Pt(9)
# Sub-captions print one step smaller than the caption (.figure-subcaption).
_SUBCAPTION_FONT_SIZE = Pt(8)
_PAGE_NUMBER_FONT_SIZE = Pt(8)
_FIGURE_WIDTH_INCHES = 6.0  # Fits US-Letter / A4 with 1" margins.
# `figure-left` / `figure-right` are 78% of the text column in the PDF.
_FIGURE_NARROW_WIDTH_INCHES = round(_FIGURE_WIDTH_INCHES * 0.78, 2)

_H3_COLOR = RGBColor(0x33, 0x33, 0x33)              # .content h3 { color: #333333 }
_FOOTNOTE_COLOR = RGBColor(0x66, 0x66, 0x66)
# The contact block: .footer-line-primary / .footer-site / .footer-line-secondary.
_FOOTER_PRIMARY_SIZE = Pt(13)
_FOOTER_SECONDARY_SIZE = Pt(9)
_FOOTER_PRIMARY_COLOR = RGBColor(0x99, 0x99, 0x99)
_FOOTER_SITE_COLOR = RGBColor(0x66, 0x66, 0x66)
_CAPTION_COLOR = RGBColor(0x55, 0x55, 0x55)         # .content figcaption { color }
_CAPTION_TITLE_COLOR = RGBColor(0x2C, 0x3E, 0x50)   # .figure-title { color }
# .pdfgen-table thead th { background: #d9d9d9 }
_TABLE_HEADER_FILL = "D9D9D9"

# Named paragraph styles: a Word user restyles the document in one place,
# and the output stays machine-inspectable.
_CAPTION_STYLE = "Figure Caption"
_SECTION_SUBTITLE_STYLE = "Section Subtitle"
# Document chrome (the PDF prints these above the body, not as prose).
_DOC_TITLE_STYLE = "Document Title"
_DOC_SUBTITLE_STYLE = "Document Subtitle"

_ALIGNMENTS = {
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
}


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(str(value).strip().lstrip("#").upper())


@dataclass(frozen=True)
class _Context:
    """What one render needs everywhere: font, palette, words."""

    font: str = DEFAULT_FONT_FAMILY
    title_color: RGBColor = field(default_factory=lambda: _rgb("#2e5395"))
    accent_color: RGBColor = field(default_factory=lambda: _rgb("#f58634"))
    labels: Labels = field(default_factory=Labels)
    numbering: str = "roman"


_CONTEXT: contextvars.ContextVar = contextvars.ContextVar("pdfgen_docx_context", default=_Context())


def _ctx() -> _Context:
    return _CONTEXT.get()


# ──────────────────────── result type ────────────────────────────────────


@dataclass
class DocxRenderResult:
    """Summary of one HTML → .docx render.

    ``warnings`` flags partially degraded outputs (e.g. ``rsvg-convert``
    missing → charts replaced by placeholders).
    """

    output_path: Path
    images_embedded: int = 0
    images_skipped: int = 0
    footnotes_attached: int = 0
    banner_attached: bool = False
    warnings: List[str] = field(default_factory=list)
    #: Render-contract directives the HTML carries that Word cannot map.
    unsupported_directives: List[str] = field(default_factory=list)


# ──────────────────────── public API ─────────────────────────────────────


class DocxRenderer:
    """Render editable HTML to .docx with a template package and options."""

    def __init__(
        self,
        package: Union[str, TemplatePackage, None] = None,
        options: Optional[RenderOptions] = None,
        *,
        registry: Optional[PackageRegistry] = None,
    ) -> None:
        self.options = options or RenderOptions()
        self._registry = registry
        self._package_arg = package if package is not None else self.options.template_package
        self.package_error: Optional[TemplatePackageError] = None
        try:
            self.package: Optional[TemplatePackage] = resolve_template_package(
                self._package_arg, registry=registry,
            )
        except TemplatePackageError as exc:
            # Reported in the result instead of swapping in another
            # letterhead: a Word file whose header contradicts its PDF
            # sibling is worse than one without a header.
            self.package = None
            self.package_error = exc

    def render(self, html_content: str, output_path: Union[str, Path]) -> DocxRenderResult:
        options = self.options
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        validate_render_text(html_content, options)

        package = self.package
        font = (package.font_family if package and package.font_family else None) or DEFAULT_FONT_FAMILY
        context = _Context(
            font=font,
            title_color=_rgb(package.color("title") if package else "#2e5395"),
            accent_color=_rgb(package.color("accent") if package else "#f58634"),
            labels=options.labels,
            numbering=options.section_numbering,
        )
        token = _CONTEXT.set(context)
        try:
            return self._render(html_content, output_path)
        finally:
            _CONTEXT.reset(token)

    def _render(self, html_content: str, output_path: Path) -> DocxRenderResult:
        options = self.options
        result = DocxRenderResult(output_path=output_path)
        doc = Document()
        _apply_editorial_styles(doc)
        _register_font_substitute(doc)
        if self.package_error is not None:
            result.warnings.append(
                f"template package {self._package_arg or '(default)'!r} could not be "
                f"resolved ({self.package_error}); the document has no letterhead"
            )
        else:
            _attach_header_banner(doc, result, self.package)

        # Contract audit: anything the HTML declares that Word cannot map is
        # recorded and logged, never silently dropped.
        scan = scan_directives(html_content, target="docx")
        result.unsupported_directives = list(scan.unsupported)
        log_unsupported(scan, renderer="docx")

        # Contact block: the options win, the letterhead fills the blanks —
        # the same precedence as the PDF.
        chrome = dict(self.package.theme) if self.package else {}
        chrome.update(options.theme_overrides())
        _set_footer(doc, chrome=chrome, show_page_numbers=options.show_page_numbers)

        title = options.title or ""
        subtitle = options.subtitle or ""
        if title:
            _add_title(doc, title, _TITLE_FONT_SIZE, bold=True, style=_DOC_TITLE_STYLE)
        if subtitle:
            _add_title(doc, subtitle, _SUBTITLE_FONT_SIZE, bold=False, style=_DOC_SUBTITLE_STYLE)
        if title or subtitle:
            doc.add_paragraph()  # spacer before the body

        # Lift every <p class="footnote"> into a native Word footnote. The
        # toggle exists because some Word builds flag the lifted XML; the
        # fallback keeps the source paragraphs as styled body text.
        footnote_map = _build_footnote_part(doc, html_content) if options.native_footnotes else {}
        result.footnotes_attached = sum(len(ids) for ids in footnote_map.values())

        _walk_html(doc, html_content, result, footnote_map=footnote_map, options=options)

        doc.save(str(output_path))
        logger.info(
            "DOCX written to %s (images embedded=%d, skipped=%d)",
            output_path, result.images_embedded, result.images_skipped,
        )
        for warning in result.warnings:
            logger.warning("docx: %s", warning)
        return result


def render_docx(
    html_content: str,
    output_path: Union[str, Path],
    *,
    options: Optional[RenderOptions] = None,
    package: Union[str, TemplatePackage, None] = None,
    registry: Optional[PackageRegistry] = None,
) -> DocxRenderResult:
    """One-call form of :meth:`DocxRenderer.render`."""
    return DocxRenderer(package, options, registry=registry).render(html_content, output_path)


# ──────────────────────── style scaffolding ──────────────────────────────


def _apply_editorial_styles(doc: Document) -> None:
    """Set the default font + heading style to match the PDF template."""
    style = doc.styles["Normal"]
    style.font.name = _ctx().font
    style.font.size = _BODY_FONT_SIZE
    # python-docx's template ships w:after="200" (10 pt) and 1,15 line
    # spacing in docDefaults. The line spacing matched the stylesheet by
    # luck; the paragraph gap was double the PDF's, which is what made
    # the Word version read looser page after page. Set both explicitly.
    style.paragraph_format.space_after = _BODY_SPACE_AFTER
    style.paragraph_format.line_spacing = _BODY_LINE_SPACING
    # The stylesheet justifies every body paragraph (`.content p`,
    # `.intro`, `.content li`) and Word left them ragged-right, so the
    # two formats of the same document did not read the same. Captions,
    # subtitles, page chrome and the footnote block set their own
    # alignment after this, so the default is the body's.
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    # Also set the eastAsia + ascii variants so Word respects the font
    # in every region of the document.
    _set_run_font_family(style.element, _ctx().font)

    # Heading 2 styled like the PDF section titles.
    try:
        h2 = doc.styles["Heading 2"]
    except KeyError:
        h2 = doc.styles.add_style("Heading 2", 1)
    h2.font.name = _ctx().font
    h2.font.size = _HEADING_FONT_SIZE
    h2.font.bold = True
    h2.font.color.rgb = _ctx().title_color
    _set_run_font_family(h2.element, _ctx().font)

    # Heading 3 styled like the PDF's h3. Left alone, it inherits Word's
    # own theme colour (4F81BD), a blue from nobody's palette.
    try:
        h3 = doc.styles["Heading 3"]
    except KeyError:
        h3 = doc.styles.add_style("Heading 3", 1)
    h3.font.name = _ctx().font
    h3.font.size = _H3_FONT_SIZE
    h3.font.bold = True
    h3.font.color.rgb = _H3_COLOR
    _set_run_font_family(h3.element, _ctx().font)

    # Contract-backed named styles (figure captions, section subtitles).
    caption = _ensure_paragraph_style(doc, _CAPTION_STYLE)
    caption.font.name = _ctx().font
    caption.font.size = _CAPTION_FONT_SIZE
    caption.font.color.rgb = _CAPTION_COLOR
    caption.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.space_after = Pt(8)

    for name, size, bold in (
        (_DOC_TITLE_STYLE, _TITLE_FONT_SIZE, True),
        (_DOC_SUBTITLE_STYLE, _SUBTITLE_FONT_SIZE, False),
    ):
        chrome = _ensure_paragraph_style(doc, name)
        chrome.font.name = _ctx().font
        chrome.font.size = size
        chrome.font.bold = bold
        chrome.font.color.rgb = _ctx().title_color
        chrome.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = _ensure_paragraph_style(doc, _SECTION_SUBTITLE_STYLE)
    subtitle.font.name = _ctx().font
    subtitle.font.size = Pt(10)
    subtitle.font.color.rgb = _ctx().title_color
    subtitle.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.keep_with_next = True


def _ensure_paragraph_style(doc: Document, name: str):
    """Return the named paragraph style, creating it when missing."""
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def _set_run_font_family(element, font_name: str) -> None:
    """Set ``w:rFonts`` for ascii / hAnsi / eastAsia / cs to ``font_name``.

    python-docx leaves the eastAsia + cs slots blank by default, which
    lets Word fall back to its theme font silently. Setting all four
    variants pins the font.
    """
    rpr = element.find(qn("w:rPr"))
    if rpr is None:
        return
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = etree.SubElement(rpr, qn("w:rFonts"))
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _add_title(
    doc: Document,
    text: str,
    size: Pt,
    *,
    bold: bool,
    style: Optional[str] = None,
) -> None:
    p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.font.name = _ctx().font
    run.font.size = size
    run.bold = bold
    run.font.color.rgb = _ctx().title_color


def _footer_line(paragraph: Any, pieces: Sequence[Tuple[str, Any, Any, bool]]) -> None:
    """Write one centred footer line from ``(text, size, colour, bold)``."""
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.15
    for text, size, colour, bold in pieces:
        run = paragraph.add_run(text)
        run.font.name = _ctx().font
        run.font.size = size
        run.font.color.rgb = colour
        run.font.bold = bold


def _set_footer(
    doc: Document,
    *,
    chrome: Optional[Dict[str, Any]] = None,
    show_page_numbers: bool = False,
) -> None:
    """Write the letterhead's whole contact block, plus the page number.

    The same three lines the PDF prints: site and phone, then street and
    e-mail, then city. ``chrome`` is the package theme with the render's
    overrides already applied.

    ``show_page_numbers`` is the Word half of the option the PDF resolves
    with CSS ``counter(page)``: a ``PAGE`` field computed by Word at layout.
    """
    section = doc.sections[0]
    theme = dict(chrome or {})
    site_text = str(theme.get("footer_site") or "").strip()
    phone_text = str(theme.get("footer_phone") or "").strip()
    address = str(theme.get("footer_address") or "").strip()
    email = str(theme.get("footer_email") or "").strip()
    city = str(theme.get("footer_city") or "").strip()

    # Line 1: <site> | <phone label> <phone> — the site bold and darker,
    # the separator in the accent colour (.footer-site / .footer-separator).
    primary: List[Tuple[str, Any, Any, bool]] = []
    if site_text:
        primary.append(
            (site_text, _FOOTER_PRIMARY_SIZE, _FOOTER_SITE_COLOR, True)
        )
    if phone_text:
        if primary:
            primary.append((" | ", _FOOTER_PRIMARY_SIZE, _ctx().accent_color, False))
        primary.append(
            (f"{_ctx().labels.phone} {phone_text}".strip(), _FOOTER_PRIMARY_SIZE, _FOOTER_PRIMARY_COLOR, False)
        )

    # Lines 2 and 3: street | e-mail, then city.
    secondary: List[str] = []
    joined = " | ".join(x for x in (address, email) if x)
    if joined:
        secondary.append(joined)
    if city:
        secondary.append(city)

    paragraphs = list(section.footer.paragraphs)

    def _next_paragraph():
        return paragraphs.pop(0) if paragraphs else section.footer.add_paragraph()

    wrote_any = False
    if primary:
        _footer_line(_next_paragraph(), primary)
        wrote_any = True
    for line in secondary:
        _footer_line(
            _next_paragraph(),
            [(line, _FOOTER_SECONDARY_SIZE, _FOOTER_SITE_COLOR, False)],
        )
        wrote_any = True

    if show_page_numbers:
        # Bottom-right, matching the PDF's @bottom-right margin box.
        para = section.footer.add_paragraph() if wrote_any else _next_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        para.paragraph_format.space_after = Pt(0)
        _add_page_number_field(para)


def _add_page_number_field(paragraph: Any) -> None:
    """Insert a Word ``PAGE`` field so the number is computed at layout."""
    run = paragraph.add_run()
    run.font.name = _ctx().font
    run.font.size = _PAGE_NUMBER_FONT_SIZE
    run.font.color.rgb = _FOOTNOTE_COLOR

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for node in (begin, instr, end):
        run._r.append(node)


# ──────────────────────── HTML walker ────────────────────────────────────


def _walk_html(
    doc: Document,
    html_content: str,
    result: DocxRenderResult,
    *,
    footnote_map: Optional[Dict[str, List[int]]] = None,
    options: Optional[RenderOptions] = None,
) -> None:
    """Walk the HTML tree and emit docx elements in order.

    Uses lxml to parse a fragment so we don't trip on missing
    ``<html>``/``<body>`` wrappers; callers often pass the body
    contents directly.

    ``footnote_map`` is the marker→Word-footnote-id queue that
    ``_build_footnote_part`` produces. When supplied, each ``<sup>N</sup>``
    run whose ``N`` is in the map consumes the next id and renders a
    native Word footnote reference (``w:footnoteReference w:id="..."``).
    The source ``<p class='footnote'>`` paragraphs are skipped from the
    body (they live in the footnotes part now).
    """
    footnote_map = footnote_map or {}
    options = options or RenderOptions()
    try:
        # huge_tree: the inline chart payloads are multi-MB base64 data
        # URLs in a single src attribute; libxml2's default 10 MB text
        # limit silently drops everything past the first oversized
        # attribute (a 10-figure document came out with 4 figures and no
        # parse error).
        tree = lxml_html.fragment_fromstring(
            html_content,
            create_parent="div",
            parser=lxml_html.HTMLParser(huge_tree=True),
        )
    except Exception as exc:
        result.warnings.append(f"HTML parse failed: {exc}; rendering as plain text")
        doc.add_paragraph(_strip_tags(html_content))
        return

    # Mirror the PDF parser: a body wrapped in a single container still
    # has its <h2>s as top-level sections.
    children = [c for c in tree if isinstance(getattr(c, "tag", None), str)]
    if len(children) == 1 and children[0].tag.lower() in {"div", "main", "article"}:
        inner = [c for c in children[0] if isinstance(getattr(c, "tag", None), str)]
        if inner:
            children = inner

    state = _WalkState(printed_titles={
        _flatten_text(lxml_html.fragment_fromstring(t, create_parent="div"))
        for t in (options.title, options.subtitle) if t
    })
    for elem in children:
        _emit_element(
            doc, elem, result, footnote_map=footnote_map, options=options, state=state
        )


@dataclass
class _WalkState:
    """Mutable state carried across the walk (section numbering)."""

    section_number: int = 0
    depth: int = 0
    #: Document title/subtitle texts already printed as chrome.
    printed_titles: set = field(default_factory=set)


def _emit_element(
    doc: Document,
    elem: Any,
    result: DocxRenderResult,
    *,
    footnote_map: Dict[str, List[int]],
    options: RenderOptions,
    state: Optional[_WalkState] = None,
) -> None:
    """Emit one block element, honouring the structural render contract.

    The contract directives (``data-page-break``, ``data-keep-with-next``)
    are handled HERE, for every block, instead of per-tag: the PDF gets
    them from CSS selectors that likewise don't care which tag carries
    the attribute, so handling them in one place is what keeps the two
    exporters in step.
    """
    # Comments / processing instructions carry a callable `tag`.
    if not isinstance(getattr(elem, "tag", None), str):
        return

    if wants_page_break_before(elem):
        doc.add_page_break()

    first_paragraph_idx = len(doc.paragraphs)
    _emit_element_body(
        doc,
        elem,
        result,
        footnote_map=footnote_map,
        options=options,
        state=state or _WalkState(),
    )

    if wants_keep_with_next(elem):
        for para in doc.paragraphs[first_paragraph_idx:]:
            para.paragraph_format.keep_with_next = True


def _emit_element_body(
    doc: Document,
    elem: Any,
    result: DocxRenderResult,
    *,
    footnote_map: Dict[str, List[int]],
    options: RenderOptions,
    state: _WalkState,
) -> None:
    tag = (elem.tag or "").lower()

    if tag in ("h1", "h2", "h3", "h4"):
        level = int(tag[1])
        text = _flatten_text(elem)
        if not text:
            return
        # The document's own title/subtitle is chrome, as in the PDF: it
        # takes the document title styles, never a section number, and is
        # not printed twice when the options already printed it.
        if is_document_heading(elem):
            if text in state.printed_titles:
                return
            subtitle = is_document_subtitle(elem)
            _add_title(
                doc, text, _SUBTITLE_FONT_SIZE if subtitle else _TITLE_FONT_SIZE,
                bold=not subtitle, style=_DOC_SUBTITLE_STYLE if subtitle else _DOC_TITLE_STYLE,
            )
            state.printed_titles.add(text)
            return
        # Top-level <h2>s are the numbered sections. The PDF numbers them
        # by position (contract.format_section_title); Word must show the
        # SAME sequence or the two documents disagree on «section III».
        if tag == "h2" and state.depth == 0:
            state.section_number += 1
            if _ctx().numbering == "roman":
                text = format_section_title(text, state.section_number)
        heading = doc.add_heading(text, level=min(level, 4))
        # h1–h3 never sit alone at the bottom of a page — the PDF does the
        # same through `break-after: avoid` on .section-title / h1-h3.
        # h4 is deliberately excluded on BOTH sides: gluing a caption to a
        # multi-page table strands it on a blank page.
        if level <= 3:
            heading.paragraph_format.keep_with_next = True
        return

    if tag == "p":
        _emit_paragraph(doc, elem, result, footnote_map=footnote_map, options=options)
        return

    # A bare <img> (no <figure> around it) is still a figure: without
    # this it fell through every branch and vanished from the Word file.
    if tag in ("figure", "img"):
        _emit_figure(doc, elem, result)
        return

    if tag in ("ul", "ol"):
        for li in elem.findall("li"):
            para = doc.add_paragraph(
                _flatten_text(li),
                style="List Bullet" if tag == "ul" else "List Number",
            )
            para.alignment = _ALIGNMENTS[options.text_align]
        return

    if tag == "table":
        _emit_table(doc, elem)
        return

    if tag in ("div", "section", "article"):
        # `div.chart` is the contract's chart container: same treatment as
        # a <figure>, or the image would be lost in the text fallback.
        if "chart" in element_classes(elem) and elem.find(".//img") is not None:
            _emit_figure(doc, elem, result)
            return
        # A table's source line. Styled like a figure's caption in both
        # formats, or the same annotation reads as body prose in Word.
        if "table-caption" in element_classes(elem) and _flatten_text(elem):
            cap = doc.add_paragraph(style=_CAPTION_STYLE)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _emit_inline(cap, elem, run_style=_CAPTION_RUN)
            return
        # Otherwise descend without emitting any wrapping element.
        state.depth += 1
        try:
            for child in elem:
                _emit_element(
                    doc,
                    child,
                    result,
                    footnote_map=footnote_map,
                    options=options,
                    state=state,
                )
        finally:
            state.depth -= 1
        return

    # Fallback: anything else with text becomes a plain paragraph.
    text = _flatten_text(elem)
    if text:
        para = doc.add_paragraph(text)
        para.alignment = _ALIGNMENTS[options.text_align]


def _emit_paragraph(
    doc: Document,
    elem: Any,
    result: DocxRenderResult,
    *,
    footnote_map: Dict[str, List[int]],
    options: RenderOptions,
) -> None:
    """Emit a ``<p>`` as a docx paragraph, preserving inline ``<sup>``.

    When the paragraph has class ``footnote`` AND the footnote part
    already carries that marker as a native Word footnote, we skip
    emitting it in the body — the source text now appears at the
    page bottom via ``w:footnoteReference`` from the inline marker.
    Paragraphs without a corresponding native footnote (e.g. the user
    crafted a custom one) fall back to styled body text so nothing is
    silently lost.
    """
    classes = element_classes(elem)
    is_footnote = "footnote" in classes

    if is_footnote and _is_native_footnote_paragraph(elem, footnote_map):
        return  # already lifted into the footnotes part

    if not is_footnote and any((child.tag or "").lower() == "figure" for child in elem):
        _emit_paragraph_with_nested_figures(
            doc,
            elem,
            result,
            footnote_map=footnote_map,
            options=options,
        )
        return

    if "section-subtitle" in classes:
        para = doc.add_paragraph(style=_SECTION_SUBTITLE_STYLE)
        _emit_inline(para, elem, footnote_map=footnote_map, run_style=_RunStyle(size=Pt(10), color=_ctx().title_color))
        return

    p = doc.add_paragraph()
    if is_footnote:
        p.paragraph_format.left_indent = Inches(0.2)

    # Alignment: the paragraph's own inline `style="text-align:…"` wins,
    # then the document-wide `RenderOptions.text_align`. The PDF resolves the
    # same precedence through CSS specificity.
    p.alignment = _ALIGNMENTS[inline_text_align(elem) or options.text_align]

    _emit_inline(p, elem, footnote=is_footnote, footnote_map=footnote_map)


def _emit_paragraph_with_nested_figures(
    doc: Document,
    elem: Any,
    result: DocxRenderResult,
    *,
    footnote_map: Dict[str, List[int]],
    options: RenderOptions,
) -> None:
    """Split invalid-but-common ``<p>text <figure>...</figure> text</p>``.

    Generated HTML can place a block figure inside a paragraph.
    Browsers and WeasyPrint recover from that shape, but the DOCX walker
    must emit the figure as a block or the image is lost and only the
    flattened caption text remains.
    """

    def _has_content(p_elem: Any) -> bool:
        if (p_elem.text or "").strip():
            return True
        return any(_flatten_text(child).strip() for child in p_elem)

    current = etree.Element("p")
    current.text = elem.text
    # The wrapper's own alignment must survive the split.
    inline_align = inline_text_align(elem)
    if inline_align:
        current.set("style", f"text-align:{inline_align}")
    for child in elem:
        ctag = (child.tag or "").lower()
        if ctag == "figure":
            if _has_content(current):
                _emit_paragraph(
                    doc, current, result, footnote_map=footnote_map, options=options
                )
            _emit_figure(doc, child, result)
            current = etree.Element("p")
            if inline_align:
                current.set("style", f"text-align:{inline_align}")
            current.text = child.tail
            continue
        current.append(copy.deepcopy(child))

    if _has_content(current):
        _emit_paragraph(
            doc, current, result, footnote_map=footnote_map, options=options
        )


def _is_native_footnote_paragraph(
    elem: Any,
    footnote_map: Dict[str, List[int]],
) -> bool:
    """Detect whether this ``<p class='footnote'>`` is already represented
    by a native Word footnote — i.e. its leading ``<sup>N</sup>`` marker
    matched an inline reference and was lifted by
    ``_build_footnote_part``."""
    sup = elem.find("sup")
    if sup is None:
        return False
    marker = _flatten_text(sup)
    return marker in footnote_map


@dataclass(frozen=True)
class _RunStyle:
    """Base typography for the runs of one paragraph."""

    size: Any = _BODY_FONT_SIZE
    color: Optional[RGBColor] = None
    italic: bool = False


_BODY_RUN = _RunStyle()
_FOOTNOTE_RUN = _RunStyle(size=_FOOTNOTE_FONT_SIZE, color=_FOOTNOTE_COLOR)
_CAPTION_RUN = _RunStyle(size=_CAPTION_FONT_SIZE, color=_CAPTION_COLOR)

#: Class-scoped run overrides for the ``<span>`` directives of the
#: contract. Keyed by class name so adding one is a registry entry, not a
#: branch in the walker.
_SPAN_RUN_STYLES: Dict[str, _RunStyle] = {
    "figure-title": _RunStyle(size=_CAPTION_FONT_SIZE, color=_CAPTION_TITLE_COLOR),
    "figure-subcaption": _RunStyle(
        size=_SUBCAPTION_FONT_SIZE, color=_CAPTION_COLOR, italic=True
    ),
}
#: Spans whose text is emitted bold (the PDF gives `.figure-title`
#: font-weight 600).
_SPAN_BOLD_CLASSES = frozenset({"figure-title"})


def _emit_inline(
    paragraph: Any,
    elem: Any,
    *,
    footnote: bool = False,
    footnote_map: Optional[Dict[str, List[int]]] = None,
    run_style: Optional[_RunStyle] = None,
) -> None:
    """Walk ``elem`` adding runs to ``paragraph``.

    Honours:
      - ``<sup>`` → superscript run (or a native footnote reference).
      - ``<strong>`` / ``<b>`` → bold.
      - ``<em>`` / ``<i>`` → italic.
      - ``<br>`` → manual line break.
      - ``<span class="figure-title|figure-subcaption">`` → the contract's
        caption run styles (see :data:`_SPAN_RUN_STYLES`).
      - bare text → plain run.
    """
    base = run_style or (_FOOTNOTE_RUN if footnote else _BODY_RUN)

    def _run(
        text: str,
        *,
        sup: bool = False,
        bold: bool = False,
        italic: bool = False,
        style: Optional[_RunStyle] = None,
    ) -> None:
        if not text:
            return
        active = style or base
        r = paragraph.add_run(text)
        r.font.name = _ctx().font
        r.font.size = active.size
        if active.color is not None:
            r.font.color.rgb = active.color
        if sup:
            r.font.superscript = True
        if bold:
            r.bold = True
        if italic or active.italic:
            r.italic = True

    footnote_map = footnote_map or {}

    # leading text before any child
    if elem.text:
        _run(elem.text)

    for child in elem:
        ctag = (child.tag or "").lower()
        if ctag == "sup":
            markers = _markers_of(child)
            # One Word reference PER number the marker carries: a word
            # citing notes 2, 3 and 4 has to produce three, or two of
            # them vanish from the document.
            emitted = False
            for marker in markers:
                fn_ids = footnote_map.get(marker)
                # Skip the very first leading <sup> on a footnote
                # paragraph (it's the source marker, not a reference).
                if fn_ids and not footnote:
                    _add_footnote_reference(paragraph, fn_ids.pop(0))
                    emitted = True
            if not emitted:
                _run(_flatten_text(child), sup=True)
        elif ctag in ("strong", "b"):
            _run(_inline_text(child), bold=True)
        elif ctag in ("em", "i"):
            _run(_inline_text(child), italic=True)
        elif ctag == "br":
            paragraph.add_run().add_break()
        elif ctag == "span":
            classes = element_classes(child)
            span_style = next(
                (_SPAN_RUN_STYLES[c] for c in classes if c in _SPAN_RUN_STYLES),
                None,
            )
            _run(
                _inline_text(child),
                bold=any(c in _SPAN_BOLD_CLASSES for c in classes),
                style=span_style,
            )
        else:
            # Unknown inline element — fall back to plain text
            _run(_inline_text(child))
        # tail text that follows the child
        if child.tail:
            _run(child.tail)


def _emit_figure(doc: Document, elem: Any, result: DocxRenderResult) -> None:
    """Decode the embedded ``<img>`` payload and add it as a centered picture.

    SVG payloads go through ``rsvg-convert``; PNG payloads (used for
    choropleths, whose inline-TopoJSON SVGs weigh ~1 MB each) embed
    directly. The figure's width follows the contract's figure classes
    (``figure-full``/``figure-column`` = full column, ``figure-left``/
    ``figure-right`` = 78%), mirroring report.css.
    """
    img = elem if (elem.tag or "").lower() == "img" else elem.find(".//img")
    if img is None:
        return
    src = img.get("src") or ""
    png_bytes: Optional[bytes] = None
    if src.startswith("data:image/png;base64,"):
        try:
            png_bytes = base64.b64decode(src.split(",", 1)[1])
        except Exception as exc:
            result.warnings.append(f"figure png decode failed: {exc}")
            result.images_skipped += 1
            return
    elif not src.startswith("data:image/svg+xml;base64,"):
        result.warnings.append("figure has non-SVG/PNG src; skipped")
        result.images_skipped += 1
        return

    if png_bytes is None:
        try:
            svg_bytes = base64.b64decode(src.split(",", 1)[1])
        except Exception as exc:
            result.warnings.append(f"figure svg decode failed: {exc}")
            result.images_skipped += 1
            return
        png_bytes = _svg_to_png(svg_bytes, result)
    if png_bytes is None:
        # Fallback placeholder so the document still has SOME mark
        # where the chart should sit.
        p = doc.add_paragraph()
        labels = _ctx().labels
        run = p.add_run(labels.figure_omitted.format(
            figure=labels.figure, alt=img.get("alt") or "chart", reason=labels.no_svg_rasterizer,
        ))
        run.font.name = _ctx().font
        run.font.size = _FOOTNOTE_FONT_SIZE
        run.italic = True
        run.font.color.rgb = _FOOTNOTE_COLOR
        result.images_skipped += 1
        return

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # Keep the image glued to its caption: the PDF ships them as one
    # keep-together block (`page-break-inside: avoid` on .content figure).
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(io.BytesIO(png_bytes), width=Inches(_figure_width_inches(elem)))
    result.images_embedded += 1

    # Caption (if the figure carries one). Emitted through the inline
    # walker so `.figure-title` / `.figure-subcaption` keep their own run
    # styling instead of collapsing into one flat italic string.
    figcaption = elem.find(".//figcaption")
    if figcaption is None:
        figcaption = elem.find(".//*[@class='chart-caption']")
    if figcaption is not None and _flatten_text(figcaption):
        cap = doc.add_paragraph(style=_CAPTION_STYLE)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _emit_inline(cap, figcaption, run_style=_CAPTION_RUN)


def _figure_width_inches(elem: Any) -> float:
    """Rendered picture width for a figure, from its contract class."""
    classes = set(element_classes(elem))
    if classes & {"figure-left", "figure-right"}:
        return _FIGURE_NARROW_WIDTH_INCHES
    return _FIGURE_WIDTH_INCHES


# ──────────────────────── SVG → PNG via rsvg-convert ─────────────────────


def _emit_table(doc: Document, elem: Any) -> None:
    """Convert an HTML ``<table>`` into a native Word table.

    Without this branch a table fell into the text fallback and shipped
    as one flattened paragraph. Header cells (``<th>`` or first
    ``<thead>`` row) render bold; ragged rows are padded so python-docx
    never raises on column count.
    """
    # Title first: a reader looks above a table for its name, and the
    # PDF puts it there.
    _emit_table_title(doc, elem)
    rows: List[List[tuple]] = []  # [(text, is_header), ...] per row
    for tr in elem.iter("tr"):
        cells = []
        for cell in tr:
            tag = (cell.tag or "").lower()
            if tag not in ("td", "th"):
                continue
            # A cell wrapped in <b> is bold on purpose (a total row, a
            # highlighted entity): the PDF keeps it bold, so must Word.
            emphasised = any(
                child.tag in ("b", "strong") for child in cell.iter()
                if child is not cell
            )
            cells.append((_flatten_text(cell), tag == "th", emphasised))
        if cells:
            rows.append(cells)
    if not rows:
        return
    n_cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=n_cols)
    table.style = "Table Grid"
    is_body = is_body_table(elem)
    widths = []
    if is_body:
        widths = body_table_widths([[t for t, _h, _b in row] for row in rows])
        section = doc.sections[-1]
        usable = section.page_width - section.left_margin - section.right_margin
        table.autofit = False
        for column, share in zip(table.columns, widths, strict=False):
            column.width = int(usable * share)
    header_rows = 0
    for r_idx, row in enumerate(rows):
        row_is_header = any(h for _t, h, _b in row)
        for c_idx in range(n_cols):
            text, is_header, emphasised = (
                row[c_idx] if c_idx < len(row) else ("", False, False)
            )
            cell = table.cell(r_idx, c_idx)
            if widths:
                cell.width = int(usable * widths[c_idx])
            # Cells start with one empty paragraph; write into it
            # directly (cell.text = ... would create a runless reset).
            para = cell.paragraphs[0]
            run = para.add_run(text)
            run.font.name = _ctx().font
            run.font.size = Pt(8.5 if is_body else 8)
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = 1.15 if is_body else 1.0
            # The body style is justified now; a table cell is not prose
            # and the stylesheet aligns it left in the PDF, so Word says
            # so explicitly instead of inheriting.
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
            if is_header or (r_idx == 0 and row_is_header) or emphasised:
                run.bold = True
        if row_is_header and r_idx == header_rows:
            # `.pdfgen-table thead { display: table-header-group }` makes
            # WeasyPrint repeat the header on every page the table breaks
            # across, and the stylesheet says so in a comment. Word needs
            # `tblHeader` for the same behaviour and never got it, so the
            # annex's 36 rows continued onto the next page with no header
            # over them — the one table a reader goes to the annex FOR.
            _mark_repeating_header(table.rows[r_idx], _TABLE_HEADER_FILL)
            header_rows += 1
        tr_pr = table.rows[r_idx]._tr.get_or_add_trPr()
        etree.SubElement(tr_pr, qn("w:cantSplit"))
    # Breathing room after the table — Word glues the next paragraph to
    # the grid otherwise. The source line that usually follows
    # (`div.table-caption`) provides it; when there is none, add it.
    if not _table_is_followed_by_a_source_line(elem):
        doc.add_paragraph("")


def _table_is_followed_by_a_source_line(elem: Any) -> bool:
    """Does a ``div.table-caption`` come right after this table?"""
    nxt = elem.getnext()
    return (
        nxt is not None
        and str(nxt.tag).lower() == "div"
        and "table-caption" in element_classes(nxt)
    )


def _emit_table_title(doc: Any, elem: Any) -> None:
    """The table's ``<caption>``, printed ABOVE it as in the PDF.

    Word used to emit it after the grid, so the same table was titled
    above in one format and below in the other — a parity divergence in
    the one line a reader uses to find the table from the prose.
    """
    caption = elem.find("caption")
    if caption is None or not _flatten_text(caption):
        return
    cap = doc.add_paragraph(style=_CAPTION_STYLE)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _emit_inline(cap, caption, run_style=_CAPTION_RUN)


def _mark_repeating_header(row: Any, fill: Optional[str] = None) -> None:
    """Repeat ``row`` at the top of every page the table spans, and shade it.

    ``fill`` mirrors ``.pdfgen-table thead th { background: … }``.
    """
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        etree.SubElement(tr_pr, qn("w:tblHeader"))
    if not fill:
        return
    for cell in row.cells:
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = tc_pr.find(qn("w:shd"))
        if shd is None:
            shd = etree.SubElement(tc_pr, qn("w:shd"))
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)


def _svg_to_png(svg_bytes: bytes, result: DocxRenderResult) -> Optional[bytes]:
    """Convert SVG bytes to PNG bytes using ``rsvg-convert``.

    Returns None when the binary is missing or the conversion fails —
    the caller substitutes a placeholder paragraph.
    """
    if not _has_rsvg_convert():
        if "rsvg-convert not on PATH" not in result.warnings:
            result.warnings.append(
                "rsvg-convert not on PATH; charts replaced by placeholders. "
                "Install via `brew install librsvg` (macOS) or `apt install librsvg2-bin` (Debian)."
            )
        return None

    try:
        proc = subprocess.run(
            ["rsvg-convert", "--format=png", "--width=1600"],
            input=svg_bytes,
            capture_output=True,
            check=True,
            timeout=10,
        )
        return proc.stdout
    except subprocess.CalledProcessError as exc:
        result.warnings.append(f"rsvg-convert failed: {exc.stderr.decode('utf-8', 'ignore')[:200]}")
        return None
    except subprocess.TimeoutExpired:
        result.warnings.append("rsvg-convert timed out after 10s")
        return None
    except FileNotFoundError:
        result.warnings.append("rsvg-convert disappeared mid-run; check PATH")
        return None


def _has_rsvg_convert() -> bool:
    from shutil import which
    return which("rsvg-convert") is not None


# ──────────────────────── tiny helpers ───────────────────────────────────


def _flatten_text(elem: Any) -> str:
    """Concatenated text of an element + its descendants, whitespace-trimmed."""
    if elem is None:
        return ""
    text = "".join(elem.itertext())
    return " ".join(text.split())


def _inline_text(elem: Any) -> str:
    """Like :func:`_flatten_text` but keeping edge spaces as single spaces.

    Runs are concatenated inside one Word paragraph, so trimming the
    space that separates an inline element from its neighbours welds the
    words together (``…(June)Source: …`` — observed against
    the figure sub-caption, whose source text starts with a space).
    """
    if elem is None:
        return ""
    raw = "".join(elem.itertext())
    if not raw:
        return ""
    collapsed = " ".join(raw.split())
    if not collapsed:
        return " " if raw.strip() == "" else ""
    lead = " " if raw[:1].isspace() else ""
    trail = " " if raw[-1:].isspace() else ""
    return f"{lead}{collapsed}{trail}"


def _strip_tags(html: str) -> str:
    try:
        tree = lxml_html.fragment_fromstring(html, create_parent="div")
        return _flatten_text(tree)
    except Exception:
        return html


# ──────────────────────── letterhead band (page header) ─────────────────


def _attach_header_banner(
    doc: Document,
    result: DocxRenderResult,
    package: Optional[TemplatePackage],
) -> None:
    """Paint the template package's header band in the section header.

    The SAME package entry the PDF reads, so a letterhead reaches both
    formats or neither. The band runs edge to edge while the body keeps
    1" side margins: the header paragraph carries a negative indent equal
    to the margin and the image is sized at the full page width.
    """
    if package is None:
        return
    try:
        asset = package.header_asset
    except TemplatePackageError as exc:
        result.warnings.append(f"template package {package.name!r}: {exc}")
        return
    if asset is None:
        return  # the package paints no band

    section = doc.sections[0]
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)
    # Room for the band at the top of every page.
    section.top_margin = Inches(1.3)
    section.header_distance = Inches(0.0)

    header_para = section.header.paragraphs[0]
    header_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    # Drop inherited paragraph properties (center tabs would push the
    # image off-axis).
    pPr = header_para._p.find(qn("w:pPr"))
    if pPr is not None:
        header_para._p.remove(pPr)
    header_para.paragraph_format.left_indent = Inches(-1.0)
    header_para.paragraph_format.right_indent = Inches(-1.0)

    run = header_para.add_run()
    run.add_picture(str(asset), width=Inches(8.5))  # full Letter width
    result.banner_attached = True


# ──────────────────────── native Word footnotes ─────────────────────────


# Microsoft Word writes the full OOXML namespace declaration suite on
# the root of ``word/footnotes.xml`` plus an ``mc:Ignorable`` attribute
# listing the newer namespaces older Word versions can skip. Without
# that declaration set, Word for Mac flags the part as "unreadable
# content" even when the schema validates locally — observed against
# a document where the body was perfectly fine but Word
# silently dropped half the footnotes.
# Sample lifted verbatim from a Word-generated reference document at
# https://github.com/essepuntato/rash/blob/master/testbed/docx/testbed-13-sources/word/footnotes.xml
_FOOTNOTES_NS_HEADER = (
    'xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
    'xmlns:mo="http://schemas.microsoft.com/office/mac/office/2008/main" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:mv="urn:schemas-microsoft-com:mac:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:w10="urn:schemas-microsoft-com:office:word" '
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml" '
    'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
    'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
    'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'mc:Ignorable="w14 w15 wp14"'
)

_FOOTNOTES_BASE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:footnotes {_FOOTNOTES_NS_HEADER}>'
    '<w:footnote w:type="separator" w:id="-1">'
    '<w:p><w:r><w:separator/></w:r></w:p>'
    '</w:footnote>'
    '<w:footnote w:type="continuationSeparator" w:id="0">'
    '<w:p><w:r><w:continuationSeparator/></w:r></w:p>'
    '</w:footnote>'
    '</w:footnotes>'
)


def _build_footnote_part(doc: Document, html_content: str) -> Dict[str, List[int]]:
    """Lift every ``<p class='footnote'>`` into a native Word footnote.

    Returns a dict ``{marker_text → [footnote_ids]}`` that the HTML walker
    uses to translate inline ``<sup>N</sup>`` runs into native
    references. Each inline occurrence gets its own Word footnote id;
    reusing one id from multiple ``w:footnoteReference`` anchors causes
    Word for Mac to repair the footnotes part on open.

    Footnotes whose marker has no matching inline ``<sup>N</sup>`` are
    skipped so the walker leaves those ``<p class='footnote'>`` source
    paragraphs visible as styled body text. Repeated inline markers are
    represented as separate native footnotes with duplicated source
    text, because Word repairs documents where multiple anchors reuse
    one ``w:footnote`` id.
    """
    try:
        tree = lxml_html.fragment_fromstring(
            html_content,
            create_parent="div",
            parser=lxml_html.HTMLParser(huge_tree=True),
        )
    except Exception:
        return {}

    # Inline references — every <sup>N</sup> in a NON-footnote paragraph.
    # Restrict to <p> parents specifically; <sup> inside <h2> or
    # <figcaption> would NOT become a footnoteReference in the body
    # walker (those elements are emitted as flat text by python-docx),
    # so lifting them as native footnotes would leave the footnote
    # dangling and Word would flag it.
    inline_markers: set[str] = set()
    for sup in tree.iter("sup"):
        parent = sup.getparent()
        if parent is None:
            continue
        if (parent.tag or "").lower() != "p":
            continue
        classes = (parent.get("class") or "").split()
        if "footnote" in classes:
            continue
        inline_markers.update(_markers_of(sup))

    # Footnote sources — pull the body text from each <p class='footnote'>,
    # stripping the leading <sup>N</sup> marker. A document may repeat
    # the same definition in several places, so the SAME marker can
    # appear in multiple paragraphs. We keep the FIRST occurrence per
    # marker; later ones
    # would create unreferenced Word footnotes that Word flags as
    # "Repaired Content" when opening the file.
    sources_by_marker: Dict[str, str] = {}
    for p in tree.xpath(".//p[contains(@class, 'footnote')]"):
        sup = p.find("sup")
        marker = _flatten_text(sup) if sup is not None else ""
        if not marker:
            continue
        if marker not in inline_markers:
            continue  # orphan — leave the paragraph in body so we don't lose data
        if marker in sources_by_marker:
            continue  # already captured the first source for this marker
        body = _footnote_body_text(p)
        if not body:
            continue
        sources_by_marker[marker] = body

    if not sources_by_marker:
        return {}

    part = _ensure_footnotes_part(doc)
    footnotes_root = etree.fromstring(part.blob)
    marker_to_ids: Dict[str, List[int]] = {}
    next_id = 1
    # Iterate in the order markers first appear in the body so the
    # Word numbering visually matches the order the reader encounters
    # citations.
    inline_order: List[str] = []
    for sup in tree.iter("sup"):
        parent = sup.getparent()
        if parent is None:
            continue
        if (parent.tag or "").lower() != "p":
            continue
        classes = (parent.get("class") or "").split()
        if "footnote" in classes:
            continue
        inline_order.extend(_markers_of(sup))
    for marker in inline_order:
        body = sources_by_marker.get(marker)
        if body is None:
            continue
        fn_id = next_id
        next_id += 1
        _append_footnote_element(footnotes_root, fn_id, body)
        marker_to_ids.setdefault(marker, []).append(fn_id)

    # Word rejects single-quote XML declarations on the footnotes part
    # ("Show repairs — Footnotes 1, 2, 3...") even
    # though they're valid XML. lxml emits single quotes by default,
    # so we serialize WITHOUT the auto-declaration and prepend the
    # double-quoted form ourselves. Reference:
    # https://github.com/droza123/python-docx-footnotes
    part._blob = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        + etree.tostring(footnotes_root, encoding="UTF-8")
    )
    _ensure_footnote_styles(doc)
    _ensure_footnote_settings(doc)
    return marker_to_ids


def _register_font_substitute(doc: Document) -> None:
    """Tell Word what to use when the document's font is not installed.

    python-docx ships its template's font table (Calibri, Arial, Cambria…)
    and never lists the font every run declares, so Word has no metadata
    to choose a substitute from and may land on a serif face. When the
    font is a metric-compatible clone (Carlito → Calibri), that original
    is declared as ``altName``: substituting it moves no line break.
    """
    font_name = _ctx().font
    alt_name = METRIC_COMPATIBLE.get(font_name)
    for part in doc.part.package.iter_parts():
        if not str(part.partname).endswith("/fontTable.xml"):
            continue
        try:
            root = etree.fromstring(part.blob)
        except Exception:  # noqa: BLE001 — never break a delivery
            return
        for existing in root.findall(qn("w:font")):
            if existing.get(qn("w:name")) == font_name:
                return  # already declared
        font = etree.SubElement(root, qn("w:font"))
        font.set(qn("w:name"), font_name)
        entries = [("w:altName", alt_name)] if alt_name else []
        if alt_name == "Calibri":
            # Calibri's panose/family/pitch, for the same reason.
            entries += [
                ("w:panose1", "020F0502020204030204"),
                ("w:charset", "00"),
                ("w:family", "swiss"),
                ("w:pitch", "variable"),
            ]
        for tag, value in entries:
            child = etree.SubElement(font, qn(tag))
            child.set(qn("w:val"), value)
        part._blob = (
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + etree.tostring(root, encoding="UTF-8")
        )
        return


def _footnote_body_text(p_elem: Any) -> str:
    """Return the footnote text WITHOUT the leading marker.

    We can't just call ``_flatten_text`` because that includes the
    ``<sup>N</sup>`` marker prefix. Walk the element manually,
    skipping the first ``<sup>``.
    """
    parts: List[str] = []
    if p_elem.text:
        parts.append(p_elem.text)
    skipped = False
    for child in p_elem:
        if not skipped and (child.tag or "").lower() == "sup":
            skipped = True
        else:
            txt = _flatten_text(child)
            if txt:
                parts.append(txt)
        if child.tail:
            parts.append(child.tail)
    return " ".join(p.strip() for p in parts if p and p.strip())


def _markers_of(sup_elem) -> List[str]:
    """Every footnote number a ``<sup>`` carries, in order.

    A word citing several notes renders as ONE marker with commas
    (``<sup>2,3,4</sup>``) so it does not read as "234". Word matches a
    footnote by the marker's text, so reading that tag as a single
    marker "2,3,4" finds no footnote at all and Word flags three
    dangling references. Split, and each number keeps its own note.
    """
    text = (_flatten_text(sup_elem) or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _ensure_footnotes_part(doc: Document) -> Part:
    """Create (or return) the ``word/footnotes.xml`` part.

    python-docx doesn't expose this through its high-level API, so we
    drop down to the OPC layer: register a Part with the right content
    type and relationship from the document part. The base XML carries
    the two mandatory ``separator`` / ``continuationSeparator`` entries
    Word expects at IDs -1 and 0.
    """
    package = doc.part.package
    # Already attached? Reuse it.
    for rel in doc.part.rels.values():
        if rel.reltype == RELATIONSHIP_TYPE.FOOTNOTES:
            return rel.target_part

    from docx.opc.packuri import PackURI

    partname = PackURI("/word/footnotes.xml")
    blob = _FOOTNOTES_BASE_XML.encode("utf-8")
    content_type = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.footnotes+xml"
    )
    part = Part(partname, content_type, blob, package)
    # ``relate_to`` registers the part with the package via the
    # relationship machinery — no manual ``package._parts`` poke needed.
    doc.part.relate_to(part, RELATIONSHIP_TYPE.FOOTNOTES)
    return part


def _append_footnote_element(root: Any, fn_id: int, body_text: str) -> None:
    """Append a ``<w:footnote w:id="N">`` element with one paragraph.

    Sets ``w14:paraId`` / ``w14:textId`` on the paragraph — Word writes
    those on every paragraph it produces, and Word for Mac flags a
    footnote part as "unreadable content" when they're absent. The
    8-hex-char IDs are deterministic per footnote so re-running the
    renderer produces byte-identical output for the same input.
    """
    fn = etree.SubElement(root, qn("w:footnote"))
    fn.set(qn("w:id"), str(fn_id))
    p = etree.SubElement(fn, qn("w:p"))
    p.set(qn("w14:paraId"), f"{fn_id:08X}")
    p.set(qn("w14:textId"), f"{fn_id:08X}")
    # Revision IDs Word writes on every paragraph. Word for Mac
    # flags paragraphs without them on the footnote part with
    # "unreadable content" even though the schema marks rsid
    # attributes as optional. Using a deterministic value (same for
    # all paragraphs in a single render) keeps output reproducible.
    p.set(qn("w:rsidR"), "00000001")
    p.set(qn("w:rsidRDefault"), "00000001")
    # paragraph style → "FootnoteText" (Word's built-in)
    pPr = etree.SubElement(p, qn("w:pPr"))
    pStyle = etree.SubElement(pPr, qn("w:pStyle"))
    pStyle.set(qn("w:val"), "FootnoteText")
    # Marker run with the auto footnoteRef.
    marker_run = etree.SubElement(p, qn("w:r"))
    marker_rPr = etree.SubElement(marker_run, qn("w:rPr"))
    marker_style = etree.SubElement(marker_rPr, qn("w:rStyle"))
    marker_style.set(qn("w:val"), "FootnoteReference")
    etree.SubElement(marker_run, qn("w:footnoteRef"))
    # Spacer run — Word writes the separator space as its own
    # ``<w:r><w:t xml:space="preserve"> </w:t></w:r>`` rather than
    # merging it into the body-text run. Matches the reference
    # implementation byte-for-byte.
    space_run = etree.SubElement(p, qn("w:r"))
    space_t = etree.SubElement(space_run, qn("w:t"))
    space_t.set(qn("xml:space"), "preserve")
    space_t.text = " "
    # Body text run (no separator embedded — separator lives on the
    # previous run).
    text_run = etree.SubElement(p, qn("w:r"))
    text_t = etree.SubElement(text_run, qn("w:t"))
    text_t.set(qn("xml:space"), "preserve")
    text_t.text = body_text


def _add_footnote_reference(paragraph: Any, fn_id: int) -> None:
    """Insert a ``<w:footnoteReference w:id="N"/>`` run into ``paragraph``."""
    run = paragraph.add_run()
    rPr = run._r.get_or_add_rPr()
    rStyle = etree.SubElement(rPr, qn("w:rStyle"))
    rStyle.set(qn("w:val"), "FootnoteReference")
    ref = etree.SubElement(run._r, qn("w:footnoteReference"))
    ref.set(qn("w:id"), str(fn_id))


_CANONICAL_FOOTNOTE_STYLES_XML = """\
<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
         w:type="paragraph" w:styleId="FootnoteText">
  <w:name w:val="footnote text"/>
  <w:basedOn w:val="Normal"/>
  <w:link w:val="FootnoteTextChar"/>
  <w:uiPriority w:val="99"/>
  <w:semiHidden/>
  <w:unhideWhenUsed/>
  <w:pPr>
    <w:spacing w:after="0" w:line="240" w:lineRule="auto"/>
  </w:pPr>
  <w:rPr>
    <w:sz w:val="20"/>
    <w:szCs w:val="20"/>
  </w:rPr>
</w:style>
<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
         w:type="character" w:customStyle="1" w:styleId="FootnoteTextChar">
  <w:name w:val="Footnote Text Char"/>
  <w:basedOn w:val="DefaultParagraphFont"/>
  <w:link w:val="FootnoteText"/>
  <w:uiPriority w:val="99"/>
  <w:semiHidden/>
  <w:rPr>
    <w:sz w:val="20"/>
    <w:szCs w:val="20"/>
  </w:rPr>
</w:style>
<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
         w:type="character" w:styleId="FootnoteReference">
  <w:name w:val="footnote reference"/>
  <w:basedOn w:val="DefaultParagraphFont"/>
  <w:uiPriority w:val="99"/>
  <w:semiHidden/>
  <w:unhideWhenUsed/>
  <w:rPr>
    <w:vertAlign w:val="superscript"/>
  </w:rPr>
</w:style>"""


def _ensure_footnote_styles(doc: Document) -> None:
    """Register Word's canonical ``FootnoteText``, ``FootnoteTextChar``
    and ``FootnoteReference`` styles when missing.

    Earlier the renderer shipped minimal styles (``<w:name>`` + a single
    ``<w:rPr>`` child); Word loaded them but flagged the file as
    "unreadable content" on open. The shape below mirrors what
    Microsoft Word writes for a blank document — same ``w:basedOn``,
    ``w:link``, ``w:uiPriority``, ``w:semiHidden``, ``w:unhideWhenUsed``
    decorations Word's validator expects. The character style
    ``FootnoteTextChar`` is the link target for ``FootnoteText`` (Word
    refuses to load a paragraph style with ``<w:link>`` pointing at a
    missing character style).
    """
    styles_root = doc.styles.element
    existing = {
        s.get(qn("w:styleId"))
        for s in styles_root.findall(qn("w:style"))
    }
    for style_elem in etree.fromstring(
        "<root xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"{_CANONICAL_FOOTNOTE_STYLES_XML}</root>"
    ):
        if style_elem.get(qn("w:styleId")) in existing:
            continue
        styles_root.append(style_elem)


def _ensure_footnote_settings(doc: Document) -> None:
    """Stamp ``<w:footnotePr>`` into ``word/settings.xml`` when absent.

    Microsoft Word always emits a ``<w:footnotePr>`` element with the
    default numbering format. When the bare python-docx template ships
    without it, opening a document that DOES carry a footnotes part
    triggers the "unreadable content" repair flow because the
    settings part is "missing required content for footnotes".
    """
    settings_root = doc.settings.element
    if settings_root.find(qn("w:footnotePr")) is not None:
        return
    fn_pr = etree.fromstring(
        '<w:footnotePr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:footnote w:id="-1"/>'
        '<w:footnote w:id="0"/>'
        '</w:footnotePr>'
    )
    # Word expects footnotePr near the top of settings, but anywhere
    # inside <w:settings> is schema-valid; appending is the simplest
    # placement.
    settings_root.append(fn_pr)


__all__ = ["DocxRenderResult", "DocxRenderer", "render_docx"]
