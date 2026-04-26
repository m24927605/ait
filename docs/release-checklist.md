# Release Checklist

## 0.1.0 MVP

Before tagging:

1. Confirm `pyproject.toml` version is `0.1.0`.
2. Confirm `CHANGELOG.md` has a `0.1.0` entry.
3. Run `git status --short`.
4. Run `.venv/bin/pytest -q`.
5. Confirm dogfood notes include the latest session.
6. Confirm README install and quickstart are current.
7. Tag with `v0.1.0`.
8. Push `main` and `v0.1.0` to GitHub.
9. Confirm GitHub Actions passes on the pushed commit.
10. Create the GitHub release from `CHANGELOG.md`.
11. Run a clean clone smoke test from the GitHub URL.

Current verification:

```text
116 passed
```

## PyPI Release

The PyPI distribution is `ait-vcs`; the `ait` name is already owned by
another project on PyPI. The CLI entry point remains `ait`.

Before uploading:

1. Confirm `pyproject.toml` version matches the PyPI release version.
2. Run `.venv/bin/pytest -q`.
3. Build with `.venv/bin/python -m build`.
4. Check artifacts with `.venv/bin/python -m twine check dist/*`.
5. Upload with `.venv/bin/python -m twine upload dist/*`.
6. Smoke test with `pip install ait-vcs`.

GitHub trusted publishing is also configured through
`.github/workflows/publish.yml`. On PyPI, create a pending trusted
publisher for:

```text
PyPI project: ait-vcs
Owner: m24927605
Repository: ait
Workflow: publish.yml
Environment: <blank>
```

Then publish a GitHub release or run the workflow manually.
