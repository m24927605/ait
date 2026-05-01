from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from ait.app import create_attempt, create_intent, init_repo, show_attempt, show_intent
from ait.memory import add_memory_note, list_memory_notes


class RefactorSmokeTests(unittest.TestCase):
    def test_split_packages_support_same_crud_from_subprocesses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _init_git_repo(repo_root)
            init_repo(repo_root)

            children = [
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        _CHILD_SCRIPT,
                        str(repo_root),
                        label,
                    ],
                    cwd=repo_root,
                    env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for label in ("child-a", "child-b")
            ]
            child_payloads = []
            for child in children:
                stdout, stderr = child.communicate(timeout=30)
                self.assertEqual(0, child.returncode, stderr)
                child_payloads.append(json.loads(stdout))

            single_payload = _create_smoke_records(repo_root, "single")
            for payload in [*child_payloads, single_payload]:
                intent_view = show_intent(repo_root, intent_id=payload["intent"])
                self.assertEqual(f"Smoke {payload['label']}", intent_view.intent["title"])
                self.assertEqual(payload["attempt"], show_attempt(repo_root, attempt_id=payload["attempt"]).attempt["id"])

            notes = list_memory_notes(repo_root, topic="smoke")
            sources = {note.source for note in notes}
            self.assertEqual({"manual:child-a", "manual:child-b", "manual:single"}, sources)


def _create_smoke_records(repo_root: Path, label: str) -> dict[str, str]:
    intent = create_intent(repo_root, title=f"Smoke {label}", description="refactor smoke", kind="test")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id=f"smoke:{label}")
    note = add_memory_note(repo_root, topic="smoke", body=f"note {label}", source=f"manual:{label}")
    return {
        "label": label,
        "intent": intent.intent_id,
        "attempt": attempt.attempt_id,
        "note": note.id,
    }


_CHILD_SCRIPT = textwrap.dedent(
    """
    from __future__ import annotations

    import json
    import sys
    from pathlib import Path

    import ait.brain
    import ait.db
    import ait.memory
    import ait.report
    from ait.app import create_attempt, create_intent
    from ait.memory import add_memory_note

    repo_root = Path(sys.argv[1])
    label = sys.argv[2]
    intent = create_intent(repo_root, title=f"Smoke {label}", description="refactor smoke", kind="test")
    attempt = create_attempt(repo_root, intent_id=intent.intent_id, agent_id=f"smoke:{label}")
    note = add_memory_note(repo_root, topic="smoke", body=f"note {label}", source=f"manual:{label}")
    print(
        json.dumps(
            {
                "label": label,
                "intent": intent.intent_id,
                "attempt": attempt.attempt_id,
                "note": note.id,
            },
            sort_keys=True,
        )
    )
    """
)


def _init_git_repo(repo_root: Path) -> None:
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "test@example.com")
    _git(repo_root, "config", "user.name", "Test User")
    (repo_root / "README.md").write_text("# test\n", encoding="utf-8")
    _git(repo_root, "add", "README.md")
    _git(repo_root, "commit", "-m", "initial")


def _git(repo_root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
