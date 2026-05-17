from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ait.cli import demo as demo_module
from ait.cli.demo import DEMO_DIR_PREFIX


def _make_args(**overrides):
    base = {
        "command": "demo",
        "clean": False,
        "keep": False,
        "quiet": True,
        "format": "text",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _run_handle(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = demo_module.handle(args, Path.cwd())
    return rc, buf.getvalue()


def _purge_demo_dirs():
    tmp = Path(tempfile.gettempdir())
    for entry in tmp.iterdir():
        if entry.is_dir() and entry.name.startswith(DEMO_DIR_PREFIX):
            shutil.rmtree(entry, ignore_errors=True)


class TestDemoSubcommand(unittest.TestCase):

    def setUp(self):
        self._captured_dirs: list[Path] = []
        _purge_demo_dirs()

    def tearDown(self):
        for d in self._captured_dirs:
            shutil.rmtree(d, ignore_errors=True)
        _purge_demo_dirs()

    def test_demo_runs_end_to_end_under_60s(self):
        args = _make_args(format="json")
        start = time.monotonic()
        rc, stdout = _run_handle(args)
        duration = time.monotonic() - start
        self.assertEqual(rc, 0, f"demo exited non-zero. stdout:\n{stdout}")
        self.assertLess(duration, 60.0)
        payload = json.loads(stdout)
        self._captured_dirs.append(Path(payload["demo_dir"]))
        self.assertGreater(payload["duration_seconds"], 0.0)
        self.assertLess(payload["duration_seconds"], 60.0)

    def test_demo_writes_real_ledger_rows(self):
        args = _make_args(format="json")
        rc, stdout = _run_handle(args)
        self.assertEqual(rc, 0)
        payload = json.loads(stdout)
        demo_dir = Path(payload["demo_dir"])
        self._captured_dirs.append(demo_dir)
        db = demo_dir / ".ait" / "state.sqlite3"
        self.assertTrue(db.exists(), f"SQLite DB missing at {db}")
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM intents").fetchone()[0],
                1,
                "expected exactly one intent row",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0],
                1,
                "expected exactly one attempt row",
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM attempt_reviews").fetchone()[0],
                1,
                "expected exactly one review row",
            )
            findings = conn.execute(
                "SELECT severity, blocking FROM attempt_review_findings"
            ).fetchall()
            self.assertEqual(len(findings), 1, "expected exactly one finding")
            self.assertIn(findings[0]["severity"], {"critical", "high"})
            self.assertTrue(bool(findings[0]["blocking"]))
        self.assertTrue(payload["apply_blocked"], "fake:high reviewer must trigger the apply gate")
        self.assertEqual(payload["intents"], 1)
        self.assertEqual(payload["attempts"], 1)
        self.assertEqual(payload["reviews"], 1)

    def test_demo_no_network(self):
        real_socket = __import__("socket").socket

        def _no_network(*a, **kw):
            raise RuntimeError("network blocked during ait demo test")

        with patch("socket.socket", side_effect=_no_network):
            args = _make_args(format="json")
            rc, stdout = _run_handle(args)
        self.assertEqual(rc, 0, f"demo touched the network. stdout:\n{stdout}")
        payload = json.loads(stdout)
        self._captured_dirs.append(Path(payload["demo_dir"]))

    def test_demo_clean_removes_prior_dirs(self):
        for _ in range(2):
            args = _make_args(format="json")
            rc, stdout = _run_handle(args)
            self.assertEqual(rc, 0)

        tmp = Path(tempfile.gettempdir())
        before = [d for d in tmp.iterdir() if d.is_dir() and d.name.startswith(DEMO_DIR_PREFIX)]
        self.assertGreaterEqual(len(before), 2)

        rc, stdout = _run_handle(_make_args(clean=True, format="json"))
        self.assertEqual(rc, 0)
        result = json.loads(stdout)
        self.assertGreaterEqual(result["removed"], 2)

        after = [d for d in tmp.iterdir() if d.is_dir() and d.name.startswith(DEMO_DIR_PREFIX)]
        self.assertEqual(after, [], f"demo dirs remain after --clean: {after}")

    def test_demo_idempotent_creates_independent_dirs(self):
        rc1, stdout1 = _run_handle(_make_args(format="json"))
        self.assertEqual(rc1, 0)
        dir1 = Path(json.loads(stdout1)["demo_dir"])
        self._captured_dirs.append(dir1)

        rc2, stdout2 = _run_handle(_make_args(format="json"))
        self.assertEqual(rc2, 0)
        dir2 = Path(json.loads(stdout2)["demo_dir"])
        self._captured_dirs.append(dir2)

        self.assertNotEqual(dir1, dir2)
        self.assertTrue(dir1.exists())
        self.assertTrue(dir2.exists())
        self.assertTrue((dir1 / ".ait" / "state.sqlite3").exists())
        self.assertTrue((dir2 / ".ait" / "state.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
