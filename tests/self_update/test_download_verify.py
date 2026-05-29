from __future__ import annotations

import hashlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import (
    ChecksumMismatch,
    download_and_verify,
)


class DownloadVerifyTests(unittest.TestCase):
    def test_happy_path_returns_bytes(self):
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()
        with mock.patch("ait.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(content)
            out = download_and_verify("https://x/y", expected_sha256=expected)
        self.assertEqual(out, content)

    def test_checksum_mismatch_raises(self):
        content = b"hello world"
        wrong = "0" * 64
        with mock.patch("ait.self_update.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(content)
            with self.assertRaises(ChecksumMismatch):
                download_and_verify("https://x/y", expected_sha256=wrong)


if __name__ == "__main__":
    unittest.main()
