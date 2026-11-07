"""Backwards-compatible alias of :mod:`pdfgen_juanipis.legacy.validator` (0.1 API).

``import pdfgen_juanipis.validator`` returns the very same module object, so
private helpers and monkeypatching keep working.
"""

import sys as _sys

from pdfgen_juanipis.legacy import validator as _module

_sys.modules[__name__] = _module
