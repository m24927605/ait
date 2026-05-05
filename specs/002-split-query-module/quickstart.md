# Quickstart: Split Query Module

## Baseline Verification

Run the current query tests before code movement:

```bash
uv run pytest tests/test_query.py
```

## Refactor Verification

After implementation, run:

```bash
uv run pytest tests/test_query.py
uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py
uv run pytest
PYTHONPATH=src python3 -m unittest discover -s tests
git diff --check
```

## Architecture Checks

Confirm `ait.query` remains import-compatible:

```bash
PYTHONPATH=src python3 - <<'PY'
from ait.query import (
    BinaryExpression, BlameRecord, BlameTarget, Comparison, QueryError,
    QueryPlan, UnaryExpression, blame_path, compile_query, execute_query,
    list_shortcut_expression, parse_blame_target, parse_query,
)
print("ait.query public imports ok")
PY
```

Confirm touched query files stay cohesive:

```bash
wc -l src/ait/query/*.py | sort -nr
```

Expected outcome:

- `src/ait/query/__init__.py` is below 150 lines.
- No `src/ait/query/*.py` file exceeds 600 lines.
- `src/ait/query.py` no longer exists.
