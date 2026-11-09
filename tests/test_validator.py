import pathlib

from pdfgen_juanipis.validator import validate_and_normalize


def test_table_padding_and_truncation(tmp_path):
    data = {
        "theme": {},
        "sections": [
            {
                "content": [
                    {
                        "type": "table",
                        "table": {
                            "groups": [
                                {"title": "A", "months": ["Ene", "Feb"]},
                                {"title": "B", "months": ["Mar"]},
                            ],
                            "rows": [
                                {"dep": "X", "vals": ["1"]},
                                {"dep": "Y", "vals": ["1", "2", "3", "4"]},
                            ],
                        },
                    }
                ]
            }
        ],
    }

    normalized, warnings = validate_and_normalize(data, root_dir=pathlib.Path.cwd())
    table = normalized["sections"][0]["content"][0]["table"]
    assert table["rows"][0]["vals"] == ["1", "", ""]
    assert table["rows"][1]["vals"] == ["1", "2", "3"]
    assert warnings


def test_refs_catalog_missing_warning(tmp_path):
    data = {
        "refs_catalog": {"1": "Fuente 1"},
        "sections": [
            {
                "content": [
                    {"type": "text", "text": "Texto con refs [1] y [2]."}
                ]
            }
        ],
    }
    _, warnings = validate_and_normalize(data, root_dir=pathlib.Path.cwd())
    assert any("Missing refs_catalog entry for [2]" in w for w in warnings)
