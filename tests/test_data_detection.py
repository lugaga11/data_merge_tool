from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.data_reading.detection import detect_encoding, detect_read_options
from data_merge_tool.errors import UserVisibleError


class ReadDetectionTests(unittest.TestCase):
    def test_encoding_sample_can_end_inside_a_chinese_character(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "measurement.csv"
            for encoding in ("utf-8", "gbk"):
                prefix = "温度,备注\n1,".encode(encoding)
                character = "测".encode(encoding)
                for split in range(1, len(character)):
                    with self.subTest(encoding=encoding, split=split):
                        padding = b"x" * (32 * 1024 - len(prefix) - split)
                        path.write_bytes(prefix + padding + character + b"\n")
                        self.assertEqual(detect_encoding(path, "自动"), encoding)

    def test_invalid_or_incomplete_final_character_still_falls_back_to_latin1(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "measurement.txt"
            for suffix in (b"", b"\n"):
                with self.subTest(suffix=suffix):
                    path.write_bytes(b"a" * (32 * 1024 - 1) + b"\xe9" + suffix)
                    self.assertEqual(detect_encoding(path, "自动"), "latin1")

    def test_excel_detection_profiles_numeric_cells(self) -> None:
        preview = pd.DataFrame(
            [
                ["Voltage", "Current"],
                [0.0, 1.0],
                [1.0, 2.0],
                [2.0, 3.0],
            ]
        )

        with patch("data_merge_tool.data_reading.detection.pd.read_excel", return_value=preview) as read_excel:
            detection = detect_read_options(Path("measurement.xlsx"), "自动", "自动", 7, False)

        read_excel.assert_called_once_with(Path("measurement.xlsx"), header=None, nrows=500, engine="openpyxl")
        self.assertTrue(detection.confident)
        self.assertEqual(detection.skip_rows, 0)
        self.assertTrue(detection.has_header)
        self.assertEqual(detection.encoding_label, "Excel 内置")

    def test_detection_surfaces_underlying_reader_error(self) -> None:
        with patch("data_merge_tool.data_reading.detection.pd.read_excel", side_effect=ValueError("corrupt workbook payload")):
            with self.assertRaisesRegex(
                UserVisibleError,
                "(?s)measurement.xlsx 自动检测读入设置失败.*corrupt workbook payload",
            ):
                detect_read_options(Path("measurement.xlsx"), "自动", "自动", 0, True)


if __name__ == "__main__":
    unittest.main()
