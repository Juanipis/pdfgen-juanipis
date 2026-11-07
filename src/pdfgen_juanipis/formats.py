"""One HTML, several formats, ONE options object.

:func:`render_formats` fans a single :class:`~pdfgen_juanipis.RenderOptions`
out to every requested exporter, so a document can no longer be rendered
to PDF with settings the Word export never saw.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from pdfgen_juanipis.contract import log_unsupported, scan_directives, validate_render_text
from pdfgen_juanipis.options import RenderOptions
from pdfgen_juanipis.packages import PackageRegistry, TemplatePackage

logger = logging.getLogger("pdfgen_juanipis")

#: Formats :func:`render_formats` knows how to produce.
SUPPORTED_FORMATS: Tuple[str, ...] = ("pdf", "docx")


@dataclass
class RenderResult:
    """Outcome of one :func:`render_formats` call."""

    #: format → written path (absent when that format failed)
    paths: Dict[str, Path] = field(default_factory=dict)
    pdf: Optional[Any] = None
    docx: Optional[Any] = None
    #: format → exception, for formats that failed
    errors: Dict[str, Exception] = field(default_factory=dict)
    #: Directives the HTML carries that one of the exporters cannot map.
    unsupported_directives: List[str] = field(default_factory=list)

    @property
    def pdf_path(self) -> Optional[Path]:
        return self.paths.get("pdf")

    @property
    def docx_path(self) -> Optional[Path]:
        return self.paths.get("docx")


def render_formats(
    html_content: str,
    options: Optional[RenderOptions] = None,
    *,
    package: Union[str, TemplatePackage, None] = None,
    registry: Optional[PackageRegistry] = None,
    output_dir: Union[str, Path, None] = None,
    basename: str = "document",
    formats: Sequence[str] = SUPPORTED_FORMATS,
    output_paths: Optional[Mapping[str, Union[str, Path]]] = None,
    source_dir: Optional[Path] = None,
    strict: bool = False,
) -> RenderResult:
    """Render one HTML to every requested format.

    ``output_dir``/``basename`` give ``<basename>.pdf`` / ``.docx``;
    ``output_paths`` names a destination per format instead. With
    ``strict=False`` (the default) a failing format is collected in
    ``errors`` so it cannot sink its sibling.
    """
    options = options or RenderOptions()
    validate_render_text(html_content, options)
    unknown = [f for f in formats if f not in SUPPORTED_FORMATS]
    if unknown:
        raise ValueError(
            f"unsupported render format(s): {', '.join(unknown)}; expected any of "
            f"{', '.join(SUPPORTED_FORMATS)}"
        )
    paths = {k: Path(v) for k, v in (output_paths or {}).items()}

    def _target(fmt: str) -> Path:
        if fmt in paths:
            return paths[fmt]
        if output_dir is None:
            raise ValueError(f"no destination for format {fmt!r}: pass output_dir or output_paths")
        return Path(output_dir) / f"{basename}.{fmt}"

    result = RenderResult()
    # One contract audit for the whole render: a directive missing on
    # either side is a parity gap.
    scan = scan_directives(html_content, target="both")
    result.unsupported_directives = list(scan.unsupported)
    log_unsupported(scan, renderer="render_formats")

    for fmt in formats:
        try:
            if fmt == "pdf":
                from pdfgen_juanipis.pdf.renderer import HtmlRenderer

                outcome = HtmlRenderer(package, options, registry=registry).render(
                    html_content, _target("pdf"), source_dir=source_dir,
                )
                result.pdf = outcome
                result.paths["pdf"] = outcome.output_path
            elif fmt == "docx":
                from pdfgen_juanipis.docx_export import DocxRenderer

                outcome = DocxRenderer(package, options, registry=registry).render(
                    html_content, _target("docx"),
                )
                result.docx = outcome
                result.paths["docx"] = outcome.output_path
        except Exception as exc:  # noqa: BLE001 - one format must not sink the other
            if strict:
                raise
            logger.warning("%s rendering failed: %s", fmt.upper(), exc)
            result.errors[fmt] = exc
    return result


__all__ = ["RenderResult", "SUPPORTED_FORMATS", "render_formats"]
