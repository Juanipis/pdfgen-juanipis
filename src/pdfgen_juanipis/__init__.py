"""pdfgen-juanipis — editable HTML to paginated PDF (and Word), on WeasyPrint.

HTML-first API (0.2)::

    from pdfgen_juanipis import HtmlRenderer, RenderOptions

    HtmlRenderer(package="plain", options=RenderOptions(title="Report")).render(html, "out.pdf")

The 0.1 structured-data API (``render_pdf``, ``PDFGen``, ``Paginator`` ...)
lives in :mod:`pdfgen_juanipis.legacy` and stays importable from here.

Names are loaded lazily, so ``import pdfgen_juanipis`` does not load
WeasyPrint (or python-docx) until a renderer is actually used.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.2.0"

_EXPORTS = {
    # HTML-first API
    "HtmlRenderer": "pdfgen_juanipis.pdf.renderer",
    "PdfRenderResult": "pdfgen_juanipis.pdf.renderer",
    "render_html": "pdfgen_juanipis.pdf.renderer",
    "DocxRenderer": "pdfgen_juanipis.docx_export",
    "DocxRenderResult": "pdfgen_juanipis.docx_export",
    "render_docx": "pdfgen_juanipis.docx_export",
    "render_formats": "pdfgen_juanipis.formats",
    "RenderResult": "pdfgen_juanipis.formats",
    "SUPPORTED_FORMATS": "pdfgen_juanipis.formats",
    "RenderOptions": "pdfgen_juanipis.options",
    "Labels": "pdfgen_juanipis.options",
    "TemplatePackage": "pdfgen_juanipis.packages",
    "TemplatePackageError": "pdfgen_juanipis.packages",
    "PackageRegistry": "pdfgen_juanipis.packages",
    "default_registry": "pdfgen_juanipis.packages",
    "register_template_packages": "pdfgen_juanipis.packages",
    "resolve_template_package": "pdfgen_juanipis.packages",
    "available_template_packages": "pdfgen_juanipis.packages",
    "describe_template_packages": "pdfgen_juanipis.packages",
    "RenderDirective": "pdfgen_juanipis.contract",
    "RenderTextError": "pdfgen_juanipis.contract",
    "register_directive": "pdfgen_juanipis.contract",
    "scan_directives": "pdfgen_juanipis.contract",
    "validate_render_text": "pdfgen_juanipis.contract",
    # Legacy 0.1 API
    "render_pdf": "pdfgen_juanipis.legacy.render",
    "build_sample_data": "pdfgen_juanipis.legacy.render",
    "validate_and_normalize": "pdfgen_juanipis.legacy.validator",
    "LayoutConfig": "pdfgen_juanipis.legacy.pagination",
    "Paginator": "pdfgen_juanipis.legacy.pagination",
    "PDFGen": "pdfgen_juanipis.legacy.api",
    "PDFGenConfig": "pdfgen_juanipis.legacy.api",
    "render_with_defaults": "pdfgen_juanipis.legacy.api",
    "render_with_defaults_bytes": "pdfgen_juanipis.legacy.api",
}

__all__ = sorted(_EXPORTS) + ["__version__"]


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'pdfgen_juanipis' has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list:
    return sorted(set(globals()) | set(_EXPORTS))
