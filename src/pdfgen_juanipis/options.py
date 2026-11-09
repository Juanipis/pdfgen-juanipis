"""Presentation options shared by every exporter.

One :class:`RenderOptions` object reaches the PDF renderer AND the Word
exporter, so the two formats of the same document can never be produced
with different settings. Every word the library itself prints lives in
:class:`Labels`, with Spanish defaults, so nothing user-visible is
hard-coded.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional, Sequence, Union

TextAlign = Literal["justify", "left", "right", "center"]
SectionNumbering = Literal["roman", "none"]

VALID_TEXT_ALIGNS: frozenset = frozenset({"justify", "left", "right", "center"})
VALID_SECTION_NUMBERING: frozenset = frozenset({"roman", "none"})


@dataclass(frozen=True)
class Labels:
    """Every word the renderers print or read on their own.

    The document's prose, captions and table names come from the HTML;
    these are the few words the library has to supply itself.
    """

    #: Word a figure caption starts with («Figura 3.»). Read when a
    #: caption carries no ``.figure-title`` span, and used in the Word
    #: placeholder for an image that could not be embedded.
    figure: str = "Figura"
    #: Prefix of the printed page number when
    #: :attr:`RenderOptions.page_number_label` is on («Página 3»).
    page: str = "Página"
    #: Prefix of the phone number in the letterhead's contact block.
    phone: str = "Cel:"
    #: Title given to a section whose HTML carries no heading.
    untitled_section: str = "Contenido"
    #: Header cell over a table's first column when the HTML gives none.
    first_column_header: str = ""
    #: ``alt`` text of the letterhead band image.
    header_image_alt: str = "Encabezado"
    #: Word paragraph printed where a chart could not be embedded.
    #: ``{figure}``, ``{alt}`` and ``{reason}`` are substituted.
    figure_omitted: str = "[{figure} — {alt} omitida: {reason}]"
    #: Reason used in :attr:`figure_omitted` when no SVG rasterizer exists.
    no_svg_rasterizer: str = "rsvg-convert no disponible"


@dataclass(frozen=True)
class RenderOptions:
    """Presentation options for one document, shared by PDF and DOCX."""

    title: Optional[str] = None
    subtitle: Optional[str] = None
    #: Override the template package's contact block (site and phone).
    footer_site: Optional[str] = None
    footer_phone: Optional[str] = None
    #: Any other template-package theme value to override for this render
    #: (``footer_address``, ``footer_email``, ``footer_city`` ...).
    theme: Mapping[str, Any] = field(default_factory=dict)
    #: Print the page number in the bottom-right page margin.
    show_page_numbers: bool = False
    #: Print «Página N» instead of the bare number (see :class:`Labels`).
    page_number_label: bool = False
    #: Body-text alignment.
    text_align: TextAlign = "justify"
    #: ``"roman"`` numbers top-level sections «I.», «II.» ... by position
    #: (any hand-written numeral is dropped); ``"none"`` leaves titles as
    #: written.
    section_numbering: SectionNumbering = "roman"
    #: Alignment of the document title/subtitle printed above the body.
    header_align: Literal["left", "center", "right"] = "center"
    #: Show the title/subtitle above the body. ``None`` = when there is one.
    show_header_titles: Optional[bool] = None
    #: Name of the template package (letterhead) to print with. ``None``
    #: = the registry's default.
    template_package: Optional[str] = None
    #: BCP 47 language tag of the document. Drives the ``lang`` attribute
    #: and the foreign-script guard.
    language: str = "es-CO"
    #: Refuse to render text with characters from an unexpected script.
    validate_text: bool = True
    #: Tallest a figure may print, in points. ``None`` keeps the layout
    #: heuristics' own caps.
    figure_max_height_pt: Optional[int] = None
    #: Raw figure-sizing heuristics (see ``pdf.visual_layout``).
    visual_layout: Optional[Mapping[str, Any]] = None
    #: Lift ``<p class="footnote">`` into native Word footnotes (DOCX only;
    #: the PDF always uses the CSS footnote area).
    native_footnotes: bool = True
    #: Post-layout passes of the PDF renderer.
    fill_figure_gaps: bool = True
    relax_lonely_breaks: bool = True
    fix_footnote_pages: bool = True
    max_footnote_passes: int = 4
    #: Join a number to its percent sign with a no-break space.
    bind_percent_signs: bool = True
    #: Fold en/em dashes and the minus sign to ASCII ``-`` in the PDF.
    ascii_dashes: bool = False
    #: Point fontconfig at the bundled and package fonts only, so the
    #: output does not depend on the fonts installed on the machine.
    isolate_fonts: bool = True
    #: Extra CSS appended after every other stylesheet (PDF only).
    css: Optional[str] = None
    #: Resource policy (see ``pdfgen_juanipis.security``). By default a
    #: render reads only data: URIs and files inside the document's
    #: ``source_dir``, the library and the template package. Extra local
    #: directories it may read:
    allowed_roots: Sequence[Union[str, Path]] = ()
    #: Read ANY local file an image / url() names (trusted input only).
    allow_absolute_paths: bool = False
    #: Fetch http(s) resources (trusted input only: server-side request
    #: forgery risk in a rendering service).
    allow_network: bool = False
    labels: Labels = field(default_factory=Labels)

    def __post_init__(self) -> None:
        align = str(self.text_align or "justify").strip().lower()
        if align not in VALID_TEXT_ALIGNS:
            align = "justify"
        object.__setattr__(self, "text_align", align)
        numbering = str(self.section_numbering or "roman").strip().lower()
        if numbering not in VALID_SECTION_NUMBERING:
            raise ValueError(
                f"section_numbering must be one of {sorted(VALID_SECTION_NUMBERING)}, "
                f"got {self.section_numbering!r}"
            )
        object.__setattr__(self, "section_numbering", numbering)
        object.__setattr__(self, "theme", dict(self.theme or {}))
        object.__setattr__(self, "allowed_roots", tuple(Path(p) for p in (self.allowed_roots or ())))

    def merged(self, **overrides: Any) -> "RenderOptions":
        """A copy with ``overrides`` applied (``None`` values ignored)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean) if clean else self

    def theme_overrides(self) -> Dict[str, Any]:
        """Theme values this render imposes over the template package."""
        out = dict(self.theme)
        if self.footer_site:
            out["footer_site"] = self.footer_site
        if self.footer_phone:
            out["footer_phone"] = self.footer_phone
        return out

    def resolved_visual_layout(self) -> Optional[Dict[str, Any]]:
        """Figure-sizing config with :attr:`figure_max_height_pt` applied.

        A declared cap applies to every container, so "no figure taller
        than N" means exactly that however the figure is laid out.
        """
        raw: Optional[Dict[str, Any]] = (
            dict(self.visual_layout) if self.visual_layout else None
        )
        if self.figure_max_height_pt:
            cap = int(self.figure_max_height_pt)
            raw = dict(raw or {})
            raw["max_height_pt"] = cap
            raw["layout_max_height_pt"] = {
                "full": cap, "column": cap, "left": cap, "right": cap,
            }
        return raw


__all__ = [
    "Labels",
    "RenderOptions",
    "SectionNumbering",
    "TextAlign",
    "VALID_SECTION_NUMBERING",
    "VALID_TEXT_ALIGNS",
]
