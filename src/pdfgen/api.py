import pathlib
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pdfgen.render import render_pdf


@dataclass
class PDFGenConfig:
    root_dir: pathlib.Path
    template_dir: pathlib.Path
    css_path: pathlib.Path
    fonts_conf: Optional[pathlib.Path]

    @classmethod
    def from_root(cls, root_dir: pathlib.Path) -> "PDFGenConfig":
        root_dir = pathlib.Path(root_dir)
        package_root = pathlib.Path(__file__).resolve().parent
        template_dir = root_dir / "template"
        if not template_dir.exists():
            template_dir = package_root / "templates"
        css_path = template_dir / "boletin.css"
        fonts_conf = root_dir / "fonts.conf"
        if not fonts_conf.exists():
            fonts_conf = None
        return cls(
            root_dir=root_dir,
            template_dir=template_dir,
            css_path=css_path,
            fonts_conf=fonts_conf,
        )


class PDFGen:
    def __init__(self, config: PDFGenConfig):
        self.config = config

    def render(
        self,
        data: Dict[str, Any],
        output_path: pathlib.Path,
        paginate: bool = True,
        validate: bool = True,
        css_extra: Optional[str] = None,
    ) -> None:
        render_pdf(
            data,
            output_path=output_path,
            paginate=paginate,
            validate=validate,
            css_extra=css_extra,
            template_dir=self.config.template_dir,
            css_path=self.config.css_path,
            fonts_conf=self.config.fonts_conf,
            root_dir=self.config.root_dir,
        )


def render_with_defaults(
    data: Dict[str, Any],
    output_path: pathlib.Path,
    root_dir: Optional[pathlib.Path] = None,
    paginate: bool = True,
    validate: bool = True,
    css_extra: Optional[str] = None,
) -> None:
    root = pathlib.Path(root_dir) if root_dir else pathlib.Path.cwd()
    config = PDFGenConfig.from_root(root)
    PDFGen(config).render(data, output_path, paginate=paginate, validate=validate, css_extra=css_extra)
