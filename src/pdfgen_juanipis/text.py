"""Text-level guards and typography helpers shared by every exporter.

Nothing here knows what a document is about: the checks look at code
points and at the shape of numbers, never at words.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Dict, List, Optional

# ── Foreign-script contamination ──────────────────────────────────────
# A text generator occasionally emits a run of characters from an
# unrelated script in the middle of a word. The bundled fonts have no
# glyphs for it, so it prints as boxes: unreadable and silently wrong.
# For a document written in a Latin-script language, anything outside
# Latin plus the punctuation and symbol blocks prose legitimately uses is
# flagged. Only code-point ranges are inspected, never words.
_LATIN_SCRIPT_LANGS = (
    "es", "en", "pt", "it", "fr", "de", "nl", "ca", "gl", "eu",
    "da", "sv", "no", "fi", "is", "pl", "cs", "sk", "sl", "hr",
    "hu", "ro", "tr", "et", "lv", "lt", "id", "ms", "vi", "sw",
)

_ALLOWED_TEXT_RANGES = (
    "\u0020-\u024F"    # ASCII + Latin-1 + Latin Extended-A/B
    "\u02B0-\u02FF"    # spacing modifier letters
    "\u0300-\u036F"    # combining diacritics
    "\u1E00-\u1EFF"    # Latin Extended Additional
    "\u2000-\u206F"    # general punctuation (dashes, curly quotes, ...)
    "\u20A0-\u20CF"    # currency symbols
    "\u2100-\u214F"    # letterlike symbols
    "\u2190-\u21FF"    # arrows
    "\u2200-\u22FF"    # math operators
    "\u25A0-\u25FF"    # geometric shapes (bullets)
    "\u2600-\u27BF"    # misc symbols / dingbats
    "\uFE0E-\uFE0F"    # variation selectors
    "\u200B-\u200D"    # zero-width space / joiners
    "\t\n\r"
)
_DISALLOWED_RUN_RE = re.compile(f"[^{_ALLOWED_TEXT_RANGES}]+")


def uses_latin_script(language: Optional[str]) -> bool:
    """Whether ``language`` (a BCP 47 tag) is normally written in Latin script."""
    primary = str(language or "").split("-")[0].strip().lower()
    return primary in _LATIN_SCRIPT_LANGS


def find_foreign_script_runs(
    html: str,
    language: Optional[str],
    *,
    context_chars: int = 24,
) -> List[Dict[str, str]]:
    """Locate runs of unexpected-script characters in ``html``'s text.

    Returns one entry per run: ``{"text", "codepoints", "context"}``. Tag
    markup and attribute values are skipped (a data URL is not prose).
    Returns ``[]`` for languages not written in Latin script, where the
    premise does not hold.
    """
    if not html or not uses_latin_script(language):
        return []
    out: List[Dict[str, str]] = []
    for chunk in re.split(r"<[^>]+>", html):
        chunk = unescape(chunk)
        if not chunk:
            continue
        for match in _DISALLOWED_RUN_RE.finditer(chunk):
            run = match.group(0)
            if not run.strip():
                continue
            start = max(0, match.start() - context_chars)
            end = min(len(chunk), match.end() + context_chars)
            out.append({
                "text": run,
                "codepoints": " ".join(f"U+{ord(c):04X}" for c in run),
                "context": chunk[start:end],
            })
    return out


#: A number, the space some locales put before the percent sign, and the
#: sign. Only in text: the lookahead refuses a match inside a tag.
_NUMBER_BEFORE_PERCENT_RE = re.compile(r"(\d) %(?![^<>]*>)")


def bind_number_to_percent(html: str) -> str:
    """Join every number to its percent sign with a no-break space.

    «5,4 %» is one quantity: WeasyPrint will otherwise happily break it
    across a line, or even a page, leaving the sign stranded.
    """
    if not html:
        return html
    return _NUMBER_BEFORE_PERCENT_RE.sub("\\1\u00a0%", html)


#: Dash-like characters folded to ASCII by ``RenderOptions.ascii_dashes``.
ASCII_DASHES = str.maketrans(
    {c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2212"}
)


__all__ = [
    "ASCII_DASHES",
    "bind_number_to_percent",
    "find_foreign_script_runs",
    "uses_latin_script",
]
