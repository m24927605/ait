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
9. Run a fresh venv smoke test from `dist/*.whl`, including the
   PATH-based `claude ...` wrapper smoke below.
10. Tag with the intended `vX.Y.Z`.
11. Push `main` and `vX.Y.Z` to GitHub.
12. Create a GitHub release with the built wheel and sdist.
13. Confirm GitHub Actions CI and Publish pass.
14. Confirm PyPI lists the new version.
15. Run a fresh venv smoke test from PyPI, including the PATH-based
    `claude ...` wrapper smoke below.

## PATH Claude Wrapper Smoke

Run this once against the local wheel and once against the just-published
PyPI version. The important detail is that the smoke invokes `claude`
through `PATH`; it should not call `.ait/bin/claude` directly.

For a local wheel:

```bash
set -e
tmpdir="$(mktemp -d)"
python3.14 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/pip" install -q dist/ait_vcs-X.Y.Z-py3-none-any.whl
repo="$tmpdir/repo" && mkdir "$repo" && cd "$repo"
git init -q
git config user.email test@example.com
git config user.name 'Test User'
printf 'hello\n' > README.md
git add README.md
git commit -qm init
bin="$tmpdir/bin" && mkdir "$bin"
cat > "$bin/claude" <<'SH'
#!/bin/sh
printf 'real claude reached\n'
printf 'agent wrote through PATH claude\n' > path-claude-output.txt
SH
chmod +x "$bin/claude"
PATH="$bin:$PATH" "$tmpdir/venv/bin/ait" init --adapter claude-code --format json > init.json
rm .ait/memory-policy.json
printf 'Prefer direct PATH claude use.\n' > CLAUDE.md
PATH="$repo/.ait/bin:$bin:$PATH" claude --fake-prompt > wrapper.json
"$tmpdir/venv/bin/ait" memory --format json > memory.json
"$tmpdir/venv/bin/python" - <<'PY'
import json
from pathlib import Path
init = json.loads(Path('init.json').read_text())
wrapper = json.loads(Path('wrapper.json').read_text())
memory = json.loads(Path('memory.json').read_text())
assert init['installed_adapters'] == ['claude-code'], init
assert wrapper['exit_code'] == 0, wrapper
assert wrapper['attempt']['commits'], wrapper
assert Path('.ait/memory-policy.json').exists()
assert Path(wrapper['workspace_ref'], 'path-claude-output.txt').exists(), wrapper
sources = {item['source'] for item in memory['notes']}
assert 'agent-memory:claude:CLAUDE.md' in sources, sources
assert any(source.startswith('attempt-memory:') for source in sources), sources
print('PATH claude smoke ok')
PY
```

For PyPI, replace the install line with:

```bash
"$tmpdir/venv/bin/pip" install -q --no-cache-dir ait-vcs==X.Y.Z
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
Environment: pypi
```

Then publish a GitHub release or run the workflow manually.
