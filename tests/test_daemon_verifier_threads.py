from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ait.daemon import _join_verifier_threads, _verify_attempt_in_background


class DaemonVerifierThreadTests(unittest.TestCase):
    def tearDown(self) -> None:
        _join_verifier_threads(timeout=1.0)

    def test_join_verifier_threads_waits_for_background_verifier(self) -> None:
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def fake_verify(repo_root: Path, attempt_id: str) -> None:
            del repo_root, attempt_id
            started.set()
            self.assertTrue(release.wait(timeout=2.0))
            finished.set()

        with patch("ait.daemon.verify_attempt", fake_verify):
            verifier = _verify_attempt_in_background(Path("."), "repo:01ATTEMPT")
            self.assertTrue(started.wait(timeout=1.0))

            joiner = threading.Thread(
                target=_join_verifier_threads,
                kwargs={"timeout": 2.0},
            )
            joiner.start()
            time.sleep(0.05)
            self.assertTrue(joiner.is_alive())

            release.set()
            joiner.join(timeout=2.0)

        self.assertFalse(joiner.is_alive())
        self.assertFalse(verifier.is_alive())
        self.assertTrue(finished.is_set())


if __name__ == "__main__":
    unittest.main()
