# pdfgen-juanipis

Librería para generar PDFs a partir de data estructurada (HTML + WeasyPrint), con paginación, validación y soporte JSON/YAML.

## Instalación

Desde el repo:

```bash
pip install -e .

Desde PyPI:

```bash
pip install pdfgen-juanipis
```
```

## Uso básico (Python)

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

## Salida en bytes

Si no quieres escribir a disco:

```python
from pdfgen_juanipis.api import render_with_defaults_bytes

pdf_bytes = render_with_defaults_bytes(data, root_dir="/ruta/a/tu/proyecto")
```

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

Opciones útiles:
- `--template-dir` usar tu template
- `--css` usar tu CSS
- `--fonts-conf` usar un `fonts.conf` propio
- `--fonts-dir` usar un directorio con `.ttf`
- `--css-extra` inyectar CSS adicional
- `--no-validate` desactivar validación
- `--no-paginate` desactivar paginación
- `--stdout` escribir bytes a stdout

## Personalización

### Fuentes propias

Opción A: `fonts.conf` propio.

```python
config = PDFGenConfig.from_root("/ruta/a/tu/proyecto")
config.fonts_conf = "/ruta/a/mi/fonts.conf"
PDFGen(config).render(data, "salida.pdf")
```

Opción B: directorio con `.ttf` desde CLI:

```bash
pdfgen-juanipis render data.json salida.pdf --fonts-dir /ruta/a/mis/fuentes
```

### Colores/estilos rápidos

Puedes inyectar CSS extra para cambiar variables o estilos:

```python
css_extra = ":root { --blue-title: #0b7285; --orange-footer: #f08c00; }"
render_with_defaults(data, "salida.pdf", root_dir="/ruta", css_extra=css_extra)
```

### Template y CSS propios

```bash
pdfgen-juanipis render data.json salida.pdf --template-dir /ruta/template --css /ruta/template/boletin.css
```

### Assets

El usuario debe proveer `banner.png` y `logo.png` (o rutas absolutas). Si no usas `assets/` en tu proyecto, indica rutas absolutas en `theme`.

## Estructura mínima del data

```python
data = {
  "theme": {
    "header_banner_path": "banner.png",
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

## Estilos inline

Los bloques de texto aceptan HTML:
- `<strong>` negrita
- `<em>` itálica
- `<u>` subrayado
- `<s>` tachado

## Ejemplos

- `examples/minimal.yaml`
- `examples/minimal.json`
- `notebooks/usage.ipynb`
- `notebooks/bytes.ipynb`
- `notebooks/advanced.ipynb`

## Validación

Se valida automáticamente con `schema.json`. Los warnings se imprimen en consola.

Si quieres desactivar:

```python
pdf.render(data, output_path="salida.pdf", validate=False)
```

## Licencia

MIT

## Releases

Al hacer push a `main`, el workflow **Auto Release** crea tag y Release si la versión en `pyproject.toml` es nueva, y publica automáticamente en PyPI.


Hecho por Juanipis
