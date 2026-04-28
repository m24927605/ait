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
9. Run `npm --prefix npm/ait-vcs test`.
10. Run `(cd npm/ait-vcs && npm pack --dry-run)`.
11. Run a fresh venv smoke test from `dist/*.whl`, including the
   PATH-based agent wrapper smoke below.
12. Tag with the intended `vX.Y.Z`.
13. Push `main` and `vX.Y.Z` to GitHub.
14. Create a GitHub release with the built wheel and sdist.
15. Confirm GitHub Actions CI and Publish pass.
16. Confirm PyPI lists the new version.
17. Run a fresh venv smoke test from PyPI, including the PATH-based
    agent wrapper smoke below.
18. Publish the npm package from `npm/ait-vcs` after PyPI lists the same
    version.
19. Run a fresh global npm smoke test with `npm install -g ait-vcs`.

## PATH Agent Wrapper Smoke

Run this once against the local wheel and once against the just-published
PyPI version. The important detail is that the smoke invokes the agent
command through `PATH`; it should not call `.ait/bin/<command>` directly.
Use `claude` for the default release smoke, and use the automated test
suite for adapter parity across `codex`, `aider`, `gemini`, and
`cursor`.

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

## npm Release

The npm distribution is `ait-vcs`; the `ait` name is already owned by
another project on npm. The npm package exports the `ait` command and
installs the matching PyPI release into a package-private virtual
environment during postinstall.

Before publishing npm:

1. Confirm `npm/ait-vcs/package.json` version matches `pyproject.toml`.
2. Confirm the matching PyPI version is already available.
3. Run `npm --prefix npm/ait-vcs test`.
4. Run `(cd npm/ait-vcs && npm pack --dry-run)`.
5. From `npm/ait-vcs`, run `npm publish --access public`.
6. Smoke test with `npm install -g ait-vcs`.
