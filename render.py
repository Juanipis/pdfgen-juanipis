import os
import pathlib
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS

ROOT = pathlib.Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "template"
TEMPLATE_NAME = "boletin_template.html.jinja"
CSS_PATH = TEMPLATE_DIR / "boletin.css"
OUTPUT_PDF = ROOT / "output.pdf"
FONTS_CONF = ROOT / "fonts.conf"


def main():
    os.environ.setdefault("FONTCONFIG_FILE", str(FONTS_CONF))
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template(TEMPLATE_NAME)

    banner = str((ROOT / "assets" / "header-banner.png").resolve())
    logo = str((ROOT / "assets" / "logo.png").resolve())

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
    ]

    data = {
        "title": "Boletin sobre la Situacion Alimentaria y Nutricional en Colombia - Primer Trimestre 2024",
        "pages": [
            {
                "header_banner_path": banner,
                "header_logo_path": logo,
                "title_line1": "Boletin sobre la Situacion Alimentaria y Nutricional en Colombia - Primer",
                "title_line2": "Trimestre 2024.",
                "intro": "La Red de Bancos de Alimentos de Colombia ABACO presenta un analisis comparativo de",
                "blocks": [
                    {
                        "type": "html",
                        "html": """
<div class=\"section-title\"><span class=\"roman\">I.</span> Indice de Riesgo de la situacion alimentaria en Colombia</div>
<div class=\"section-subtitle\">Historico de Mapas Departamentales de la Situacion Alimentaria en Colombia<br/>durante el Primer Trimestre del 2024.</div>
""",
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
                    {
                        "type": "html",
                        "html": """
<div class=\"section-title\"><span class=\"roman\">II.</span> Indicadores de prevalencia de Consumo Insuficiente de Alimentos.</div>
""",
                    },
                    {
                        "type": "table",
                        "table": {
                            "groups": table_header,
                            "rows": medium_rows,
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                    {
                        "type": "html",
                        "html": """
<div class=\"section-title-serif\">III.&nbsp;&nbsp;Estrategias de Afrontamiento a las Crisis Basadas en la<br/>Alimentacion.</div>
""",
                    },
                    {
                        "type": "table",
                        "table": {
                            "groups": table_header,
                            "rows": large_rows,
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                    },
                ],
                "refs": [
                    "1 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 31 January 2024. P. 2",
                    "2 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 19 February 2024. P. 2",
                ],
                "footer_notes": [],
                "page_number": "1",
                "footer_site": "abaco.org.co",
                "footer_phone": "Telefono: 313 245 79 78",
            },
            {
                "header_banner_path": banner,
                "header_logo_path": logo,
                "title_line1": "Boletin sobre la Situacion Alimentaria y Nutricional en Colombia - Primer",
                "title_line2": "Trimestre 2024.",
                "intro": "",
                "blocks": [
                    {
                        "type": "html",
                        "html": """
<p>Este cambio resalta la necesidad de un seguimiento continuo y detallado de las tendencias en seguridad alimentaria a lo largo del ano.</p>
<p>La naturaleza dinamica de la situacion alimentaria exige una vigilancia constante, lo cual es fundamental para implementar de manera oportuna estrategias de intervencion y mitigacion que sean efectivas y adecuadas a las condiciones cambiantes.</p>
""",
                    }
                ],
                "refs": [
                    "4 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 31 January 2024. P. 2",
                    "5 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 19 February 2024. P. 2",
                    "6 World Food Programme (WFP). (2024). HungerMap LIVE: Colombia insight and key trends [PDF]. 31 March 2024. P. 2",
                ],
                "footer_notes": [],
                "page_number": "2",
                "footer_site": "abaco.org.co",
                "footer_phone": "Telefono: 313 245 79 78",
            },
        ],
    }

    html = template.render(**data)

    HTML(string=html, base_url=str(ROOT)).write_pdf(
        OUTPUT_PDF, stylesheets=[CSS(filename=str(CSS_PATH))]
    )

    print(f"Wrote {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
