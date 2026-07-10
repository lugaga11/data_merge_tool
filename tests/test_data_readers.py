from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.data_reading.readers import read_table, scan_data_files
from data_merge_tool.data_types import ReadOptions
from data_merge_tool.errors import UserVisibleError


def csv_options(*, skip_bad_lines: bool = False) -> ReadOptions:
    return ReadOptions(
        skip_rows=0,
        delimiter_label="逗号 ,",
        encoding_label="utf-8",
        has_header=True,
        skip_bad_lines=skip_bad_lines,
    )


class DataReaderTests(unittest.TestCase):
    def test_skip_bad_lines_removes_parser_errors_and_non_numeric_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "measurement.csv"
            path.write_text(
                "x,y\n"
                "1,2\n"
                "not-a-value,also-not-a-value\n"
                "3,4,unexpected\n"
                "5,6\n",
                encoding="utf-8",
            )

            result = read_table(path, csv_options(skip_bad_lines=True))

        expected = pd.DataFrame({"x": [1, 5], "y": [2, 6]})
        pd.testing.assert_frame_equal(result, expected)

    def test_parser_error_is_preserved_when_bad_line_skipping_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "measurement.csv"
            path.write_text("x,y\n1,2\n3,4,unexpected\n", encoding="utf-8")

            with self.assertRaisesRegex(
                UserVisibleError,
                "(?s)measurement.csv 读取失败.*Expected 2 fields.*saw 3",
            ):
                read_table(path, csv_options())

    def test_wide_whitespace_header_is_combined_to_match_data_width(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "measurement.txt"
            path.write_text(
                "Voltage Current Density\n"
                "0 1\n"
                "1 2\n",
                encoding="utf-8",
            )
            options = ReadOptions(
                skip_rows=0,
                delimiter_label="空格/连续空白",
                encoding_label="utf-8",
                has_header=True,
                skip_bad_lines=False,
            )

            result = read_table(path, options)

        self.assertEqual(list(result.columns), ["Voltage Current", "Density"])
        pd.testing.assert_frame_equal(
            result,
            pd.DataFrame({"Voltage Current": [0, 1], "Density": [1, 2]}),
        )

    def test_usecols_reads_only_selected_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "measurement.csv"
            path.write_text("x,y,z\n1,2,3\n4,5,6\n", encoding="utf-8")

            result = read_table(path, csv_options(), usecols=[0, 2])

        pd.testing.assert_frame_equal(result, pd.DataFrame({"x": [1, 4], "z": [3, 6]}))

    def test_scan_data_files_is_recursive_natural_and_filters_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "nested"
            nested.mkdir()
            (nested / "run10.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (nested / "run2.csv").write_text("x,y\n1,2\n", encoding="utf-8")
            (nested / "notes.md").write_text("ignore", encoding="utf-8")

            result = scan_data_files(root)

        self.assertEqual(
            [Path(path).name for path in result],
            ["run2.csv", "run10.csv"],
        )


if __name__ == "__main__":
    unittest.main()
