# Release Checklist

## Tagged Release

Before tagging:

1. Confirm `pyproject.toml` version matches the intended tag.
2. Confirm `CHANGELOG.md` has an entry for the intended tag.
3. Run `git status --short`.
4. Run `.venv/bin/pytest -q`.
5. Run `git diff --check`.
6. Confirm README install and quickstart are current.
7. Build with `.venv/bin/python -m build`.
8. Check artifacts with `.venv/bin/python -m twine check dist/*`.
9. Run a fresh venv smoke test from `dist/*.whl`.
10. Tag with the intended `vX.Y.Z`.
11. Push `main` and `vX.Y.Z` to GitHub.
12. Create a GitHub release with the built wheel and sdist.
13. Confirm GitHub Actions CI and Publish pass.
14. Confirm PyPI lists the new version.
15. Run a fresh venv smoke test from PyPI.

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
Environment: pypi
```

Then publish a GitHub release or run the workflow manually.
