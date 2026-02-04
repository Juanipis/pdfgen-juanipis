"""PDF generation package."""

from pdfgen_juanipis.render import render_pdf, build_sample_data
from pdfgen_juanipis.validator import validate_and_normalize
from pdfgen_juanipis.pagination import LayoutConfig, Paginator
from pdfgen_juanipis.api import PDFGen, PDFGenConfig, render_with_defaults, render_with_defaults_bytes

__all__ = [
    "render_pdf",
    "build_sample_data",
    "validate_and_normalize",
    "LayoutConfig",
    "Paginator",
    "PDFGen",
    "PDFGenConfig",
    "render_with_defaults",
    "render_with_defaults_bytes",
]
