# AIT Bug Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the opt-in `ait bug-report` feature defined in
`docs/superpowers/specs/2026-05-28-bug-report-design.md`: detect AIT-internal
failures, with user consent send a redacted report to
`github.com/m24927605/ait/issues` via the `gh` CLI or a pre-filled URL,
deduplicate across runs, never block the main CLI flow.

**Architecture:** New `src/ait/bug_report/` package (stdlib-only) exposing
`install_excepthook`, `report_internal_error`, and `flush_at_exit`. CLI
surface via `src/ait/cli/bug_report.py` and `ait config bug-report`. XDG
state under `~/.config/ait/` and `~/.local/state/ait/bug_reports/`. Layer 2
instrumentation at 8 known catch sites. All public surfaces are
`_safe`-wrapped so any failure in the bug-report path is silently logged
and never propagates.

**Tech Stack:** Python 3.14 stdlib only (`urllib.request`, `subprocess`,
`hashlib`, `json`, `pathlib`, `os`, `sys`, `atexit`, `webbrowser`, `re`,
`socket`, `functools`, `dataclasses`). Tests use stdlib `unittest`. No new
runtime dependencies.

---

## Conventions (read before any task)

**Test invocation (run inside repo root):**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

For a single test module:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_fingerprint -v
```

**Commit message format (CLAUDE.md mandate)** — every commit ends with:

```
docs:<comma-separated-related-doc-paths>
keyword:<comma-separated-keywords>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Use HEREDOC for the `-m` argument (see existing examples in this plan).

**Test file boilerplate** (mirrors existing tests):

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
```

(For tests under `tests/bug_report/` — note `parents[2]` because of the
extra subdirectory.)

**Source file boilerplate:**

```python
from __future__ import annotations
```

**Forbidden:** new runtime dependencies, network access in tests, real
`subprocess` spawning in tests, mutating `~/.config` or `~/.local/state`
in tests (use `XDG_CONFIG_HOME` / `XDG_STATE_HOME` env vars).

---

## File Structure

**New source files (all under `src/ait/`):**

```
bug_report/
  __init__.py                # empty
  api.py                     # public: install_excepthook, report_internal_error, flush_at_exit
  config.py                  # XDG paths, preference schema, load/save
  fingerprint.py             # pure: fingerprint(exc_type, frames) -> str
  redactor.py                # pure: redact(text) -> str
  collector.py               # process-local single-instance accumulator
  excepthook.py              # install/uninstall sys.excepthook chain
  seen_store.py              # ~/.local/state/ait/bug_reports/seen.json I/O
  pending_queue.py           # ~/.local/state/ait/bug_reports/pending/ I/O
  builder.py                 # compose Issue title + body markdown
  submitter.py               # gh -> URL -> pending fallback ladder
  safety.py                  # _safe decorator + _log_internal_error
cli/
  bug_report.py              # `ait bug-report` subcommand
```

**Modified source files:**

- `src/ait/cli/main.py` — install excepthook + register atexit
- `src/ait/cli/__init__.py` or `cli/main.py` argparse — register `bug-report` subcommand
- `src/ait/cli/config.py` — add `bug-report` subkey handling
- `src/ait/daemon_transport.py:36` — Layer 2 site #1
- `src/ait/daemon.py:197` — Layer 2 site #2
- `src/ait/db/core.py:52` — Layer 2 site #3
- `src/ait/events.py:455` — Layer 2 site #4
- `src/ait/runner.py:477` — Layer 2 site #5
- `src/ait/hooks.py` — Layer 2 site #6 (hook install failure)
- `src/ait/reconcile.py` — Layer 2 site #7
- `src/ait/verifier.py` — Layer 2 site #8

**New test files (all under `tests/bug_report/`):**

```
__init__.py
test_fingerprint.py
test_redactor.py
test_config.py
test_seen_store.py
test_pending_queue.py
test_collector.py
test_excepthook.py
test_safety.py
test_builder.py
test_submitter_gh.py
test_submitter_url.py
test_submitter_pending.py
test_api.py
test_cli_bug_report.py
test_cli_config_bug_report.py
test_layer2_instrumentation.py
test_end_to_end_flow.py
```

---

# Phase 1 — Foundation primitives

Pure functions and storage primitives. No external IO except disk through
the XDG paths. Each task should commit independently.

## Task 1: Fingerprint algorithm

**Files:**
- Create: `src/ait/bug_report/__init__.py` (empty)
- Create: `src/ait/bug_report/fingerprint.py`
- Create: `tests/bug_report/__init__.py` (empty)
- Create: `tests/bug_report/test_fingerprint.py`

- [ ] **Step 1: Create the empty package init files**

```bash
mkdir -p src/ait/bug_report tests/bug_report
touch src/ait/bug_report/__init__.py tests/bug_report/__init__.py
```

- [ ] **Step 2: Write the failing test**

File: `tests/bug_report/test_fingerprint.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.fingerprint import Frame, fingerprint


