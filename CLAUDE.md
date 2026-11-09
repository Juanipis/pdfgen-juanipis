# pdfgen-juanipis

Editable HTML to paginated PDF (and Word), built on WeasyPrint and Jinja2.
Since 0.2 the library is HTML-first (`HtmlRenderer`); the 0.1 structured-data
API lives in `pdfgen_juanipis.legacy` and must keep working.

## Golden Rules

### 1. Content MUST flow naturally — never use position:absolute for content

The CSS template uses **CSS Paged Media** for layout. Content lives in normal document flow
and WeasyPrint handles page breaks automatically — like a word processor.

- `position: fixed` → header banner, logo, footer contact (repeat on every page)
- `@page` margins → reserve space so content doesn't overlap fixed elements
- `.content`, `.intro`, `.cover` → **normal flow**, no absolute positioning

**NEVER** use `position: absolute` or fixed `height` + `overflow: hidden` on content
containers. This prevents WeasyPrint from paginating and causes content to be clipped
to a single page.

### 2. The paginator is a helper, not the layout engine

The Python `Paginator` class organizes blocks (distributes footnotes, measures heights
for table splitting, etc.) but **WeasyPrint is the actual layout engine**. A single
`<p>` with 10,000 words must flow across pages naturally without Python needing to
split it.

### 3. Only open fonts, no brands

The repo is public. Bundle only fonts whose license allows redistribution,
each next to its license and listed in `assets/fonts/FONTS.md`. Brand
letterheads, logos and proprietary fonts live in their owner's template
package, registered at runtime — never in this repo.

### 4. Template structure

```
<body>
  <!-- Fixed elements (position:fixed = repeat on every page) -->
  <img class="header-banner" ...>
  <img class="header-logo" ...>
  <div class="footer-contact">...</div>

  <!-- Flowing content (WeasyPrint paginates this) -->
  <div class="header-title">...</div>
  <div class="intro">...</div>
  <div class="content">
    <!-- blocks flow naturally here -->
  </div>
  <div class="footer-meta">...</div>
</body>
```

## Project Structure

```
src/pdfgen_juanipis/
  __init__.py      — lazy public API (new + legacy names)
  options.py       — RenderOptions, Labels (every user-visible word)
  contract.py      — render-contract directives, scan, numbering, text guard
  packages.py      — template packages (letterhead) + PackageRegistry
  fonts.py         — bundled fonts, isolated fontconfig
  text.py          — foreign-script guard, number/percent binding
  formats.py       — render_formats(): PDF + DOCX from one options object
  docx_export.py   — Word exporter ([docx] extra)
  pdf/
    renderer.py    — HtmlRenderer (payload → Jinja → WeasyPrint + passes)
    parsing.py     — HTML → sections / blocks / tables
    pages.py       — sections → the single flowing page, footnote placement
    passes.py      — post-layout passes (footnotes, figure gaps, lonely breaks)
    visual_layout.py, images.py — figure sizing and image fitting
  templates/       — report.html.jinja + report.css (HTML-first renderer)
  packages/plain/  — the built-in neutral template package
  assets/fonts/    — open fonts, one dir per family + license, FONTS.md
  legacy/          — 0.1 API: render, api, pagination, validator, templates
  render.py, api.py, pagination.py, validator.py — aliases of legacy modules
```

## Commands

```bash
uv sync --extra dev --extra docx # Install dependencies
uv run pytest -q                 # Run all tests
uv run python scripts/parity_harness.py doc.html --compare other.pdf  # page count + text layer
```

On macOS with Apple Silicon, WeasyPrint needs:
```bash
brew install pango cairo gdk-pixbuf libffi
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

## Key Dependencies

- **WeasyPrint** >= 66.0 — CSS Paged Media PDF renderer
- **Jinja2** — Template engine
- **lxml**, **Pillow** — HTML parsing, image fitting
- **PyYAML** — Template package manifests, legacy data input
- **jsonschema** — Legacy payload validation
- **python-docx** — Word exporter (optional `[docx]` extra)
