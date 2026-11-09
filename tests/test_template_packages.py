"""Document chrome is a registry, and both exporters read the same entry."""

from __future__ import annotations

import zipfile

import pytest

from pdfgen_juanipis.options import RenderOptions
from pdfgen_juanipis.packages import (
    BUILTIN_DEFAULT_PACKAGE,
    DEFAULT_FOOTER_BOTTOM_OFFSET_PT,
    DEFAULT_HEADER_HEIGHT_PT,
    DEFAULT_PAGE_MARGIN_BOTTOM_PT,
    PackageRegistry,
    TemplatePackageError,
    build_chrome_geometry_css,
    default_registry,
)
from pdfgen_juanipis.pdf.renderer import STYLESHEET


class TestTheRegistry:
    def test_the_library_ships_one_neutral_default(self):
        registry = PackageRegistry()
        assert registry.available() == [BUILTIN_DEFAULT_PACKAGE]
        plain = registry.resolve(None)
        assert plain.name == "plain" and plain.header_asset is None
        assert registry.resolve("").name == "plain"

    def test_an_unknown_name_raises_and_lists_the_options(self):
        with pytest.raises(TemplatePackageError) as exc:
            PackageRegistry().resolve("no_such_letterhead")
        assert "plain" in str(exc.value)

    def test_a_directory_of_packages_registers_each(self, make_package, tmp_path):
        make_package("alpha")
        make_package("beta")
        registry = PackageRegistry()
        assert registry.register(tmp_path / "packages") == ["alpha", "beta"]
        assert registry.available() == ["alpha", "beta", "plain"]

    def test_a_single_package_dir_and_a_default(self, make_package):
        path = make_package("gamma")
        registry = PackageRegistry()
        registry.register(path, name="brand", default="brand")
        assert registry.default == "brand"
        assert registry.resolve().name == "brand"
        rows = registry.describe()
        assert [r["name"] for r in rows if r["default"]] == ["brand"]

    def test_the_default_must_be_registered(self):
        with pytest.raises(TemplatePackageError):
            PackageRegistry().set_default("nope")

    def test_registering_does_not_touch_the_process_wide_registry(self, make_package):
        PackageRegistry().register(make_package("local_only"))
        assert "local_only" not in default_registry.available()

    def test_an_empty_directory_is_an_error(self, tmp_path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(TemplatePackageError):
            PackageRegistry().register(tmp_path / "empty")


class TestAssets:
    def test_a_package_may_reuse_a_shared_asset(self, make_package, tmp_path):
        from conftest import _png

        shared = tmp_path / "bundle" / "assets"
        _png(shared / "shared-band.png")
        path = make_package("reuser", band=False,
                            manifest={"theme": {"header_complete_path": "shared-band.png"}})
        registry = PackageRegistry()
        registry.register(path, shared_assets=shared)
        package = registry.resolve("reuser")
        assert package.header_asset == (shared / "shared-band.png").resolve()

    def test_a_missing_band_fails_at_resolution(self, make_package):
        path = make_package("broken", band=False,
                            manifest={"theme": {"header_complete_path": "nowhere.png"}})
        registry = PackageRegistry()
        registry.register(path)
        with pytest.raises(TemplatePackageError):
            registry.resolve("broken")

    def test_unknown_theme_or_layout_keys_are_errors(self, make_package):
        registry = PackageRegistry()
        registry.register(make_package("typo", manifest={"theme": {"footer_phon": "1"}}))
        with pytest.raises(TemplatePackageError):
            registry.resolve("typo")
        registry.register(make_package("typo2", manifest={"layout": {"header_hieght_pt": 1}}))
        with pytest.raises(TemplatePackageError):
            registry.resolve("typo2")


class TestGeometryOverridesAreDifferencesNotCopies:
    def test_defaults_match_the_stylesheet(self):
        css = STYLESHEET.read_text(encoding="utf-8")
        assert f"height: {DEFAULT_HEADER_HEIGHT_PT:g}pt" in css
        assert f"bottom: {DEFAULT_FOOTER_BOTTOM_OFFSET_PT:g}pt" in css
        assert f"margin: 120pt 85pt {DEFAULT_PAGE_MARGIN_BOTTOM_PT:g}pt 85pt" in css

    def test_a_package_matching_the_stylesheet_emits_no_css(self):
        assert build_chrome_geometry_css(PackageRegistry().resolve("plain")) == ""

    def test_the_css_offset_is_derived_from_the_measurement(self, make_package):
        registry = PackageRegistry()
        registry.register(make_package("measured", manifest={"layout": {
            "header_height_pt": 105, "page_margin_bottom_pt": 82,
            "footer_bottom_from_page_pt": 36.5}}))
        package = registry.resolve("measured")
        css = build_chrome_geometry_css(package)
        assert "margin-bottom: 82pt" in css and "bottom: -45.5pt" in css
        assert ".header-complete" not in css

    def test_palette_and_body_font_become_css_variables(self, make_package, tmp_path):
        from pdfgen_juanipis.fonts import FONTS_DIR

        font = FONTS_DIR / "selawik" / "selawk.ttf"
        registry = PackageRegistry()
        registry.register(make_package("styled", manifest={
            "palette": {"title": "#112233", "accent": "#445566", "brand_other": "#000"},
            "font_family": "Selawik",
            "fonts": [{"family": "Selawik", "file": str(font), "weight": 400}],
        }))
        css = registry.resolve("styled").stylesheet()
        assert "--pdfgen-title-color: #112233" in css
        assert "--pdfgen-accent-color: #445566" in css
        assert "--pdfgen-font-family: 'Selawik', 'Carlito'" in css
        assert "@font-face" in css and font.as_uri() in css


class TestTheOptionReachesBothExporters:
    def test_the_pdf_paints_the_selected_band_and_contact_block(self, make_package):
        registry = PackageRegistry()
        registry.register(make_package("brand"))
        from pdfgen_juanipis.pdf.renderer import HtmlRenderer

        renderer = HtmlRenderer(options=RenderOptions(template_package="brand"), registry=registry)
        html = renderer.build_html("<h2>Uno</h2><p>Texto.</p>")
        assert "band.png" in html and 'class="header-complete"' in html
        assert "example.org" in html and "Cel: +1 555 0100" in html

    def test_the_plain_package_paints_no_chrome(self):
        from pdfgen_juanipis.pdf.renderer import HtmlRenderer

        html = HtmlRenderer().build_html("<h2>Uno</h2><p>Texto.</p>")
        assert 'class="header-complete"' not in html and 'class="footer-contact"' not in html

    def test_word_gets_the_letterhead_band(self, make_package, tmp_path):
        pytest.importorskip("docx")
        from pdfgen_juanipis.docx_export import DocxRenderer

        registry = PackageRegistry()
        registry.register(make_package("brand"))
        expected = registry.resolve("brand").header_asset.read_bytes()
        out = DocxRenderer("brand", RenderOptions(title="T"), registry=registry).render(
            "<h1>T</h1><p>Texto.</p>", tmp_path / "brand.docx")
        assert out.banner_attached and not out.warnings
        with zipfile.ZipFile(out.output_path) as bundle:
            media = [bundle.read(n) for n in bundle.namelist() if n.startswith("word/media/")]
        assert expected in media

    def test_word_reports_a_broken_package_instead_of_swapping_brands(self, tmp_path):
        pytest.importorskip("docx")
        from pdfgen_juanipis.docx_export import DocxRenderer

        out = DocxRenderer("no_such_letterhead", RenderOptions(title="T"),
                           registry=PackageRegistry()).render("<p>x</p>", tmp_path / "b.docx")
        assert not out.banner_attached
        assert any("template package" in w for w in out.warnings)

    def test_the_pdf_refuses_an_unknown_package(self):
        from pdfgen_juanipis.pdf.renderer import HtmlRenderer

        with pytest.raises(TemplatePackageError):
            HtmlRenderer("no_such_letterhead", registry=PackageRegistry())
