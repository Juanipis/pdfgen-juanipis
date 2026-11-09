"""Render an HTML document with the library and report what came out.

Meant for regression and parity checks against another renderer: it
prints the page count and the PDF text layer (per page), and with
``--compare`` it diffs both against an existing PDF (e.g. the one another
pipeline produced from the same HTML).

Nothing here is committed with real data: point it at your own files.

    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \\
    uv run python scripts/parity_harness.py document.html --out /tmp/doc.pdf \\
        --package-dir path/to/packages --shared-assets path/to/assets --package my_letterhead \\
        --title "Title" --subtitle "Subtitle" --page-numbers \\
        --compare /tmp/other.pdf --text-out /tmp/doc.txt --json

``--font-dir DIR`` adds a directory to the isolated fontconfig and makes
the body font the family given with ``--font-family`` (to compare a
render in the bundled open fonts against one in fonts you are licensed
to use, without committing them).
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional


def _pdf_pages_text(path: Path) -> List[str]:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dev extra
        raise SystemExit("pypdf is needed for the text layer: pip install pypdf")
    return [page.extract_text() or "" for page in PdfReader(str(path)).pages]


def _norm(text: str) -> str:
    return " ".join(text.replace(" ", " ").replace(" ", " ").split())


def _font_package(font_dir: Path, family: str, base: Optional[str], registry) -> str:
    """A throw-away package that only swaps the body font."""
    from pdfgen_juanipis.packages import MANIFEST_NAME, resolve_template_package

    tmp = Path(tempfile.mkdtemp(prefix="pdfgen_font_pkg_"))
    pkg = tmp / "font_override"
    pkg.mkdir()
    parent = resolve_template_package(base, registry=registry)
    faces = []
    for path in sorted(font_dir.glob("*.[ot]tf")):
        name = path.stem.lower()
        weight = 700 if "bold" in name else 400
        style = "italic" if ("italic" in name or name.endswith("i")) else "normal"
        faces.append({"family": family, "file": str(path), "weight": weight, "style": style})
    import yaml

    manifest = {
        "label": f"{parent.label} + {family}",
        "font_family": family,
        "fonts": faces,
        "theme": {k: (str(parent.asset(v)) if k.endswith("_path") and v else v)
                  for k, v in parent.theme.items()},
        "layout": dict(parent.layout),
        "palette": dict(parent.palette),
    }
    if parent.css_text:
        (pkg / "package.css").write_text(parent.css_text, encoding="utf-8")
        manifest["css"] = "package.css"
    (pkg / MANIFEST_NAME).write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    registry.register(pkg)
    return "font_override"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("html", type=Path)
    parser.add_argument("--out", type=Path, default=None, help="PDF to write (default: a temp file)")
    parser.add_argument("--package", default=None)
    parser.add_argument("--package-dir", action="append", default=[])
    parser.add_argument("--shared-assets", action="append", default=[])
    parser.add_argument("--title", default=None)
    parser.add_argument("--subtitle", default=None)
    parser.add_argument("--page-numbers", action="store_true")
    parser.add_argument("--ascii-dashes", action="store_true")
    parser.add_argument("--figure-max-height", type=int, default=None, help="Cap figures (pt)")
    parser.add_argument("--no-passes", action="store_true", help="Disable the post-layout passes")
    parser.add_argument("--font-dir", type=Path, default=None)
    parser.add_argument("--font-family", default=None)
    parser.add_argument("--compare", type=Path, default=None, help="Another PDF to diff against")
    parser.add_argument("--text-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print a JSON summary")
    args = parser.parse_args(argv)

    from pdfgen_juanipis.options import RenderOptions
    from pdfgen_juanipis.packages import PackageRegistry
    from pdfgen_juanipis.pdf.renderer import HtmlRenderer

    registry = PackageRegistry()
    for directory in args.package_dir:
        registry.register(directory, shared_assets=args.shared_assets or None)
    package = args.package
    if args.font_dir:
        if not args.font_family:
            raise SystemExit("--font-dir needs --font-family")
        package = _font_package(args.font_dir.resolve(), args.font_family, package, registry)

    options = RenderOptions(
        title=args.title,
        subtitle=args.subtitle,
        show_page_numbers=args.page_numbers,
        ascii_dashes=args.ascii_dashes,
        figure_max_height_pt=args.figure_max_height,
        fill_figure_gaps=not args.no_passes,
        relax_lonely_breaks=not args.no_passes,
        fix_footnote_pages=not args.no_passes,
    )
    out = args.out or Path(tempfile.mkdtemp(prefix="pdfgen_harness_")) / "document.pdf"
    started = time.monotonic()
    result = HtmlRenderer(package, options, registry=registry).render_file(args.html, out)
    elapsed = time.monotonic() - started

    pages_text = _pdf_pages_text(result.output_path)
    if args.text_out:
        args.text_out.write_text(
            "".join(f"\n===== page {i} =====\n{t}" for i, t in enumerate(pages_text, 1)),
            encoding="utf-8",
        )
    summary = {
        "html": str(args.html),
        "pdf": str(result.output_path),
        "package": result.package,
        "pages": result.pages,
        "seconds": round(elapsed, 1),
        "footnote_mismatches": result.footnote_mismatches,
        "unsupported_directives": result.unsupported_directives,
        "words": len(_norm(" ".join(pages_text)).split()),
    }
    if args.compare:
        other = _pdf_pages_text(args.compare)
        mine_words = _norm(" ".join(pages_text)).split()
        other_words = _norm(" ".join(other)).split()
        matcher = difflib.SequenceMatcher(a=other_words, b=mine_words, autojunk=False)
        summary["compare"] = {
            "pdf": str(args.compare),
            "pages": len(other),
            "page_delta": result.pages - len(other),
            "words": len(other_words),
            "word_similarity": round(matcher.ratio(), 4),
            "first_page_starts": {
                "this": [re.sub(r"\s+", " ", t[:60]) for t in pages_text],
                "other": [re.sub(r"\s+", " ", t[:60]) for t in other],
            },
        }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"{summary['pdf']}: {summary['pages']} pages, {summary['words']} words, "
              f"{summary['seconds']} s, package {summary['package']}")
        if "compare" in summary:
            c = summary["compare"]
            print(f"  vs {c['pdf']}: {c['pages']} pages (delta {c['page_delta']:+d}), "
                  f"word similarity {c['word_similarity']:.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
