"""Backwards-compatible alias of :mod:`pdfgen_juanipis.legacy.api` (0.1 API).

``import pdfgen_juanipis.api`` returns the very same module object, so
private helpers and monkeypatching keep working.
"""

import sys as _sys

from pdfgen_juanipis.legacy import api as _module

_sys.modules[__name__] = _module
