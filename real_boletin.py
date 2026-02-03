import os
import pathlib
import re
from typing import List, Tuple

import fitz

from render import render_pdf, FONTS_CONF

ROOT = pathlib.Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
EXTRACTED = ASSETS / "extracted"


def extract_page_lines(pdf_path: pathlib.Path) -> List[List[str]]:
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(doc.page_count):
        text = doc[i].get_text("text")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        pages.append(lines)
    return pages


def clean_lines(lines: List[str]) -> List[str]:
    skip = {"abaco.org.co", "Teléfono: 313 245 79 78"}
    return [line for line in lines if line not in skip]


def split_refs(lines: List[str]) -> Tuple[List[str], List[str]]:
    refs = []
    body = []
    for line in lines:
        if re.match(r"^\*+", line) or re.match(r"^\d+", line) or line.lower().startswith("fuente"):
            refs.append(line)
        else:
            body.append(line)
    return body, refs


def chunk_paragraphs(lines: List[str], max_chars: int = 520) -> List[str]:
    text = " ".join(lines)
    sentences = re.split(r"(?<=[\.!\?])\s+", text)
    paragraphs = []
    buf = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(buf) + len(sentence) + 1 > max_chars and buf:
            paragraphs.append(buf.strip())
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        paragraphs.append(buf.strip())
    return paragraphs


