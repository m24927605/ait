# Completion Audit: Split Query Module

## Evidence

- `uv run pytest tests/test_query.py` -> 18 passed in 0.07s
- `uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py` -> 89 passed in 34.22s
- `uv run pytest tests/test_query.py -k blame` -> 3 passed in 0.03s
- `uv run pytest` -> 503 passed in 323.37s
- `PYTHONPATH=src python3 -m unittest discover -s tests` -> Ran 503 tests in 320.474s, OK
- `git diff --check` -> passed
- `PYTHONPATH=src python3 - <<'PY' ...` public import contract -> `ait.query public imports ok`
- `wc -l src/ait/query/*.py | sort -nr` -> largest file is `fields.py` at 475 lines
- `test ! -f src/ait/query.py` -> passed

## Requirement Mapping

| Requirement | Evidence | Status |
| --- | --- | --- |
| FR-001 parse behavior | `tests/test_query.py` parser tests pass; parser moved to `src/ait/query/parser.py` | Pass |
| FR-002 compile behavior | `tests/test_query.py` compile/query tests pass; compile remains exported from `ait.query` | Pass |
| FR-003 execute behavior | `tests/test_query.py` execution tests and full suite pass | Pass |
| FR-004 shortcuts | `tests/test_query.py::test_shortcut_expression_quotes_user_input` passes | Pass |
| FR-005 blame behavior | `uv run pytest tests/test_query.py -k blame` passes | Pass |
| FR-006 public imports | Public import contract command passes; facade exports dataclasses and `QueryError` | Pass |
| FR-007 focused modules | `models.py`, `parser.py`, `fields.py`, `executor.py`, `blame.py` exist | Pass |
| FR-008 facade | `src/ait/query/__init__.py` is 40 lines and owns re-exports only | Pass |
| FR-009 public behavior | Targeted CLI/query tests and full suites pass unchanged | Pass |
| FR-010 cohesion/coupling metrics | No query module exceeds 600 lines; dependency direction matches plan | Pass |
| FR-011 discovered bugs | No query or blame bug was discovered during extraction; no regression test needed | Pass |

## Success Criteria Mapping

| Success Criterion | Evidence | Status |
| --- | --- | --- |
| SC-001 query tests pass | `uv run pytest tests/test_query.py` -> 18 passed | Pass |
| SC-002 CLI query/list behavior tests pass | `uv run pytest tests/test_cli_adapters.py tests/test_cli_run.py` -> 89 passed | Pass |
| SC-003 facade below 150 lines | `src/ait/query/__init__.py` is 40 lines; legacy `query.py` removed | Pass |
| SC-004 touched modules below 600 lines | Largest query module is `fields.py` at 475 lines | Pass |
| SC-005 public imports remain available | Public import contract command passes | Pass |
| SC-006 full tests and diff check pass | Full pytest, unittest discover, and `git diff --check` pass | Pass |

## Residual Risk

Generated SQL text was not snapshot-tested. This is acceptable because the
contract allows SQL reorganization when results, ordering, and bound-parameter
semantics remain equivalent; existing tests exercise those public outcomes.
