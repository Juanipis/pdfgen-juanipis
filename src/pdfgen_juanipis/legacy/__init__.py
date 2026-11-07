"""The 0.1 structured-data API, kept so existing users do not break.

Everything that was importable from ``pdfgen_juanipis`` in 0.1 still is
(``render_pdf``, ``PDFGen``, ``Paginator`` ...), and the old module paths
(``pdfgen_juanipis.render``, ``.api``, ``.pagination``, ``.validator``)
alias the modules of this package. New code should render HTML with
:class:`pdfgen_juanipis.HtmlRenderer`.
"""

from pdfgen_juanipis.legacy.api import PDFGen, PDFGenConfig, render_with_defaults, render_with_defaults_bytes
from pdfgen_juanipis.legacy.pagination import LayoutConfig, Paginator
from pdfgen_juanipis.legacy.render import build_sample_data, render_pdf
from pdfgen_juanipis.legacy.validator import validate_and_normalize

__all__ = [
    "LayoutConfig",
    "PDFGen",
    "PDFGenConfig",
    "Paginator",
    "build_sample_data",
    "render_pdf",
    "render_with_defaults",
    "render_with_defaults_bytes",
    "validate_and_normalize",
]
