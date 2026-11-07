"""pdfgen-juanipis command line.

    pdfgen-juanipis html report.html report.pdf [--docx report.docx] [--package NAME]
    pdfgen-juanipis packages [--package-dir DIR]
    pdfgen-juanipis render data.yaml out.pdf        # legacy 0.1 structured data
    pdfgen-juanipis validate data.yaml              # legacy 0.1 schema check
"""

import argparse
import json
import pathlib
import sys
import tempfile


def _build_fonts_conf(fonts_dir: pathlib.Path) -> pathlib.Path:
    fonts_dir = pathlib.Path(fonts_dir).resolve()
    content = f"""<?xml version=\"1.0\"?>
<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">
<fontconfig>
  <dir>{fonts_dir}</dir>
  <cache>
    <dir>~/.cache/fontconfig</dir>
  </cache>
</fontconfig>
"""
    tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".conf")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return pathlib.Path(tmp.name)


def _load_data(path: pathlib.Path, fmt: str | None = None):
    if str(path) == "-":
        raw = sys.stdin.read()
        inferred = fmt or "yaml"
    else:
        raw = path.read_text(encoding="utf-8")
        inferred = fmt or path.suffix.lower().lstrip(".")

    if inferred in ("yaml", "yml"):
        try:
            import yaml
        except Exception as exc:
            raise SystemExit("PyYAML is required for YAML input. Install with: pip install pyyaml") from exc
        return yaml.safe_load(raw)

    # default JSON
    return json.loads(raw)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="pdfgen-juanipis CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="Render a PDF from JSON/YAML")
    render.add_argument("input", help="Path to JSON/YAML data (or - for stdin)")
    render.add_argument("output", help="Output PDF path")
    render.add_argument("--root", dest="root_dir", default=".", help="Project root dir")
    render.add_argument("--template-dir", dest="template_dir", default=None)
    render.add_argument("--css", dest="css_path", default=None)
    render.add_argument("--fonts-conf", dest="fonts_conf", default=None)
    render.add_argument("--fonts-dir", dest="fonts_dir", default=None)
    render.add_argument("--css-extra", dest="css_extra", default=None, help="Extra CSS string")
    render.add_argument("--format", dest="fmt", default=None, help="Input format: json|yaml")
    render.add_argument("--no-validate", action="store_true")
    render.add_argument("--no-paginate", action="store_true")
    render.add_argument("--stdout", action="store_true", help="Write PDF bytes to stdout")

    html = sub.add_parser("html", help="Render an HTML document to PDF (and optionally DOCX)")
    html.add_argument("input", help="Path to the HTML file (or - for stdin)")
    html.add_argument("output", help="Output PDF path")
    html.add_argument("--docx", dest="docx_path", default=None, help="Also write a .docx here")
    html.add_argument("--package", dest="package", default=None, help="Template package name")
    html.add_argument(
        "--package-dir", dest="package_dirs", action="append", default=[],
        help="Register a template package directory (or a directory of packages); repeatable",
    )
    html.add_argument(
        "--shared-assets", dest="shared_assets", action="append", default=[],
        help="Asset directory the registered packages fall back to; repeatable",
    )
    html.add_argument("--title", default=None)
    html.add_argument("--subtitle", default=None)
    html.add_argument("--language", default=None, help="BCP 47 tag, default es-CO")
    html.add_argument("--page-numbers", action="store_true", help="Print page numbers")
    html.add_argument("--css-extra", dest="css_extra", default=None, help="Extra CSS string")
    html.add_argument(
        "--allow-root", dest="allowed_roots", action="append", default=[],
        help="Extra local directory images/CSS may be read from; repeatable",
    )
    html.add_argument("--allow-network", action="store_true", help="Allow http(s) resources")

    packages = sub.add_parser("packages", help="List the available template packages")
    packages.add_argument("--package-dir", dest="package_dirs", action="append", default=[])
    packages.add_argument("--shared-assets", dest="shared_assets", action="append", default=[])

    validate = sub.add_parser("validate", help="Validate JSON/YAML input against schema")
    validate.add_argument("input", help="Path to JSON/YAML data (or - for stdin)")
    validate.add_argument("--root", dest="root_dir", default=".", help="Project root dir")
    validate.add_argument("--format", dest="fmt", default=None, help="Input format: json|yaml")

    args = parser.parse_args(argv)

    if args.command in ("html", "packages"):
        return _run_html_command(args)

    if args.command == "validate":
        from pdfgen_juanipis.validator import validate_and_normalize

        root_dir = pathlib.Path(args.root_dir)
        data = _load_data(pathlib.Path(args.input), fmt=args.fmt)
        _, warnings = validate_and_normalize(data, root_dir=root_dir)
        for warning in warnings:
            print(f"[validate] {warning}")
        return 0 if not warnings else 1

    from pdfgen_juanipis.legacy.api import PDFGen, PDFGenConfig

    root_dir = pathlib.Path(args.root_dir)
    config = PDFGenConfig.from_root(root_dir)

    if args.template_dir:
        config.template_dir = pathlib.Path(args.template_dir)
    if args.css_path:
        config.css_path = pathlib.Path(args.css_path)
    if args.fonts_conf:
        config.fonts_conf = pathlib.Path(args.fonts_conf)
    if args.fonts_dir:
        config.fonts_conf = _build_fonts_conf(pathlib.Path(args.fonts_dir))

    data = _load_data(pathlib.Path(args.input), fmt=args.fmt)

    if args.stdout:
        pdf_bytes = PDFGen(config).render_bytes(
            data,
            paginate=not args.no_paginate,
            validate=not args.no_validate,
            css_extra=args.css_extra,
        )
        sys.stdout.buffer.write(pdf_bytes)
        return 0

    PDFGen(config).render(
        data,
        output_path=pathlib.Path(args.output),
        paginate=not args.no_paginate,
        validate=not args.no_validate,
        css_extra=args.css_extra,
    )
    return 0


