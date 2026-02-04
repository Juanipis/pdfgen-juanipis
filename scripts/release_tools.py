import argparse
import re
from datetime import date
from pathlib import Path


def read_version(pyproject_path: Path) -> str:
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r"^version\s*=\s*\"([0-9]+\.[0-9]+\.[0-9]+)\"", text, re.M)
    if not match:
        raise SystemExit("Could not find version in pyproject.toml")
    return match.group(1)


def bump_patch(version: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def write_version(pyproject_path: Path, new_version: str) -> None:
    text = pyproject_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"^version\s*=\s*\"([0-9]+\.[0-9]+\.[0-9]+)\"",
        f'version = "{new_version}"',
        text,
        flags=re.M,
    )
    if text == updated:
        raise SystemExit("Failed to update version in pyproject.toml")
    pyproject_path.write_text(updated, encoding="utf-8")


def update_changelog(changelog_path: Path, new_version: str) -> None:
    today = date.today().isoformat()
    text = changelog_path.read_text(encoding="utf-8")

    if "## Unreleased" not in text:
        text = text.replace("# Changelog\n\n", "# Changelog\n\n## Unreleased\n\n- _TBD_\n\n")

    entry = (
        f"## {new_version} - {today}\n\n"
        "- Automated release.\n\n"
    )

    parts = text.split("## Unreleased")
    if len(parts) < 2:
        raise SystemExit("Could not find Unreleased section in CHANGELOG.md")

    header, rest = parts[0], "## Unreleased" + parts[1]
    sections = rest.split("\n\n", 2)
    if len(sections) < 3:
        rest = rest + "\n\n"
        sections = rest.split("\n\n", 2)
    new_text = header + "## Unreleased" + "\n\n" + sections[1] + "\n\n" + entry + sections[2]
    changelog_path.write_text(new_text, encoding="utf-8")


def extract_release_notes(changelog_path: Path, version: str) -> str:
    text = changelog_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^##\s+{re.escape(version)}\s+-\s+.*$", re.M)
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"Version {version} not found in CHANGELOG.md")
    start = match.start()
    next_match = re.search(r"^##\s+", text[match.end():], re.M)
    end = match.end() + (next_match.start() if next_match else len(text))
    return text[start:end].strip() + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", default="pyproject.toml")
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--notes", default="release-notes.md")
    args = parser.parse_args()

    pyproject_path = Path(args.pyproject)
    changelog_path = Path(args.changelog)

    current = read_version(pyproject_path)
    new_version = bump_patch(current)
    write_version(pyproject_path, new_version)
    update_changelog(changelog_path, new_version)

    notes = extract_release_notes(changelog_path, new_version)
    Path(args.notes).write_text(notes, encoding="utf-8")

    print(new_version)


if __name__ == "__main__":
    main()
