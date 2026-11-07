"""HTML → PDF: the HTML-first renderer.

    from pdfgen_juanipis import HtmlRenderer, RenderOptions

    result = HtmlRenderer(options=RenderOptions(title="Report")).render(html, "out.pdf")

Pipeline: editable HTML → section / block payload (``parsing``, ``pages``)
→ Jinja template → WeasyPrint, followed by the post-layout passes in
``passes`` (figure gaps, lonely breaks, footnotes on their marker's page).
WeasyPrint is the layout engine: content flows and paginates naturally.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from jinja2 import Environment, FileSystemLoader
from lxml import html as lxml_html

from pdfgen_juanipis.contract import (
    DOCUMENT_SUBTITLE_CLASSES,
    DOCUMENT_TITLE_CLASSES,
    log_unsupported,
    scan_directives,
    validate_render_text,
)
from pdfgen_juanipis.fonts import isolated_fontconfig
from pdfgen_juanipis.options import RenderOptions
from pdfgen_juanipis.packages import (
    PackageRegistry,
    TemplatePackage,
    TemplatePackageError,
    resolve_template_package,
)
from pdfgen_juanipis.pdf import passes
from pdfgen_juanipis.pdf.pages import build_pages
from pdfgen_juanipis.pdf.parsing import HtmlParser, first_text
from pdfgen_juanipis.security import ResourcePolicy
from pdfgen_juanipis.text import ASCII_DASHES, bind_number_to_percent

logger = logging.getLogger("pdfgen_juanipis.pdf")

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_NAME = "report.html.jinja"
STYLESHEET = TEMPLATE_DIR / "report.css"

_TEXT_ALIGN_CSS = """\
.content p, .content li, .intro, .fn-note, p.footnote {{
  text-align: {align} !important;
}}
"""

_PAGE_NUMBER_CSS = """\
@page {{
  @bottom-right {{
    content: {content};
    font-family: var(--pdfgen-font-family);
    font-size: 6.5pt;
    font-weight: 400;
    color: #666666;
    letter-spacing: 0.02em;
    margin-bottom: 14pt;
  }}
}}
"""


def _css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass
class PdfRenderResult:
    """Outcome of one :meth:`HtmlRenderer.render` call."""

    output_path: Optional[Path]
    pages: int = 0
    #: Notes still laid out on a later page than their marker.
    footnote_mismatches: List[str] = field(default_factory=list)
    footnote_passes: int = 0
    #: Directives the HTML carries that the PDF side cannot map.
    unsupported_directives: List[str] = field(default_factory=list)
    package: str = ""


class HtmlRenderer:
    """Render editable HTML to PDF with a template package and options."""

    def __init__(
        self,
        package: Union[str, TemplatePackage, None] = None,
        options: Optional[RenderOptions] = None,
        *,
        registry: Optional[PackageRegistry] = None,
    ) -> None:
        self.options = options or RenderOptions()
        # Resolved here so an unknown letterhead fails before a page is
        # painted, never by silently falling back to another one.
        self.package = resolve_template_package(
            package if package is not None else self.options.template_package,
            registry=registry,
        )

    def resource_policy(self, source_dir: Optional[Path] = None) -> ResourcePolicy:
        """What this render may read (see :mod:`pdfgen_juanipis.security`)."""
        options = self.options
        return ResourcePolicy.build(
            [source_dir, TEMPLATE_DIR, *self.package.trusted_dirs(), *options.allowed_roots],
            allow_absolute_paths=options.allow_absolute_paths,
            allow_network=options.allow_network,
        )

    # ── payload ─────────────────────────────────────────────────────
    def build_payload(self, html_content: str, *, source_dir: Optional[Path] = None) -> Dict[str, Any]:
        """The template context: title, theme, sections and pages."""
        options = self.options
        text = str(html_content or "")
        if options.ascii_dashes:
            text = text.translate(ASCII_DASHES)
        # Element ids serve the editable HTML; in the PDF they only cause
        # duplicate-anchor warnings (and would clash with tracking ids).
        if 'id="' in text or "id='" in text:
            text = re.sub(r"""\s+id=(["']).*?\1""", "", text)
        root = lxml_html.fromstring(text or "<div></div>", parser=lxml_html.HTMLParser(huge_tree=True))

        title_xpaths = [f"//h1[contains(@class, '{c}')]" for c in DOCUMENT_TITLE_CLASSES] + ["//h1"]
        subtitle_xpaths = [f"//*[contains(@class, '{c}')]" for c in DOCUMENT_SUBTITLE_CLASSES]
        title = (options.title or "").strip() or first_text(root, title_xpaths)
        subtitle = (options.subtitle or "").strip() or first_text(root, subtitle_xpaths)

        parser = HtmlParser(
            labels=options.labels,
            visual_layout=options.resolved_visual_layout(),
            source_dir=source_dir,
            policy=self.resource_policy(source_dir),
        )
        sections = parser.extract_sections(root)
        if not sections:
            sections = [{
                "title": options.labels.untitled_section,
                "content": [{"type": "html", "html": parser.normalize_html_fragment(text)}],
            }]
        cover = parser.extract_cover(root, fallback_title=title, fallback_subtitle=subtitle)

        show_titles = options.show_header_titles
        if show_titles is None:
            show_titles = bool(title or subtitle)
        theme: Dict[str, Any] = {
            **self.package.theme,
            **options.theme_overrides(),
            "title_line1": title,
            "title_line2": subtitle,
            "show_header_titles": bool(show_titles),
            "header_title_align": options.header_align,
            "header_subtitle_align": options.header_align,
            "show_page_numbers": options.show_page_numbers,
        }
        pages = build_pages(
            sections, theme=theme, cover=cover, numbering=options.section_numbering,
        )
        return {"title": title, "theme": theme, "sections": sections, "pages": pages}

    # ── HTML for WeasyPrint ─────────────────────────────────────────
    def build_html(self, html_content: str, *, source_dir: Optional[Path] = None) -> str:
        """The full HTML WeasyPrint lays out (before the post-layout passes)."""
        payload = self.build_payload(html_content, source_dir=source_dir)
        passes.separate_numbers_from_markers(payload)
        passes.inject_inline_footnotes(payload)
        passes.add_footnote_tracking_ids(payload)

        # Letterhead assets resolve through the package: its own assets
        # first, then the shared ones.
        for page in payload.get("pages") or []:
            for key in ("header_complete_path", "header_banner_path",
                        "header_banner_path_cont", "header_logo_path"):
                value = page.get(key, "")
                if value and not Path(str(value)).is_absolute():
                    try:
                        page[key] = str(self.package.asset(str(value)))
                    except TemplatePackageError as exc:
                        logger.warning("template package %r: %s", self.package.name, exc)

        # Autoescape: titles, labels, letterhead values and table cells are
        # plain text. Only the body blocks, which the parser rebuilt from the
        # HTML tree, are marked safe in the template.
        env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
        html_str = env.get_template(TEMPLATE_NAME).render(
            **payload,
            labels=self.options.labels,
            lang=(self.options.language or "es").split("-")[0],
        )
        if self.options.bind_percent_signs:
            html_str = bind_number_to_percent(html_str)
        return html_str

    def extra_css(self) -> str:
        """CSS appended after ``report.css``: package, options, caller."""
        options = self.options
        parts = [self.package.stylesheet()]
        if options.show_page_numbers:
            content = "counter(page)"
            if options.page_number_label and options.labels.page:
                content = f"{_css_string(options.labels.page + ' ')} counter(page)"
            parts.append(_PAGE_NUMBER_CSS.format(content=content))
        if options.text_align != "justify":
            parts.append(_TEXT_ALIGN_CSS.format(align=options.text_align))
        if options.css:
            parts.append(options.css)
        return "\n".join(p for p in parts if p)

    # ── rendering ───────────────────────────────────────────────────
    def render_document(self, html_content: str, *, source_dir: Optional[Path] = None) -> Any:
        """Lay the document out (passes included); a WeasyPrint ``Document``."""
        document, _info = self._layout(html_content, source_dir=source_dir)
        return document

    def render(
        self,
        html_content: str,
        output_path: Union[str, Path],
        *,
        source_dir: Optional[Path] = None,
    ) -> PdfRenderResult:
        """Render ``html_content`` to ``output_path``."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document, info = self._layout(html_content, source_dir=source_dir)
        document.write_pdf(str(output_path))
        info.output_path = output_path
        logger.info("PDF written to %s (%d pages)", output_path, info.pages)
        return info

    def render_bytes(self, html_content: str, *, source_dir: Optional[Path] = None) -> bytes:
        document, _info = self._layout(html_content, source_dir=source_dir)
        return document.write_pdf()

    def render_file(self, html_path: Union[str, Path], output_path: Union[str, Path]) -> PdfRenderResult:
        """Render an HTML file; relative image paths resolve next to it."""
        html_path = Path(html_path).resolve()
        return self.render(
            html_path.read_text(encoding="utf-8"), output_path, source_dir=html_path.parent,
        )

    def _layout(self, html_content: str, *, source_dir: Optional[Path]) -> "tuple[Any, PdfRenderResult]":
        from weasyprint import CSS, HTML
        from weasyprint.text.fonts import FontConfiguration

        options = self.options
        validate_render_text(html_content, options)
        info = PdfRenderResult(output_path=None, package=self.package.name)
        scan = scan_directives(html_content, target="pdf")
        info.unsupported_directives = list(scan.unsupported)
        log_unsupported(scan, renderer="pdf")

        html_str = self.build_html(html_content, source_dir=source_dir)
        base_url = str(source_dir or TEMPLATE_DIR)

        # Every resource WeasyPrint loads (images, CSS url(), @font-face)
        # goes through the policy: data: URIs and files inside the allowed
        # roots only, unless the options opt in to more.
        fetcher = self.resource_policy(source_dir).url_fetcher()

        with isolated_fontconfig(self.package.font_dirs(), enabled=options.isolate_fonts):
            # Without a FontConfiguration WeasyPrint ignores every @font-face.
            font_config = FontConfiguration()
            stylesheets = [CSS(filename=str(STYLESHEET), font_config=font_config, url_fetcher=fetcher)]
            extra = self.extra_css()
            if extra:
                # url() in a package stylesheet resolves inside the package.
                stylesheets.append(CSS(
                    string=extra, font_config=font_config,
                    base_url=str(self.package.root) + "/", url_fetcher=fetcher,
                ))

            def render(markup: str) -> Any:
                return HTML(string=markup, base_url=base_url, url_fetcher=fetcher).render(
                    stylesheets=stylesheets, font_config=font_config,
                )

            if options.fill_figure_gaps:
                html_str = passes.fill_figure_gaps(
                    html_str, render, figure_label=options.labels.figure,
                )
            if options.relax_lonely_breaks:
                html_str = passes.relax_lonely_breaks(html_str, render)

            document = render(html_str)
            if options.fix_footnote_pages:
                # At most ``max_footnote_passes`` layouts: each pass measures
                # the current one and, when a note can be pulled back to its
                # marker's page, adjusts the HTML for the next.
                limit = max(1, options.max_footnote_passes)
                for pass_num in range(1, limit + 1):
                    info.footnote_passes = pass_num
                    mismatches = passes.detect_footnote_mismatches(document)
                    fixable = [m for m in mismatches if m[3] >= passes.FOOTNOTE_FIX_MIN_PAGE_FRACTION]
                    if not fixable or pass_num == limit:
                        break
                    logger.info(
                        "pass %d: %d footnote(s) on a later page than their marker, correcting",
                        pass_num, len(fixable),
                    )
                    fixed = passes.fix_footnote_mismatches(html_str, mismatches)
                    if fixed == html_str:
                        break
                    html_str = fixed
                    document = render(html_str)
                info.footnote_mismatches = [m[0] for m in passes.detect_footnote_mismatches(document)]
                if info.footnote_mismatches:
                    logger.info(
                        "footnotes on a later page than their marker: %s",
                        ", ".join(info.footnote_mismatches),
                    )
        info.pages = len(document.pages)
        return document, info


def render_html(
    html_content: str,
    output_path: Union[str, Path],
    *,
    options: Optional[RenderOptions] = None,
    package: Union[str, TemplatePackage, None] = None,
    registry: Optional[PackageRegistry] = None,
    source_dir: Optional[Path] = None,
) -> PdfRenderResult:
    """One-call form of :meth:`HtmlRenderer.render`."""
    return HtmlRenderer(package, options, registry=registry).render(
        html_content, output_path, source_dir=source_dir,
    )


__all__ = ["HtmlRenderer", "PdfRenderResult", "STYLESHEET", "TEMPLATE_DIR", "render_html"]
