import copy
import pathlib
import random
from typing import Dict, List

import fitz

from pagination import LayoutConfig, Paginator
from render import FONTS_CONF, render_pdf

ROOT = pathlib.Path(__file__).resolve().parent
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


def build_base_page():
    banner = str((ROOT / "assets" / "header-banner.png").resolve())
    logo = str((ROOT / "assets" / "logo.png").resolve())
    return {
        "header_banner_path": banner,
        "header_logo_path": logo,
        "title_line1": "Boletin sobre la Situacion Alimentaria y Nutricional en Colombia - Primer",
        "title_line2": "Trimestre 2024.",
        "intro": "",
        "blocks": [],
        "refs": [],
        "footer_notes": [],
        "page_number": "1",
        "footer_site": "abaco.org.co",
        "footer_phone": "Telefono: 313 245 79 78",
    }


def build_case_long_header_intro():
    page = build_base_page()
    page["title_line1"] = (
        "Boletin sobre la Situacion Alimentaria y Nutricional en Colombia y la Region Andina "
        "con Enfasis en Tendencias Recientes y Prospectivas"
    )
    page["title_line2"] = "Informe Especial de Resultados Consolidado - Primer Trimestre 2024"

    words = "situacion alimentaria seguridad nutricional hogares vulnerables seguimiento continuo".split()
    intro = " ".join(make_text(words, 18) for _ in range(5))
    page["intro"] = intro

    page["blocks"] = [
        {
            "type": "html",
            "html": """
<div class=\"section-title\"><span class=\"roman\">I.</span> Resumen ejecutivo</div>
<p>"""
            + intro
            + "</p>",
        },
        {
            "type": "table",
            "table": {
                "groups": make_table_header(),
                "rows": make_rows(20),
                "total_width": 532.66,
                "dep_width": 120.0,
            },
        },
    ]

    return {
        "title": "Stress - Long Header + Intro",
        "pages": [page],
    }


def build_case_huge_table():
    page = build_base_page()
    page["blocks"] = [
        {
            "type": "html",
            "html": """
<div class=\"section-title\"><span class=\"roman\">I.</span> Tabla masiva</div>
<div class=\"section-subtitle\">Mas de 200 filas con nombres largos.</div>
""",
        },
        {
            "type": "table",
            "table": {
                "groups": make_table_header(),
                "rows": make_rows(220, long_names=True),
                "total_width": 532.66,
                "dep_width": 120.0,
            },
        },
    ]

    return {
        "title": "Stress - Huge Table",
        "pages": [page],
    }


def build_case_many_tables():
    page = build_base_page()
    blocks = []
    for idx in range(1, 5):
        blocks.append(
            {
                "type": "html",
                "html": (
                    f"<div class=\"section-title\"><span class=\"roman\">{idx}.</span> "
                    f"Seccion {idx}</div>"
                ),
            }
        )
        blocks.append(
            {
                "type": "table",
                "table": {
                    "groups": make_table_header(),
                    "rows": make_rows(50, prefix=f"Dept {idx}"),
                    "total_width": 532.66,
                    "dep_width": 120.0,
                },
            }
        )
    page["blocks"] = blocks
    return {
        "title": "Stress - Many Tables",
        "pages": [page],
    }


def build_case_long_refs_notes():
    page = build_base_page()
    page["blocks"] = [
        {
            "type": "html",
            "html": """
<div class=\"section-title\"><span class=\"roman\">I.</span> Referencias extensas</div>
<p>Contenido breve para maximizar el espacio de referencias.</p>
""",
        }
    ]

    refs = [
        f"{i} Fuente extensa con descripcion y detalles adicionales para pruebas de pie de pagina."
        for i in range(1, 18)
    ]
    notes = [
        "Nota: este texto de prueba sirve para evaluar el ajuste de notas al pie de pagina."
        for _ in range(8)
    ]

    page["refs"] = refs
    page["footer_notes"] = notes

    return {
        "title": "Stress - Long Refs/Notes",
        "pages": [page],
    }