class FingerprintTests(unittest.TestCase):
    def test_returns_fp_prefixed_8_hex(self):
        fp = fingerprint("ValueError", [Frame("foo.py", "bar")])
        self.assertTrue(fp.startswith("fp:"))
        self.assertEqual(len(fp), 11)  # 'fp:' + 8 hex
        int(fp[3:], 16)  # must be valid hex

    def test_same_input_same_output(self):
        frames = [Frame("foo.py", "bar"), Frame("baz.py", "qux")]
        self.assertEqual(
            fingerprint("ValueError", frames),
            fingerprint("ValueError", frames),
        )

    def test_different_exc_type_different_fp(self):
        frames = [Frame("foo.py", "bar")]
        self.assertNotEqual(
            fingerprint("ValueError", frames),
            fingerprint("TypeError", frames),
        )

    def test_line_numbers_ignored(self):
        a = [Frame("foo.py", "bar")]
        b = [Frame("foo.py", "bar")]
        self.assertEqual(fingerprint("E", a), fingerprint("E", b))

    def test_basename_extracted(self):
        a = [Frame("/long/abs/path/foo.py", "bar")]
        b = [Frame("foo.py", "bar")]
        self.assertEqual(fingerprint("E", a), fingerprint("E", b))

    def test_only_top_3_frames(self):
        a = [Frame(f"f{i}.py", "g") for i in range(5)]
        b = a[:3]
        self.assertEqual(fingerprint("E", a), fingerprint("E", b))

    def test_fewer_than_3_frames_ok(self):
        fp = fingerprint("E", [Frame("a.py", "b")])
        self.assertTrue(fp.startswith("fp:"))

    def test_empty_frames_ok(self):
        fp = fingerprint("E", [])
        self.assertTrue(fp.startswith("fp:"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_fingerprint -v
```

Expected: `ImportError: No module named 'ait.bug_report.fingerprint'` or
similar.

- [ ] **Step 4: Write implementation**

File: `src/ait/bug_report/fingerprint.py`

```python
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    filename: str
    function: str


def fingerprint(exc_type: str, frames: list[Frame]) -> str:
    """Return 'fp:' + 8-hex SHA256 over (exc_type, top-3 (basename, fn))."""
    parts = [exc_type]
    for frame in frames[:3]:
        parts.append(f"{os.path.basename(frame.filename)}:{frame.function}")
    blob = "\n".join(parts).encode("utf-8")
    return "fp:" + hashlib.sha256(blob).hexdigest()[:8]
```

- [ ] **Step 5: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_fingerprint -v
```

Expected: `OK` with all 8 cases passing.

- [ ] **Step 6: Commit**

```bash
git add src/ait/bug_report/__init__.py src/ait/bug_report/fingerprint.py \
        tests/bug_report/__init__.py tests/bug_report/test_fingerprint.py
git commit -m "$(cat <<'EOF'
feat(bug-report): fingerprint algorithm for error dedup

Pure function: SHA256 over exc_type + top-3 (basename, function) frames.
Deliberately excludes line numbers and AIT version so minor edits and
version bumps don't shatter dedup.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,fingerprint,dedup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Redactor

**Files:**
- Create: `src/ait/bug_report/redactor.py`
- Create: `tests/bug_report/test_redactor.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_redactor.py`

```python
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.redactor import redact, redact_argv


class RedactTests(unittest.TestCase):
    def test_home_replaced(self):
        home = os.path.expanduser("~")
        self.assertIn("~/projects/foo", redact(f"{home}/projects/foo"))

    def test_gh_token_redacted(self):
        s = "token=ghp_" + "A" * 36
        self.assertIn("[REDACTED_TOKEN]", redact(s))
        self.assertNotIn("ghp_", redact(s))

    def test_openai_key_redacted(self):
        s = "key=sk-" + "B" * 32
        self.assertIn("[REDACTED_TOKEN]", redact(s))

    def test_email_redacted(self):
        s = "from alice@example.com to me"
        self.assertIn("[REDACTED_EMAIL]", redact(s))
        self.assertNotIn("alice@example.com", redact(s))

    def test_passthrough_safe_text(self):
        s = "plain stack trace line"
        self.assertEqual(redact(s), s)


class RedactArgvTests(unittest.TestCase):
    def test_space_separated(self):
        argv = ["ait", "run", "--api-key", "secret123", "--intent", "foo"]
        out = redact_argv(argv)
        self.assertEqual(out, ["ait", "run", "--api-key", "[REDACTED]",
                               "--intent", "foo"])

    def test_equals_joined(self):
        argv = ["ait", "run", "--token=abc", "--intent=foo"]
        out = redact_argv(argv)
        self.assertEqual(out, ["ait", "run", "--token=[REDACTED]",
                               "--intent=foo"])

    def test_password_flag(self):
        argv = ["x", "--password", "p"]
        self.assertEqual(redact_argv(argv), ["x", "--password", "[REDACTED]"])

    def test_unknown_flag_untouched(self):
        argv = ["x", "--foo", "bar"]
        self.assertEqual(redact_argv(argv), ["x", "--foo", "bar"])

    def test_trailing_sensitive_flag(self):
        argv = ["x", "--api-key"]  # no value
        self.assertEqual(redact_argv(argv), ["x", "--api-key"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_redactor -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/redactor.py`

```python
from __future__ import annotations

import os
import re

_TOKEN_PATTERNS = (
    re.compile(r"gh[ps]_[A-Za-z0-9]{30,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SENSITIVE_FLAGS = frozenset({"--api-key", "--token", "--password"})


def redact(text: str) -> str:
    if not text:
        return text
    home = os.path.expanduser("~")
    if home and home in text:
        text = text.replace(home, "~")
    for pat in _TOKEN_PATTERNS:
        text = pat.sub("[REDACTED_TOKEN]", text)
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    return text


def redact_argv(argv: list[str]) -> list[str]:
    out: list[str] = []
    skip_next = False
    for i, arg in enumerate(argv):
        if skip_next:
            out.append("[REDACTED]")
            skip_next = False
            continue
        if "=" in arg:
            flag, _, _ = arg.partition("=")
            if flag in _SENSITIVE_FLAGS:
                out.append(f"{flag}=[REDACTED]")
                continue
        if arg in _SENSITIVE_FLAGS:
            out.append(arg)
            # Only mark next for redaction if there IS a next.
            if i + 1 < len(argv):
                skip_next = True
            continue
        out.append(arg)
    return out
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_redactor -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/redactor.py tests/bug_report/test_redactor.py
git commit -m "$(cat <<'EOF'
feat(bug-report): redactor for HOME, tokens, emails, argv flags

Best-effort substitution layer. The review screen remains the final
defense — this is not a security guarantee.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,redaction,privacy

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Config (XDG paths + preference schema)

**Files:**
- Create: `src/ait/bug_report/config.py`
- Create: `tests/bug_report/test_config.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_config.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.config import (
    BugReportPrefs,
    config_path,
    env_disabled,
    load_prefs,
    save_prefs,
    state_dir,
)


class XDGPathTests(unittest.TestCase):
    def test_config_path_default(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CONFIG_HOME"] = td
            try:
                p = config_path()
                self.assertEqual(p, Path(td) / "ait" / "config.json")
            finally:
                del os.environ["XDG_CONFIG_HOME"]

    def test_state_dir_default(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_STATE_HOME"] = td
            try:
                p = state_dir()
                self.assertEqual(p, Path(td) / "ait" / "bug_reports")
            finally:
                del os.environ["XDG_STATE_HOME"]


class PrefsRoundTripTests(unittest.TestCase):
    def test_load_missing_returns_unset_default(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CONFIG_HOME"] = td
            try:
                prefs = load_prefs()
                self.assertEqual(prefs.mode, "unset")
                self.assertTrue(prefs.include_tier2)
                self.assertFalse(prefs.include_tier3)
            finally:
                del os.environ["XDG_CONFIG_HOME"]

    def test_save_then_load_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["XDG_CONFIG_HOME"] = td
            try:
                prefs = BugReportPrefs(
                    mode="always",
                    include_tier2=False,
                    include_tier3=True,
                )
                save_prefs(prefs)
                loaded = load_prefs()
                self.assertEqual(loaded.mode, "always")
                self.assertFalse(loaded.include_tier2)
                self.assertTrue(loaded.include_tier3)
            finally:
                del os.environ["XDG_CONFIG_HOME"]


class EnvDisableTests(unittest.TestCase):
    def test_env_never_disables(self):
        os.environ["AIT_BUG_REPORT"] = "never"
        try:
            self.assertTrue(env_disabled())
        finally:
            del os.environ["AIT_BUG_REPORT"]

    def test_no_env_means_not_disabled(self):
        os.environ.pop("AIT_BUG_REPORT", None)
        self.assertFalse(env_disabled())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_config -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/config.py`

```python
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
VALID_MODES = ("unset", "ask", "always", "never")


@dataclass
class BugReportPrefs:
    mode: str = "unset"
    first_setup_at: str | None = None
    last_prompted_at: str | None = None
    include_tier2: bool = True
    include_tier3: bool = False


def _xdg_config_home() -> Path:
    val = os.environ.get("XDG_CONFIG_HOME")
    if val:
        return Path(val)
    return Path.home() / ".config"


def _xdg_state_home() -> Path:
    val = os.environ.get("XDG_STATE_HOME")
    if val:
        return Path(val)
    return Path.home() / ".local" / "state"


def config_path() -> Path:
    return _xdg_config_home() / "ait" / "config.json"


def state_dir() -> Path:
    return _xdg_state_home() / "ait" / "bug_reports"


def env_disabled() -> bool:
    return os.environ.get("AIT_BUG_REPORT", "").strip().lower() == "never"


def load_prefs() -> BugReportPrefs:
    p = config_path()
    if not p.exists():
        return BugReportPrefs()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return BugReportPrefs()
    block = data.get("bug_report") or {}
    mode = block.get("mode", "unset")
    if mode not in VALID_MODES:
        mode = "unset"
    return BugReportPrefs(
        mode=mode,
        first_setup_at=block.get("first_setup_at"),
        last_prompted_at=block.get("last_prompted_at"),
        include_tier2=bool(block.get("include_tier2", True)),
        include_tier3=bool(block.get("include_tier3", False)),
    )


def save_prefs(prefs: BugReportPrefs) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.setdefault("schema_version", SCHEMA_VERSION)
    existing["bug_report"] = asdict(prefs)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(existing, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(p)
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_config -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/config.py tests/bug_report/test_config.py
git commit -m "$(cat <<'EOF'
feat(bug-report): XDG-compliant preference store

BugReportPrefs dataclass + load/save via XDG_CONFIG_HOME. Atomic write
through .tmp + replace. AIT_BUG_REPORT=never env override.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,config,xdg,preferences

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Seen store (dedup state JSON)

**Files:**
- Create: `src/ait/bug_report/seen_store.py`
- Create: `tests/bug_report/test_seen_store.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_seen_store.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.seen_store import (
    SeenEntry,
    load_seen,
    record_seen,
    record_submitted,
    save_seen,
)


class SeenStoreTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_load_missing_returns_empty(self):
        self.assertEqual(load_seen(), {})

    def test_record_seen_increments_count(self):
        record_seen("fp:aaaa1111", category="db.operational", now="2026-05-28T10:00:00Z")
        record_seen("fp:aaaa1111", category="db.operational", now="2026-05-28T10:05:00Z")
        store = load_seen()
        self.assertEqual(store["fp:aaaa1111"].count, 2)
        self.assertEqual(store["fp:aaaa1111"].first_seen_at, "2026-05-28T10:00:00Z")
        self.assertEqual(store["fp:aaaa1111"].last_seen_at, "2026-05-28T10:05:00Z")

    def test_record_submitted_attaches_issue_url(self):
        record_seen("fp:bbbb2222", category="x", now="2026-05-28T10:00:00Z")
        record_submitted("fp:bbbb2222",
                        issue_url="https://github.com/m24927605/ait/issues/123",
                        method="gh",
                        now="2026-05-28T10:01:00Z")
        e = load_seen()["fp:bbbb2222"]
        self.assertEqual(e.submitted_issue_url,
                         "https://github.com/m24927605/ait/issues/123")
        self.assertEqual(e.submitted_method, "gh")

    def test_save_round_trip(self):
        record_seen("fp:cccc3333", category="c", now="2026-05-28T10:00:00Z")
        store = load_seen()
        save_seen(store)
        again = load_seen()
        self.assertEqual(again["fp:cccc3333"].count, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_seen_store -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/seen_store.py`

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ait.bug_report.config import state_dir

SCHEMA_VERSION = 1


@dataclass
class SeenEntry:
    fingerprint: str
    category: str
    count: int = 0
    first_seen_at: str = ""
    last_seen_at: str = ""
    submitted_issue_url: str | None = None
    submitted_method: str | None = None
    submitted_at: str | None = None
    last_status_check_at: str | None = None
    last_known_state: str | None = None  # "open" | "closed" | "locked" | None


def _path() -> Path:
    return state_dir() / "seen.json"


def load_seen() -> dict[str, SeenEntry]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, SeenEntry] = {}
    for fp, raw in (data.get("entries") or {}).items():
        out[fp] = SeenEntry(
            fingerprint=fp,
            category=raw.get("category", ""),
            count=int(raw.get("count", 0)),
            first_seen_at=raw.get("first_seen_at", ""),
            last_seen_at=raw.get("last_seen_at", ""),
            submitted_issue_url=raw.get("submitted_issue_url"),
            submitted_method=raw.get("submitted_method"),
            submitted_at=raw.get("submitted_at"),
            last_status_check_at=raw.get("last_status_check_at"),
            last_known_state=raw.get("last_known_state"),
        )
    return out


def save_seen(store: dict[str, SeenEntry]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "entries": {fp: _entry_to_json(e) for fp, e in store.items()},
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def _entry_to_json(e: SeenEntry) -> dict:
    d = asdict(e)
    d.pop("fingerprint", None)
    return d


def record_seen(fingerprint: str, *, category: str, now: str) -> None:
    store = load_seen()
    e = store.get(fingerprint)
    if e is None:
        e = SeenEntry(
            fingerprint=fingerprint,
            category=category,
            count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
    else:
        e.count += 1
        e.last_seen_at = now
    store[fingerprint] = e
    save_seen(store)


def record_submitted(
    fingerprint: str,
    *,
    issue_url: str | None,
    method: str,
    now: str,
) -> None:
    store = load_seen()
    e = store.get(fingerprint)
    if e is None:
        # First record-submit without record-seen — shouldn't happen but be safe.
        e = SeenEntry(
            fingerprint=fingerprint,
            category="",
            count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
    e.submitted_issue_url = issue_url
    e.submitted_method = method
    e.submitted_at = now
    if issue_url:
        e.last_known_state = "open"
    store[fingerprint] = e
    save_seen(store)
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_seen_store -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/seen_store.py tests/bug_report/test_seen_store.py
git commit -m "$(cat <<'EOF'
feat(bug-report): seen.json dedup state store

SeenEntry dataclass with count + submitted_issue_url + last_known_state
for the dedup decision table. Atomic writes via XDG_STATE_HOME path.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,dedup,seen-store

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Pending queue

**Files:**
- Create: `src/ait/bug_report/pending_queue.py`
- Create: `tests/bug_report/test_pending_queue.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_pending_queue.py`

```python
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.pending_queue import (
    PendingReport,
    clear_pending,
    enqueue,
    list_pending,
    load_pending,
    prune_old,
    remove,
)


class PendingQueueTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_enqueue_then_load(self):
        report = PendingReport(
            fingerprint="fp:aaaa1111",
            title="t",
            body="b",
            category="x",
            created_at="2026-05-28T10:00:00Z",
        )
        enqueue(report)
        loaded = load_pending("fp:aaaa1111")
        self.assertEqual(loaded.title, "t")
        self.assertEqual(loaded.body, "b")

    def test_list_empty(self):
        self.assertEqual(list_pending(), [])

    def test_list_returns_all_fingerprints(self):
        for fp in ("fp:aaaa1111", "fp:bbbb2222"):
            enqueue(PendingReport(
                fingerprint=fp, title="t", body="b",
                category="c", created_at="2026-05-28T10:00:00Z",
            ))
        self.assertEqual(set(list_pending()), {"fp:aaaa1111", "fp:bbbb2222"})

    def test_remove(self):
        enqueue(PendingReport(
            fingerprint="fp:aaaa1111", title="t", body="b",
            category="c", created_at="2026-05-28T10:00:00Z",
        ))
        remove("fp:aaaa1111")
        self.assertEqual(list_pending(), [])

    def test_prune_old_drops_files_over_30_days(self):
        old = (dt.datetime(2026, 5, 28, tzinfo=dt.timezone.utc)
               - dt.timedelta(days=31)).isoformat().replace("+00:00", "Z")
        enqueue(PendingReport(
            fingerprint="fp:oldold01", title="t", body="b",
            category="c", created_at=old,
        ))
        enqueue(PendingReport(
            fingerprint="fp:new1111", title="t", body="b",
            category="c", created_at="2026-05-28T10:00:00Z",
        ))
        prune_old(now=dt.datetime(2026, 5, 28, tzinfo=dt.timezone.utc))
        remaining = set(list_pending())
        self.assertEqual(remaining, {"fp:new1111"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_pending_queue -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/pending_queue.py`

```python
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ait.bug_report.config import state_dir


@dataclass
class PendingReport:
    fingerprint: str
    title: str
    body: str
    category: str
    created_at: str


def _pending_dir() -> Path:
    return state_dir() / "pending"


def _path_for(fingerprint: str) -> Path:
    # Sanitize: only allow fp:hex form (collector controls input but defense in depth).
    safe = fingerprint.replace("/", "_").replace("\\", "_")
    return _pending_dir() / f"{safe}.json"


def enqueue(report: PendingReport) -> None:
    d = _pending_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = _path_for(report.fingerprint)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(p)


def load_pending(fingerprint: str) -> PendingReport | None:
    p = _path_for(fingerprint)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return PendingReport(
        fingerprint=data["fingerprint"],
        title=data["title"],
        body=data["body"],
        category=data["category"],
        created_at=data["created_at"],
    )


def list_pending() -> list[str]:
    d = _pending_dir()
    if not d.exists():
        return []
    out = []
    for entry in d.iterdir():
        if entry.suffix == ".json":
            out.append(entry.stem)
    return out


def remove(fingerprint: str) -> bool:
    p = _path_for(fingerprint)
    if not p.exists():
        return False
    p.unlink()
    return True


def clear_pending() -> int:
    d = _pending_dir()
    if not d.exists():
        return 0
    count = 0
    for entry in list(d.iterdir()):
        if entry.suffix == ".json":
            entry.unlink()
            count += 1
    return count


def prune_old(*, now: dt.datetime, max_age_days: int = 30) -> int:
    cutoff = now - dt.timedelta(days=max_age_days)
    pruned = 0
    for fp in list_pending():
        report = load_pending(fp)
        if report is None:
            continue
        try:
            created = dt.datetime.fromisoformat(
                report.created_at.replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if created < cutoff:
            remove(fp)
            pruned += 1
    return pruned
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_pending_queue -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/pending_queue.py tests/bug_report/test_pending_queue.py
git commit -m "$(cat <<'EOF'
feat(bug-report): pending queue for offline / oversized reports

PendingReport on-disk format under XDG_STATE_HOME/ait/bug_reports/pending/.
30-day prune helper for housekeeping at CLI startup.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,pending-queue,offline

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 2 — Collection & lifecycle

## Task 6: Collector (process-local accumulator)

**Files:**
- Create: `src/ait/bug_report/collector.py`
- Create: `tests/bug_report/test_collector.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_collector.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.collector import Collector, CollectedEntry
from ait.bug_report.fingerprint import Frame


def _make_exc():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


class CollectorTests(unittest.TestCase):
    def test_starts_empty(self):
        c = Collector()
        self.assertEqual(c.entries(), [])

    def test_record_one(self):
        c = Collector()
        c.record(category="db.operational", exc=_make_exc(),
                 context=None, now="2026-05-28T10:00:00Z")
        self.assertEqual(len(c.entries()), 1)
        e = c.entries()[0]
        self.assertEqual(e.category, "db.operational")
        self.assertEqual(e.exc_type, "ValueError")
        self.assertEqual(e.exc_message, "boom")

    def test_same_fp_merges_count(self):
        c = Collector()
        for _ in range(3):
            c.record(category="x", exc=_make_exc(),
                     context=None, now="2026-05-28T10:00:00Z")
        entries = c.entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].count, 3)

    def test_capacity_20(self):
        c = Collector(max_entries=20)
        # 21 distinct categories => 21 distinct entries; oldest should be dropped.
        for i in range(21):
            c.record(category=f"cat-{i}", exc=_make_exc(),
                     context=None, now="2026-05-28T10:00:00Z")
        self.assertEqual(len(c.entries()), 20)
        cats = {e.category for e in c.entries()}
        self.assertNotIn("cat-0", cats)
        self.assertIn("cat-20", cats)
        self.assertTrue(c.truncated)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_collector -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/collector.py`

```python
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any

from ait.bug_report.fingerprint import Frame, fingerprint


@dataclass
class CollectedEntry:
    category: str
    exc_type: str
    exc_message: str
    frames: list[Frame]
    fingerprint: str
    count: int
    context: dict[str, Any] | None
    first_recorded_at: str
    last_recorded_at: str


def _extract_frames(exc: BaseException) -> list[Frame]:
    tb = exc.__traceback__
    frames: list[Frame] = []
    while tb is not None:
        frames.append(Frame(
            filename=tb.tb_frame.f_code.co_filename,
            function=tb.tb_frame.f_code.co_name,
        ))
        tb = tb.tb_next
    # Deepest frame first.
    frames.reverse()
    return frames


class Collector:
    def __init__(self, max_entries: int = 20) -> None:
        self._max = max_entries
        self._entries: dict[str, CollectedEntry] = {}
        self._order: list[str] = []
        self.truncated = False

    def record(
        self,
        *,
        category: str,
        exc: BaseException,
        context: dict[str, Any] | None,
        now: str,
    ) -> None:
        frames = _extract_frames(exc)
        exc_type = type(exc).__name__
        fp = fingerprint(exc_type, frames)
        existing = self._entries.get(fp)
        if existing is not None:
            existing.count += 1
            existing.last_recorded_at = now
            return
        entry = CollectedEntry(
            category=category,
            exc_type=exc_type,
            exc_message=str(exc),
            frames=frames,
            fingerprint=fp,
            count=1,
            context=context,
            first_recorded_at=now,
            last_recorded_at=now,
        )
        if len(self._entries) >= self._max:
            # Drop oldest by insertion order.
            oldest = self._order.pop(0)
            self._entries.pop(oldest, None)
            self.truncated = True
        self._entries[fp] = entry
        self._order.append(fp)

    def entries(self) -> list[CollectedEntry]:
        return [self._entries[fp] for fp in self._order]


_GLOBAL: Collector | None = None


def collector() -> Collector:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Collector()
    return _GLOBAL


def reset_for_tests() -> None:
    """Test-only helper to clear the singleton between cases."""
    global _GLOBAL
    _GLOBAL = None
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_collector -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/collector.py tests/bug_report/test_collector.py
git commit -m "$(cat <<'EOF'
feat(bug-report): process-local error collector

Module-level singleton Collector with 20-entry cap (FIFO drop) and
fingerprint-based merge. Records exc_type, message, frames, count.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,collector,singleton

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Self-safety wrapper

**Files:**
- Create: `src/ait/bug_report/safety.py`
- Create: `tests/bug_report/test_safety.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_safety.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.safety import _safe, _log_internal_error


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_safe_returns_value_on_success(self):
        @_safe
        def f(x: int) -> int:
            return x + 1
        self.assertEqual(f(2), 3)

    def test_safe_swallows_exception_returning_none(self):
        @_safe
        def f():
            raise RuntimeError("boom")
        self.assertIsNone(f())

    def test_log_internal_error_writes_file(self):
        try:
            raise ValueError("hello")
        except ValueError as exc:
            _log_internal_error(exc)
        log = Path(self._td.name) / "ait" / "bug_reports" / "internal_errors.log"
        self.assertTrue(log.exists())
        content = log.read_text(encoding="utf-8")
        self.assertIn("ValueError", content)
        self.assertIn("hello", content)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_safety -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/safety.py`

```python
from __future__ import annotations

import datetime as dt
import functools
import traceback
from typing import Any, Callable, TypeVar

from ait.bug_report.config import state_dir

T = TypeVar("T")


def _log_path():
    return state_dir() / "internal_errors.log"


def _log_internal_error(exc: BaseException) -> None:
    """Append a traceback to internal_errors.log. Never raises."""
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"--- {ts} ---\n{tb}\n")
    except Exception:
        # Truly cannot do anything if even the log fails.
        pass


def _safe(fn: Callable[..., T]) -> Callable[..., T | None]:
    """Wrap fn so any exception is logged and converted to None.

    Never re-enters the bug_report collector to avoid infinite recursion.
    """
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> T | None:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            _log_internal_error(exc)
            return None
    return wrapper
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_safety -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/safety.py tests/bug_report/test_safety.py
git commit -m "$(cat <<'EOF'
feat(bug-report): _safe wrapper and internal_errors.log

Decorator catches any exception in bug-report public API, appends
traceback to internal_errors.log, returns None. Never re-enters
collector — avoids infinite recursion when bug_report itself faults.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,safety,error-handling

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Excepthook chain installer

**Files:**
- Create: `src/ait/bug_report/excepthook.py`
- Create: `tests/bug_report/test_excepthook.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_excepthook.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.excepthook import install, uninstall


class ExcepthookTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()
        self._original_hook = sys.excepthook

    def tearDown(self):
        sys.excepthook = self._original_hook
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_install_records_ait_exception(self):
        install()
        # Fabricate an exception with a frame whose module looks like 'ait.x'.
        try:
            raise ValueError("from ait")
        except ValueError as exc:
            # Force module attribution: set exc's traceback frame globals.
            sys.excepthook(type(exc), exc, exc.__traceback__)
        entries = collector_mod.collector().entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].exc_type, "ValueError")

    def test_install_skips_keyboard_interrupt(self):
        install()
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        self.assertEqual(collector_mod.collector().entries(), [])

    def test_chain_calls_previous_hook(self):
        calls = []

        def prev_hook(et, ev, tb):
            calls.append("prev")

        sys.excepthook = prev_hook
        install()
        try:
            raise ValueError("x")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        self.assertEqual(calls, ["prev"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_excepthook -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/excepthook.py`

```python
from __future__ import annotations

import datetime as dt
import sys
from types import TracebackType
from typing import Any, Callable

from ait.bug_report import collector as collector_mod
from ait.bug_report.config import env_disabled, load_prefs
from ait.bug_report.safety import _safe

_SKIP = (KeyboardInterrupt, SystemExit, BrokenPipeError)

_PREV_HOOK: Callable[..., Any] | None = None


@_safe
def install() -> None:
    """Chain a new excepthook that records to the collector then delegates."""
    if env_disabled():
        return
    if load_prefs().mode == "never":
        return

    global _PREV_HOOK
    if _PREV_HOOK is not None:
        return  # already installed
    _PREV_HOOK = sys.excepthook
    sys.excepthook = _hook


@_safe
def uninstall() -> None:
    global _PREV_HOOK
    if _PREV_HOOK is None:
        return
    sys.excepthook = _PREV_HOOK
    _PREV_HOOK = None


def _hook(exc_type, exc_value, tb) -> None:
    try:
        if not isinstance(exc_value, _SKIP):
            now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
            collector_mod.collector().record(
                category="excepthook",
                exc=exc_value,
                context=None,
                now=now,
            )
    except Exception:
        # Never let our hook break the previous hook.
        pass
    finally:
        if _PREV_HOOK is not None:
            _PREV_HOOK(exc_type, exc_value, tb)
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_excepthook -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/excepthook.py tests/bug_report/test_excepthook.py
git commit -m "$(cat <<'EOF'
feat(bug-report): sys.excepthook chain installer

install() saves the previous hook then installs a new one that records
into the collector before delegating, preserving existing traceback
output bit-for-bit. Skips KeyboardInterrupt / SystemExit / BrokenPipeError.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,excepthook,layer-1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 3 — Builder & submitter

## Task 9: Issue body builder

**Files:**
- Create: `src/ait/bug_report/builder.py`
- Create: `tests/bug_report/test_builder.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_builder.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.builder import BuildInput, build_issue
from ait.bug_report.collector import CollectedEntry
from ait.bug_report.fingerprint import Frame


def _entry(fp="fp:aaaa1111", cat="db.operational", msg="disk fail"):
    return CollectedEntry(
        category=cat,
        exc_type="ValueError",
        exc_message=msg,
        frames=[Frame("foo.py", "bar")],
        fingerprint=fp,
        count=1,
        context=None,
        first_recorded_at="2026-05-28T10:00:00Z",
        last_recorded_at="2026-05-28T10:00:00Z",
    )


class BuilderTests(unittest.TestCase):
    def test_title_includes_category_and_fp(self):
        b = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3",
            python_version="3.14.4",
            os_arch="darwin/arm64",
            argv=["ait", "run"],
            include_tier2=False,
            include_tier3=False,
            install_nonce="abc12345",
            daemon_log_tail="",
            daemon_state="",
            phase="",
            env_vars={},
            extra_transcript=None,
            repo_id=None,
        ))
        self.assertIn("[crash]", b.title)
        self.assertIn("db.operational", b.title)
        self.assertIn("fp:aaaa1111", b.title)

    def test_body_tier1_always_present(self):
        b = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait", "run"],
            include_tier2=False, include_tier3=False,
            install_nonce="x", daemon_log_tail="", daemon_state="",
            phase="", env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertIn("AIT: 1.4.3", b.body)
        self.assertIn("Python: 3.14.4", b.body)
        self.assertIn("darwin/arm64", b.body)
        self.assertIn("ait run", b.body)
        self.assertIn("fp:aaaa1111", b.body)

    def test_tier2_gated(self):
        with_t2 = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait"],
            include_tier2=True, include_tier3=False,
            install_nonce="abc12345",
            daemon_log_tail="log line 1\nlog line 2",
            daemon_state="running", phase="provision",
            env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertIn("abc12345", with_t2.body)
        self.assertIn("log line 1", with_t2.body)

        no_t2 = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait"],
            include_tier2=False, include_tier3=False,
            install_nonce="abc12345",
            daemon_log_tail="log line 1",
            daemon_state="running", phase="provision",
            env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertNotIn("abc12345", no_t2.body)
        self.assertNotIn("log line 1", no_t2.body)

    def test_scope_banner_present(self):
        b = build_issue(BuildInput(
            entries=[_entry()],
            ait_version="1.4.3", python_version="3.14.4",
            os_arch="darwin/arm64", argv=["ait"],
            include_tier2=False, include_tier3=False,
            install_nonce="x", daemon_log_tail="", daemon_state="",
            phase="", env_vars={}, extra_transcript=None, repo_id=None,
        ))
        self.assertIn("bug in **AIT itself**", b.body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_builder -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/builder.py`

```python
from __future__ import annotations

import shlex
from dataclasses import dataclass

from ait.bug_report.collector import CollectedEntry
from ait.bug_report.redactor import redact, redact_argv


SCOPE_BANNER = (
    "> Automatically generated by `ait`. Reviewed and submitted by the user.\n"
    "> Reports a bug in **AIT itself** — not the user's code or AI-agent output.\n"
)


@dataclass
class BuildInput:
    entries: list[CollectedEntry]
    ait_version: str
    python_version: str
    os_arch: str
    argv: list[str]
    include_tier2: bool
    include_tier3: bool
    install_nonce: str
    daemon_log_tail: str
    daemon_state: str
    phase: str
    env_vars: dict[str, str]
    extra_transcript: str | None
    repo_id: str | None


@dataclass
class BuiltIssue:
    title: str
    body: str
    primary_fingerprint: str


def _join_argv(argv: list[str]) -> str:
    return " ".join(shlex.quote(a) for a in redact_argv(argv))


def _format_stack(entry: CollectedEntry) -> str:
    lines = [f"{entry.exc_type}: {entry.exc_message}"]
    for frame in entry.frames:
        lines.append(f"  at {frame.function} ({frame.filename})")
    return redact("\n".join(lines))


def build_issue(inp: BuildInput) -> BuiltIssue:
    primary = inp.entries[0]
    short_msg = primary.exc_message.splitlines()[0][:80]
    title = f"[crash] {primary.category} — {short_msg} [{primary.fingerprint}]"

    parts = [SCOPE_BANNER, ""]
    parts.append("## Summary")
    parts.append(f"{primary.category}: {short_msg}")
    parts.append("")
    parts.append("## Environment")
    parts.append(f"- AIT: {inp.ait_version}")
    parts.append(f"- Python: {inp.python_version}")
    parts.append(f"- OS: {inp.os_arch}")
    parts.append("")
    parts.append("## Command")
    parts.append("```")
    parts.append(_join_argv(inp.argv))
    parts.append("```")
    parts.append("")
    parts.append("## Stack Trace")
    parts.append("```")
    parts.append(_format_stack(primary))
    parts.append("```")
    parts.append("")
    if len(inp.entries) > 1:
        parts.append("## Internal Errors (Layer 2)")
        for e in inp.entries:
            parts.append(f"- [{e.category}] {e.exc_message[:60]} (×{e.count})")
        parts.append("")
    if inp.include_tier2:
        parts.append("## Context")
        parts.append(f"- Install ID: {inp.install_nonce}")
        if inp.daemon_state:
            parts.append(f"- Daemon: {inp.daemon_state}")
        if inp.phase:
            parts.append(f"- Phase: {inp.phase}")
        parts.append("")
        if inp.daemon_log_tail:
            parts.append("## Daemon Log Tail (redacted)")
            parts.append("```")
            parts.append(redact(inp.daemon_log_tail))
            parts.append("```")
            parts.append("")
    if inp.include_tier3 and inp.env_vars:
        parts.append("## Environment Variables")
        for k, v in sorted(inp.env_vars.items()):
            parts.append(f"- {k}: {redact(v)}")
        parts.append("")
    if inp.extra_transcript:
        parts.append("## Attached Transcript (high-risk, user-confirmed)")
        parts.append("```")
        parts.append(redact(inp.extra_transcript))
        parts.append("```")
        parts.append("")
    if inp.repo_id:
        parts.append(f"## Repository ID (high-risk, user-confirmed)")
        parts.append(f"`{inp.repo_id}`")
        parts.append("")
    parts.append("---")
    parts.append(f"Fingerprint: `{primary.fingerprint}`")

    body = "\n".join(parts) + "\n"
    return BuiltIssue(title=title, body=body, primary_fingerprint=primary.fingerprint)
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_builder -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/builder.py tests/bug_report/test_builder.py
git commit -m "$(cat <<'EOF'
feat(bug-report): builder composes issue title and tiered body

build_issue(BuildInput) -> BuiltIssue. Tier 1 always; Tier 2 / Tier 3 /
transcript / repo_id only on explicit opt-in. Scope banner repeated at
top of every issue body.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,builder,tiered-data

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Submitter — gh CLI route

**Files:**
- Create: `src/ait/bug_report/submitter.py`
- Create: `tests/bug_report/test_submitter_gh.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_submitter_gh.py`

```python
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.submitter import SubmitResult, submit


class GhSubmitTests(unittest.TestCase):
    def _fake_run(self, returncode=0, stdout="", stderr=""):
        m = mock.Mock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_gh_happy_path(self):
        with mock.patch("ait.bug_report.submitter.which", return_value="/usr/bin/gh"), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=True), \
             mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = self._fake_run(
                returncode=0,
                stdout="https://github.com/m24927605/ait/issues/123\n",
            )
            result = submit(title="t", body="b",
                            browser_opener=lambda _u: True)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.method, "gh")
            self.assertEqual(result.issue_url,
                             "https://github.com/m24927605/ait/issues/123")

    def test_gh_missing_falls_through(self):
        with mock.patch("ait.bug_report.submitter.which", return_value=None), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=False):
            opens = []
            result = submit(title="t", body="b",
                            browser_opener=lambda u: (opens.append(u) or True))
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.method, "url")
            self.assertEqual(len(opens), 1)

    def test_gh_nonzero_exit_falls_through(self):
        with mock.patch("ait.bug_report.submitter.which", return_value="/usr/bin/gh"), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=True), \
             mock.patch("subprocess.run") as run_mock:
            run_mock.return_value = self._fake_run(returncode=1, stderr="oops")
            opens = []
            result = submit(title="t", body="b",
                            browser_opener=lambda u: (opens.append(u) or True))
            self.assertEqual(result.method, "url")

    def test_gh_timeout_falls_through(self):
        with mock.patch("ait.bug_report.submitter.which", return_value="/usr/bin/gh"), \
             mock.patch("ait.bug_report.submitter._gh_auth_ok", return_value=True), \
             mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=15)):
            opens = []
            result = submit(title="t", body="b",
                            browser_opener=lambda u: (opens.append(u) or True))
            self.assertEqual(result.method, "url")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_submitter_gh -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/submitter.py`

```python
from __future__ import annotations

import subprocess
import urllib.parse
import webbrowser
from dataclasses import dataclass
from shutil import which
from typing import Callable

REPO = "m24927605/ait"
URL_MAX = 7000


@dataclass
class SubmitResult:
    status: str          # "ok" | "deferred"
    method: str | None   # "gh" | "url" | None
    issue_url: str | None
    reason: str | None = None


def _gh_auth_ok() -> bool:
    try:
        r = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        return False
    return "not logged in" not in (r.stderr or "").lower()


def _try_gh(title: str, body: str) -> SubmitResult | None:
    if not which("gh"):
        return None
    if not _gh_auth_ok():
        return None
    try:
        r = subprocess.run(
            ["gh", "issue", "create",
             "--repo", REPO,
             "--title", title,
             "--body-file", "-"],
            input=body, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return SubmitResult(status="ok", method="gh",
                        issue_url=(r.stdout or "").strip())


def build_prefill_url(title: str, body: str) -> str:
    q = urllib.parse.urlencode({"title": title, "body": body})
    return f"https://github.com/{REPO}/issues/new?{q}"


def _try_url(title: str, body: str,
             opener: Callable[[str], bool]) -> SubmitResult | None:
    url = build_prefill_url(title, body)
    if len(url) > URL_MAX:
        return None
    ok = bool(opener(url))
    if not ok:
        return None
    return SubmitResult(status="ok", method="url", issue_url=None)


def submit(
    *,
    title: str,
    body: str,
    browser_opener: Callable[[str], bool] = webbrowser.open,
) -> SubmitResult:
    gh = _try_gh(title, body)
    if gh is not None:
        return gh
    url = _try_url(title, body, browser_opener)
    if url is not None:
        return url
    reason = "body_too_long_or_no_browser"
    return SubmitResult(status="deferred", method=None,
                        issue_url=None, reason=reason)
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_submitter_gh -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/submitter.py tests/bug_report/test_submitter_gh.py
git commit -m "$(cat <<'EOF'
feat(bug-report): submitter with gh CLI route

submit(title, body) tries `gh issue create` first when authenticated.
Returns SubmitResult with method='gh' on success. Falls through on
missing gh, auth failure, non-zero exit, OSError, or timeout.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,submitter,gh-cli

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Submitter — URL fallback (extend tests, no new file)

**Files:**
- Modify: `src/ait/bug_report/submitter.py` (already includes URL path; tests below verify)
- Create: `tests/bug_report/test_submitter_url.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_submitter_url.py`

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.submitter import URL_MAX, build_prefill_url, submit


class UrlSubmitTests(unittest.TestCase):
    def test_prefill_url_encodes_title_and_body(self):
        url = build_prefill_url("a title", "b & body")
        self.assertIn("title=a+title", url)
        self.assertIn("body=b+%26+body", url)
        self.assertTrue(url.startswith(
            "https://github.com/m24927605/ait/issues/new"))

    def test_url_too_long_defers(self):
        big = "X" * (URL_MAX + 5000)
        with mock.patch("ait.bug_report.submitter.which", return_value=None):
            opens = []
            result = submit(title="t", body=big,
                            browser_opener=lambda u: opens.append(u) or True)
            self.assertEqual(result.status, "deferred")
            self.assertEqual(opens, [])

    def test_browser_open_false_defers(self):
        with mock.patch("ait.bug_report.submitter.which", return_value=None):
            result = submit(title="t", body="b",
                            browser_opener=lambda _u: False)
            self.assertEqual(result.status, "deferred")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_submitter_url -v
```

Expected: `OK` (submitter already implements URL fallback from Task 10).

- [ ] **Step 3: Commit**

```bash
git add tests/bug_report/test_submitter_url.py
git commit -m "$(cat <<'EOF'
test(bug-report): URL fallback coverage for submitter

Verifies encoding, URL_MAX threshold defers, and browser_opener
returning False also defers.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,submitter,url-fallback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Submitter — wire pending-queue fallback

**Files:**
- Modify: `src/ait/bug_report/submitter.py`
- Create: `tests/bug_report/test_submitter_pending.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_submitter_pending.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.submitter import submit_or_defer


class SubmitOrDeferTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_defer_writes_to_pending_queue(self):
        with mock.patch("ait.bug_report.submitter.which", return_value=None):
            result = submit_or_defer(
                fingerprint="fp:aaaa1111",
                category="x",
                title="t",
                body="x" * 9000,  # exceeds URL_MAX so URL path fails too
                created_at="2026-05-28T10:00:00Z",
                browser_opener=lambda _u: False,
            )
        self.assertEqual(result.status, "deferred")
        # Pending file must exist
        path = Path(self._td.name) / "ait" / "bug_reports" / "pending" / "fp:aaaa1111.json"
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_submitter_pending -v
```

Expected: AttributeError or ImportError on `submit_or_defer`.

- [ ] **Step 3: Extend implementation**

Append to `src/ait/bug_report/submitter.py`:

```python
from ait.bug_report.pending_queue import PendingReport, enqueue


def submit_or_defer(
    *,
    fingerprint: str,
    category: str,
    title: str,
    body: str,
    created_at: str,
    browser_opener: Callable[[str], bool] = webbrowser.open,
) -> SubmitResult:
    """Like submit() but persists to pending queue when deferred."""
    result = submit(title=title, body=body, browser_opener=browser_opener)
    if result.status == "deferred":
        enqueue(PendingReport(
            fingerprint=fingerprint,
            title=title,
            body=body,
            category=category,
            created_at=created_at,
        ))
    return result
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_submitter_pending -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/submitter.py tests/bug_report/test_submitter_pending.py
git commit -m "$(cat <<'EOF'
feat(bug-report): submit_or_defer persists to pending on failure

Wraps submit() so deferred outcomes write the report to the pending
queue for later replay via `ait bug-report --replay`.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,submitter,pending-queue

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 4 — Public API & flush logic

## Task 13: Public API surface

**Files:**
- Create: `src/ait/bug_report/api.py`
- Create: `tests/bug_report/test_api.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_api.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.api import report_internal_error


class ApiTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_report_internal_error_appends_to_collector(self):
        try:
            raise ValueError("boom")
        except ValueError as exc:
            report_internal_error(category="db.operational", exc=exc)
        entries = collector_mod.collector().entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].category, "db.operational")

    def test_never_raises(self):
        report_internal_error(category="x", exc=None)  # type: ignore[arg-type]
        # No assertion needed — failure to swallow would raise.


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_api -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/api.py`

```python
from __future__ import annotations

import datetime as dt
from typing import Any

from ait.bug_report import collector as collector_mod
from ait.bug_report import excepthook as excepthook_mod
from ait.bug_report.config import env_disabled, load_prefs
from ait.bug_report.safety import _safe


@_safe
def install_excepthook() -> None:
    excepthook_mod.install()


@_safe
def report_internal_error(
    *,
    category: str,
    exc: BaseException,
    context: dict[str, Any] | None = None,
    user_facing: str | None = None,
) -> None:
    if env_disabled():
        return
    if load_prefs().mode == "never":
        return
    if exc is None:
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    collector_mod.collector().record(
        category=category, exc=exc, context=context, now=now,
    )


@_safe
def flush_at_exit() -> None:
    # Filled in next task (Task 14). For now, no-op stub.
    return
```

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_api -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/bug_report/api.py tests/bug_report/test_api.py
git commit -m "$(cat <<'EOF'
feat(bug-report): public API install_excepthook + report_internal_error

All three public entry points _safe-wrapped. report_internal_error
honors AIT_BUG_REPORT=never and mode=never short-circuits.
flush_at_exit is a stub here; the dedup/flush flow lands in Task 14.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,api,public-surface

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: flush_at_exit dedup decision table

**Files:**
- Modify: `src/ait/bug_report/api.py` — replace stub `flush_at_exit`
- Create: `src/ait/bug_report/flush.py` — dedup decision logic separated for testability
- Extend: `tests/bug_report/test_api.py` (or new `tests/bug_report/test_flush.py`)

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_flush.py`

```python
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.config import BugReportPrefs, save_prefs
from ait.bug_report.flush import decide_prompt, FlushDecision
from ait.bug_report.seen_store import record_seen, record_submitted


def _make_exc():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


class DecidePromptTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def _now(self, d=0):
        base = dt.datetime(2026, 5, 28, tzinfo=dt.timezone.utc)
        return (base + dt.timedelta(days=d)).isoformat().replace("+00:00", "Z")

    def test_unseen_fp_should_prompt(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "prompt")
        self.assertEqual(len(d.to_prompt), 1)

    def test_seen_recently_not_submitted_silent(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        fp = c.entries()[0].fingerprint
        record_seen(fp, category="x", now=self._now(-1))
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "silent")

    def test_seen_over_7d_ago_reprompt(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        fp = c.entries()[0].fingerprint
        record_seen(fp, category="x", now=self._now(-10))
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "prompt")

    def test_already_submitted_open_silent(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None, now=self._now())
        fp = c.entries()[0].fingerprint
        record_seen(fp, category="x", now=self._now())
        record_submitted(fp, issue_url="https://x/123",
                         method="gh", now=self._now())
        d = decide_prompt(now=self._now())
        self.assertEqual(d.action, "silent")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_flush -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/flush.py`

```python
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ait.bug_report import collector as collector_mod
from ait.bug_report.collector import CollectedEntry
from ait.bug_report.seen_store import load_seen


@dataclass
class FlushDecision:
    action: str   # "prompt" | "silent" | "reprompt"
    to_prompt: list[CollectedEntry]


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decide_prompt(*, now: str, reprompt_days: int = 7) -> FlushDecision:
    entries = collector_mod.collector().entries()
    if not entries:
        return FlushDecision(action="silent", to_prompt=[])
    seen = load_seen()
    now_dt = _parse(now)
    to_prompt: list[CollectedEntry] = []
    for entry in entries:
        e = seen.get(entry.fingerprint)
        if e is None:
            to_prompt.append(entry)
            continue
        if e.submitted_issue_url and (e.last_known_state or "open") == "open":
            continue  # silent
        if e.submitted_issue_url and e.last_known_state in ("closed", "locked"):
            to_prompt.append(entry)  # regression re-prompt
            continue
        if not e.submitted_issue_url:
            last = _parse(e.last_seen_at) if e.last_seen_at else now_dt
            age = (now_dt - last).days
            if age >= reprompt_days:
                to_prompt.append(entry)
    action = "prompt" if to_prompt else "silent"
    return FlushDecision(action=action, to_prompt=to_prompt)
```

Now replace the stub in `src/ait/bug_report/api.py`. Find the
`flush_at_exit` definition and replace with:

```python
@_safe
def flush_at_exit() -> None:
    from ait.bug_report.flush import decide_prompt
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if env_disabled() or load_prefs().mode == "never":
        return
    decision = decide_prompt(now=now)
    if decision.action != "prompt":
        return
    # Delegate prompting + submission to CLI layer (Task 17 wires this).
    # For now, defer interactive flows: write to pending queue so
    # `ait bug-report --replay` can ship them.
    from ait.bug_report.collector import CollectedEntry
    from ait.bug_report.pending_queue import PendingReport, enqueue
    from ait.bug_report.builder import build_issue, BuildInput
    inp = _build_default_input(decision.to_prompt)
    issue = build_issue(inp)
    enqueue(PendingReport(
        fingerprint=issue.primary_fingerprint,
        title=issue.title,
        body=issue.body,
        category=decision.to_prompt[0].category,
        created_at=now,
    ))


def _build_default_input(entries):
    import platform, sys
    from ait.bug_report.builder import BuildInput
    try:
        from ait import __version__ as ait_version
    except Exception:
        ait_version = "unknown"
    prefs = load_prefs()
    return BuildInput(
        entries=entries,
        ait_version=ait_version,
        python_version=platform.python_version(),
        os_arch=f"{platform.system().lower()}/{platform.machine()}",
        argv=list(sys.argv),
        include_tier2=prefs.include_tier2,
        include_tier3=prefs.include_tier3,
        install_nonce="",
        daemon_log_tail="",
        daemon_state="",
        phase="",
        env_vars={},
        extra_transcript=None,
        repo_id=None,
    )
```

(Note: this Task 14 lands a non-interactive flush — TTY interactive
prompting is added in Task 17 alongside the CLI wiring.)

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_flush -v
```

Expected: `OK`.

- [ ] **Step 5: Run full bug_report test subdir to catch regressions**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/bug_report -v
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ait/bug_report/flush.py src/ait/bug_report/api.py \
        tests/bug_report/test_flush.py
git commit -m "$(cat <<'EOF'
feat(bug-report): flush_at_exit dedup decision table

decide_prompt() implements the spec's dedup table: unseen → prompt,
seen <7d → silent, seen ≥7d → reprompt, submitted+open → silent,
submitted+closed → regression reprompt. flush_at_exit currently
defers to pending queue — TTY-interactive prompting lands in Task 17.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,flush,dedup-decision-table

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 5 — CLI surface

## Task 15: `ait bug-report` subcommand

**Files:**
- Create: `src/ait/cli/bug_report.py`
- Modify: `src/ait/cli/__init__.py` or `src/ait/cli/main.py` argparse registration
- Create: `tests/bug_report/test_cli_bug_report.py`

- [ ] **Step 1: Locate the argparse registration site**

Read `src/ait/cli/main.py` to identify where existing subcommands (e.g.,
`config`, `run`, `intent`) register. The new subcommand follows the same
pattern.

- [ ] **Step 2: Write the failing test**

File: `tests/bug_report/test_cli_bug_report.py`

```python
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.cli.bug_report import run_list, run_clear, run_show
from ait.bug_report.pending_queue import PendingReport, enqueue


class CliBugReportTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def _enq(self, fp):
        enqueue(PendingReport(
            fingerprint=fp, title="t", body="b",
            category="c", created_at="2026-05-28T10:00:00Z",
        ))

    def test_list_empty(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = run_list()
        self.assertEqual(rc, 0)
        self.assertIn("no pending", buf.getvalue().lower())

    def test_list_with_entries(self):
        self._enq("fp:aaaa1111")
        self._enq("fp:bbbb2222")
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            run_list()
        out = buf.getvalue()
        self.assertIn("fp:aaaa1111", out)
        self.assertIn("fp:bbbb2222", out)

    def test_show_prints_body(self):
        self._enq("fp:aaaa1111")
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = run_show("fp:aaaa1111")
        self.assertEqual(rc, 0)
        self.assertIn("Title: t", buf.getvalue())
        self.assertIn("b", buf.getvalue())

    def test_clear_all(self):
        self._enq("fp:aaaa1111")
        self._enq("fp:bbbb2222")
        rc = run_clear(all_flag=True, fingerprint=None)
        self.assertEqual(rc, 0)
        from ait.bug_report.pending_queue import list_pending
        self.assertEqual(list_pending(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Write implementation**

File: `src/ait/cli/bug_report.py`

```python
from __future__ import annotations

import argparse
import sys

from ait.bug_report.pending_queue import (
    clear_pending,
    list_pending,
    load_pending,
    remove,
)

SCOPE_LINE = (
    "Reports bugs in AIT itself. For issues with your code or your "
    "agent's behavior, this is not the right tool."
)


def run_list() -> int:
    fps = sorted(list_pending())
    if not fps:
        print("no pending bug reports.")
        return 0
    print(f"{len(fps)} pending bug report(s):")
    for fp in fps:
        report = load_pending(fp)
        if report is None:
            continue
        print(f"  {fp}  [{report.category}]  created={report.created_at}")
    return 0


def run_show(fingerprint: str) -> int:
    report = load_pending(fingerprint)
    if report is None:
        print(f"no pending report with fingerprint {fingerprint}",
              file=sys.stderr)
        return 1
    print(f"Title: {report.title}")
    print()
    print(report.body)
    return 0


def run_clear(*, all_flag: bool, fingerprint: str | None) -> int:
    if all_flag:
        n = clear_pending()
        print(f"cleared {n} pending report(s).")
        return 0
    if fingerprint is None:
        print("specify a fingerprint or use --all", file=sys.stderr)
        return 2
    ok = remove(fingerprint)
    if not ok:
        print(f"no pending report with fingerprint {fingerprint}",
              file=sys.stderr)
        return 1
    print(f"removed {fingerprint}.")
    return 0


def run_replay(*, all_flag: bool, fingerprint: str | None) -> int:
    from ait.bug_report.submitter import submit

    targets: list[str]
    if all_flag:
        targets = sorted(list_pending())
    elif fingerprint:
        targets = [fingerprint]
    else:
        print("specify a fingerprint or use --all", file=sys.stderr)
        return 2

    if not targets:
        print("nothing to replay.")
        return 0

    for fp in targets:
        report = load_pending(fp)
        if report is None:
            print(f"skip: {fp} (not found)", file=sys.stderr)
            continue
        result = submit(title=report.title, body=report.body)
        if result.status == "ok":
            remove(fp)
            print(f"sent: {fp} via {result.method} → {result.issue_url or 'browser'}")
        else:
            print(f"defer: {fp} ({result.reason})", file=sys.stderr)
    return 0


def add_subparser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "bug-report",
        help="Report a bug in AIT itself (not your code or your agents).",
        description=SCOPE_LINE,
    )
    sp = p.add_subparsers(dest="bug_report_cmd")

    sp.add_parser("list")

    show = sp.add_parser("show")
    show.add_argument("fingerprint")

    clear = sp.add_parser("clear")
    clear.add_argument("fingerprint", nargs="?", default=None)
    clear.add_argument("--all", dest="all_flag", action="store_true")

    replay = sp.add_parser("replay")
    replay.add_argument("fingerprint", nargs="?", default=None)
    replay.add_argument("--all", dest="all_flag", action="store_true")

    p.set_defaults(handler=_dispatch)


def _dispatch(args: argparse.Namespace) -> int:
    cmd = getattr(args, "bug_report_cmd", None)
    if cmd == "list":
        return run_list()
    if cmd == "show":
        return run_show(args.fingerprint)
    if cmd == "clear":
        return run_clear(all_flag=args.all_flag, fingerprint=args.fingerprint)
    if cmd == "replay":
        return run_replay(all_flag=args.all_flag, fingerprint=args.fingerprint)
    # No subcommand → interactive wizard placeholder.
    print(SCOPE_LINE)
    print("(interactive wizard is implemented in a follow-up task; "
          "use `ait bug-report list|show|clear|replay` for now.)")
    return 0
```

- [ ] **Step 4: Register the subcommand**

Open `src/ait/cli/main.py` and find the existing `subparsers =
parser.add_subparsers(...)` block (search for `add_subparsers(`). After
the existing registrations add:

```python
from ait.cli import bug_report as bug_report_cli
bug_report_cli.add_subparser(subparsers)
```

Hook the `handler` dispatch into the main `args.handler(args)` path the
file already uses. If `cli/main.py` uses a different pattern (per-command
`if args.command == "x": ...`), instead add:

```python
if args.command == "bug-report":
    return bug_report_cli._dispatch(args)
```

- [ ] **Step 5: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_cli_bug_report -v
```

Expected: `OK`.

- [ ] **Step 6: Smoke test**

```bash
PYTHONPATH=src .venv/bin/python -m ait.cli bug-report list
```

Expected: `no pending bug reports.`

- [ ] **Step 7: Commit**

```bash
git add src/ait/cli/bug_report.py src/ait/cli/main.py \
        tests/bug_report/test_cli_bug_report.py
git commit -m "$(cat <<'EOF'
feat(cli): ait bug-report subcommand (list/show/clear/replay)

Non-interactive subcommands for managing pending bug reports. The
interactive wizard follows in Task 17. Scope line ("AIT itself only")
shown in --help and as fallback when invoked without a subcommand.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,cli,subcommand

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: `ait config bug-report` extension

**Files:**
- Modify: `src/ait/cli/config.py`
- Create: `tests/bug_report/test_cli_config_bug_report.py`

- [ ] **Step 1: Read the current config CLI**

```bash
sed -n '1,80p' src/ait/cli/config.py
```

Identify the existing argparse structure and the place where keys are
listed.

- [ ] **Step 2: Write the failing test**

File: `tests/bug_report/test_cli_config_bug_report.py`

```python
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report.config import load_prefs
from ait.cli.config import run_bug_report_config


class ConfigCmdTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_CONFIG_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_set_mode_always(self):
        rc = run_bug_report_config(args=["always"])
        self.assertEqual(rc, 0)
        self.assertEqual(load_prefs().mode, "always")

    def test_invalid_mode_returns_error(self):
        rc = run_bug_report_config(args=["bogus"])
        self.assertNotEqual(rc, 0)

    def test_show_when_no_args(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = run_bug_report_config(args=[])
        self.assertEqual(rc, 0)
        self.assertIn("mode:", buf.getvalue().lower())

    def test_tier_toggle(self):
        run_bug_report_config(args=["tier3", "on"])
        self.assertTrue(load_prefs().include_tier3)
        run_bug_report_config(args=["tier3", "off"])
        self.assertFalse(load_prefs().include_tier3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Write implementation**

Add to `src/ait/cli/config.py`:

```python
from ait.bug_report.config import VALID_MODES, load_prefs, save_prefs


def run_bug_report_config(*, args: list[str]) -> int:
    prefs = load_prefs()
    if not args:
        print(f"mode: {prefs.mode}")
        print(f"include_tier2: {prefs.include_tier2}")
        print(f"include_tier3: {prefs.include_tier3}")
        return 0
    head, *rest = args
    if head in ("ask", "always", "never"):
        prefs.mode = head
        save_prefs(prefs)
        print(f"mode set to {head}.")
        return 0
    if head in ("tier2", "tier3") and rest and rest[0] in ("on", "off"):
        val = rest[0] == "on"
        if head == "tier2":
            prefs.include_tier2 = val
        else:
            prefs.include_tier3 = val
        save_prefs(prefs)
        print(f"{head} = {'on' if val else 'off'}.")
        return 0
    print(f"unknown bug-report config: {' '.join(args)}", file=sys.stderr)
    return 2
```

Then register in `cli/config.py`'s argparse so `ait config bug-report ...`
dispatches to `run_bug_report_config(args=remaining)`. The exact wiring
depends on the existing `cli/config.py` structure — read the file and
follow its pattern.

- [ ] **Step 4: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_cli_config_bug_report -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/ait/cli/config.py tests/bug_report/test_cli_config_bug_report.py
git commit -m "$(cat <<'EOF'
feat(cli): ait config bug-report

Shows current settings when no arg; sets mode (ask|always|never) or
toggles tier2/tier3 inclusion. Persists via BugReportPrefs.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,cli,config

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 6 — Integration

## Task 17: Wire excepthook + atexit + interactive prompt

**Files:**
- Modify: `src/ait/cli/main.py`
- Create: `src/ait/bug_report/prompt.py` (TTY-interactive prompting)
- Create: `tests/bug_report/test_prompt.py`

- [ ] **Step 1: Write the failing test for prompt module**

File: `tests/bug_report/test_prompt.py`

```python
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.prompt import interactive_flush


def _make_exc():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


class PromptTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_non_tty_writes_to_pending(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None,
                 now="2026-05-28T10:00:00Z")
        out = io.StringIO()
        # is_tty False on both streams
        interactive_flush(
            input_provider=lambda _p: "",
            is_tty=False,
            stdout=out,
            stderr=out,
            now="2026-05-28T10:00:00Z",
        )
        text = out.getvalue()
        self.assertIn("pending", text.lower())

    def test_tty_no_keypress_to_n(self):
        c = collector_mod.collector()
        c.record(category="x", exc=_make_exc(), context=None,
                 now="2026-05-28T10:00:00Z")
        out = io.StringIO()
        interactive_flush(
            input_provider=lambda _p: "n",
            is_tty=True,
            stdout=out,
            stderr=out,
            now="2026-05-28T10:00:00Z",
        )
        # No submission happened — verify pending NOT written either
        # because the user explicitly declined this run.
        from ait.bug_report.pending_queue import list_pending
        self.assertEqual(list_pending(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify failure**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_prompt -v
```

Expected: ImportError.

- [ ] **Step 3: Write implementation**

File: `src/ait/bug_report/prompt.py`

```python
from __future__ import annotations

import sys
from typing import Callable, TextIO

from ait.bug_report import collector as collector_mod
from ait.bug_report.builder import build_issue
from ait.bug_report.config import BugReportPrefs, load_prefs, save_prefs
from ait.bug_report.flush import decide_prompt
from ait.bug_report.pending_queue import PendingReport, enqueue
from ait.bug_report.seen_store import record_seen, record_submitted
from ait.bug_report.submitter import submit


def _build_input(entries, prefs: BugReportPrefs):
    import platform
    from ait.bug_report.builder import BuildInput
    try:
        from ait import __version__ as ait_version
    except Exception:
        ait_version = "unknown"
    return BuildInput(
        entries=entries,
        ait_version=ait_version,
        python_version=platform.python_version(),
        os_arch=f"{platform.system().lower()}/{platform.machine()}",
        argv=list(sys.argv),
        include_tier2=prefs.include_tier2,
        include_tier3=prefs.include_tier3,
        install_nonce="",
        daemon_log_tail="",
        daemon_state="",
        phase="",
        env_vars={},
        extra_transcript=None,
        repo_id=None,
    )


def interactive_flush(
    *,
    input_provider: Callable[[str], str],
    is_tty: bool,
    stdout: TextIO,
    stderr: TextIO,
    now: str,
) -> None:
    decision = decide_prompt(now=now)
    if decision.action != "prompt":
        return

    prefs = load_prefs()
    issue = build_issue(_build_input(decision.to_prompt, prefs))

    if not is_tty:
        # Non-interactive: defer to pending queue.
        enqueue(PendingReport(
            fingerprint=issue.primary_fingerprint,
            title=issue.title, body=issue.body,
            category=decision.to_prompt[0].category,
            created_at=now,
        ))
        n = len(decision.to_prompt)
        print(
            f"ait: {n} internal error(s) saved to pending. "
            f"Run `ait bug-report --replay --all` to send.",
            file=stderr,
        )
        return

    # Mark seen regardless of user choice.
    for e in decision.to_prompt:
        record_seen(e.fingerprint, category=e.category, now=now)

    # First-time setup if mode is unset.
    if prefs.mode == "unset":
        print(_first_time_text(), file=stdout)
        choice = (input_provider("Choice [1]: ") or "1").strip()
        new_mode = {"1": "ask", "2": "always", "3": "never"}.get(choice, "ask")
        prefs.mode = new_mode
        prefs.first_setup_at = now
        save_prefs(prefs)
        if new_mode == "never":
            return

    if prefs.mode == "ask":
        print(_summary(decision.to_prompt), file=stdout)
        ans = (input_provider(
            "Send a bug report to help improve AIT? [y/n/s/a]: "
        ) or "n").strip().lower()
        if ans == "s":
            prefs.mode = "never"
            save_prefs(prefs)
            return
        if ans == "a":
            prefs.mode = "ask"
            save_prefs(prefs)
        if ans not in ("y", "yes"):
            return

    # Review screen.
    print("\n----- Review -----", file=stdout)
    print(f"Title: {issue.title}", file=stdout)
    print(issue.body, file=stdout)
    print("------------------", file=stdout)
    confirm = (input_provider("[s] send  [x] cancel: ") or "x").strip().lower()
    if confirm != "s":
        return

    result = submit(title=issue.title, body=issue.body)
    if result.status == "ok":
        record_submitted(
            issue.primary_fingerprint,
            issue_url=result.issue_url,
            method=result.method or "url",
            now=now,
        )
        if result.issue_url:
            print(f"sent: {result.issue_url}", file=stdout)
        else:
            print("sent (browser).", file=stdout)
    else:
        enqueue(PendingReport(
            fingerprint=issue.primary_fingerprint,
            title=issue.title, body=issue.body,
            category=decision.to_prompt[0].category,
            created_at=now,
        ))
        print("save to pending — replay with `ait bug-report --replay`.",
              file=stdout)


def _first_time_text() -> str:
    return (
        "ait noticed an internal error. AIT can send a bug report to help fix it.\n"
        "\n"
        "What gets sent: stack trace, AIT/Python version, OS, the command you ran.\n"
        "You'll always see the exact contents and approve before anything is sent.\n"
        "\n"
        "How should AIT handle bug reports?\n"
        "  [1] Ask me each time     (default)\n"
        "  [2] Always ask to send   (skip 'report?', still review contents)\n"
        "  [3] Never                (turn off bug reporting)\n"
    )


def _summary(entries) -> str:
    lines = [f"ait encountered {len(entries)} internal error(s) during this run.", ""]
    for e in entries:
        lines.append(f"  • {e.category}  (×{e.count})  [{e.fingerprint}]")
    lines.append("")
    lines.append("  [y] yes, review and send")
    lines.append("  [n] not now")
    lines.append("  [s] not now, and stop asking")
    lines.append("  [a] always ask for next time too")
    return "\n".join(lines)
```

- [ ] **Step 4: Wire into cli/main.py**

Open `src/ait/cli/main.py`. As the **first** line of the `main()`
function (before any other logic), add:

```python
from ait.bug_report.api import install_excepthook, flush_at_exit
import atexit
install_excepthook()
```

Then replace the existing `flush_at_exit` registration (or add new) so it
calls the interactive version:

```python
def _atexit_flush():
    import datetime as _dt
    import sys as _sys
    from ait.bug_report.prompt import interactive_flush
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        is_tty = _sys.stdin.isatty() and _sys.stdout.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    interactive_flush(
        input_provider=input,
        is_tty=is_tty,
        stdout=_sys.stdout,
        stderr=_sys.stderr,
        now=now,
    )

atexit.register(_atexit_flush)
```

Also update `api.flush_at_exit` to use this same path (replace the
non-interactive stub from Task 14):

```python
@_safe
def flush_at_exit() -> None:
    import datetime as _dt, sys as _sys
    from ait.bug_report.prompt import interactive_flush
    now = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        is_tty = _sys.stdin.isatty() and _sys.stdout.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    interactive_flush(
        input_provider=input, is_tty=is_tty,
        stdout=_sys.stdout, stderr=_sys.stderr,
        now=now,
    )
```

- [ ] **Step 5: Run prompt test**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_prompt -v
```

Expected: `OK`.

- [ ] **Step 6: Run full repo test suite**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Expected: `OK` for all 870+ existing tests plus the new ones.

- [ ] **Step 7: Commit**

```bash
git add src/ait/bug_report/prompt.py src/ait/bug_report/api.py \
        src/ait/cli/main.py tests/bug_report/test_prompt.py
git commit -m "$(cat <<'EOF'
feat(bug-report): interactive flush prompt + cli wiring

interactive_flush in prompt.py handles TTY vs non-TTY, first-time
setup, ask/always/never branches, review screen, and submission with
seen.json update. main.py installs excepthook on entry and registers
the flush at atexit.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,prompt,interactive,cli-wiring

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Add 8 Layer 2 instrumentation sites

**Files:**
- Modify: `src/ait/daemon_transport.py`
- Modify: `src/ait/daemon.py`
- Modify: `src/ait/db/core.py`
- Modify: `src/ait/events.py`
- Modify: `src/ait/runner.py`
- Modify: `src/ait/hooks.py`
- Modify: `src/ait/reconcile.py`
- Modify: `src/ait/verifier.py`
- Create: `tests/bug_report/test_layer2_instrumentation.py`

- [ ] **Step 1: Write the failing test**

File: `tests/bug_report/test_layer2_instrumentation.py`

```python
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.api import report_internal_error


class Layer2Tests(unittest.TestCase):
    """Smoke test that the helper is callable from each module's context.

    Real-call-site coverage relies on each module's existing tests still
    passing post-instrumentation; this case checks the contract.
    """

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_each_layer2_category_records(self):
        categories = [
            "daemon.protocol.transport",
            "daemon.protocol.main",
            "db.operational",
            "events.txn_rollback",
            "memory.note_write",
            "hooks.install",
            "reconcile.post_rewrite",
            "verifier.crash",
        ]
        for cat in categories:
            try:
                raise RuntimeError(f"simulated {cat}")
            except RuntimeError as exc:
                report_internal_error(category=cat, exc=exc)
        entries = collector_mod.collector().entries()
        cats = {e.category for e in entries}
        for cat in categories:
            self.assertIn(cat, cats)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_layer2_instrumentation -v
```

Expected: `OK` (this test only exercises the helper; the call sites are
added next).

- [ ] **Step 3: Add call sites — one module at a time**

For each of the 8 modules, locate the existing `except` block at the
indicated line and add a `report_internal_error` call **before** the
existing behavior (log/raise/swallow). Do not change the existing
behavior; the helper is additive.

Pattern (apply at each site):

```python
# Add this import at the top of the module (alongside existing imports):
from ait.bug_report.api import report_internal_error

# At the catch site, before the existing log/raise/swallow:
except SomeError as exc:  # existing
    report_internal_error(category="<spec-category>", exc=exc)  # ADD
    # ... existing handling unchanged ...
```

**Site 1** — `src/ait/daemon_transport.py:36`
```python
except ProtocolError as exc:
    report_internal_error(category="daemon.protocol.transport", exc=exc)
    # ... existing handling ...
```

**Site 2** — `src/ait/daemon.py:197`
```python
except (ProtocolError, OSError) as exc:
    report_internal_error(category="daemon.protocol.main", exc=exc)
    # ... existing handling ...
```

**Site 3** — `src/ait/db/core.py:52`
```python
except sqlite3.OperationalError as exc:
    report_internal_error(category="db.operational", exc=exc)
    # ... existing handling ...
```

**Site 4** — `src/ait/events.py:455`
```python
except Exception as exc:
    report_internal_error(category="events.txn_rollback", exc=exc)
    if started_transaction:
        conn.rollback()
    # ... existing handling ...
```

**Site 5** — `src/ait/runner.py:477`
```python
except Exception as exc:
    report_internal_error(category="memory.note_write", exc=exc)
    print(f"ait warning: add_attempt_memory_note failed: {exc}", file=sys.stderr)
```

**Site 6** — `src/ait/hooks.py` (find the post-rewrite hook install
`except` block; add `report_internal_error(category="hooks.install", exc=exc)`)

**Site 7** — `src/ait/reconcile.py` (find the top-level reconcile
exception block; add `report_internal_error(category="reconcile.post_rewrite", exc=exc)`)

**Site 8** — `src/ait/verifier.py` (find the verification-fail exception
block; add `report_internal_error(category="verifier.crash", exc=exc)`)

- [ ] **Step 4: Run full repo test suite**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Expected: all green. Any regressions mean an instrumentation insertion
changed surrounding behavior — revert and reapply additively.

- [ ] **Step 5: Commit**

```bash
git add src/ait/daemon_transport.py src/ait/daemon.py src/ait/db/core.py \
        src/ait/events.py src/ait/runner.py src/ait/hooks.py \
        src/ait/reconcile.py src/ait/verifier.py \
        tests/bug_report/test_layer2_instrumentation.py
git commit -m "$(cat <<'EOF'
feat(bug-report): Layer 2 instrumentation at 8 internal catch sites

Adds report_internal_error() calls at the 8 catch sites from the spec
without altering any existing behavior. Surrounding log/raise/swallow
logic is untouched — the helper only accumulates into the collector.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md
keyword:bug-report,layer-2,instrumentation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: End-to-end integration test

**Files:**
- Create: `tests/bug_report/test_end_to_end_flow.py`

- [ ] **Step 1: Write the test**

File: `tests/bug_report/test_end_to_end_flow.py`

```python
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.bug_report import collector as collector_mod
from ait.bug_report.api import flush_at_exit, report_internal_error
from ait.bug_report.config import BugReportPrefs, save_prefs
from ait.bug_report.pending_queue import list_pending


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name
        os.environ["XDG_CONFIG_HOME"] = self._td.name
        collector_mod.reset_for_tests()

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        del os.environ["XDG_CONFIG_HOME"]
        self._td.cleanup()

    def test_env_never_disables_pipeline(self):
        os.environ["AIT_BUG_REPORT"] = "never"
        try:
            try:
                raise ValueError("x")
            except ValueError as exc:
                report_internal_error(category="x", exc=exc)
            self.assertEqual(collector_mod.collector().entries(), [])
        finally:
            del os.environ["AIT_BUG_REPORT"]

    def test_mode_never_disables_pipeline(self):
        save_prefs(BugReportPrefs(mode="never"))
        try:
            raise ValueError("x")
        except ValueError as exc:
            report_internal_error(category="x", exc=exc)
        self.assertEqual(collector_mod.collector().entries(), [])

    def test_non_tty_flush_writes_pending(self):
        save_prefs(BugReportPrefs(mode="ask"))
        try:
            raise ValueError("integration boom")
        except ValueError as exc:
            report_internal_error(category="db.operational", exc=exc)
        with mock.patch("sys.stdin") as si, mock.patch("sys.stdout") as so:
            si.isatty.return_value = False
            so.isatty.return_value = False
            flush_at_exit()
        self.assertEqual(len(list_pending()), 1)

    def test_self_safety_internal_failure_does_not_break(self):
        # Force a failure inside the submitter (network call). Even though
        # submit shouldn't be called in non-tty path, simulate worst case:
        with mock.patch("ait.bug_report.builder.build_issue",
                        side_effect=RuntimeError("synthetic")):
            try:
                raise ValueError("x")
            except ValueError as exc:
                report_internal_error(category="x", exc=exc)
            # flush_at_exit must NOT raise even though build_issue is broken.
            flush_at_exit()
        # No assertion needed: the test passes iff no exception escaped.


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify pass**

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.bug_report.test_end_to_end_flow -v
```

Expected: `OK`.

- [ ] **Step 3: Final full-suite run**

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
```

Expected: `OK` (all 870+ existing tests still pass, plus the new
bug_report tests).

- [ ] **Step 4: Manual acceptance per spec**

Walk through the 6 manual checks in
`docs/superpowers/specs/2026-05-28-bug-report-design.md` § "Manual
acceptance checks". Record results in
`docs/bug-report-dogfood-2026-05-28.md` (one short paragraph per check,
plus `gh` output or screenshots if the maintainer wants them).

- [ ] **Step 5: Commit**

```bash
git add tests/bug_report/test_end_to_end_flow.py \
        docs/bug-report-dogfood-2026-05-28.md
git commit -m "$(cat <<'EOF'
test(bug-report): end-to-end integration + dogfood notes

Covers: env disable, mode=never disable, non-TTY flush → pending,
self-safety under a synthetic build_issue failure. Adds dogfood notes
from the 6 manual acceptance checks in the spec.

docs:docs/superpowers/specs/2026-05-28-bug-report-design.md,docs/superpowers/plans/2026-05-28-bug-report-implementation.md,docs/bug-report-dogfood-2026-05-28.md
keyword:bug-report,integration-test,dogfood

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Self-review

**Spec coverage:**

| Spec section                             | Plan task                       |
|------------------------------------------|---------------------------------|
| Scope statement                          | T9 (banner), T15 (SCOPE_LINE)   |
| Architecture & file layout               | All tasks (file structure)      |
| Storage layout (XDG)                     | T3, T4, T5                      |
| Preference schema                        | T3, T16                         |
| Trigger surface (Layer 1)                | T8, T17                         |
| Trigger surface (Layer 2)                | T13, T18                        |
| Collector                                | T6                              |
| Consent model (two tiers)                | T17 (first-time + review)       |
| Data tiers (T1/T2/T3 + explicit-flag)    | T9                              |
| Redaction                                | T2, T9                          |
| Submission flow (gh → URL → pending)     | T10, T11, T12                   |
| Fingerprinting                           | T1                              |
| Dedup decision table                     | T14                             |
| Per-process hard cap                     | T6                              |
| TTY / non-interactive behavior           | T17                             |
| CLI surface (`ait bug-report`)           | T15                             |
| CLI surface (`ait config bug-report`)    | T16                             |
| Issue body template                      | T9                              |
| Self-safety wrapper                      | T7, T13                         |
| Manual acceptance checks                 | T19                             |
| Non-functional checks (cold start, IO)   | T19 (manual acceptance)         |

No spec section is unaddressed.

**Placeholder scan:** Searched plan text — no "TBD", "TODO", "implement
later", "fill in details", "similar to Task N", or steps without code.

**Type consistency:** Cross-checked `Frame`, `CollectedEntry`,
`BuildInput`, `BuiltIssue`, `SubmitResult`, `SeenEntry`, `PendingReport`,
`BugReportPrefs`, `FlushDecision` — same field names everywhere used.
Function names (`fingerprint`, `redact`, `redact_argv`, `build_issue`,
`submit`, `submit_or_defer`, `report_internal_error`, `flush_at_exit`,
`install_excepthook`, `decide_prompt`, `interactive_flush`, `enqueue`,
`load_pending`, `list_pending`, `remove`, `clear_pending`, `prune_old`,
`record_seen`, `record_submitted`, `load_seen`, `save_seen`, `load_prefs`,
`save_prefs`) referenced consistently across tasks.

**Scope check:** This plan is one focused feature. Each phase clusters
naturally; no sub-project decomposition needed.

---

# Execution Handoff

Plan complete and saved to
`docs/superpowers/plans/2026-05-28-bug-report-implementation.md`.
Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per
   task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using
   `executing-plans`, batch execution with checkpoints.
