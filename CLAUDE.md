# pdfgen-juanipis

HTML-to-PDF generator with pagination and validation, built on WeasyPrint and Jinja2.

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

### 3. Template structure

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
  pagination.py    — Block measurer, paginator, HTML chunk splitting
  render.py        — render_pdf() entry point, Jinja + WeasyPrint pipeline
  validator.py     — Schema validation and data normalization
  api.py           — Public API (PDFGenConfig, convenience functions)
  templates/
    boletin_template.html.jinja  — Jinja2 page template
    boletin.css                  — CSS Paged Media stylesheet
  assets/
    fonts/         — Bundled TTF fonts
    *.png          — Default banner/logo images
```

## Commands

```bash
uv sync                          # Install dependencies
uv run pytest -v                 # Run all tests
uv run pytest tests/test_pagination_smoke.py -v  # Pagination tests only
```

On macOS with Apple Silicon, WeasyPrint needs:
```bash
brew install pango cairo gdk-pixbuf libffi
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

## Key Dependencies

- **WeasyPrint** >= 66.0 — CSS Paged Media PDF renderer
- **Jinja2** — Template engine
- **PyYAML** — Data input format
- **jsonschema** — Payload validation
