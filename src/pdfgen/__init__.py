"""PDF generation package."""

from pdfgen.render import render_pdf, build_sample_data
from pdfgen.pagination import LayoutConfig, Paginator

__all__ = ["render_pdf", "build_sample_data", "LayoutConfig", "Paginator"]
