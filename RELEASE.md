# Release checklist

1. Update `CHANGELOG.md`.
2. Bump version in `pyproject.toml`.
3. Run tests: `pytest -q`.
4. Create release via GitHub Actions workflow `Release` (workflow_dispatch).
5. Publish happens automatically on GitHub Release (workflow `Publish`).
