"""Template packages: the document's chrome as a registry, not a constant.

What a package owns
-------------------
Everything a reader sees that is NOT the content: the page-header band,
the contact block in the footer, the vertical geometry of both, the
palette, the fonts and any stylesheet override the look needs. It cannot
change a number, a figure or a label — it changes letterhead.

A package is a directory with a ``package.yml``::

    my_letterhead/
      package.yml
      letterhead.css          # optional, appended after the stylesheet
      assets/
        header.png            # the band, 612 pt wide (Letter)
        fonts/MyFont-Regular.ttf

    # package.yml
    label: "My organisation"
    description: "Blue band with the logo on the right."
    css: letterhead.css
    font_family: "My Font"            # body text family (optional)
    fonts:                            # faces the package ships (optional)
      - {family: "My Font", file: fonts/MyFont-Regular.ttf, weight: 400}
      - {family: "My Font", file: fonts/MyFont-Bold.ttf, weight: 700}
    theme:
      header_complete_path: header.png
      footer_site: example.org
      footer_phone: "+1 555 0100"
      footer_address: "1 Main St"
      footer_email: hello@example.org
      footer_city: "Springfield"
    layout:
      header_height_pt: 105
      page_margin_bottom_pt: 82
      footer_bottom_from_page_pt: 36.5
    palette:
      title: "#2e5395"     # titles and headings (PDF and Word)
      accent: "#f58634"    # contact-block separator

Both exporters read the resolved package, so a letterhead reaches Word and
PDF at the same time or not at all.

Registering packages
--------------------
The library ships one neutral package, ``plain`` (no band, no contact
block). Brand packages live with their owner and are registered at
start-up::

    from pdfgen_juanipis import register_template_packages
    register_template_packages("path/to/my_packages", shared_assets="path/to/bundle/assets",
                               default="my_letterhead")

Asset resolution searches the package's own ``assets/``, then the shared
asset directories given at registration, then the library's own assets.
A missing asset raises: a letterhead that silently prints someone else's
banner is the failure this module exists to prevent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import yaml

from pdfgen_juanipis.fonts import ASSETS_DIR, FONTS_DIR, font_family_css_value

logger = logging.getLogger("pdfgen_juanipis.packages")

PathLike = Union[str, Path]

#: Packages shipped with the library.
BUILTIN_PACKAGES_ROOT: Path = Path(__file__).resolve().parent / "packages"
#: The library's default package.
BUILTIN_DEFAULT_PACKAGE = "plain"
#: Manifest file that makes a directory a package.
MANIFEST_NAME = "package.yml"

#: Stylesheet values of the chrome geometry a package may override. They
#: are the numbers ``templates/report.css`` carries, kept here so an
#: override is emitted as a difference from a known value instead of a
#: second copy of the stylesheet (the tests check they still match).
DEFAULT_HEADER_HEIGHT_PT = 105.0
DEFAULT_FOOTER_BOTTOM_OFFSET_PT = -50.0
DEFAULT_PAGE_MARGIN_BOTTOM_PT = 60.0

#: Palette keys the exporters read, and the stylesheet's values for them.
PALETTE_DEFAULTS: Dict[str, str] = {
    "title": "#2e5395",
    "accent": "#f58634",
}

#: Theme keys the exporters read. Anything else is a typo, and a typo in
#: a letterhead is invisible until a reader sees the wrong phone number.
THEME_KEYS = frozenset({
    "header_complete_path",
    "header_banner_path",
    "header_banner_path_cont",
    "header_logo_path",
    "footer_site",
    "footer_phone",
    "footer_address",
    "footer_email",
    "footer_city",
    "show_header_titles",
})

LAYOUT_KEYS = frozenset({
    # Rendered height of the header band.
    "header_height_pt",
    # Paper the chrome reserves at the bottom. Moving the contact block up
    # without moving the content box with it prints the footer on top of
    # the footnote area.
    "page_margin_bottom_pt",
    # Where the contact block's last line sits, measured from the bottom
    # EDGE OF THE PAPER — the number a ruler on the letterhead gives you.
    # The stylesheet positions that block relative to the content box, so
    # the CSS offset is derived from this and the margin above.
    "footer_bottom_from_page_pt",
})

MANIFEST_KEYS = frozenset({
    "label", "description", "css", "fonts", "font_family", "theme",
    "layout", "palette", "publisher", "metadata",
})


class TemplatePackageError(ValueError):
    """A package is missing, malformed, or names an asset it lacks."""


@dataclass(frozen=True)
class TemplatePackage:
    """One resolved letterhead: theme values, geometry, assets, CSS, fonts."""

    name: str
    root: Path
    label: str = ""
    description: str = ""
    theme: Dict[str, Any] = field(default_factory=dict)
    layout: Dict[str, float] = field(default_factory=dict)
    palette: Dict[str, str] = field(default_factory=dict)
    css_text: str = ""
    #: Who publishes with this letterhead (``{"names": [...]}``). Free-form
    #: metadata for consumers; the renderers do not read it.
    publisher: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    #: Font faces the package ships: ``({family, file, weight, style}, ...)``,
    #: ``file`` relative to ``assets/``.
    fonts: Tuple[Dict[str, Any], ...] = ()
    #: Body text family; ``None`` keeps the library's (Carlito).
    font_family: Optional[str] = None
    #: Fallback asset directories searched after ``assets/``.
    asset_dirs: Tuple[Path, ...] = ()

    @property
    def publisher_names(self) -> Tuple[str, ...]:
        names = (self.publisher or {}).get("names")
        if not isinstance(names, (list, tuple)):
            return ()
        return tuple(str(n).strip() for n in names if str(n or "").strip())

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets"

    def _search_dirs(self) -> List[Path]:
        return [self.assets_dir, *self.asset_dirs, ASSETS_DIR]

    def asset(self, filename: str) -> Path:
        """Resolve one asset: the package's own copy, else a shared one."""
        name = str(filename or "").strip()
        if not name:
            raise TemplatePackageError(f"template package {self.name!r}: empty asset name")
        candidate = Path(name)
        if candidate.is_absolute():
            if candidate.exists():
                return candidate.resolve()
        else:
            for directory in self._search_dirs():
                path = directory / name
                if path.exists():
                    return path.resolve()
        raise TemplatePackageError(
            f"template package {self.name!r} names asset {name!r}, which exists "
            f"in none of: {', '.join(str(d) for d in self._search_dirs())}"
        )

    @property
    def header_asset(self) -> Optional[Path]:
        """The page-header band both exporters paint, or ``None``."""
        name = (
            self.theme.get("header_complete_path")
            or self.theme.get("header_banner_path")
            or ""
        )
        return self.asset(name) if name else None

    def font_dirs(self) -> List[Path]:
        """Directories fontconfig should know for this package."""
        dirs = [FONTS_DIR]
        for directory in (self.assets_dir / "fonts", *(d / "fonts" for d in self.asset_dirs)):
            if directory.is_dir():
                dirs.append(directory)
        for face in self.fonts:
            try:
                dirs.append(self.asset(face["file"]).parent)
            except TemplatePackageError:
                continue
        return dirs

    def font_face_css(self) -> str:
        """``@font-face`` rules for the package's own fonts (file URIs)."""
        rules = []
        for face in self.fonts:
            uri = self.asset(face["file"]).as_uri()
            fmt = "opentype" if str(face["file"]).lower().endswith(".otf") else "truetype"
            rules.append(
                "@font-face {\n"
                f"  font-family: '{face['family']}';\n"
                f"  src: url('{uri}') format('{fmt}');\n"
                f"  font-weight: {face['weight']};\n"
                f"  font-style: {face['style']};\n"
                "}"
            )
        return "\n".join(rules)

    def color(self, key: str) -> str:
        """A palette colour the exporters read (``title``, ``accent``)."""
        return str(self.palette.get(key) or PALETTE_DEFAULTS[key])

    def header_height_pt(self, default: float = DEFAULT_HEADER_HEIGHT_PT) -> float:
        value = self.layout.get("header_height_pt")
        return float(default if value is None else value)

    def page_margin_bottom_pt(self, default: float = DEFAULT_PAGE_MARGIN_BOTTOM_PT) -> float:
        value = self.layout.get("page_margin_bottom_pt")
        return float(default if value is None else value)

    def footer_bottom_from_page_pt(self) -> Optional[float]:
        value = self.layout.get("footer_bottom_from_page_pt")
        return None if value is None else float(value)

    def footer_css_bottom_pt(self, page_margin_bottom: float) -> Optional[float]:
        """The stylesheet ``bottom`` that lands the block where declared."""
        from_page = self.footer_bottom_from_page_pt()
        if from_page is None:
            return None
        return -(page_margin_bottom - from_page)

    def stylesheet(self) -> str:
        """Everything this package adds after the shared stylesheet."""
        parts = [
            build_chrome_geometry_css(self),
            build_palette_css(self),
            self.font_face_css(),
        ]
        if self.font_family:
            parts.append(
                ":root {\n"
                f"  --pdfgen-font-family: {font_family_css_value(self.font_family)};\n"
                "}"
            )
        parts.append(self.css_text or "")
        return "\n".join(p for p in parts if p)


