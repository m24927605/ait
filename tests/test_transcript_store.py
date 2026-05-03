from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from ait.memory_policy import MemoryPolicy
from ait.transcript_store import prune_transcripts, transcripts_dir


def _write_transcript(directory: Path, name: str, *, mtime: float, size: int = 64) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))
    return path


class TranscriptStoreTests(unittest.TestCase):
    def test_prune_transcripts_no_directory_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            policy = MemoryPolicy()
            self.assertEqual((), prune_transcripts(repo_root, policy=policy))
            self.assertFalse((repo_root / ".ait" / "transcripts").exists())

    def test_prune_transcripts_deletes_files_older_than_retain_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            base = transcripts_dir(repo_root)
            now = time.time()
            old = _write_transcript(base, "old.jsonl", mtime=now - 200 * 86400)
            recent = _write_transcript(base, "recent.jsonl", mtime=now - 30 * 86400)

            policy = MemoryPolicy(
                transcript_retain_days=90,
                transcript_max_total_bytes=0,
            )

            deleted = prune_transcripts(repo_root, policy=policy, now=now)

            self.assertEqual((".ait/transcripts/old.jsonl",), deleted)
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())

    def test_prune_transcripts_trims_to_total_size_cap_oldest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            base = transcripts_dir(repo_root)
            now = time.time()
            oldest = _write_transcript(base, "a.jsonl", mtime=now - 10, size=100)
            middle = _write_transcript(base, "b.jsonl", mtime=now - 5, size=100)
            newest = _write_transcript(base, "c.jsonl", mtime=now - 1, size=100)

            policy = MemoryPolicy(
                transcript_retain_days=0,
                transcript_max_total_bytes=150,
            )

            deleted = prune_transcripts(repo_root, policy=policy, now=now)

            self.assertEqual(
                (
                    ".ait/transcripts/a.jsonl",
                    ".ait/transcripts/b.jsonl",
                ),
                deleted,
            )
            self.assertFalse(oldest.exists())
            self.assertFalse(middle.exists())
            self.assertTrue(newest.exists())

    def test_prune_transcripts_zero_retain_disables_age_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            base = transcripts_dir(repo_root)
            now = time.time()
            ancient = _write_transcript(base, "ancient.jsonl", mtime=now - 365 * 86400)

            policy = MemoryPolicy(
                transcript_retain_days=0,
                transcript_max_total_bytes=0,
            )

            deleted = prune_transcripts(repo_root, policy=policy, now=now)

            self.assertEqual((), deleted)
            self.assertTrue(ancient.exists())

    def test_prune_transcripts_skips_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            base = transcripts_dir(repo_root)
            base.mkdir(parents=True)
            (base / "subdir").mkdir()
            sub_file = base / "subdir" / "nested.jsonl"
            sub_file.write_bytes(b"x" * 64)

            policy = MemoryPolicy(
                transcript_retain_days=1,
                transcript_max_total_bytes=1,
            )

            deleted = prune_transcripts(repo_root, policy=policy)

            self.assertEqual((), deleted)
            self.assertTrue(sub_file.exists())


if __name__ == "__main__":
    unittest.main()
