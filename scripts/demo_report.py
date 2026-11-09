import math
import os
import pathlib
import random
import sys

import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PACKAGE_ASSETS = ROOT / "src" / "pdfgen_juanipis" / "assets"

from pdfgen_juanipis.render import render_pdf, FONTS_CONF

ASSETS = ROOT / "tmp_assets"
CHARTS_DIR = ASSETS / "charts"


def generate_charts():
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    # Chart 1: Trend line
    months = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    series_a = [40 + 5 * math.sin(i / 2) + i * 0.8 for i in range(12)]
    series_b = [35 + 6 * math.cos(i / 3) + i * 0.6 for i in range(12)]

    plt.figure(figsize=(6.4, 3.2), dpi=120)
    plt.plot(months, series_a, marker="o", label="Indice de riesgo (urbano)")
    plt.plot(months, series_b, marker="o", label="Indice de riesgo (rural)")
    plt.title("Evolucion mensual del indice de riesgo, 2024")
    plt.ylabel("Puntos (0-100)")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend(loc="upper left", frameon=False)
    plt.tight_layout()
    chart1 = CHARTS_DIR / "chart_trend.png"
    plt.savefig(chart1)
    plt.close()

    # Chart 2: Bar comparison
    departments = ["Bogota", "Antioquia", "Valle", "Atlantico", "Bolivar", "Cauca"]
    values = [56, 48, 43, 39, 35, 31]
    plt.figure(figsize=(6.4, 3.2), dpi=120)
    plt.bar(departments, values, color="#2e5395")
    plt.title("Consumo insuficiente estimado por departamento")
    plt.ylabel("Miles de hogares")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    chart2 = CHARTS_DIR / "chart_bar.png"
    plt.savefig(chart2)
    plt.close()

    # Chart 3: Scenario area
    horizon = list(range(1, 9))
    optimistic = [20 + i * 1.1 for i in horizon]
    base = [24 + i * 1.5 for i in horizon]
    stress = [28 + i * 2.2 for i in horizon]

    plt.figure(figsize=(6.4, 3.2), dpi=120)
    plt.fill_between(horizon, optimistic, base, color="#8fbcd4", alpha=0.4, label="Rango probable")
    plt.plot(horizon, base, color="#2e5395", label="Escenario base")
    plt.plot(horizon, stress, color="#f58534", label="Escenario estres")
    plt.title("Proyeccion trimestral de hogares en riesgo")
    plt.xlabel("Trimestres")
    plt.ylabel("Miles de hogares")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend(frameon=False)
    plt.tight_layout()
    chart3 = CHARTS_DIR / "chart_projection.png"
    plt.savefig(chart3)
    plt.close()

    return {
        "trend": chart1,
        "bar": chart2,
        "projection": chart3,
    }


def long_paragraph(sentences=5):
    vocab = [
        "seguridad", "alimentaria", "hogares", "vulnerables", "resiliencia", "territorial",
        "monitoreo", "tendencias", "nutricional", "intervencion", "impacto", "comunitario",
        "distribucion", "cadena", "logistica", "apoyo", "institucional", "riesgo",
    ]
    output = []
    for _ in range(sentences):
        words = [random.choice(vocab) for _ in range(18)]
        output.append(" ".join(words).capitalize() + ".")
    return " ".join(output)


def build_demo_data(charts):
    banner = str((PACKAGE_ASSETS / "banner.png").resolve())
    banner_clean = str((PACKAGE_ASSETS / "banner-clean.png").resolve())
    logo = str((PACKAGE_ASSETS / "logo.png").resolve())

    table_header = [
        {
            "title": "Consumo insuficiente de alimentos (Miles)",
            "months": ["Ene", "Feb", "Mar"],
        },
        {
            "title": "Estrategias de afrontamiento (Miles)",
            "months": ["Ene", "Feb", "Mar"],
        },
    ]

    rows = [
        {"dep": "Bogota D.C.", "vals": ["120", "128", "132", "95", "97", "101"]},
        {"dep": "Antioquia", "vals": ["86", "90", "94", "70", "72", "75"]},
        {"dep": "Valle", "vals": ["64", "67", "69", "54", "56", "58"]},
        {"dep": "Atlantico", "vals": ["44", "46", "49", "36", "37", "39"]},
        {"dep": "Bolivar", "vals": ["38", "40", "41", "32", "33", "34"]},
        {"dep": "Cauca", "vals": ["31", "33", "34", "25", "26", "28"]},
    ]

    return {
        "title": "Informe demo - Resultados ficticios 2024",
        "theme": {
            "header_banner_path": banner,
            "header_banner_path_cont": banner_clean,
            "header_logo_path": logo,
            "title_line1": "Reporte de Indicadores y Tendencias",
            "title_line2": "Informe Especial - Resultados 2024",
            "footer_site": "example.org",
            "footer_phone": "Contacto: +1 555 0100",
            "show_header_titles": False,
        },
        "sections": [
            {
                "title": "I. Panorama general",
                "content": [
                    {
                        "type": "text",
                        "text": long_paragraph(6),
                        "refs": [
                            "1 Estudio ficticio de referencia (2024).",
                            "2 Encuesta simulada de hogares (2023-2024).",
                        ],
                    },
                    {
                        "type": "figure",
                        "path": str(charts["trend"]),
                        "caption": "Figura 1. Evolucion mensual del indice de riesgo (simulado).",
                        "refs": ["3 Modelo estadistico simulado para tendencias."],
                    },
                    {
                        "type": "table",
                        "table": {
                            "groups": table_header,
                            "rows": rows,
                            "total_width": 532.66,
                            "dep_width": 120.0,
                        },
                        "refs": ["4 Base territorial de ejemplo (2024)."],
                    },
                    {
                        "type": "figure",
                        "path": str(charts["bar"]),
                        "caption": "Figura 2. Consumo insuficiente estimado por departamento.",
                        "refs": ["5 Simulacion comparativa departamental."],
                    },
                ],
                "refs": ["Nota general: Todas las cifras son ficticias y solo demostrativas."],
            },
            {
                "title": "II. Escenarios de proyeccion",
                "content": [
                    {
                        "type": "text",
                        "text": long_paragraph(7),
                        "refs": ["6 Escenario base simulado."],
                    },
                    {
                        "type": "figure",
                        "path": str(charts["projection"]),
                        "caption": "Figura 3. Proyeccion trimestral de hogares en riesgo.",
                        "refs": ["7 Modelo de proyeccion ficticio."],
                    },
                ],
                "refs": [
                    "10 Resumen ejecutivo ficticio del informe tecnico.",
                    "11 Documento de soporte simulado.",
                ],
            },
            {
                "title": "III. Recomendaciones",
                "content": [
                    {
                        "type": "text",
                        "text": long_paragraph(8),
                        "refs": [
                            "8 Guia simulada de respuesta institucional.",
                            "9 Lineamientos de coordinacion ficticios.",
                        ],
                    },
                ],
                "footer_notes": [
                    "Nota: Datos simulados para validar estilos y consistencia visual.",
                ],
            },
        ],
    }


def main():
    os.environ.setdefault("FONTCONFIG_FILE", str(FONTS_CONF))
    random.seed(2024)
    charts = generate_charts()
    data = build_demo_data(charts)
    output_path = ROOT / "demo_output.pdf"
    render_pdf(data, output_path=output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
