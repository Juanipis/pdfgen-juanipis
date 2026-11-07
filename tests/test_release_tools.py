"""The release script publishes a hand-bumped version as is, else the next patch."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_tools", ROOT / "scripts" / "release_tools.py")
release_tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_tools)


def _repo(tmp_path, version, changelog):
    (tmp_path / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def _run(monkeypatch, tmp_path, released):
    monkeypatch.setattr(release_tools, "is_released", lambda v: v in released)
    monkeypatch.setattr("sys.argv", ["release_tools", "--pyproject", str(tmp_path / "pyproject.toml"),
                                     "--changelog", str(tmp_path / "CHANGELOG.md"),
                                     "--notes", str(tmp_path / "notes.md")])
    release_tools.main()
    return release_tools.read_version(tmp_path / "pyproject.toml")


def test_a_hand_bumped_version_is_released_as_is(monkeypatch, tmp_path):
    repo = _repo(tmp_path, "0.2.0", "# Changelog\n\n## Unreleased\n\n- _TBD_\n\n## 0.2.0 - 2026-11-06\n\nNotes.\n")
    before = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert _run(monkeypatch, repo, released={"0.1.12"}) == "0.2.0"
    assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == before
    assert (repo / "notes.md").read_text(encoding="utf-8").startswith("## 0.2.0")


def test_a_released_version_bumps_the_patch(monkeypatch, tmp_path):
    repo = _repo(tmp_path, "0.2.0", "# Changelog\n\n## Unreleased\n\n- _TBD_\n\n")
    assert _run(monkeypatch, repo, released={"0.2.0"}) == "0.2.1"
    assert "## 0.2.1 - " in (repo / "CHANGELOG.md").read_text(encoding="utf-8")
