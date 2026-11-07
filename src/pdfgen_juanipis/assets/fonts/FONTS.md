# Bundled fonts

Every font shipped with pdfgen-juanipis is open source and redistributable.
Each family lives in its own directory next to its license file. All files
were downloaded unmodified from the upstream listed below.

Since 0.2.0 these fonts replace the Microsoft fonts (Calibri, Century Gothic,
Segoe UI, Times New Roman, Aptos Narrow) that releases up to 0.1.12 shipped.
The replacements were chosen to be **metric-compatible** wherever such a font
exists, so text set in them breaks lines and pages exactly where the original
did. "Advance widths" below is the ratio of glyph advance widths measured
against the files previous releases shipped (1.0000 = identical metrics).

| Directory | Font (version) | Replaces | Advance widths | License | Upstream |
|---|---|---|---|---|---|
| `carlito/` | Carlito 1.104 — Regular, Bold, Italic, Bold Italic | Calibri | 1.0000 | SIL OFL 1.1 (`OFL.txt`) | https://github.com/google/fonts/tree/main/ofl/carlito |
| `tex-gyre-adventor/` | TeX Gyre Adventor 2.501 — Regular, Bold, Italic, Bold Italic | Century Gothic | 1.0000 | GUST Font License (`GUST-FONT-LICENSE.txt`, LPPL 1.3c in `LPPL-1.3c.txt`) | https://ctan.org/pkg/tex-gyre (files from https://mirrors.ctan.org/fonts/tex-gyre/opentype/) |
| `selawik/` | Selawik 1.01 — Regular, Bold | Segoe UI | 1.0000 | SIL OFL 1.1 (`OFL.txt`) | https://github.com/microsoft/Selawik (release 1.01) |
| `liberation-serif/` | Liberation Serif 2.1.5 — Regular, Bold | Times New Roman | 1.0000 | SIL OFL 1.1 (`OFL.txt`) | https://github.com/liberationfonts/liberation-fonts (release 2.1.5) |
| `ibm-plex-sans-condensed/` | IBM Plex Sans Condensed 1.3 — Regular, Bold | Aptos Narrow | ≈1.01 (not metric-compatible) | SIL OFL 1.1 (`OFL.txt`) | https://github.com/google/fonts/tree/main/ofl/ibmplexsanscondensed |

Notes:

- Century Gothic was drawn to the metrics of ITC Avant Garde Gothic, and TeX
  Gyre Adventor is the GUST e-foundry's Avant Garde clone, which is why the
  two share advance widths.
- No open font is metric-compatible with Aptos Narrow. IBM Plex Sans
  Condensed is the closest measured candidate (overall width +0.9 %, tabular
  digits 0.540 em vs 0.507 em). It is only used by the legacy (0.1) template.
- The HTML-first renderer sets body text in Carlito. A template package may
  ship other fonts (including proprietary ones its owner is licensed to use)
  without changing this directory: see "Fonts" in the README.
