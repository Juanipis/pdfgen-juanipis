# pdfgen-juanipis

HTML editable → PDF paginado (y Word), sobre [WeasyPrint](https://weasyprint.org/).

Desde la 0.2 la librería gira alrededor de **HTML**: le das un documento HTML
(párrafos, `<h2>` de sección, figuras, notas al pie, tablas) y devuelve un PDF
maquetado con CSS Paged Media, con:

- **paquetes de plantilla** (membrete: banda de encabezado, bloque de contacto,
  geometría, paleta, fuentes) registrables desde fuera de la librería;
- **pasadas post-maquetación**: notas al pie en la página de su llamada,
  relleno del hueco que deja una figura que salta de página, y supresión del
  salto forzado que deja una página casi vacía;
- un **contrato de render** (`data-page-break`, `data-keep-with-next`,
  clases de figura y de nota) que el exportador de **Word** (`[docx]`) honra
  igual que el PDF;
- **opciones** compartidas por ambos formatos y **palabras visibles
  configurables** (por defecto en español);
- **solo fuentes libres** incluidas (Carlito, métrica idéntica a Calibri).

La API 0.1 (datos estructurados YAML/JSON → PDF) sigue funcionando: ver
[API 0.1 (legacy)](#api-01-legacy).

## Instalación

```bash
pip install pdfgen-juanipis            # PDF
pip install "pdfgen-juanipis[docx]"    # + exportador Word (python-docx)
```

WeasyPrint necesita Pango. En macOS con Apple Silicon:

```bash
brew install pango cairo gdk-pixbuf libffi
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
```

Para que el exportador Word incruste gráficos SVG hace falta `rsvg-convert`
(`brew install librsvg` / `apt install librsvg2-bin`); sin él imprime un
marcador y lo reporta en `warnings`.

## Uso rápido

```python
from pdfgen_juanipis import HtmlRenderer, RenderOptions

html = """
<h1 class="document-title">Informe trimestral</h1>
<h2 class="document-subtitle">Primer trimestre</h2>
<p>Introducción sin encabezado: se imprime sin número.</p>
<h2>Indicador A</h2>
<p>El indicador subió<sup>1</sup>.</p>
<p class="footnote"><sup>1</sup> Fuente: registro administrativo.</p>
<figure class="figure-full"><img src="grafico.svg">
  <figcaption><span class="figure-title">Figura 1.</span> Evolución.</figcaption></figure>
<h2 data-page-break="before">Anexo</h2>
<table><thead><tr><th>Grupo</th><th>2025</th></tr></thead>
  <tbody><tr><td>A</td><td>12,4</td></tr></tbody></table>
"""

result = HtmlRenderer(options=RenderOptions(show_page_numbers=True)).render(html, "informe.pdf")
print(result.pages, result.footnote_mismatches)
```

- Las secciones son los `<h2>`; se numeran «I.», «II.»… por **posición**
  (un numeral escrito a mano se reemplaza). `section_numbering="none"` lo apaga.
- El texto antes del primer `<h2>` es una introducción sin título ni número.
- Cada `<p class="footnote">` se imprime al pie de la página donde está su
  `<sup>` (varias notas en una llamada: `<sup>2,3</sup>`).
- Las rutas relativas de imágenes se resuelven contra `source_dir`
  (`render_file()` lo hace solo).

PDF y Word con las mismas opciones:

```python
from pdfgen_juanipis import render_formats, RenderOptions

out = render_formats(html, RenderOptions(title="Informe"), output_dir="out", basename="informe")
out.pdf_path, out.docx_path, out.errors
```

O por separado: `DocxRenderer(package, options).render(html, "informe.docx")`.

## Opciones (`RenderOptions`)

| Opción | Por defecto | Qué hace |
|---|---|---|
| `title`, `subtitle` | del `<h1 class="document-title">` / `.document-subtitle` | Título y subtítulo sobre el cuerpo |
| `template_package` | el default del registro (`plain`) | Membrete a usar |
| `footer_site`, `footer_phone`, `theme` | del paquete | Sobrescriben valores del membrete |
| `show_page_numbers`, `page_number_label` | `False` | Número de página (y «Página N») |
| `text_align` | `justify` | Alineación del cuerpo |
| `section_numbering` | `roman` | `roman` o `none` |
| `language` | `es-CO` | Atributo `lang` y guardia de escritura ajena |
| `validate_text` | `True` | Rechaza texto con caracteres de otra escritura (cajas vacías en el PDF) |
| `figure_max_height_pt` | — | Tope de alto para toda figura |
| `fill_figure_gaps`, `relax_lonely_breaks`, `fix_footnote_pages` | `True` | Pasadas post-maquetación |
| `bind_percent_signs` | `True` | «5,4 %» nunca se parte entre líneas |
| `ascii_dashes` | `False` | Convierte guiones largos y signo menos a `-` |
| `isolate_fonts` | `True` | fontconfig solo ve las fuentes incluidas y las del paquete (salida reproducible) |
| `native_footnotes` | `True` | Word: notas nativas (`footnotes.xml`) |
| `css` | — | CSS extra al final |
| `allowed_roots` | `()` | Directorios locales extra que el render puede leer (ver [Seguridad](#seguridad)) |
| `allow_absolute_paths` | `False` | Permite leer cualquier archivo local (solo HTML de confianza) |
| `allow_network` | `False` | Permite descargar recursos `http(s)` (solo HTML de confianza) |
| `labels` | `Labels()` | Palabras visibles (abajo) |

### Palabras visibles (`Labels`)

Todo lo que la librería escribe por su cuenta es configurable; los valores por
defecto son en español:

```python
from pdfgen_juanipis import Labels, RenderOptions

RenderOptions(language="en-US", labels=Labels(
    figure="Figure", page="Page", phone="Phone:", untitled_section="Contents",
    header_image_alt="Header", figure_omitted="[{figure} — {alt} omitted: {reason}]",
    no_svg_rasterizer="rsvg-convert not available",
))
```

«Tabla» y «Fuente» no aparecen: la librería nunca los escribe, vienen en el
HTML (`<caption>`, `div.table-caption`).

## Paquetes de plantilla (membrete)

Un paquete es un directorio con `package.yml`. Es lo único que sabe de marca:
no puede cambiar un dato, una figura ni una etiqueta, solo el papel.

```text
mi_membrete/
  package.yml
  letterhead.css            # opcional, se aplica después del CSS base
  assets/
    banda.png               # 612 pt de ancho (Letter), p. ej. 2448×420 px
    fonts/MiFuente-Regular.ttf
```

```yaml
label: "Mi organización"
description: "Banda azul con el logo a la derecha."
css: letterhead.css
font_family: "Mi Fuente"          # fuente del cuerpo (opcional)
fonts:                            # caras que trae el paquete (opcional)
  - {family: "Mi Fuente", file: fonts/MiFuente-Regular.ttf, weight: 400}
  - {family: "Mi Fuente", file: fonts/MiFuente-Bold.ttf, weight: 700}
theme:
  header_complete_path: banda.png
  footer_site: ejemplo.org
  footer_phone: "+57 300 000 0000"
  footer_address: "Calle 1 # 2-3"
  footer_email: hola@ejemplo.org
  footer_city: "Ciudad"
layout:                           # en puntos, medidos sobre el membrete
  header_height_pt: 105
  page_margin_bottom_pt: 82
  footer_bottom_from_page_pt: 36.5  # última línea del pie, desde el borde del papel
palette:
  title: "#2e5395"                # títulos y encabezados (PDF y Word)
  accent: "#f58634"               # separador del bloque de contacto
```

La librería trae un solo paquete neutro, `plain` (sin banda ni pie). Los
membretes de marca viven con su dueño y se registran al arrancar:

```python
from pdfgen_juanipis import register_template_packages, HtmlRenderer

register_template_packages(
    "mi_proyecto/template_packages",          # un paquete o un directorio de paquetes
    shared_assets="mi_proyecto/bundle/assets", # donde buscar lo que el paquete no trae
    default="mi_membrete",
)
HtmlRenderer().render(html, "out.pdf")            # usa mi_membrete
HtmlRenderer("otro_membrete").render(html, "b.pdf")
```

- Los assets se buscan en `assets/` del paquete, luego en `shared_assets`,
  luego en los de la librería. Un asset que no existe **falla** al resolver el
  paquete: nunca se imprime en silencio el membrete de otro.
- Un nombre desconocido falla con la lista de disponibles.
- Para registros aislados (tests, varios clientes) usa `PackageRegistry()` y
  pásalo como `registry=`.
- `pdfgen-juanipis packages --package-dir DIR` lista lo registrado.

## Fuentes

La librería solo incluye fuentes libres (licencias junto a cada familia y en
[`assets/fonts/FONTS.md`](src/pdfgen_juanipis/assets/fonts/FONTS.md)):

| Familia | Reemplaza a | Licencia |
|---|---|---|
| Carlito | Calibri (métricas idénticas) | SIL OFL 1.1 |
| TeX Gyre Adventor | Century Gothic (métricas idénticas) | GUST Font License |
| Selawik | Segoe UI (métricas idénticas) | SIL OFL 1.1 |
| Liberation Serif | Times New Roman (métricas idénticas) | SIL OFL 1.1 |
| IBM Plex Sans Condensed | Aptos Narrow (aproximada, solo plantilla 0.1) | SIL OFL 1.1 |

El cuerpo usa Carlito: como comparte métricas con Calibri, el texto corta en
las mismas líneas y páginas. **Para usar fuentes propias (incluidas
propietarias que tengas licencia de usar) no las metas en esta librería**:
ponlas en tu paquete de plantilla (`fonts:` + `font_family:`). El paquete
vive en tu repositorio; la librería solo las carga al renderizar. En Word, el
documento declara la fuente y, si es un clon métrico (Carlito), su original
como sustituto.

## Seguridad

El HTML que recibe un renderer suele ser generado o editado por usuarios, así
que se trata como **no confiable**. Por defecto:

- **Archivos locales**: solo se leen `data:` URIs y archivos **dentro** de las
  raíces permitidas — el `source_dir` del documento, las plantillas y assets de
  la librería, y los directorios del paquete de plantilla (incluidos los
  archivos que nombra su `package.yml`). Rutas absolutas, `file://` o `../`
  que resuelvan fuera (también vía enlace simbólico) se **rechazan con un
  warning** (`pdfgen_juanipis.security`) y la imagen se omite.
- **Red (SSRF)**: WeasyPrint recibe un `url_fetcher` restrictivo en todas las
  llamadas, también para lo que referencia el CSS (`url()`, `@font-face`):
  `http(s)` y cualquier otro esquema se rechazan.
- **Inyección de HTML**: la plantilla escapa todo valor de texto plano
  (títulos, membrete, celdas de tabla, notas al pie, subtítulos, portada);
  solo los bloques de cuerpo, que el parser reconstruye desde el árbol HTML,
  se insertan como HTML.

Para documentos de confianza, el llamador lo habilita explícitamente:

```python
RenderOptions(allowed_roots=["/srv/graficos"])   # una carpeta más
RenderOptions(allow_absolute_paths=True)          # cualquier archivo local
RenderOptions(allow_network=True)                 # recursos http(s)
```

La API 0.1 (legacy) no cambió de comportamiento: lee las rutas que le pasan.

## Contrato de render

`pdfgen_juanipis.contract` declara las directivas estructurales que el HTML
puede llevar y cómo las implementa cada exportador:

| Directiva | Efecto |
|---|---|
| `data-page-break="before"` | El bloque empieza en página nueva |
| `data-keep-with-next` | No separar del bloque siguiente |
| `p.footnote` | Definición de nota (su `<sup>N</sup>` inicial empata con la llamada) |
| `figure.figure-full` / `figure-column` / `figure-left` / `figure-right` | Ancho de la figura (100 % / 78 %) |
| `span.figure-title`, `span.figure-subcaption` | Rótulo «Figura N.» y fuente bajo la figura |
| `p.section-subtitle` | Subtítulo bajo el título de sección |
| `div.chart` | Contenedor de gráfico (como `<figure>`) |
| `table.body-table` (o `tabla-cuerpo`) | Tabla de cuerpo: anchos por contenido, puede partirse |
| `div.table-caption` tras una tabla | Línea de fuente bajo la tabla |
| `style="text-align:…"` en `<p>` | Alineación del párrafo |
| `section[data-section-type=cover]` / `.cover-section` | Portada (solo PDF) |

`scan_directives(html)` reporta lo que el HTML trae y lo que algún lado no
implementa; los renderers lo registran como warning. Si tu pipeline usa sus
propios atributos `data-*`, regístralos con `register_directive(...)`.

## Pasadas post-maquetación

WeasyPrint es el motor: el contenido fluye y pagina solo. Después, la
librería mide las cajas y ajusta el HTML donde lo haría un diagramador:

1. **Huecos de figura**: si una figura no cabe y salta, la prosa que la sigue
   (sin cruzar un título ni anunciar una figura posterior) sube a llenar el
   hueco, o la imagen se reduce hasta un 35 %. Se queda el layout con menos
   blanco.
2. **Saltos solitarios**: un salto de sección forzado tras una página con un
   par de líneas se elimina si así el documento queda más corto.
3. **Notas al pie**: si una nota cae en una página posterior a su llamada, el
   párrafo (o el título justo encima) pasa a la página siguiente — salvo que
   la llamada esté alta en su página (desperdiciaría media página).

`PdfRenderResult` informa páginas, notas que quedaron cruzadas y directivas no
soportadas.

## CLI

```bash
pdfgen-juanipis html informe.html informe.pdf --docx informe.docx \
    --package-dir mi_proyecto/template_packages --shared-assets mi_proyecto/bundle/assets \
    --package mi_membrete --title "Informe" --page-numbers
pdfgen-juanipis packages --package-dir mi_proyecto/template_packages
```

`scripts/parity_harness.py` renderiza un HTML y reporta páginas y capa de
texto; con `--compare otro.pdf` lo compara contra el PDF de otro renderizador.

## Migrar desde 0.1

- Nada se rompe: `render_pdf`, `render_with_defaults`, `PDFGen`,
  `PDFGenConfig`, `Paginator`, `LayoutConfig`, `validate_and_normalize` y la
  CLI `render`/`validate` siguen importables desde `pdfgen_juanipis` y desde
  sus módulos de siempre (`pdfgen_juanipis.render`, `.api`, `.pagination`,
  `.validator` son alias de `pdfgen_juanipis.legacy.*`).
- Las fuentes de Microsoft incluidas hasta 0.1.12 se reemplazaron por las
  libres de la tabla de arriba, con las mismas métricas. La plantilla 0.1 ahora
  sí carga sus `@font-face` (antes WeasyPrint los ignoraba por falta de
  `FontConfiguration` y se usaban las fuentes del sistema).
- Si generabas HTML y lo metías como bloques `{"type": "html"}` en el YAML,
  pásalo directo a `HtmlRenderer`: secciones, numeración, notas, tablas y
  figuras salen del HTML.
- Si copiaste `boletin.css`/`boletin_template.html.jinja` a tu proyecto, siguen
  funcionando con la API 0.1; las del renderer nuevo son
  `templates/report.css` y `templates/report.html.jinja`.

## API 0.1 (legacy)

Datos estructurados (YAML/JSON) → PDF con el paginador propio.

```bash
pdfgen-juanipis render examples/demo.yaml examples/demo.pdf --root .
pdfgen-juanipis validate data.yaml
```

### Que archivos de configuracion usa

No hay un archivo unico de configuracion. `PDFGenConfig.from_root(root_dir)` arma la configuracion por convencion:
- Si existe `template/` en tu proyecto, usa `template/boletin_template.html.jinja` y `template/boletin.css`
- Si no existe `template/`, usa los templates incluidos en el paquete
- `fonts.conf` en `root_dir` es opcional; si no existe se ignora
- `assets/` en `root_dir` es opcional; si no existe se usan assets del paquete cuando corresponda

En resumen: la configuracion se define por la estructura de carpetas, no por un archivo `config.*`.

### Estructura recomendada del proyecto

```text
mi-proyecto/
  assets/
    banner.png
    logo.png
  template/
    boletin_template.html.jinja
    boletin.css
  fonts.conf   (opcional)
  data.yaml
```

### Assets demo incluidos

Para jugar sin preparar assets, puedes referenciar nombres simples como `banner.png` y `logo.png`.
Resolucion de rutas:
- Primero busca en `root_dir/assets/`
- Si no existen, usa los assets incluidos en el paquete (`src/pdfgen_juanipis/assets/`)

Assets de demo incluidos:
- `banner.png`
- `banner-clean.png`
- `logo.png`
- `figure.png`
- `map.png`
- `chart.png`

### Uso basico (Python)

```python
from pdfgen_juanipis.api import PDFGenConfig, PDFGen

config = PDFGenConfig.from_root("/ruta/a/tu/proyecto")
pdf = PDFGen(config)

pdf.render(data, output_path="salida.pdf", paginate=True, validate=True)
```

Atajo:

```python
from pdfgen_juanipis.api import render_with_defaults

render_with_defaults(data, output_path="salida.pdf", root_dir="/ruta/a/tu/proyecto")
```

Salida en bytes:

```python
from pdfgen_juanipis.api import render_with_defaults_bytes

pdf_bytes = render_with_defaults_bytes(data, root_dir="/ruta/a/tu/proyecto")
```

### Estructura minima del data

```python
data = {
  "theme": {
    "header_banner_path": "banner.png",
    "header_banner_path_cont": "banner-clean.png",
    "header_logo_path": "logo.png",
    "title_line1": "Titulo",
    "title_line2": "Subtitulo",
    "footer_site": "example.org",
    "footer_phone": "Contacto: +1 555 0100"
  },
  "sections": [
    {
      "title": "I. Introduccion",
      "content": [
        {"type": "text", "text": "Texto con <strong>negrita</strong>."}
      ]
    }
  ]
}
```

Notas:
- `header_banner_path_cont` es opcional (banner limpio para paginas continuas)
- Puedes trabajar sin assets propios usando los demo (ver seccion Assets)

### Bloques con assets demo (para jugar)

```python
data = {
  "theme": {
    "header_banner_path": "banner.png",
    "header_logo_path": "logo.png",
    "title_line1": "Demo",
    "title_line2": "Assets incluidos"
  },
  "sections": [
    {
      "title": "Figuras y mapas",
      "content": [
        {"type": "figure", "path": "figure.png", "caption": "Figura demo"},
        {"type": "figure", "path": "chart.png", "caption": "Grafica demo", "wide": True},
        {"type": "map_grid", "items": [{"path": "map.png", "label": "Mapa demo"}]}
      ]
    }
  ]
}
```

### Estilos inline

Los bloques de texto aceptan HTML:
- `<strong>` negrita
- `<em>` italica
- `<u>` subrayado
- `<s>` tachado

### CLI

Render (JSON o YAML):

```bash
pdfgen-juanipis render data.json salida.pdf --root /ruta/proyecto
pdfgen-juanipis render data.yaml salida.pdf
```

Validar (sin generar PDF):

```bash
pdfgen-juanipis validate data.yaml
```

Desde stdin (YAML por defecto):

```bash
cat data.yaml | pdfgen-juanipis render - salida.pdf
```

Opciones utiles:
- `--template-dir` usar tu template
- `--css` usar tu CSS
- `--fonts-conf` usar un `fonts.conf` propio
- `--fonts-dir` usar un directorio con `.ttf`
- `--css-extra` inyectar CSS adicional
- `--no-validate` desactivar validacion
- `--no-paginate` desactivar paginacion
- `--stdout` escribir bytes a stdout

### Personalizacion

Fuentes propias (Python):

```python
config = PDFGenConfig.from_root("/ruta/a/tu/proyecto")
config.fonts_conf = "/ruta/a/mi/fonts.conf"
PDFGen(config).render(data, "salida.pdf")
```

Fuentes propias (CLI):

```bash
pdfgen-juanipis render data.json salida.pdf --fonts-dir /ruta/a/mis/fuentes
```

Colores/estilos rapidos:

```python
css_extra = ":root { --blue-title: #0b7285; --orange-footer: #f08c00; }"
render_with_defaults(data, "salida.pdf", root_dir="/ruta", css_extra=css_extra)
```

Template y CSS propios:

```bash
pdfgen-juanipis render data.json salida.pdf --template-dir /ruta/template --css /ruta/template/boletin.css
```

### Ejemplos

- `examples/minimal.yaml`
- `examples/minimal.json`
- `examples/demo.yaml`
- `examples/demo.pdf`
- `notebooks/demo.ipynb`
- `notebooks/usage.ipynb`
- `notebooks/bytes.ipynb`
- `notebooks/advanced.ipynb`

### Generar el demo con un script

```bash
./scripts/make_demo.sh
```

### Validacion

Se valida automaticamente con `schema.json`. Los warnings se imprimen en consola.

Si quieres desactivar:

```python
pdf.render(data, output_path="salida.pdf", validate=False)
```

### Solucion de problemas

- Assets no encontrados: asegurate de ponerlos en `root_dir/assets/` o usa los nombres demo incluidos.
- Warnings de `schema`: instala `jsonschema` o desactiva la validacion con `--no-validate`.
- Warnings de `Fontconfig`: puedes proveer un `fonts.conf` propio o ignorarlos si el PDF se genera bien.
- Imagenes no aparecen: verifica que los paths sean relativos (se resuelven contra `assets/`) o absolutos.

## Desarrollo

```bash
uv sync --extra dev --extra docx
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -q
```

## Licencia

MIT (código). Las fuentes incluidas tienen su propia licencia libre: ver
[`FONTS.md`](src/pdfgen_juanipis/assets/fonts/FONTS.md).

## Releases

Al hacer push a `main`, el workflow **Auto Release** sube la versión de parche,
crea tag y Release, y publica en PyPI.

Hecho por Juanipis