def build_chrome_geometry_css(package: TemplatePackage) -> str:
    """Per-package overrides for the geometry a letterhead changes.

    Only emitted when the package differs from the stylesheet's own
    values, so a package that matches it adds no CSS at all.
    """
    parts = []
    height = package.header_height_pt(DEFAULT_HEADER_HEIGHT_PT)
    if abs(height - DEFAULT_HEADER_HEIGHT_PT) > 1e-6:
        parts.append(
            "/* template package: header band height */\n"
            f".header-complete {{\n  height: {height:g}pt;\n}}\n"
        )
    margin = package.page_margin_bottom_pt(DEFAULT_PAGE_MARGIN_BOTTOM_PT)
    if abs(margin - DEFAULT_PAGE_MARGIN_BOTTOM_PT) > 1e-6:
        parts.append(
            "/* template package: paper reserved for the chrome */\n"
            f"@page {{\n  margin-bottom: {margin:g}pt;\n}}\n"
        )
    offset = package.footer_css_bottom_pt(margin)
    if offset is not None and abs(offset - DEFAULT_FOOTER_BOTTOM_OFFSET_PT) > 1e-6:
        parts.append(
            "/* template package: contact block, derived from the measured "
            "distance to the paper edge */\n"
            f".footer-contact {{\n  bottom: {offset:g}pt;\n}}\n"
        )
    return "\n".join(parts)


