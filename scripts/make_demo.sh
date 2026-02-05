#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.venv/bin/activate"
fi

python -m pdfgen_juanipis.cli render "$ROOT_DIR/examples/demo.yaml" "$ROOT_DIR/examples/demo.pdf" --root "$ROOT_DIR"

printf "OK: %s\n" "$ROOT_DIR/examples/demo.pdf"
