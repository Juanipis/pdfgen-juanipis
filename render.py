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


def estimate_block_height(block, include_header=True):
    """Estima la altura en puntos de un bloque de contenido."""
    if block["type"] == "html":
        # Estimar por cantidad de texto
        html_text = block["html"]
        lines = html_text.count("<br/>") + html_text.count("</p>") + html_text.count("</div>")
        if "section-title" in html_text:
            return 20 + lines * 14
        return lines * 14 + 10
    elif block["type"] == "table":
        # Altura de tabla: header (2 filas) + filas de datos
        num_rows = len(block["table"]["rows"])
        header_height = 40 if include_header else 0  # 2 filas de header
        row_height = 16  # aprox por fila
        return header_height + (num_rows * row_height) + 16  # + margen


def split_table_block(block, max_rows):
    """
    Divide un bloque de tabla en múltiples bloques si tiene demasiadas filas.
    
    Args:
        block: Bloque de tabla original
        max_rows: Número máximo de filas por bloque
    
    Returns:
        Lista de bloques de tabla divididos
    """
    if block["type"] != "table":
        return [block]
    
    rows = block["table"]["rows"]
    if len(rows) <= max_rows:
        return [block]
    
    # Dividir en múltiples bloques
    result_blocks = []
    for i in range(0, len(rows), max_rows):
        chunk_rows = rows[i:i + max_rows]
        is_first_chunk = (i == 0)
        
        new_block = {
            "type": "table",
            "table": {
                "groups": block["table"]["groups"],
                "rows": chunk_rows,
                "total_width": block["table"]["total_width"],
                "dep_width": block["table"]["dep_width"],
                "show_header": is_first_chunk,  # Solo mostrar header en primer chunk
            }
        }
        result_blocks.append(new_block)
    
    return result_blocks


def auto_paginate_content(pages_data, max_content_height=520):
    """
    Divide automáticamente el contenido en páginas cuando excede el espacio disponible.
    Incluye división inteligente de tablas grandes.
    
    Args:
        pages_data: Lista de objetos page del formato original
        max_content_height: Altura máxima disponible para contenido (en puntos)
    
    Returns:
        Lista de páginas con contenido dividido automáticamente
    """
    result_pages = []
    
    for page_idx, page in enumerate(pages_data):
        current_height = 0
        current_blocks = []
        is_first_page = len(result_pages) == 0
        
        # Altura inicial (intro si existe)
        intro_height = 0
        if page.get("intro") and is_first_page:
            intro_lines = len(page["intro"]) // 80 + 1  # ~80 chars por línea
            intro_height = intro_lines * 13
            current_height += intro_height + 12
        
        # Procesar bloques
        for block in page.get("blocks", []):
            # Si es una tabla muy grande, dividirla primero
            if block["type"] == "table":
                num_rows = len(block["table"]["rows"])
                # Calcular cuántas filas caben en el espacio disponible
                available_height = max_content_height - current_height
                header_height = 40
                row_height = 16
                
                # Si la tabla completa no cabe, dividirla
                if header_height + (num_rows * row_height) > available_height and current_blocks:
                    # Crear página con bloques acumulados
                    new_page = {
                        "header_banner_path": page["header_banner_path"],
                        "header_logo_path": page["header_logo_path"],
                        "title_line1": page["title_line1"],
                        "title_line2": page["title_line2"],
                        "intro": page["intro"] if is_first_page else "",
                        "blocks": current_blocks,
                        "refs": [],
                        "footer_notes": [],
                        "page_number": str(len(result_pages) + 1),
                        "footer_site": page["footer_site"],
                        "footer_phone": page["footer_phone"],
                    }
                    result_pages.append(new_page)
                    
                    # Resetear para nueva página
                    current_blocks = []
                    current_height = 0
                    available_height = max_content_height
                
                # Calcular cuántas filas caben en esta página
                rows_that_fit = int((available_height - header_height - 16) / row_height)
                rows_that_fit = max(1, rows_that_fit)  # Al menos 1 fila
                
                # Dividir tabla en chunks
                all_rows = block["table"]["rows"]
                start_idx = 0
                
                while start_idx < len(all_rows):
                    # Determinar cuántas filas incluir en este chunk
                    if start_idx == 0:
                        # Primera parte con header
                        chunk_size = rows_that_fit
                        chunk_rows = all_rows[start_idx:start_idx + chunk_size]
                        show_header = True
                        chunk_height = header_height + len(chunk_rows) * row_height + 16
                    else:
                        # Continuación sin header - caben más filas
                        rows_without_header = int((max_content_height - 16) / row_height)
                        chunk_size = rows_without_header
                        chunk_rows = all_rows[start_idx:start_idx + chunk_size]
                        show_header = False
                        chunk_height = len(chunk_rows) * row_height + 16
                    
                    table_chunk = {
                        "type": "table",
                        "table": {
                            "groups": block["table"]["groups"],
                            "rows": chunk_rows,
                            "total_width": block["table"]["total_width"],
                            "dep_width": block["table"]["dep_width"],
                            "show_header": show_header,
                        }
                    }
                    
                    # Si este chunk no cabe en la página actual, crear nueva página
                    if current_height + chunk_height > max_content_height and current_blocks:
                        new_page = {
                            "header_banner_path": page["header_banner_path"],
                            "header_logo_path": page["header_logo_path"],
                            "title_line1": page["title_line1"],
                            "title_line2": page["title_line2"],
                            "intro": "",
                            "blocks": current_blocks,
                            "refs": [],
                            "footer_notes": [],
                            "page_number": str(len(result_pages) + 1),
                            "footer_site": page["footer_site"],
                            "footer_phone": page["footer_phone"],
                        }
                        result_pages.append(new_page)
                        current_blocks = []
                        current_height = 0
                    
                    current_blocks.append(table_chunk)
                    current_height += chunk_height
                    start_idx += chunk_size
            else:
                # Bloque HTML normal
                block_height = estimate_block_height(block)
                
                # Si este bloque excede el espacio disponible, crear nueva página
                if current_height + block_height > max_content_height and current_blocks:
                    new_page = {
                        "header_banner_path": page["header_banner_path"],
                        "header_logo_path": page["header_logo_path"],
                        "title_line1": page["title_line1"],
                        "title_line2": page["title_line2"],
                        "intro": "",
                        "blocks": current_blocks,
                        "refs": [],
                        "footer_notes": [],
                        "page_number": str(len(result_pages) + 1),
                        "footer_site": page["footer_site"],
                        "footer_phone": page["footer_phone"],
                    }
                    result_pages.append(new_page)
                    
                    # Resetear para nueva página
                    current_blocks = [block]
                    current_height = block_height
                else:
                    current_blocks.append(block)
                    current_height += block_height
        
        # Agregar última página con bloques restantes
        if current_blocks:
            new_page = {
                "header_banner_path": page["header_banner_path"],
                "header_logo_path": page["header_logo_path"],
                "title_line1": page["title_line1"],
                "title_line2": page["title_line2"],
                "intro": "",
                "blocks": current_blocks,
                "refs": page.get("refs", []),
                "footer_notes": page.get("footer_notes", []),
                "page_number": str(len(result_pages) + 1),
                "footer_site": page["footer_site"],
                "footer_phone": page["footer_phone"],
            }
            result_pages.append(new_page)
    
    return result_pages


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

    # Aplicar paginación automática
    data["pages"] = auto_paginate_content(data["pages"])

    html = template.render(**data)

    HTML(string=html, base_url=str(ROOT)).write_pdf(
        OUTPUT_PDF, stylesheets=[CSS(filename=str(CSS_PATH))]
    )

    print(f"Wrote {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