def build_palette_css(package: TemplatePackage) -> str:
    """CSS custom properties for the palette keys the package declares."""
    lines = []
    if package.palette.get("title"):
        lines.append(f"  --pdfgen-title-color: {package.palette['title']};")
    if package.palette.get("accent"):
        lines.append(f"  --pdfgen-accent-color: {package.palette['accent']};")
    if not lines:
        return ""
    return ":root {\n" + "\n".join(lines) + "\n}"


def _load_manifest(directory: Path) -> Dict[str, Any]:
    manifest = directory / MANIFEST_NAME
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        raise TemplatePackageError(
            f"template package {directory.name!r}: {MANIFEST_NAME} could not be read ({exc})"
        ) from exc
    if not isinstance(raw, dict):
        raise TemplatePackageError(
            f"template package {directory.name!r}: {MANIFEST_NAME} must be a mapping, "
            f"got {type(raw).__name__}"
        )
    return raw


def load_template_package(
    directory: PathLike,
    *,
    name: Optional[str] = None,
    asset_dirs: Sequence[PathLike] = (),
) -> TemplatePackage:
    """Load and validate one package directory."""
    directory = Path(directory).resolve()
    wanted = name or directory.name
    if not (directory / MANIFEST_NAME).exists():
        raise TemplatePackageError(
            f"{directory} is not a template package (no {MANIFEST_NAME})"
        )
    raw = _load_manifest(directory)

    unknown_top = sorted(set(raw) - MANIFEST_KEYS)
    if unknown_top:
        logger.warning(
            "template package %r: ignoring unknown manifest key(s) %s", wanted, unknown_top,
        )

    theme = dict(raw.get("theme") or {})
    unknown_theme = sorted(set(theme) - THEME_KEYS)
    if unknown_theme:
        raise TemplatePackageError(
            f"template package {wanted!r}: unknown theme key(s) {unknown_theme}. "
            f"Known: {sorted(THEME_KEYS)}"
        )
    layout_raw = dict(raw.get("layout") or {})
    unknown_layout = sorted(set(layout_raw) - LAYOUT_KEYS)
    if unknown_layout:
        raise TemplatePackageError(
            f"template package {wanted!r}: unknown layout key(s) {unknown_layout}. "
            f"Known: {sorted(LAYOUT_KEYS)}"
        )
    layout: Dict[str, float] = {}
    for key, value in layout_raw.items():
        try:
            layout[key] = float(value)
        except (TypeError, ValueError) as exc:
            raise TemplatePackageError(
                f"template package {wanted!r}: layout.{key} must be a number in "
                f"points, got {value!r}"
            ) from exc

    css_text = ""
    css_name = str(raw.get("css") or "").strip()
    if css_name:
        css_path = directory / css_name
        if not css_path.exists():
            raise TemplatePackageError(
                f"template package {wanted!r}: css {css_name!r} not found at {css_path}"
            )
        css_text = css_path.read_text(encoding="utf-8")

    fonts = []
    for i, face in enumerate(raw.get("fonts") or []):
        if not isinstance(face, dict) or not face.get("family") or not face.get("file"):
            raise TemplatePackageError(
                f"template package {wanted!r}: fonts[{i}] needs a family and a file "
                f"(relative to assets/), got {face!r}"
            )
        fonts.append({
            "family": str(face["family"]),
            "file": str(face["file"]),
            "weight": int(face.get("weight", 400)),
            "style": str(face.get("style", "normal")),
        })

    package = TemplatePackage(
        name=wanted,
        root=directory,
        label=str(raw.get("label") or wanted),
        description=str(raw.get("description") or "").strip(),
        theme=theme,
        layout=layout,
        palette={str(k): str(v) for k, v in (raw.get("palette") or {}).items()},
        css_text=css_text,
        publisher=dict(raw.get("publisher") or {}),
        metadata=dict(raw.get("metadata") or {}),
        fonts=tuple(fonts),
        font_family=(str(raw["font_family"]).strip() or None) if raw.get("font_family") else None,
        asset_dirs=tuple(Path(d).resolve() for d in asset_dirs),
    )
    # Fail at resolution time, not at paint time: a package whose header
    # asset or font is absent must never reach a renderer that would then
    # quietly draw nothing or fall back to another face.
    _ = package.header_asset
    for face in package.fonts:
        _ = package.asset(face["file"])
    return package


