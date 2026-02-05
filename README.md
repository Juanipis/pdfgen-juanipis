# pdfgen-juanipis

Libreria para generar PDFs a partir de data estructurada (HTML + WeasyPrint), con paginacion, validacion y soporte JSON/YAML.

## Quickstart

Desde este repo (usa tu `.venv` si ya la tienes):

```bash
pip install -e .

pdfgen-juanipis render examples/demo.yaml examples/demo.pdf --root .
```

Resultados:
- `examples/demo.pdf` generado con assets demo incluidos

## Instalacion

Desde el repo:

```bash
pip install -e .
```

Desde PyPI:

```bash
pip install pdfgen-juanipis
```

## Que archivos de configuracion usa

No hay un archivo unico de configuracion. `PDFGenConfig.from_root(root_dir)` arma la configuracion por convencion:
- Si existe `template/` en tu proyecto, usa `template/boletin_template.html.jinja` y `template/boletin.css`
- Si no existe `template/`, usa los templates incluidos en el paquete
- `fonts.conf` en `root_dir` es opcional; si no existe se ignora
- `assets/` en `root_dir` es opcional; si no existe se usan assets del paquete cuando corresponda

En resumen: la configuracion se define por la estructura de carpetas, no por un archivo `config.*`.

## Estructura recomendada del proyecto

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

## Assets demo incluidos

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

## Uso basico (Python)

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

## Estructura minima del data

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

## Bloques con assets demo (para jugar)

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

## Estilos inline

Los bloques de texto aceptan HTML:
- `<strong>` negrita
- `<em>` italica
- `<u>` subrayado
- `<s>` tachado

## CLI

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

## Personalizacion

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

## Ejemplos

- `examples/minimal.yaml`
- `examples/minimal.json`
- `examples/demo.yaml`
- `examples/demo.pdf`
- `notebooks/demo.ipynb`
- `notebooks/usage.ipynb`
- `notebooks/bytes.ipynb`
- `notebooks/advanced.ipynb`

## Generar el demo con un script

```bash
./scripts/make_demo.sh
```

## Validacion

Se valida automaticamente con `schema.json`. Los warnings se imprimen en consola.

Si quieres desactivar:

```python
pdf.render(data, output_path="salida.pdf", validate=False)
```

## Solucion de problemas

- Assets no encontrados: asegurate de ponerlos en `root_dir/assets/` o usa los nombres demo incluidos.
- Warnings de `schema`: instala `jsonschema` o desactiva la validacion con `--no-validate`.
- Warnings de `Fontconfig`: puedes proveer un `fonts.conf` propio o ignorarlos si el PDF se genera bien.
- Imagenes no aparecen: verifica que los paths sean relativos (se resuelven contra `assets/`) o absolutos.

## Licencia

MIT

## Releases

Al hacer push a `main`, el workflow **Auto Release** crea tag y Release si la version en `pyproject.toml` es nueva, y publica automaticamente en PyPI.

Hecho por Juanipis
