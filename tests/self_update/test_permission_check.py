from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.self_update import check_install_path_writable, InstallPathNotWritable


class PermissionCheckTests(unittest.TestCase):
    def test_writable_dir_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "ait"
            target.write_text("x")
            check_install_path_writable(target)  # no raise

    def test_non_writable_dir_raises(self):
        with mock.patch("os.access", return_value=False):
            with self.assertRaises(InstallPathNotWritable) as ctx:
                check_install_path_writable(Path("/usr/local/bin/ait"))
            self.assertIn("/usr/local/bin", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
