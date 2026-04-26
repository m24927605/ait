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

Current verification:

```text
116 passed
```
