from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import (
    cache_path,
    load_cache,
    save_cache,
    is_cache_fresh,
)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        os.environ["XDG_STATE_HOME"] = self._td.name

    def tearDown(self):
        del os.environ["XDG_STATE_HOME"]
        self._td.cleanup()

    def test_cache_path_under_xdg_state(self):
        p = cache_path()
        self.assertEqual(
            p,
            Path(self._td.name) / "ait" / "self_update_cache.json",
        )

    def test_load_missing_returns_none(self):
        self.assertIsNone(load_cache())

    def test_round_trip(self):
        save_cache({
            "tag_name": "v1.5.1",
            "asset_urls": {"macos-arm64": "https://x/y"},
            "checksums_url": "https://x/sums.txt",
        }, now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc))
        cached = load_cache()
        self.assertIsNotNone(cached)
        self.assertEqual(cached["latest"]["tag_name"], "v1.5.1")
        self.assertEqual(cached["fetched_at"], "2026-05-29T12:00:00Z")

    def test_is_cache_fresh_within_ttl(self):
        save_cache({"tag_name": "v1.5.1"},
                   now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc))
        # 30 min later (TTL is 1 hour)
        self.assertTrue(is_cache_fresh(
            now=dt.datetime(2026, 5, 29, 12, 30, tzinfo=dt.timezone.utc)))

    def test_is_cache_fresh_expired(self):
        save_cache({"tag_name": "v1.5.1"},
                   now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc))
        # 90 min later
        self.assertFalse(is_cache_fresh(
            now=dt.datetime(2026, 5, 29, 13, 30, tzinfo=dt.timezone.utc)))

    def test_is_cache_fresh_no_cache(self):
        self.assertFalse(is_cache_fresh(
            now=dt.datetime(2026, 5, 29, 12, 0, tzinfo=dt.timezone.utc)))


if __name__ == "__main__":
    unittest.main()
