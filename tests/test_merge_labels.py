from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.merge.labels import make_unique_columns


class UniqueColumnTests(unittest.TestCase):
    def test_generated_suffix_does_not_collide_with_existing_name(self) -> None:
        columns = make_unique_columns(["a", "a", "a_2"])

        self.assertEqual(columns, ["a", "a_2", "a_2_2"])
        self.assertEqual(len(columns), len(set(columns)))

    def test_repeated_base_skips_an_already_used_suffix(self) -> None:
        columns = make_unique_columns(["a", "a_2", "a"])

        self.assertEqual(columns, ["a", "a_2", "a_3"])


if __name__ == "__main__":
    unittest.main()
