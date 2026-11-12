# Changelog

## Unreleased

What a rich-text editor writes now reaches the Word file, not only the PDF
(measured against TipTap and documents pasted from Word, Google Docs and
the web).

## 0.2.2 - 2026-11-12

- Automated release.

### Fixed
- Word: inline formatting is walked recursively and accumulated. Italics
  inside bold, bold inside a coloured `<span>` (how Google Docs pastes),
  `<u>`, `<s>`, `<sub>`, `<code>`, inline `font-weight` / `font-style` /
  `text-decoration`, `color` and `background-color` survive; before, one
  level was read and its content flattened.
- Word: `<mark>` (and its `data-color`) becomes run shading in the exact
  colour; `<a href>` with http(s)/mailto becomes a real Word hyperlink.
- Word: list items keep their formatting, nested lists go one level deeper
  (`List Bullet 2`…), and every numbered list starts again at 1 (two lists
  read 1-2 and 3-4).
- Word: `<blockquote>` is indented and in italics; `<pre>` is monospaced;
  `<h5>`/`<h6>` are headings; unknown blocks keep their inline formatting.
- Word: JPEG, GIF and WEBP images are embedded (re-encoded as PNG); an
  image declaring more than 16 Mpx is not decoded, a large one is scaled to
  2400 px. A bare `<img>` prints at its own size up to the text width.
- PDF: a one-column table prints its rows as paragraphs and a one-cell row
  inside a grid keeps its label; both vanished without a warning.

### Added
- Contract directive `data-color` on `<mark>`.

## 0.2.1 - 2026-11-08

- Automated release.

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

### Security
- The HTML-first renderer treats its input as untrusted. By default it reads
  only `data:` URIs and local files inside the allowed roots (`source_dir`,
  the library's templates/assets, the template package's directories);
  absolute paths, `file://` and `../` escapes outside them are refused with a
  warning. Every WeasyPrint `HTML()`/`CSS()` call gets a restrictive
  `url_fetcher` (images, CSS `url()`, `@font-face`): `http(s)` and other
  schemes are refused (no SSRF). Opt-ins: `RenderOptions(allowed_roots=[...])`,
  `allow_absolute_paths=True`, `allow_network=True`.
- The Jinja environment autoescapes; only the body blocks rebuilt by the
  parser are inserted as HTML. Plain-text values spliced into HTML (inline
  headings, cover lines, footnote texts, section subtitles) are escaped.

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