@dataclass
class _Entry:
    directory: Path
    asset_dirs: Tuple[Path, ...]


class PackageRegistry:
    """Named template packages and which one is the default.

    The library's own packages are registered first; a consumer's
    registration with the same name shadows them.
    """

    def __init__(self, *, include_builtin: bool = True) -> None:
        self._entries: Dict[str, _Entry] = {}
        self._default: str = BUILTIN_DEFAULT_PACKAGE
        if include_builtin:
            self.register(BUILTIN_PACKAGES_ROOT)

    # ── registration ────────────────────────────────────────────────
    def register(
        self,
        path: PathLike,
        *,
        name: Optional[str] = None,
        shared_assets: Union[PathLike, Iterable[PathLike], None] = None,
        default: Optional[str] = None,
    ) -> List[str]:
        """Register one package directory, or a directory OF packages.

        ``shared_assets``: directories searched after each package's own
        ``assets/`` (e.g. a bundle of logos and fonts the packages share).
        ``default``: make that package (by name) the registry default.
        Returns the names registered.
        """
        root = Path(path).resolve()
        if isinstance(shared_assets, (str, Path)):
            asset_dirs: Tuple[Path, ...] = (Path(shared_assets).resolve(),)
        else:
            asset_dirs = tuple(Path(d).resolve() for d in (shared_assets or ()))
        for directory in asset_dirs:
            if not directory.is_dir():
                raise TemplatePackageError(f"shared asset directory {directory} does not exist")
        if not root.is_dir():
            raise TemplatePackageError(f"{root} is not a directory")

        names: List[str] = []
        if (root / MANIFEST_NAME).exists():
            names.append(name or root.name)
            self._entries[names[-1]] = _Entry(root, asset_dirs)
        else:
            if name:
                raise TemplatePackageError(
                    f"{root} holds several packages; `name` only applies to one package"
                )
            for child in sorted(root.iterdir()):
                if child.is_dir() and (child / MANIFEST_NAME).exists():
                    self._entries[child.name] = _Entry(child.resolve(), asset_dirs)
                    names.append(child.name)
            if not names:
                raise TemplatePackageError(
                    f"{root} contains no template package (no {MANIFEST_NAME} in it or "
                    f"in its subdirectories)"
                )
        if default:
            self.set_default(default)
        return names

    def unregister(self, name: str) -> None:
        self._entries.pop(name, None)
        if self._default == name:
            self._default = BUILTIN_DEFAULT_PACKAGE

    def set_default(self, name: str) -> None:
        if name not in self._entries:
            raise TemplatePackageError(
                f"cannot make {name!r} the default: it is not registered "
                f"(available: {', '.join(self.available()) or '(none)'})"
            )
        self._default = name

    # ── lookup ──────────────────────────────────────────────────────
    @property
    def default(self) -> str:
        return self._default

    def available(self) -> List[str]:
        """Every registered package, by name."""
        return sorted(self._entries)

    def resolve(self, name: Optional[str] = None) -> TemplatePackage:
        """Load one package by name; ``None``/empty resolves the default.

        An unknown name raises with the available list instead of falling
        back to the default: asking for letterhead A and silently getting
        letterhead B is a defect nobody sees until it is printed.
        """
        wanted = str(name or "").strip() or self._default
        entry = self._entries.get(wanted)
        if entry is None:
            raise TemplatePackageError(
                f"unknown template package {wanted!r}. Available: "
                f"{', '.join(self.available()) or '(none)'}. Register a directory "
                f"with register_template_packages()."
            )
        return load_template_package(entry.directory, name=wanted, asset_dirs=entry.asset_dirs)

    def describe(self) -> List[Dict[str, Any]]:
        """``[{name, label, description, default}]`` for a CLI or an API."""
        out: List[Dict[str, Any]] = []
        for name in self.available():
            try:
                package = self.resolve(name)
            except TemplatePackageError as exc:
                logger.warning("template package %r is unusable: %s", name, exc)
                continue
            out.append({
                "name": package.name,
                "label": package.label,
                "description": package.description,
                "default": package.name == self._default,
            })
        return out


