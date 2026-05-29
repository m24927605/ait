from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ait.cli.self_update import handle


class CliSelfUpdateTests(unittest.TestCase):
    def test_pip_install_method_returns_refusal_code(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="pip"):
            args = mock.Mock(check=False, yes=False, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 1)

    def test_brew_install_method_returns_refusal_code(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="brew"):
            args = mock.Mock(check=False, yes=False, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 1)

    def test_binary_already_up_to_date_returns_zero(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="binary"), \
             mock.patch("ait.cli.self_update.package_version", return_value="1.5.0"), \
             mock.patch("ait.cli.self_update.fetch_latest",
                        return_value={"tag_name": "v1.5.0"}):
            args = mock.Mock(check=False, yes=True, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 0)

    def test_check_only_returns_zero_even_when_newer_available(self):
        with mock.patch("ait.cli.self_update.install_method", return_value="binary"), \
             mock.patch("ait.cli.self_update.package_version", return_value="1.5.0"), \
             mock.patch("ait.cli.self_update.fetch_latest",
                        return_value={"tag_name": "v1.5.1"}):
            args = mock.Mock(check=True, yes=False, force=False, json=False)
            rc = handle(args)
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
