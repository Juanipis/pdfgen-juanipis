"""What a render may read: the resource policy behind every image, stylesheet
and font the PDF loads.

The HTML a renderer receives is often generated or user-edited, so it is
untrusted input. By default a render only reads:

* ``data:`` URIs;
* local files INSIDE the allowed roots — the document's ``source_dir``,
  the library's templates and assets, the template package's own
  directories (and the files its manifest names), and any extra root the
  caller lists in :attr:`RenderOptions.allowed_roots`.

Everything else is refused with a warning, never silently: absolute paths
or ``file://`` URLs outside those roots (``/etc/passwd``,
``../../secret``), ``http(s)://`` URLs (server-side request forgery from a
rendering service) and any other scheme. Callers that need more opt in
explicitly with ``RenderOptions(allow_absolute_paths=True)`` or
``RenderOptions(allow_network=True)``.

The same policy is enforced twice: when the parser resolves an ``<img src>``
and in the URL fetcher WeasyPrint uses for EVERY resource it loads
(images, CSS ``url()``, ``@font-face`` sources).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

logger = logging.getLogger("pdfgen_juanipis.security")


class ResourceRejected(ValueError):
    """A resource the policy does not allow (raised inside the fetcher)."""


def _resolve(path: Path) -> Optional[Path]:
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


@dataclass(frozen=True)
class ResourcePolicy:
    roots: Tuple[Path, ...] = ()
    allow_absolute_paths: bool = False
    allow_network: bool = False

    @classmethod
    def build(
        cls,
        roots: Iterable[Any],
        *,
        allow_absolute_paths: bool = False,
        allow_network: bool = False,
    ) -> "ResourcePolicy":
        resolved = []
        for root in roots:
            if root is None:
                continue
            path = _resolve(Path(root))
            if path is not None and path not in resolved:
                resolved.append(path)
        return cls(tuple(resolved), allow_absolute_paths, allow_network)

    # ── checks ──────────────────────────────────────────────────────
    def allows_path(self, path: Path) -> bool:
        if self.allow_absolute_paths:
            return True
        resolved = _resolve(path)
        if resolved is None:
            return False
        return any(resolved.is_relative_to(root) for root in self.roots)

    def _reject(self, what: str, why: str) -> None:
        logger.warning("resource refused: %s (%s)", what[:200], why)

    def check_url(self, url: str) -> None:
        """Raise :class:`ResourceRejected` unless ``url`` may be fetched."""
        scheme = (urlparse(url).scheme or "").lower()
        if scheme == "data":
            return
        if scheme == "file":
            path = Path(url2pathname(unquote(urlparse(url).path)))
            if self.allows_path(path):
                return
            why = "local file outside the allowed roots; list its directory in " \
                  "RenderOptions.allowed_roots or set allow_absolute_paths=True"
        elif scheme in ("http", "https"):
            if self.allow_network:
                return
            why = "network access is disabled; set RenderOptions(allow_network=True)"
        else:
            why = f"scheme {scheme or '(none)'!r} is not allowed"
        self._reject(url, why)
        raise ResourceRejected(f"{why}: {url[:200]}")

    def resolve_src(self, src: str, source_dir: Optional[Path]) -> Optional[str]:
        """The URL an ``<img src>`` may load, or ``None`` (with a warning)."""
        src = (src or "").strip()
        if not src:
            return None
        parsed = urlparse(src)
        scheme = (parsed.scheme or "").lower()
        # A single letter is a Windows drive ("C:\\..."), not a scheme.
        if scheme and len(scheme) > 1:
            try:
                self.check_url(src)
            except ResourceRejected:
                return None
            return src
        path = Path(src)
        if not path.is_absolute():
            if source_dir is None:
                self._reject(src, "relative path with no source_dir to resolve it against")
                return None
            path = Path(source_dir) / path
        resolved = _resolve(path)
        if resolved is None or not resolved.exists():
            self._reject(src, "file not found")
            return None
        if not self.allows_path(resolved):
            self._reject(
                src, "path resolves outside the allowed roots; list its directory in "
                     "RenderOptions.allowed_roots or set allow_absolute_paths=True",
            )
            return None
        return resolved.as_uri()

    # ── WeasyPrint ──────────────────────────────────────────────────
    def url_fetcher(self) -> Any:
        """A WeasyPrint URL fetcher that enforces this policy."""
        import weasyprint

        policy = self
        base = getattr(weasyprint, "URLFetcher", None)
        if base is not None:  # WeasyPrint >= 68

            class _PolicyFetcher(base):  # type: ignore[misc, valid-type]
                def fetch(self, url: str, headers: Any = None) -> Any:
                    policy.check_url(url)
                    return super().fetch(url, headers)

            return _PolicyFetcher(allow_redirects=policy.allow_network)

        def _fetcher(url: str, timeout: int = 10, ssl_context: Any = None) -> Any:
            policy.check_url(url)
            return weasyprint.default_url_fetcher(url, timeout=timeout, ssl_context=ssl_context)

        return _fetcher


__all__ = ["ResourcePolicy", "ResourceRejected"]
