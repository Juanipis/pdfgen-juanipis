import copy
import pathlib
import random
import sys
from typing import Dict, List

import fitz

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfgen.pagination import LayoutConfig, Paginator
from pdfgen.render import FONTS_CONF, render_pdf, _build_pages_from_sections

CSS_PATH = ROOT / "template" / "boletin.css"
OUTPUT_DIR = ROOT / "stress_outputs"


def make_table_header():
    return [
        {
            "title": "Consumo insuficiente de alimentos (Millones)",
            "months": ["Enero", "Febrero", "Marzo"],
        },
        {
            "title": "Estrategias de afrontamiento del hambre (Millones)",
            "months": ["Enero", "Febrero", "Marzo"],
        },
    ]


def make_rows(count, prefix="Dept", val_count=6, long_names=False):
    rows = []
    for idx in range(1, count + 1):
        name = f"{prefix} {idx}"
        if long_names:
            name += " " + "-".join(["Departamento"] * 4)
        vals = [f"{random.random():.2f}" for _ in range(val_count)]
        rows.append({"dep": name, "vals": vals})
    return rows


def make_text(words, sentence_len=14):
    tokens = [random.choice(words) for _ in range(sentence_len)]
    return " ".join(tokens).capitalize() + "."


def build_theme():
    banner = str((ROOT / "assets" / "header-banner.png").resolve())
    logo = str((ROOT / "assets" / "logo.png").resolve())
    return {
        "header_banner_path": banner,
        "header_logo_path": logo,
        "title_line1": "Reporte de Indicadores y Tendencias - Primer",
        "title_line2": "Trimestre 2024",
        "footer_site": "example.org",
        "footer_phone": "Contacto: +1 555 0100",
        "show_header_titles": False,
    }