def _run_html_command(args) -> int:
    from pdfgen_juanipis.packages import PackageRegistry

    registry = PackageRegistry()
    for directory in args.package_dirs:
        registry.register(directory, shared_assets=args.shared_assets or None)

    if args.command == "packages":
        for row in registry.describe():
            marker = "*" if row["default"] else " "
            print(f"{marker} {row['name']:<28} {row['label']}")
        return 0

    from pdfgen_juanipis.options import RenderOptions
    from pdfgen_juanipis.pdf.renderer import HtmlRenderer

    if args.input == "-":
        html_text, source_dir = sys.stdin.read(), None
    else:
        source = pathlib.Path(args.input)
        html_text, source_dir = source.read_text(encoding="utf-8"), source.resolve().parent
    overrides = {
        "title": args.title,
        "subtitle": args.subtitle,
        "language": args.language,
        "css": args.css_extra,
        "template_package": args.package,
    }
    options = RenderOptions().merged(**overrides)
    if args.page_numbers:
        options = options.merged(show_page_numbers=True)
    if args.allowed_roots or args.allow_network:
        options = options.merged(allowed_roots=args.allowed_roots, allow_network=args.allow_network)
    result = HtmlRenderer(options=options, registry=registry).render(
        html_text, pathlib.Path(args.output), source_dir=source_dir,
    )
    print(f"{result.output_path} ({result.pages} pages, package {result.package})")
    if args.docx_path:
        from pdfgen_juanipis.docx_export import DocxRenderer

        outcome = DocxRenderer(options=options, registry=registry).render(
            html_text, pathlib.Path(args.docx_path),
        )
        print(f"{outcome.output_path} (images {outcome.images_embedded}, "
              f"footnotes {outcome.footnotes_attached})")
        for warning in outcome.warnings:
            print(f"[docx] {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
