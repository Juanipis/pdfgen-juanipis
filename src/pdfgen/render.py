import os
import pathlib
import sys

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from pdfgen.pagination import LayoutConfig, Paginator
from pdfgen.validator import validate_and_normalize

ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_ROOT / "templates"
TEMPLATE_NAME = "boletin_template.html.jinja"
CSS_PATH = TEMPLATE_DIR / "boletin.css"
OUTPUT_PDF = ROOT / "output.pdf"
FONTS_CONF = ROOT / "fonts.conf"


def build_sample_data():
    banner = str((PACKAGE_ROOT / "assets" / "banner.png").resolve())
    banner_clean = str((PACKAGE_ROOT / "assets" / "banner-clean.png").resolve())
    logo = str((PACKAGE_ROOT / "assets" / "logo.png").resolve())

    table_header = [
        {
            "title": "Consumo insuficiente de alimentos (Millones)",
            "months": ["Enero", "Febrero", "Marzo"],
        },
        {
            "title": "Estrategias de afrontamiento del hambre (Millones)",
            "months": ["Enero", "Febrero", "Marzo"],
        },
    ]

    small_rows = [
        {"dep": "Amazonas", "vals": ["0,05", "0,04", "0,04", "0,05", "0,04", "0,04"]},
        {"dep": "Antioquia", "vals": ["1,48", "1,63", "1,76", "1,82", "1,90", "2,05"]},
        {"dep": "Arauca", "vals": ["0,15", "0,14", "0,11", "0,16", "0,12", "0,11"]},
    ]

    medium_rows = [
        {"dep": "Atlantico", "vals": ["0,81", "0,69", "0,76", "0,63", "0,76", "0,76"]},
        {"dep": "Bogota D. C.", "vals": ["1,88", "2,07", "2,23", "2,30", "2,41", "2,61"]},
        {"dep": "Bolivar", "vals": ["0,61", "0,67", "0,72", "0,75", "0,78", "0,85"]},
        {"dep": "Boyaca", "vals": ["0,28", "0,30", "0,33", "0,34", "0,35", "0,38"]},
        {"dep": "Caldas", "vals": ["0,20", "0,22", "0,24", "0,24", "0,26", "0,28"]},
        {"dep": "Caqueta", "vals": ["0,21", "0,20", "0,17", "0,24", "0,18", "0,17"]},
    ]

    large_rows = [
        {"dep": "Cundinamarca", "vals": ["0,76", "0,84", "0,90", "0,93", "0,98", "1,06"]},
        {"dep": "Guainia", "vals": ["0,04", "0,03", "0,03", "0,04", "0,03", "0,03"]},
        {"dep": "Guaviare", "vals": ["0,06", "0,06", "0,05", "0,07", "0,05", "0,05"]},
        {"dep": "Huila", "vals": ["0,27", "0,30", "0,32", "0,33", "0,35", "0,37"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
        {"dep": "La Guajira", "vals": ["0,36", "0,30", "0,28", "0,38", "0,40", "0,43"]},
        {"dep": "Meta", "vals": ["0,41", "0,38", "0,32", "0,46", "0,34", "0,32"]},
        {"dep": "Santander", "vals": ["0,50", "0,56", "0,60", "0,62", "0,65", "0,70"]},
    ]

    data = {
        "title": "Reporte de Indicadores - Ejemplo Generico 2024",
        "theme": {
            "header_banner_path": banner,
            "header_banner_path_cont": banner_clean,
            "header_logo_path": logo,
            "title_line1": "Reporte de Indicadores y Tendencias",
            "title_line2": "Ejemplo Generico - 2024",
            "footer_site": "example.org",
            "footer_phone": "Contacto: +1 555 0100",
            "show_header_titles": False,
        },
        "sections": [
            {
                "title": "I. Indice de Riesgo de la situacion alimentaria en Colombia",
                "subtitle": "Historico de Mapas Departamentales de la Situacion Alimentaria en Colombia durante el Primer Trimestre del 2024.",
                "content": [
                    {
                        "type": "text",
                        "text": [
                            "La Red de Bancos de Alimentos de Colombia ABACO presenta un analisis comparativo de indicadores clave sobre la situacion alimentaria y nutricional del pais en el I trimestre del ano 2024.",
                            "Este cambio resalta la necesidad de un seguimiento continuo y detallado de las tendencias en seguridad alimentaria a lo largo del ano.",
                        ],
                        "refs": [
                            "1 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 31 January 2024. P. 2",
                            "2 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 19 February 2024. P. 2",
                        ],
                    },
                    {
                        "type": "table",
                        "table": {
                            "groups": table_header,
                            "rows": small_rows,
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                ],
            },
            {
                "title": "II. Indicadores de prevalencia de Consumo Insuficiente de Alimentos.",
                "content": [
                    {
                        "type": "table",
                        "table": {
                            "groups": table_header,
                            "rows": medium_rows,
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                        "refs": [
                            "4 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 31 January 2024. P. 2",
                            "5 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 19 February 2024. P. 2",
                            "6 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 31 March 2024. P. 2",
                        ],
                    }
                ],
            },
            {
                "title": "III. Estrategias de Afrontamiento a las Crisis Basadas en la Alimentacion.",
                "content": [
                    {
                        "type": "table",
                        "table": {
                            "groups": table_header,
                            "rows": large_rows,
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    }
                ],
            },
        ],
    }
    return data


def _paragraphs_from_text(text):
    if isinstance(text, list):
        return [t.strip() for t in text if t and t.strip()]
    if not text:
        return []
    chunks = []
    for block in str(text).split("\n\n"):
        block = " ".join([line.strip() for line in block.splitlines()]).strip()
        if block:
            chunks.append(block)
    return chunks


def _section_heading_html(title, subtitle):
    html = f"<div class=\"section-title\">{title}</div>" if title else ""
    if subtitle:
        html += f"<div class=\"section-subtitle\">{subtitle}</div>"
    return html


def _map_grid_html(items):
    blocks = []
    for item in items:
        path = item.get("path")
        label = item.get("label", "")
        blocks.append(
            "<div class=\"map-item\">"
            f"<img class=\"map-img\" src=\"{path}\" alt=\"{label}\" />"
            f"<div class=\"map-label\">{label}</div>"
            "</div>"
        )
    return "<div class=\"map-grid\">" + "".join(blocks) + "</div>"


def _figure_html(path, caption, wide=False):
    cls = "figure figure-wide" if wide else "figure"
    html = f"<img class=\"{cls}\" src=\"{path}\" alt=\"{caption}\" />"
    if caption:
        html += f"<div class=\"figure-caption\">{caption}</div>"
    return html


def _blocks_from_section(section):
    blocks = []
    title_html = _section_heading_html(section.get("title"), section.get("subtitle"))
    if title_html:
        blocks.append({"type": "html", "html": title_html, "keep_with_next": True})

    for item in section.get("content", []):
        itype = item.get("type", "text")
        if itype == "text":
            paragraphs = _paragraphs_from_text(item.get("text"))
            if paragraphs:
                html = "".join(f"<p>{p}</p>" for p in paragraphs)
                block = {"type": "html", "html": html}
            else:
                continue
        elif itype == "figure":
            block = {
                "type": "html",
                "html": _figure_html(item.get("path"), item.get("caption", ""), item.get("wide", False)),
            }
        elif itype == "map_grid":
            html = _map_grid_html(item.get("items", []))
            if item.get("caption"):
                html += f"<div class=\"figure-caption\">{item['caption']}</div>"
            if item.get("source"):
                html += f"<div class=\"figure-source\">{item['source']}</div>"
            block = {"type": "html", "html": html}
        elif itype == "table":
            block = {"type": "table", "table": item.get("table", {})}
        else:
            block = {"type": "html", "html": item.get("html", "")}

        if item.get("refs"):
            block["refs"] = item.get("refs")
        blocks.append(block)

    if section.get("refs") and blocks:
        blocks[0].setdefault("refs", [])
        blocks[0]["refs"].extend(section["refs"])

    return blocks


def _build_pages_from_sections(data):
    theme = data.get("theme", {})
    pages = []
    footer_notes = []
    refs_catalog = data.get("refs_catalog", {})

    if data.get("cover"):
        cover = dict(theme)
        cover.update(data["cover"])
        cover["cover"] = True
        pages.append(cover)

    blocks = []
    for section in data.get("sections", []):
        blocks.extend(_blocks_from_section(section))
        if section.get("footer_notes"):
            footer_notes.extend(section["footer_notes"])

    pages.append({
        **theme,
        "intro": "",
        "blocks": blocks,
        "refs": [],
        "refs_catalog": refs_catalog,
        "footer_notes": footer_notes,
        "page_number": "1",
    })

    data["pages"] = pages
    return data


def render_pdf(
    data,
    output_path=OUTPUT_PDF,
    paginate=True,
    validate=True,
    template_dir=None,
    css_path=None,
    fonts_conf=None,
    css_extra=None,
    root_dir=None,
):
    root_dir = pathlib.Path(root_dir) if root_dir else ROOT
    template_dir = pathlib.Path(template_dir) if template_dir else TEMPLATE_DIR
    css_path = pathlib.Path(css_path) if css_path else CSS_PATH
    fonts_conf = pathlib.Path(fonts_conf) if fonts_conf else None

    if fonts_conf and fonts_conf.exists():
        os.environ.setdefault("FONTCONFIG_FILE", str(fonts_conf))
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template(TEMPLATE_NAME)

    if "sections" in data and "pages" not in data:
        data = _build_pages_from_sections(data)

    if validate:
        data, warnings = validate_and_normalize(data, root_dir=root_dir)
        for warning in warnings:
            print(f"[validate] {warning}")

    layout = LayoutConfig()
    paginator = Paginator(layout, str(css_path), str(root_dir), fonts_conf_path=str(fonts_conf))
    if paginate:
        data["pages"] = paginator.paginate(data["pages"])
    data["layout"] = layout.to_template()

    html = template.render(**data)

    stylesheets = [CSS(filename=str(css_path))]
    if css_extra:
        stylesheets.append(CSS(string=str(css_extra)))

    HTML(string=html, base_url=str(root_dir)).write_pdf(output_path, stylesheets=stylesheets)

    print(f"Wrote {output_path}")


def main():
    data = build_sample_data()
    render_pdf(data)


if __name__ == "__main__":
    main()
