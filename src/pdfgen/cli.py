import argparse
import json
import pathlib
import sys
import tempfile

from pdfgen.api import PDFGen, PDFGenConfig


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
    parser = argparse.ArgumentParser(description="pdfgen CLI")
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

    validate = sub.add_parser("validate", help="Validate JSON/YAML input against schema")
    validate.add_argument("input", help="Path to JSON/YAML data (or - for stdin)")
    validate.add_argument("--root", dest="root_dir", default=".", help="Project root dir")
    validate.add_argument("--format", dest="fmt", default=None, help="Input format: json|yaml")

    args = parser.parse_args(argv)

    if args.command == "validate":
        from pdfgen.validator import validate_and_normalize

        root_dir = pathlib.Path(args.root_dir)
        data = _load_data(pathlib.Path(args.input), fmt=args.fmt)
        _, warnings = validate_and_normalize(data, root_dir=root_dir)
        for warning in warnings:
            print(f"[validate] {warning}")
        return 0 if not warnings else 1

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


if __name__ == "__main__":
    raise SystemExit(main())
