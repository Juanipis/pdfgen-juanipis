from io import BytesIO

from pdfgen.cli import main


class _StdoutProxy:
    def __init__(self):
        self._buffer = BytesIO()

    @property
    def buffer(self):
        return self._buffer

    def write(self, _text):
        return len(_text)

    def flush(self):
        return None


def test_cli_stdout(monkeypatch, tmp_path):
    data = tmp_path / "data.json"
    data.write_text(
        '{"theme": {"header_banner_path": "banner.png", "header_logo_path": "logo.png", "title_line1": "T", "title_line2": "S"}, "sections": [{"title": "I", "content": [{"type": "text", "text": "Hola"}]}]}',
        encoding="utf-8",
    )

    proxy = _StdoutProxy()
    monkeypatch.setattr("sys.stdout", proxy)
    rc = main(["render", str(data), "out.pdf", "--stdout"])  # output ignored
    assert rc == 0
    assert len(proxy.buffer.getvalue()) > 1000
