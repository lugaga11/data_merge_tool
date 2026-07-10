from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.data_reading.detection import detect_read_options
from data_merge_tool.errors import UserVisibleError


class ReadDetectionTests(unittest.TestCase):
    def test_excel_detection_profiles_numeric_cells(self) -> None:
        preview = pd.DataFrame(
            [
                ["Voltage", "Current"],
                [0.0, 1.0],
                [1.0, 2.0],
                [2.0, 3.0],
            ]
        )

        with (
            patch("data_merge_tool.data_reading.detection.require_excel_reader") as require_reader,
            patch("data_merge_tool.data_reading.detection.pd.read_excel", return_value=preview),
        ):
            detection = detect_read_options(Path("measurement.xlsx"), "自动", "自动", 7, False)

        require_reader.assert_called_once_with(".xlsx")
        self.assertTrue(detection.confident)
        self.assertEqual(detection.skip_rows, 0)
        self.assertTrue(detection.has_header)
        self.assertEqual(detection.encoding_label, "Excel 内置")

    def test_detection_surfaces_underlying_reader_error(self) -> None:
        with (
            patch("data_merge_tool.data_reading.detection.require_excel_reader"),
            patch(
                "data_merge_tool.data_reading.detection.pd.read_excel",
                side_effect=ValueError("corrupt workbook payload"),
            ),
        ):
            with self.assertRaisesRegex(
                UserVisibleError,
                "(?s)measurement.xlsx 自动检测读入设置失败.*corrupt workbook payload",
            ):
                detect_read_options(Path("measurement.xlsx"), "自动", "自动", 0, True)


if __name__ == "__main__":
    unittest.main()
