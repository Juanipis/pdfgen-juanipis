"""What a render may read, and what it may inject.

Each defence is tested both ways: the malicious input is refused (with a
warning, never silently) and the legitimate input still works.
"""

from __future__ import annotations

import http.server
import logging
import threading
from pathlib import Path

import pytest

from conftest import _png
from pdfgen_juanipis.options import RenderOptions
from pdfgen_juanipis.pdf.renderer import HtmlRenderer
from pdfgen_juanipis.security import ResourcePolicy, ResourceRejected


@pytest.fixture
def layout(tmp_path):
    """A document dir with an image, and a 'secret' image outside it."""
    doc = tmp_path / "doc"
    _png(doc / "img" / "ok.png", size=(40, 20))
    secret = _png(tmp_path / "outside" / "secret.png", size=(40, 20))
    return doc, secret


# ── 1. local files / path traversal ───────────────────────────────────────


class TestImageSources:
    def test_data_uris_and_files_inside_source_dir_are_allowed(self, layout):
        doc, _secret = layout
        policy = ResourcePolicy.build([doc])
        assert policy.resolve_src("data:image/png;base64,AAAA", doc) == "data:image/png;base64,AAAA"
        assert policy.resolve_src("img/ok.png", doc) == (doc / "img" / "ok.png").resolve().as_uri()
        assert policy.resolve_src(str(doc / "img" / "ok.png"), doc)

    @pytest.mark.parametrize("make_src", [
        lambda doc, secret: "../outside/secret.png",          # traversal
        lambda doc, secret: str(secret),                       # absolute path
        lambda doc, secret: secret.as_uri(),                   # file:// URL
        lambda doc, secret: "img/../../outside/secret.png",    # traversal via a subdir
    ])
    def test_files_outside_the_roots_are_refused_with_a_warning(self, layout, caplog, make_src):
        doc, secret = layout
        policy = ResourcePolicy.build([doc])
        with caplog.at_level(logging.WARNING, logger="pdfgen_juanipis.security"):
            assert policy.resolve_src(make_src(doc, secret), doc) is None
        assert "resource refused" in caplog.text

    def test_a_symlink_out_of_the_root_is_refused(self, layout):
        doc, secret = layout
        link = doc / "img" / "link.png"
        link.symlink_to(secret)
        assert ResourcePolicy.build([doc]).resolve_src("img/link.png", doc) is None

    def test_relative_paths_need_a_source_dir(self, layout):
        assert ResourcePolicy.build([]).resolve_src("img/ok.png", None) is None

    @pytest.mark.parametrize("src", ["javascript:alert(1)", "ftp://example.org/x.png", "gopher://x"])
    def test_other_schemes_are_refused(self, layout, src):
        doc, _secret = layout
        assert ResourcePolicy.build([doc]).resolve_src(src, doc) is None

    def test_opt_in_extra_root_or_any_absolute_path(self, layout):
        doc, secret = layout
        assert ResourcePolicy.build([doc, secret.parent]).resolve_src(str(secret), doc)
        assert ResourcePolicy.build([doc], allow_absolute_paths=True).resolve_src(str(secret), doc)

    def test_the_renderer_drops_a_refused_image_and_keeps_an_allowed_one(self, layout, caplog):
        doc, secret = layout
        html = f'<h2>A</h2><figure><img src="{secret}"></figure><figure><img src="img/ok.png"></figure>'
        with caplog.at_level(logging.WARNING, logger="pdfgen_juanipis.security"):
            out = HtmlRenderer().build_html(html, source_dir=doc)
        assert str(secret) not in out and "secret.png" not in out
        assert out.count("data:image/png;base64,") == 1   # the allowed one, fitted and inlined
        assert "secret.png" in caplog.text

    def test_allowed_roots_option_lets_the_caller_widen_it(self, layout):
        doc, secret = layout
        html = f'<h2>A</h2><figure><img src="{secret}"></figure>'
        out = HtmlRenderer(options=RenderOptions(allowed_roots=[secret.parent])).build_html(
            html, source_dir=doc)
        assert out.count("data:image/png;base64,") == 1


# ── 2. what WeasyPrint itself fetches (SSRF, CSS url(), fonts) ────────────


