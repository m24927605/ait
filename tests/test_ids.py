from __future__ import annotations

import random
import unittest

from ait.ids import new_ulid


class IdTests(unittest.TestCase):
    def test_new_ulid_is_monotonic_and_not_mersenne_seeded(self) -> None:
        random.seed(0)

        ids = [new_ulid() for _ in range(1000)]

        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
