# Release checklist

1. Update `CHANGELOG.md`.
2. Bump version in `pyproject.toml`.
3. Run tests: `pytest -q`.
4. Push to `main`.
5. Workflow `Auto Release` will create tag/release and publish if the tag does not exist.