class TestUrlFetcher:
    def test_fetcher_refuses_network_and_outside_files(self, layout):
        pytest.importorskip("weasyprint")
        doc, secret = layout
        fetcher = ResourcePolicy.build([doc]).url_fetcher()
        for url in ("http://127.0.0.1:1/x.png", "https://example.org/x.css", secret.as_uri()):
            with pytest.raises(ResourceRejected):
                fetcher(url)
        fetcher((doc / "img" / "ok.png").as_uri()).close()     # inside the root: fetched

    @pytest.fixture
    def server(self):
        hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                hits.append(self.path)
                self.send_response(404)
                self.end_headers()

            def log_message(self, *args):
                pass

        httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}", hits
        httpd.shutdown()

    def _html(self, base):
        return (f'<h2>A</h2><p>texto</p><figure><img src="{base}/img.png"></figure>'
                f'<div style="background:url({base}/bg.png)">fondo</div>')

    def test_a_render_makes_no_network_request_by_default(self, server):
        pytest.importorskip("weasyprint")
        base, hits = server
        HtmlRenderer(options=RenderOptions(css=f"body {{ background: url({base}/css.png) }}")) \
            .render_bytes(self._html(base))
        assert hits == []

    def test_allow_network_is_an_explicit_opt_in(self, server):
        pytest.importorskip("weasyprint")
        base, hits = server
        HtmlRenderer(options=RenderOptions(allow_network=True,
                                           css=f"body {{ background: url({base}/css.png) }}")) \
            .render_bytes(self._html(base))
        assert hits, "with allow_network the resources are fetched"

    def test_the_bundled_fonts_still_load(self):
        """The library's own @font-face files live inside an allowed root."""
        pytest.importorskip("weasyprint")
        pypdf = pytest.importorskip("pypdf")
        import io

        data = HtmlRenderer().render_bytes("<h2>A</h2><p>texto</p>")
        reader = pypdf.PdfReader(io.BytesIO(data))
        fonts = {str(f.get_object().get("/BaseFont"))
                 for p in reader.pages for f in ((p.get("/Resources") or {}).get("/Font") or {}).values()}
        assert any("Carlito" in f for f in fonts)


# ── 3. HTML injection through plain-text values ───────────────────────────


class TestEscaping:
    def test_plain_text_values_are_escaped(self, make_package):
        from pdfgen_juanipis.packages import PackageRegistry

        registry = PackageRegistry()
        registry.register(make_package("evil", manifest={"theme": {
            "footer_site": "<script>alert(1)</script>"}}))
        html = (
            "<section data-section-type='cover'><p class='cover-line'>&lt;img src=x onerror=1&gt;</p></section>"
            "<section><h2>Uno</h2><p class='section-subtitle'>&lt;b&gt;sub&lt;/b&gt;</p>"
            "<h3>&lt;script&gt;h3&lt;/script&gt;</h3>"
            "<p>texto<sup>1</sup></p><p class='footnote'><sup>1</sup> &lt;iframe&gt; nota</p>"
            "<table><thead><tr><th>&lt;i&gt;col&lt;/i&gt;</th><th>v</th></tr></thead>"
            "<tbody><tr><td>&lt;script&gt;x&lt;/script&gt;</td><td>1</td></tr></tbody></table></section>"
        )
        out = HtmlRenderer("evil", RenderOptions(title="<b>T</b>"), registry=registry).build_html(html)
        for raw in ("<script>", "<img src=x", "<b>sub", "<iframe>", "<i>col", "<b>T</b>"):
            assert raw not in out, raw
        for escaped in ("&lt;script&gt;", "&lt;img src=x", "&lt;iframe&gt;", "&lt;b&gt;T&lt;/b&gt;"):
            assert escaped in out, escaped

    def test_legitimate_markup_still_renders(self):
        html = "<h2>Tema <em>clave</em></h2><p>a &amp; b<sup>1</sup> <strong>fuerte</strong></p>" \
               "<p class='footnote'><sup>1</sup> Nota &amp; fuente.</p>"
        out = HtmlRenderer().build_html(html)
        assert "<em>clave</em>" in out and "<strong>fuerte</strong>" in out
        assert "a &amp; b" in out and "Nota &amp; fuente." in out
        assert "&amp;amp;" not in out
