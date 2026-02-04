import pathlib

from pdfgen_juanipis.validator import validate_and_normalize


def test_schema_validation_catches_missing_sections(tmp_path):
    data = {"title": "Sin secciones"}
    _, warnings = validate_and_normalize(data, root_dir=pathlib.Path.cwd())
    assert any("schema" in w for w in warnings)