#: The process-wide registry the renderers use unless given another one.
default_registry = PackageRegistry()


def register_template_packages(
    path: PathLike,
    *,
    name: Optional[str] = None,
    shared_assets: Union[PathLike, Iterable[PathLike], None] = None,
    default: Optional[str] = None,
) -> List[str]:
    """Register packages in the default registry (see :meth:`PackageRegistry.register`)."""
    return default_registry.register(path, name=name, shared_assets=shared_assets, default=default)


def resolve_template_package(
    package: Union[str, TemplatePackage, None] = None,
    *,
    registry: Optional[PackageRegistry] = None,
) -> TemplatePackage:
    """A :class:`TemplatePackage` from a name, a package, or ``None`` (default)."""
    if isinstance(package, TemplatePackage):
        return package
    return (registry or default_registry).resolve(package)


def available_template_packages(*, registry: Optional[PackageRegistry] = None) -> List[str]:
    return (registry or default_registry).available()


def describe_template_packages(*, registry: Optional[PackageRegistry] = None) -> List[Dict[str, Any]]:
    return (registry or default_registry).describe()


__all__ = [
    "BUILTIN_DEFAULT_PACKAGE",
    "BUILTIN_PACKAGES_ROOT",
    "DEFAULT_FOOTER_BOTTOM_OFFSET_PT",
    "DEFAULT_HEADER_HEIGHT_PT",
    "DEFAULT_PAGE_MARGIN_BOTTOM_PT",
    "LAYOUT_KEYS",
    "MANIFEST_NAME",
    "PALETTE_DEFAULTS",
    "PackageRegistry",
    "THEME_KEYS",
    "TemplatePackage",
    "TemplatePackageError",
    "available_template_packages",
    "build_chrome_geometry_css",
    "build_palette_css",
    "default_registry",
    "describe_template_packages",
    "load_template_package",
    "register_template_packages",
    "resolve_template_package",
]