def build_sections(pages_text: List[List[str]]):
    banner = str((ASSETS / "header-banner.png").resolve())
    banner_clean = str((ASSETS / "header-banner-clean.png").resolve())
    logo = str((ASSETS / "logo.png").resolve())

    extracted = {
        "level_bar": str((EXTRACTED / "page_1" / "img_3.png").resolve()),
        "map_jan": str((EXTRACTED / "page_2" / "img_4.jpeg").resolve()),
        "map_feb": str((EXTRACTED / "page_2" / "img_6.jpeg").resolve()),
        "map_mar": str((EXTRACTED / "page_2" / "img_8.jpeg").resolve()),
        "line_ii": str((EXTRACTED / "page_3" / "img_5.png").resolve()),
        "people_ii": str((EXTRACTED / "page_3" / "img_3.png").resolve()),
        "line_iii": str((EXTRACTED / "page_4" / "img_4.png").resolve()),
        "people_iii": str((EXTRACTED / "page_5" / "img_3.png").resolve()),
        "line_iv": str((EXTRACTED / "page_6" / "img_4.png").resolve()),
        "chart_v": str((EXTRACTED / "page_7" / "img_3.png").resolve()),
        "chart_vi": str((EXTRACTED / "page_8" / "img_3.png").resolve()),
        "chart_vii": str((EXTRACTED / "page_10" / "img_3.png").resolve()),
        "chart_viii": str((EXTRACTED / "page_11" / "img_3.png").resolve()),
    }

    # Page 1 content
    lines = clean_lines(pages_text[0])
    title_lines = []
    while lines and lines[0].startswith("Boletín sobre la Situación Alimentaria"):
        title_lines.append(lines.pop(0))
        if lines and lines[0].startswith("Trimestre 2024"):
            title_lines.append(lines.pop(0))
            break

    body, refs = split_refs(lines)
    paragraphs = chunk_paragraphs(body)

    sections = []

    def add_section(section):
        title = (section.get("title") or "").strip()
        if not title and sections:
            sections[-1]["content"].extend(section.get("content", []))
            return
        sections.append(section)

    add_section({
        "title": " ".join(title_lines[:-1]) if len(title_lines) > 1 else (title_lines[0] if title_lines else ""),
        "subtitle": title_lines[-1] if len(title_lines) > 1 else "",
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:2]},
            {
                "type": "figure",
                "path": extracted["level_bar"],
                "caption": "Gráfica 1. Niveles de riesgos de acuerdo con el Programa Mundial de Alimentos.",
                "wide": True,
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[2:]},
        ],
    })

    # Page 2 section I with maps
    lines = clean_lines(pages_text[1])
    body, refs = split_refs(lines)
    heading = "I. Índice de Riesgo de la situación alimentaria en Colombia"
    subheading = "Histórico de Mapas Departamentales de la Situación Alimentaria en Colombia durante el Primer Trimestre del 2024."
    map_caption = "Fuente: HungerMap Live, enero-marzo 2024."
    paragraphs = chunk_paragraphs([line for line in body if line not in {"Enero", "Febrero", "Marzo", map_caption}])

    add_section({
        "title": heading,
        "subtitle": subheading,
        "content": [
            {
                "type": "map_grid",
                "items": [
                    {"path": extracted["map_jan"], "label": "Enero"},
                    {"path": extracted["map_feb"], "label": "Febrero"},
                    {"path": extracted["map_mar"], "label": "Marzo"},
                ],
                "source": map_caption,
            },
            {"type": "text", "text": paragraphs, "refs": refs},
        ],
    })

    # Page 3 section II
    lines = clean_lines(pages_text[2])
    body, refs = split_refs(lines)
    heading = "II. Indicadores de prevalencia de Consumo Insuficiente de Alimentos."
    body = [line for line in body if line != heading]
    paragraphs = chunk_paragraphs(body)

    add_section({
        "title": heading,
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:5]},
            {
                "type": "figure",
                "path": extracted["line_ii"],
                "caption": "Gráfica 2. Índice de prevalencia en el consumo insuficiente de alimentos a nivel nacional en el primer trimestre de 2023 – 2024.",
            },
            {"type": "text", "text": paragraphs[2:4], "refs": refs[5:8]},
            {
                "type": "figure",
                "path": extracted["people_ii"],
                "caption": "Gráfica 3. Consumo insuficiente de alimentos a nivel nacional en el primer trimestre de 2023 – 2024.",
            },
            {"type": "text", "text": paragraphs[4:], "refs": refs[8:]},
        ],
    })

    # Page 4 / 5 section III
    lines = clean_lines(pages_text[3])
    body, refs = split_refs(lines)
    heading = "III. Estrategias de Afrontamiento a las Crisis Basadas en la Alimentación."
    pre = []
    post = []
    seen = False
    for line in body:
        if line.startswith("III."):
            seen = True
            continue
        (post if seen else pre).append(line)

    pre_paragraphs = chunk_paragraphs(pre)
    post_paragraphs = chunk_paragraphs(post)

    add_section({
        "title": heading,
        "content": [
            {"type": "text", "text": pre_paragraphs, "refs": refs[:4]},
            {
                "type": "figure",
                "path": extracted["line_iii"],
                "caption": "Gráfica 4. Número de personas que aplican estrategias para afrontar el hambre en Colombia (2023 – 2024).",
            },
            {"type": "text", "text": post_paragraphs, "refs": refs[4:]},
        ],
    })

    lines = clean_lines(pages_text[4])
    body, refs = split_refs(lines)
    paragraphs = chunk_paragraphs(body)
    add_section({
        "title": "",
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:3]},
            {
                "type": "figure",
                "path": extracted["people_iii"],
                "caption": "Gráfica 5. Estrategias de afrontamiento en el primer trimestre de 2023 – 2024.",
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[3:]},
        ],
    })

    # Page 6 section IV
    lines = clean_lines(pages_text[5])
    body, refs = split_refs(lines)
    heading = "IV. Desnutrición aguda en menores de 5 años."
    body = [line for line in body if not line.startswith("IV.")]
    paragraphs = chunk_paragraphs(body)

    add_section({
        "title": heading,
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:4]},
            {
                "type": "figure",
                "path": extracted["line_iv"],
                "caption": "Gráfica 6. Desnutrición aguda en menores de 5 años en el primer trimestre (2023 – 2024).",
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[4:]},
        ],
    })

    # Page 7 section V
    lines = clean_lines(pages_text[6])
    body, refs = split_refs(lines)
    heading = "V. Mortalidad Materna."
    body = [line for line in body if not line.startswith("V.")]
    paragraphs = chunk_paragraphs(body)

    add_section({
        "title": heading,
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:4]},
            {
                "type": "figure",
                "path": extracted["chart_v"],
                "caption": "Gráfica 7. Mortalidad materna por departamento (2023 – 2024).",
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[4:]},
        ],
    })

    # Page 8 section VI
    lines = clean_lines(pages_text[7])
    body, refs = split_refs(lines)
    heading = "VI. Mortalidad por Enfermedades Diarreicas Agudas (EDA)."
    body = [line for line in body if not line.startswith("VI.")]
    paragraphs = chunk_paragraphs(body)

    add_section({
        "title": heading,
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:3]},
            {
                "type": "figure",
                "path": extracted["chart_vi"],
                "caption": "Gráfica 8. Mortalidad por EDA por departamento (2023 – 2024).",
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[3:]},
        ],
    })

    # Page 9 text-only continuation
    lines = clean_lines(pages_text[8])
    body, refs = split_refs(lines)
    paragraphs = chunk_paragraphs(body)
    add_section({
        "title": "",
        "content": [
            {"type": "text", "text": paragraphs, "refs": refs},
        ],
    })

    # Page 10 section VII
    lines = clean_lines(pages_text[9])
    body, refs = split_refs(lines)
    heading = "VII. Mortalidad por y asociada a la desnutrición (DNT)."
    body = [line for line in body if not line.startswith("VII.")]
    paragraphs = chunk_paragraphs(body)

    add_section({
        "title": heading,
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:3]},
            {
                "type": "figure",
                "path": extracted["chart_vii"],
                "caption": "Gráfica 9. Mortalidad por DNT por departamento (2023 – 2024).",
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[3:]},
        ],
    })

    # Page 11 continuation with chart
    lines = clean_lines(pages_text[10])
    body, refs = split_refs(lines)
    paragraphs = chunk_paragraphs(body)
    add_section({
        "title": "",
        "content": [
            {"type": "text", "text": paragraphs[:2], "refs": refs[:3]},
            {
                "type": "figure",
                "path": extracted["chart_viii"],
                "caption": "Gráfica 10. Mortalidad por DNT por departamento (continuación).",
            },
            {"type": "text", "text": paragraphs[2:], "refs": refs[3:]},
        ],
    })

    # Remaining pages as text-only (annexes)
    for idx in range(11, len(pages_text)):
        lines = clean_lines(pages_text[idx])
        body, refs = split_refs(lines)
        paragraphs = chunk_paragraphs(body)
        add_section({
            "title": "",
            "content": [
                {"type": "text", "text": paragraphs, "refs": refs},
            ],
        })

    return {
        "title": "Boletin real - replica",
        "theme": {
            "header_banner_path": banner,
            "header_banner_path_cont": banner_clean,
            "header_logo_path": logo,
            "title_line1": "",
            "title_line2": "",
            "footer_site": "abaco.org.co",
            "footer_phone": "Teléfono: 313 245 79 78",
            "show_header_titles": False,
        },
        "sections": sections,
    }


def main():
    os.environ.setdefault("FONTCONFIG_FILE", str(FONTS_CONF))
    data = build_sections(extract_page_lines(ROOT / "boletin.pdf"))
    output_path = ROOT / "boletin_real_output.pdf"
    render_pdf(data, output_path=output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
