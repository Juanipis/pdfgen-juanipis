"""Render contract: the closed set of structural directives an input HTML
may carry, and how each exporter implements them.

Two exporters read the SAME HTML: the PDF renderer (WeasyPrint, which
interprets ``templates/report.css``) and the Word exporter (a walker that
emits OOXML and does not interpret CSS). Anything that lives only in the
stylesheet therefore exists only in the PDF. This module makes the
coupling explicit:

1. :data:`RENDER_DIRECTIVES` lists every ``data-*`` attribute / class with
   structural meaning, with its implementation on *each* side. A
   directive with no implementation in both renderers should not be
   emitted by a producer that wants PDF/Word parity.
2. :func:`scan_directives` reports what an HTML string actually carries,
   so an unmapped directive surfaces as a warning instead of in a review.
3. Shared helpers (section numbering, page-break / keep-with-next
   readers, body-table column widths) give both exporters one answer.

Consumers may register their own attributes with :func:`register_directive`
(for instance markers their own pipeline reads), so the scan stops
reporting them as unknown.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from lxml import html as lxml_html

from pdfgen_juanipis.options import VALID_TEXT_ALIGNS, RenderOptions
from pdfgen_juanipis.text import find_foreign_script_runs

logger = logging.getLogger("pdfgen_juanipis.contract")


# ────────────────────────── text guard ───────────────────────────────────


class RenderTextError(ValueError):
    """The input text carries characters the document cannot print."""


def validate_render_text(html: str, options: Optional[RenderOptions] = None) -> None:
    """Refuse script corruption before either exporter can publish it."""
    options = options or RenderOptions()
    if not options.validate_text:
        return
    runs = find_foreign_script_runs(html, options.language)
    if runs:
        raise RenderTextError(
            "Render blocked: unexpected-script text: "
            + "; ".join(str(run["context"]) for run in runs[:5])
        )


# ────────────────────────── page geometry ────────────────────────────────

#: The page the stylesheet declares (``@page { size: Letter; margin: … }``)
#: and the width left between its side margins. One owner: the tests read
#: the stylesheet to check these still describe it.
PAGE_WIDTH_PT = 612.0
PAGE_SIDE_MARGIN_PT = 85.0
TEXT_WIDTH_PT = PAGE_WIDTH_PT - 2 * PAGE_SIDE_MARGIN_PT


def body_table_widths(rows: List[List[str]]) -> List[float]:
    """Share of the printable width per column, used by Word and PDF alike.

    Square-root weighting gives prose room without letting one long cell
    squeeze the numeric columns to nothing.
    """
    count = max((len(row) for row in rows), default=0)
    weights = [
        math.sqrt(max(12, min(360, max(
            (len(str(row[i])) for row in rows if i < len(row)), default=0,
        )))) for i in range(count)
    ]
    total = sum(weights)
    return [w / total for w in weights] if total else []


# ────────────────────────── document headings ────────────────────────────

#: Classes marking the document's own title / subtitle. They are printed
#: above the body and never open a numbered section.
DOCUMENT_TITLE_CLASSES: Tuple[str, ...] = ("document-title", "bulletin-title")
DOCUMENT_SUBTITLE_CLASSES: Tuple[str, ...] = ("document-subtitle", "bulletin-subtitle")

#: Classes marking a table as BODY prose in a grid (left aligned, may
#: break across pages) rather than a compact data grid.
BODY_TABLE_CLASSES: Tuple[str, ...] = ("body-table", "tabla-cuerpo")


def is_document_heading(elem: Any) -> bool:
    classes = element_classes(elem)
    return any(c in classes for c in DOCUMENT_TITLE_CLASSES + DOCUMENT_SUBTITLE_CLASSES)


def is_document_subtitle(elem: Any) -> bool:
    classes = element_classes(elem)
    return any(c in classes for c in DOCUMENT_SUBTITLE_CLASSES)


def is_body_table(elem: Any) -> bool:
    classes = element_classes(elem)
    return any(c in classes for c in BODY_TABLE_CLASSES)


# ────────────────────────── directive registry ───────────────────────────

DirectiveKind = Literal["attribute", "class", "inline-style", "placeholder"]


@dataclass(frozen=True)
class RenderDirective:
    """One structural directive of the HTML → PDF/DOCX contract.

    ``pdf`` / ``docx`` describe the implementation on each side; ``None``
    means *not implemented* on that side.
    """

    key: str
    kind: DirectiveKind
    applies_to: str
    semantics: str
    pdf: Optional[str]
    docx: Optional[str]
    #: Part of the stable contract producers are expected to emit.
    emitted: bool = False
    #: Accepted values for attribute directives ("" = presence is enough).
    values: Tuple[str, ...] = ()

    @property
    def supported(self) -> bool:
        return bool(self.pdf) and bool(self.docx)


#: Attribute prefix stamped by the PDF pipeline itself (measurement and
#: layout hints). Never authored, never reported.
INTERNAL_ATTR_PREFIX = "data-pdf-"

_BUILTIN_DIRECTIVES: Tuple[RenderDirective, ...] = (
    RenderDirective(
        key="data-page-break",
        kind="attribute",
        applies_to="block elements (headings, paragraphs, figures, tables)",
        semantics="Start the block on a fresh page.",
        pdf="`break-before: page` (report.css); on a section heading the "
            "section title carries it",
        docx="`Document.add_page_break()` before the block",
        emitted=True,
        values=("before",),
    ),
    RenderDirective(
        key="data-keep-with-next",
        kind="attribute",
        applies_to="block elements (typically headings and captions)",
        semantics="Do not separate this block from the one that follows.",
        pdf="`break-after: avoid` (report.css)",
        docx="`paragraph_format.keep_with_next = True`",
        emitted=True,
        values=("", "true"),
    ),
    RenderDirective(
        key="data-color",
        kind="attribute",
        applies_to="<mark>",
        semantics="Highlight colour of a marked run (what a rich-text editor "
                  "writes for a highlight; the colour also travels as an "
                  "inline `background-color`).",
        pdf="the mark's inline `background-color` (report.css draws <mark>)",
        docx="run shading `w:shd w:fill` with the same colour",
        emitted=False,
    ),
    RenderDirective(
        key="footnote",
        kind="class",
        applies_to="<p>",
        semantics="Footnote definition; its leading <sup>N</sup> matches an "
                  "inline marker.",
        pdf="printed in the CSS footnote area of the marker's page",
        docx="lifted into `word/footnotes.xml` as a native Word footnote",
        emitted=True,
    ),
    RenderDirective(
        key="figure-full",
        kind="class",
        applies_to="<figure>",
        semantics="Figure spanning the full text column.",
        pdf="`width: 100%`, kept whole",
        docx="picture at the full body width",
        emitted=True,
    ),
    RenderDirective(
        key="figure-column",
        kind="class",
        applies_to="<figure>",
        semantics="Figure spanning the full text column (alias of figure-full).",
        pdf="`width: 100%`, kept whole",
        docx="picture at the full body width",
    ),
    RenderDirective(
        key="figure-left",
        kind="class",
        applies_to="<figure>",
        semantics="Narrow figure (78% of the text column).",
        pdf="`width: 78%`",
        docx="picture at 78% of the body width",
    ),
    RenderDirective(
        key="figure-right",
        kind="class",
        applies_to="<figure>",
        semantics="Narrow figure (78% of the text column).",
        pdf="`width: 78%`",
        docx="picture at 78% of the body width",
    ),
    RenderDirective(
        key="figure-title",
        kind="class",
        applies_to="<span> inside <figcaption>",
        semantics="The «Figura N.» label of a caption.",
        pdf="semi-bold, darker colour (report.css)",
        docx="bold run inside the caption paragraph",
        emitted=True,
    ),
    RenderDirective(
        key="figure-subcaption",
        kind="class",
        applies_to="<span> inside <figcaption>",
        semantics="Methodological sub-caption / source line under a figure.",
        pdf="reduced size + italic, lighter colour (report.css)",
        docx="reduced-size italic run inside the caption paragraph",
        emitted=True,
    ),
    RenderDirective(
        key="section-subtitle",
        kind="class",
        applies_to="<p>",
        semantics="Secondary title under a section heading.",
        pdf="printed as the section's subtitle block",
        docx="centred small paragraph, kept with next",
    ),
    RenderDirective(
        key="chart",
        kind="class",
        applies_to="<div>",
        semantics="Chart container (image + optional title/caption).",
        pdf="kept whole, image height capped by the visual-layout heuristics",
        docx="picture + caption paragraph, same treatment as <figure>",
    ),
    RenderDirective(
        key="table-caption",
        kind="class",
        applies_to="<div> right after a <table>",
        semantics="The table's source line, printed under it.",
        pdf="folded into the table block and printed under the grid",
        docx="caption-styled paragraph under the table",
        emitted=True,
    ),
    RenderDirective(
        key="body-table",
        kind="class",
        applies_to="<table>",
        semantics="A table in the body of a section (prose in a grid) rather "
                  "than a compact data grid: left-aligned cells, column "
                  "widths by content, and it may break across pages.",
        pdf="`variant: body` table block (content-weighted widths, breakable)",
        docx="native Word table with content-weighted column widths",
        emitted=True,
    ),
    RenderDirective(
        key="tabla-cuerpo",
        kind="class",
        applies_to="<table>",
        semantics="Spanish alias of `body-table`.",
        pdf="same as `body-table`",
        docx="same as `body-table`",
    ),
    RenderDirective(
        key="text-align",
        kind="inline-style",
        applies_to="<p>",
        semantics="Per-paragraph alignment override.",
        pdf="honoured natively by WeasyPrint",
        docx="mapped to `WD_ALIGN_PARAGRAPH`",
        emitted=True,
    ),
    RenderDirective(
        key="data-section-type",
        kind="attribute",
        applies_to="<section>",
        semantics="Marks the cover section so the PDF lifts it out of the body.",
        pdf="cover lines printed at the top of the first page",
        docx=None,  # the Word walker would print the cover as body text
        values=("cover",),
    ),
    RenderDirective(
        key="cover-section",
        kind="class",
        applies_to="<section>",
        semantics="Cover section (alias of `data-section-type=cover`).",
        pdf="cover lines printed at the top of the first page",
        docx=None,
    ),
)

#: The live registry: built-ins plus whatever consumers registered.
RENDER_DIRECTIVES: List[RenderDirective] = list(_BUILTIN_DIRECTIVES)
DIRECTIVES_BY_KEY: Dict[str, RenderDirective] = {d.key: d for d in RENDER_DIRECTIVES}


def register_directive(directive: RenderDirective, *, replace: bool = False) -> None:
    """Add a consumer-specific directive (e.g. a ``data-*`` marker its own
    pipeline reads) so :func:`scan_directives` stops reporting it."""
    if directive.key in DIRECTIVES_BY_KEY and not replace:
        raise ValueError(f"directive {directive.key!r} is already registered")
    if directive.key in DIRECTIVES_BY_KEY:
        RENDER_DIRECTIVES[:] = [d for d in RENDER_DIRECTIVES if d.key != directive.key]
    RENDER_DIRECTIVES.append(directive)
    DIRECTIVES_BY_KEY[directive.key] = directive


# ────────────────────────── scanning ─────────────────────────────────────


@dataclass
class DirectiveScan:
    """What an HTML string carries, contract-wise."""

    #: directive key → number of elements carrying it
    counts: Dict[str, int] = field(default_factory=dict)
    #: descriptions of directives with no mapping on the target side(s)
    unsupported: List[str] = field(default_factory=list)


def _iter_elements(html_content: str) -> Iterable[Any]:
    try:
        # huge_tree: inline chart payloads are multi-MB data URLs, and
        # libxml2's default 10 MB cap silently truncates the document.
        tree = lxml_html.fragment_fromstring(
            html_content or "",
            create_parent="div",
            parser=lxml_html.HTMLParser(huge_tree=True),
        )
    except Exception:  # noqa: BLE001 - malformed HTML is the caller's problem
        return ()
    return tree.iter()


def scan_directives(html_content: str, *, target: str = "both") -> DirectiveScan:
    """Inventory the contract directives present in ``html_content``.

    ``target`` selects which side must implement a directive for it to
    count as supported: ``"pdf"``, ``"docx"`` or ``"both"``.
    """
    scan = DirectiveScan()
    unsupported: Dict[str, str] = {}

    def _bump(key: str) -> None:
        scan.counts[key] = scan.counts.get(key, 0) + 1

    def _check(directive: RenderDirective, detail: str) -> None:
        if target == "pdf":
            ok = bool(directive.pdf)
        elif target == "docx":
            ok = bool(directive.docx)
        else:
            ok = directive.supported
        if not ok:
            unsupported.setdefault(directive.key, detail)

    for elem in _iter_elements(html_content):
        tag = getattr(elem, "tag", None)
        if not isinstance(tag, str):
            continue
        for name, value in (getattr(elem, "attrib", {}) or {}).items():
            lname = str(name).lower()
            if lname == "class":
                for cls in str(value).split():
                    directive = DIRECTIVES_BY_KEY.get(cls)
                    if directive is None or directive.kind != "class":
                        continue  # cosmetic class, not part of the contract
                    _bump(directive.key)
                    _check(directive, f"class='{cls}' on <{tag}> — {directive.semantics}")
                continue
            if lname == "style":
                if re.search(r"(?i)\btext-align\s*:", str(value)):
                    directive = DIRECTIVES_BY_KEY["text-align"]
                    _bump(directive.key)
                    _check(directive, f"inline text-align on <{tag}>")
                continue
            if not lname.startswith("data-") or lname.startswith(INTERNAL_ATTR_PREFIX):
                continue
            directive = DIRECTIVES_BY_KEY.get(lname)
            if directive is None:
                unsupported.setdefault(
                    lname,
                    f"{lname}='{value}' on <{tag}> — not in the render contract",
                )
                continue
            _bump(directive.key)
            accepted = {v for v in directive.values if v}
            if accepted and str(value).strip().lower() not in accepted:
                unsupported.setdefault(
                    f"{lname}={value}",
                    f"{lname}='{value}' on <{tag}> — unknown value; accepted: "
                    f"{', '.join(sorted(accepted))}",
                )
                continue
            _check(directive, f"{lname}='{value}' on <{tag}> — {directive.semantics}")

    scan.unsupported = [unsupported[k] for k in sorted(unsupported)]
    return scan


def log_unsupported(scan: DirectiveScan, *, renderer: str) -> None:
    """One WARNING per unmapped directive, so the gap shows in the log."""
    for detail in scan.unsupported:
        logger.warning("%s: unsupported render directive — %s", renderer, detail)


# ────────────────────────── section numbering ────────────────────────────
#
# Numbering is presentation, so the POSITION always wins: honouring
# hand-written numerals next to auto-numbered sections produces
# incoherent sequences («I.», «I.», «VII.»). Both exporters strip any
# leading numeral and print the counter, so they show the same sequence.

_ROMAN_PREFIX_RE = re.compile(r"^\s*[IVXLCDM]+\.\s*(.+)$", re.IGNORECASE | re.DOTALL)

_ROMAN_NUMERALS: Tuple[Tuple[int, str], ...] = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def to_roman(value: int) -> str:
    """Roman numeral for a 1-based section number."""
    n = max(1, int(value or 1))
    out: List[str] = []
    for arabic, roman in _ROMAN_NUMERALS:
        while n >= arabic:
            out.append(roman)
            n -= arabic
    return "".join(out)


def strip_leading_numeral(title: str) -> str:
    """Remove a hand-written ``"IV. "`` prefix from a section title."""
    raw = (title or "").strip()
    match = _ROMAN_PREFIX_RE.match(raw)
    return match.group(1).strip() if match else raw


def format_section_title(title: str, section_number: int) -> str:
    """``("Introducción", 1)`` → ``"I. Introducción"``."""
    return f"{to_roman(section_number)}. {strip_leading_numeral(title)}"


# ────────────────────────── element helpers ──────────────────────────────


def wants_page_break_before(elem: Any) -> bool:
    """True when the element declares ``data-page-break="before"``."""
    try:
        value = elem.get("data-page-break")
    except AttributeError:  # pragma: no cover - non-element nodes
        return False
    return str(value or "").strip().lower() == "before"


def wants_keep_with_next(elem: Any) -> bool:
    """True when the element declares ``data-keep-with-next`` (presence is
    enough; an explicit ``"false"``/``"0"``/``"no"`` opts out)."""
    try:
        if "data-keep-with-next" not in (elem.attrib or {}):
            return False
        value = str(elem.get("data-keep-with-next") or "").strip().lower()
    except AttributeError:  # pragma: no cover - non-element nodes
        return False
    return value not in ("false", "0", "no")


def inline_text_align(elem: Any) -> Optional[str]:
    """The inline ``style="text-align:…"`` value, when valid."""
    try:
        style = str(elem.get("style") or "")
    except AttributeError:  # pragma: no cover - non-element nodes
        return None
    match = re.search(r"(?i)\btext-align\s*:\s*([a-z]+)", style)
    if not match:
        return None
    value = match.group(1).lower()
    return value if value in VALID_TEXT_ALIGNS else None


def element_classes(elem: Any) -> List[str]:
    try:
        return [c for c in str(elem.get("class") or "").split() if c]
    except AttributeError:  # pragma: no cover - non-element nodes
        return []


__all__ = [
    "BODY_TABLE_CLASSES",
    "DIRECTIVES_BY_KEY",
    "DOCUMENT_SUBTITLE_CLASSES",
    "DOCUMENT_TITLE_CLASSES",
    "DirectiveScan",
    "INTERNAL_ATTR_PREFIX",
    "PAGE_SIDE_MARGIN_PT",
    "PAGE_WIDTH_PT",
    "RENDER_DIRECTIVES",
    "RenderDirective",
    "RenderTextError",
    "TEXT_WIDTH_PT",
    "body_table_widths",
    "element_classes",
    "format_section_title",
    "inline_text_align",
    "is_body_table",
    "is_document_heading",
    "is_document_subtitle",
    "log_unsupported",
    "register_directive",
    "scan_directives",
    "strip_leading_numeral",
    "to_roman",
    "validate_render_text",
    "wants_keep_with_next",
    "wants_page_break_before",
]
