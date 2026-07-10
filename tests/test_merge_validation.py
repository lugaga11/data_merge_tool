from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.errors import UserVisibleError
from data_merge_tool.merge.validation import validate_x_series


class XSeriesValidationTests(unittest.TestCase):
    def test_equal_values_with_different_dtypes_pass(self) -> None:
        reference = pd.Series([1, 2, 3], dtype="int64")
        current = pd.Series([1.0, 2.0, 3.0], dtype="float64")

        validate_x_series(Path("current.csv"), current, reference, len(reference))

    def test_different_values_still_report_first_mismatch(self) -> None:
        reference = pd.Series([1, 2, 3], dtype="int64")
        current = pd.Series([1.0, 2.5, 3.0], dtype="float64")

        with self.assertRaisesRegex(UserVisibleError, "第 2 行"):
            validate_x_series(Path("current.csv"), current, reference, len(reference))


if __name__ == "__main__":
    unittest.main()
