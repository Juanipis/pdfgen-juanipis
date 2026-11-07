# Changelog

## Unreleased

- _TBD_

## 0.2.0 - 2026-11-06

HTML-first renderer, brought back from the downstream bulletin project that
had rebuilt the HTML → PDF pipeline on top of this library.

### Added
- `HtmlRenderer(package=..., options=RenderOptions(...)).render(html, path)`:
  editable HTML → sections/blocks → Jinja (`templates/report.html.jinja`,
  `templates/report.css`) → WeasyPrint, with post-layout passes: footnotes
  verified on their marker's page, figure-gap filling (move prose / shrink the
  image), lonely forced breaks relaxed. `render_bytes`, `render_file`,
  `render_document`, `build_payload`, `build_html`.
- `RenderOptions` (shared by PDF and Word) and `Labels` (every word the
  library prints: «Figura», «Página», «Cel:», «Contenido» …, Spanish defaults).
- Template packages: `package.yml` manifests (theme, layout geometry, palette,
  fonts, body font, CSS), `PackageRegistry` / `register_template_packages()`
  for packages that live outside the library, shared asset directories,
  built-in neutral `plain` package.
- Render contract (`pdfgen_juanipis.contract`): directive registry,
  `scan_directives`, `register_directive`, roman section numbering,
  body-table column widths, foreign-script text guard.
- Word exporter (`DocxRenderer`, `render_docx`) behind the `[docx]` extra,
  mirroring the stylesheet's typography, the package's letterhead and native
  Word footnotes; `render_formats()` renders both from one options object.
- CLI: `pdfgen-juanipis html` and `pdfgen-juanipis packages`.
- `scripts/parity_harness.py` (page count + text layer, optional comparison
  against another PDF).

### Changed
- **Fonts**: the Microsoft fonts shipped up to 0.1.12 (Calibri, Century Gothic,
  Segoe UI, Times New Roman, Aptos Narrow subsets) were removed and replaced by
  open fonts with their licenses: Carlito, TeX Gyre Adventor, Selawik,
  Liberation Serif (all metric-compatible) and IBM Plex Sans Condensed. See
  `assets/fonts/FONTS.md`.
- The 0.1 API moved to `pdfgen_juanipis.legacy`; every old name and module
  path still works (`pdfgen_juanipis.render`, `.api`, `.pagination`,
  `.validator` alias the legacy modules).
- The legacy renderer now passes a `FontConfiguration`, so its `@font-face`
  rules are honoured (they were silently ignored before).
- Dependencies: exact pins relaxed to minimums; `lxml` and `Pillow` added;
  `python-docx` only under the `docx` extra; `dev` extra for tests.
- Importing `pdfgen_juanipis` no longer imports WeasyPrint (lazy exports).

### Fixed
- Legacy `render_pdf` set `FONTCONFIG_FILE="None"` when no fonts.conf was
  given, breaking fontconfig for the rest of the process.

## 0.1.12 - 2026-03-28

- Automated release.

## 0.1.11 - 2026-03-28

- Automated release.

## 0.1.10 - 2026-03-28

- Automated release.

## 0.1.9 - 2026-03-09

- Automated release.

## 0.1.8 - 2026-02-23

- Automated release.

## 0.1.7 - 2026-02-10

- Automated release.

## 0.1.6 - 2026-02-10

- Automated release.

## 0.1.5 - 2026-02-05

- Automated release.

## 0.1.4 - 2026-02-04

- Automated release.

## 0.1.3 - 2026-02-04

- Automated release.

## 0.1.2 - 2026-02-04

- Automated release.

## 0.1.1 - 2026-02-04

- Automated release.

## 0.1.0 - 2026-02-04

- Initial package release with HTML-to-PDF rendering.
- Paginator with table splitting and footer-aware layout.
- Schema validation and normalization (JSON Schema).
- Inline references catalog + per-page placement.
- CLI with JSON/YAML support.
- Optional CSS injection and custom fonts support.
- Stress harness and test suite.
