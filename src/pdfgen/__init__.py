"""PDF generation package."""

from pdfgen.render import render_pdf, build_sample_data
from pdfgen.validator import validate_and_normalize
from pdfgen.pagination import LayoutConfig, Paginator
from pdfgen.api import PDFGen, PDFGenConfig, render_with_defaults

__all__ = [
    "render_pdf",
    "build_sample_data",
    "validate_and_normalize",
    "LayoutConfig",
    "Paginator",
    "PDFGen",
    "PDFGenConfig",
    "render_with_defaults",
]