def build_case_dense_html():
    page = build_base_page()
    paragraph = (
        "<p>"
        + " ".join(
            "texto" for _ in range(200)
        )
        + "</p>"
    )
    html = (
        "<div class=\"section-title-serif\">"
        "III. Texto denso con muchos parrafos</div>"
        + "".join(paragraph for _ in range(10))
    )
    page["blocks"] = [{"type": "html", "html": html}]
    return {
        "title": "Stress - Dense HTML",
        "pages": [page],
    }


def build_case_mixed_overflow():
    page = build_base_page()
    page["title_line1"] = (
        "Boletin de Seguimiento Intersemestral con Analisis Expandido de Indicadores"
    )
    words = "monitoreo hogares vulnerables intervencion seguridad alimentaria tendencia".split()
    page["intro"] = " ".join(make_text(words, 20) for _ in range(7))

    html_block = """
<div class=\"section-title\"><span class=\"roman\">I.</span> Panorama general</div>
<p>""" + " ".join(make_text(words, 16) for _ in range(6)) + "</p>"

    page["blocks"] = [
        {
            "type": "html",
            "html": html_block,
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
        {
            "type": "html",
            "html": """
<div class=\"section-title-serif\">II. Comentarios adicionales</div>
<p>""" + " ".join(make_text(words, 18) for _ in range(4)) + "</p>",
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
    ]

    page["refs"] = [
        f"{i} Fuente adicional con notas detalladas para pruebas de stress." for i in range(1, 6)
    ]

    return {
        "title": "Stress - Mixed Overflow",
        "pages": [page],
    }


def build_case_extreme_table_headers():
    page = build_base_page()
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
    page["blocks"] = [
        {
            "type": "html",
            "html": """
<div class=\"section-title\"><span class=\"roman\">I.</span> Encabezados extensos</div>
<p>Tabla con encabezados largos y muchas columnas.</p>
""",
        },
        {
            "type": "table",
            "table": {
                "groups": header,
                "rows": make_rows(30, val_count=12),
                "total_width": 532.66,
                "dep_width": 120.0,
            },
        },
    ]

    return {
        "title": "Stress - Extended Headers",
        "pages": [page],
    }


def build_case_sparse_sections():
    page = build_base_page()
    page["blocks"] = [
        {
            "type": "html",
            "html": """
<div class=\"section-title\"><span class=\"roman\">I.</span> Seccion corta</div>
<p>Contenido breve.</p>
""",
        },
        {
            "type": "html",
            "html": """
<div class=\"section-title\"><span class=\"roman\">II.</span> Seccion con salto</div>
<p>""" + " ".join("texto" for _ in range(120)) + "</p>",
        },
    ]

    return {
        "title": "Stress - Sparse Sections",
        "pages": [page],
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


def run_case(case_name: str):
    builder = CASES[case_name]
    data = builder()

    output_dir = OUTPUT_DIR / case_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_dir / "output.pdf"

    layout = LayoutConfig()
    paginator = Paginator(layout, str(CSS_PATH), str(ROOT), fonts_conf_path=str(FONTS_CONF))

    paginated = paginator.paginate(copy.deepcopy(data["pages"]))
    data["pages"] = paginated
    data["layout"] = layout.to_template()

    render_pdf(data, output_path=output_pdf, paginate=False)
    issues = validate_pages(paginator, paginated)
    render_pngs(output_pdf, output_dir)

    return output_pdf, issues


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    random.seed(42)
    failures = []

    for case_name in CASES:
        output_pdf, issues = run_case(case_name)
        if issues:
            failures.append((case_name, issues))
        print(f"Case {case_name}: wrote {output_pdf} ({'issues' if issues else 'ok'})")
        for issue in issues:
            print(f"  - {issue}")

    if failures:
        raise SystemExit("Stress harness found layout issues.")


if __name__ == "__main__":
    main()