def build_case_long_header_intro():
    theme = build_theme()
    theme["title_line1"] = (
        "Boletin sobre la Situacion Alimentaria y Nutricional en Colombia y la Region Andina "
        "con Enfasis en Tendencias Recientes y Prospectivas"
    )
    theme["title_line2"] = "Informe Especial de Resultados Consolidado - Primer Trimestre 2024"

    words = "situacion alimentaria seguridad nutricional hogares vulnerables seguimiento continuo".split()
    intro = " ".join(make_text(words, 18) for _ in range(5))

    return {
        "title": "Stress - Long Header + Intro",
        "theme": theme,
        "sections": [
            {
                "title": "I. Resumen ejecutivo",
                "content": [
                    {"type": "text", "text": intro},
                    {
                        "type": "table",
                        "table": {
                            "groups": make_table_header(),
                            "rows": make_rows(20),
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                ],
            }
        ],
    }


def build_case_huge_table():
    return {
        "title": "Stress - Huge Table",
        "theme": build_theme(),
        "sections": [
            {
                "title": "I. Tabla masiva",
                "subtitle": "Mas de 200 filas con nombres largos.",
                "content": [
                    {
                        "type": "table",
                        "table": {
                            "groups": make_table_header(),
                            "rows": make_rows(220, long_names=True),
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    }
                ],
            }
        ],
    }


def build_case_many_tables():
    return {
        "title": "Stress - Many Tables",
        "theme": build_theme(),
        "sections": [
            {
                "title": f"{idx}. Seccion {idx}",
                "content": [
                    {
                        "type": "table",
                        "table": {
                            "groups": make_table_header(),
                            "rows": make_rows(50, prefix=f"Dept {idx}"),
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    }
                ],
            }
            for idx in range(1, 5)
        ],
    }


def build_case_long_refs_notes():
    refs = [
        f"{i} Fuente extensa con descripcion y detalles adicionales para pruebas de pie de pagina."
        for i in range(1, 18)
    ]
    notes = [
        "Nota: este texto de prueba sirve para evaluar el ajuste de notas al pie de pagina."
        for _ in range(8)
    ]

    return {
        "title": "Stress - Long Refs/Notes",
        "theme": build_theme(),
        "sections": [
            {
                "title": "I. Referencias extensas",
                "content": [
                    {
                        "type": "text",
                        "text": "Contenido breve para maximizar el espacio de referencias.",
                        "refs": refs,
                    }
                ],
                "footer_notes": notes,
            }
        ],
    }


def build_case_dense_html():
    paragraph = " ".join("texto" for _ in range(200))
    return {
        "title": "Stress - Dense HTML",
        "theme": build_theme(),
        "sections": [
            {
                "title": "III. Texto denso con muchos parrafos",
                "content": [
                    {"type": "text", "text": [paragraph for _ in range(10)]}
                ],
            }
        ],
    }


def build_case_mixed_overflow():
    theme = build_theme()
    theme["title_line1"] = (
        "Boletin de Seguimiento Intersemestral con Analisis Expandido de Indicadores"
    )
    words = "monitoreo hogares vulnerables intervencion seguridad alimentaria tendencia".split()
    intro = " ".join(make_text(words, 20) for _ in range(7))

    return {
        "title": "Stress - Mixed Overflow",
        "theme": theme,
        "sections": [
            {
                "title": "I. Panorama general",
                "content": [
                    {
                        "type": "text",
                        "text": intro,
                        "refs": [
                            "1 Fuente ligada al panorama general para pruebas de pie de pagina.",
                            "2 Segunda referencia para pruebas de ubicacion.",
                        ],
                    },
                    {
                        "type": "table",
                        "table": {
                            "groups": make_table_header(),
                            "rows": make_rows(80, long_names=True),
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                ],
                "refs": [
                    f"{i} Fuente adicional con notas detalladas para pruebas de stress." for i in range(1, 6)
                ],
            },
            {
                "title": "II. Comentarios adicionales",
                "content": [
                    {
                        "type": "text",
                        "text": " ".join(make_text(words, 18) for _ in range(4)),
                        "refs": ["3 Nota asociada a comentarios adicionales."],
                    },
                    {
                        "type": "table",
                        "table": {
                            "groups": make_table_header(),
                            "rows": make_rows(60),
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                ],
            },
        ],
    }


def build_case_extreme_table_headers():
    header = [
        {
            "title": "Consumo insuficiente de alimentos y otras categorias extendidas (Millones)",
            "months": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio"],
        },
        {
            "title": "Estrategias de afrontamiento del hambre y resiliencia (Millones)",
            "months": ["Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
        },
    ]
    return {
        "title": "Stress - Extended Headers",
        "theme": build_theme(),
        "sections": [
            {
                "title": "I. Encabezados extensos",
                "content": [
                    {"type": "text", "text": "Tabla con encabezados largos y muchas columnas."},
                    {
                        "type": "table",
                        "table": {
                            "groups": header,
                            "rows": make_rows(30, val_count=12),
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                ],
            }
        ],
    }


def build_case_sparse_sections():
    return {
        "title": "Stress - Sparse Sections",
        "theme": build_theme(),
        "sections": [
            {
                "title": "I. Seccion corta",
                "content": [{"type": "text", "text": "Contenido breve."}],
            },
            {
                "title": "II. Seccion con salto",
                "content": [{"type": "text", "text": " ".join("texto" for _ in range(120))}],
            },
        ],
    }


def build_case_random(name_suffix: str):
    theme = build_theme()
    words = "seguridad alimentaria riesgos datos tendencias vulnerables impacto".split()

    sections = []
    for idx in range(1, random.randint(3, 6)):
        content = []
        for _ in range(random.randint(2, 4)):
            if random.random() < 0.5:
                content.append({
                    "type": "text",
                    "text": " ".join(make_text(words, 16) for _ in range(random.randint(2, 4))),
                    "refs": [f"{idx} Fuente simulada {random.randint(1, 99)}."],
                })
            else:
                content.append({
                    "type": "table",
                    "table": {
                        "groups": make_table_header(),
                        "rows": make_rows(random.randint(12, 50)),
                        "total_width": 532.66,
                        "dep_width": 120.0,
                    },
                })
        sections.append({"title": f"{idx}. Seccion aleatoria", "content": content})

    return {
        "title": f"Stress - Random {name_suffix}",
        "theme": theme,
        "sections": sections,
    }


def build_case_inline_refs_split():
    theme = build_theme()
    words = "seguridad alimentaria riesgos datos tendencias vulnerables impacto".split()
    long_text = " ".join(make_text(words, 18) for _ in range(20))
    # Insert many inline refs to force distribution across chunks.
    inline_text = (
        f"{long_text} [1] {long_text} [2,3] {long_text} [4-6] "
        f"{long_text} [7] {long_text} [8–10]"
    )
    refs_catalog = {str(i): f"{i} Fuente inline generada para stress." for i in range(1, 11)}

    return {
        "title": "Stress - Inline Refs Split",
        "theme": theme,
        "refs_catalog": refs_catalog,
        "sections": [
            {
                "title": "I. Texto largo con referencias inline",
                "content": [
                    {"type": "text", "text": inline_text},
                ],
            }
        ],
    }


CASES = {
    "long_header_intro": build_case_long_header_intro,
    "huge_table": build_case_huge_table,
    "many_tables": build_case_many_tables,
    "long_refs_notes": build_case_long_refs_notes,
    "dense_html": build_case_dense_html,
    "mixed_overflow": build_case_mixed_overflow,
    "extended_headers": build_case_extreme_table_headers,
    "sparse_sections": build_case_sparse_sections,
    "inline_refs_split": build_case_inline_refs_split,
}


def validate_pages(paginator: Paginator, pages: List[Dict], tolerance_pt: float = 2.0) -> List[str]:
    issues = []
    for idx, page in enumerate(pages, start=1):
        _, _, header_bottom, _, _ = paginator._compute_header_positions(
            page, show_titles=page.get("show_header_titles", True)
        )
        include_intro = bool(page.get("intro"))
        layout_state = paginator._compute_layout_state(
            page,
            header_bottom,
            include_intro,
            compact_top=not page.get("show_header_titles", True),
        )
        has_meta = bool(page.get("refs") or page.get("footer_notes"))
        limit = (
            layout_state.content_height_meta_pt
            if has_meta
            else layout_state.content_height_base_pt
        )

        total_height = 0.0
        for block in page.get("blocks", []):
            if block.get("type") == "table":
                table = block.get("table", {})
                show_header = table.get("show_header", True)
                total_height += paginator.measurer.measure_table(table, show_header)
            else:
                total_height += paginator.measurer.measure_html(block.get("html", ""))

        if total_height - limit > tolerance_pt:
            issues.append(
                f"Page {idx}: content height {total_height:.2f}pt exceeds limit {limit:.2f}pt"
            )
    return issues


def render_pngs(pdf_path: pathlib.Path, output_dir: pathlib.Path, zoom=2):
    doc = fitz.open(pdf_path)
    for page_index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img_path = output_dir / f"page-{page_index}.png"
        pix.save(str(img_path))


def run_case(case_name: str, data: Dict):
    output_dir = OUTPUT_DIR / case_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_dir / "output.pdf"

    layout = LayoutConfig()
    paginator = Paginator(layout, str(CSS_PATH), str(ROOT), fonts_conf_path=str(FONTS_CONF))

    # Build pages for validation
    build_data = _build_pages_from_sections(copy.deepcopy(data))
    paginated = paginator.paginate(copy.deepcopy(build_data["pages"]))

    render_pdf(data, output_path=output_pdf, paginate=True)
    issues = validate_pages(paginator, paginated)
    render_pngs(output_pdf, output_dir)

    return output_pdf, issues


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    random.seed(42)
    failures = []

    for case_name, builder in CASES.items():
        output_pdf, issues = run_case(case_name, builder())
        if issues:
            failures.append((case_name, issues))
        print(f"Case {case_name}: wrote {output_pdf} ({'issues' if issues else 'ok'})")
        for issue in issues:
            print(f"  - {issue}")

    for idx in range(1, 6):
        case_name = f"random_{idx}"
        output_pdf, issues = run_case(case_name, build_case_random(case_name))
        if issues:
            failures.append((case_name, issues))
        print(f"Case {case_name}: wrote {output_pdf} ({'issues' if issues else 'ok'})")
        for issue in issues:
            print(f"  - {issue}")

    if failures:
        raise SystemExit("Stress harness found layout issues.")


if __name__ == "__main__":
    main()
