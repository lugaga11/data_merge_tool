from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.data_reading.readers import (
    coerce_numeric_columns,
    read_table,
    scan_data_files,
)
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
    def test_numeric_strings_with_missing_values_convert_while_text_and_dates_are_preserved(self) -> None:
        frame = pd.DataFrame({
            "x": pd.Series(["1", None, "2.5"], dtype="string"),
            "note": pd.Series(["1", None, "完成"], dtype="string"),
            "date": pd.date_range("2026-01-01", periods=3),
        })

        result = coerce_numeric_columns(frame)

        self.assertTrue(pd.api.types.is_numeric_dtype(result["x"]))
        self.assertEqual(result["x"].dropna().tolist(), [1, 2.5])
        self.assertTrue(pd.isna(result["x"].iloc[1]))
        pd.testing.assert_frame_equal(result[["note", "date"]], frame[["note", "date"]])

    def test_short_header_cannot_shift_columns_even_with_bad_line_skipping_or_usecols(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "measurement.csv"
            for extra in ("", "100"):
                path.write_text(f"x,y\n0,10,{extra}\n1,20,{extra}\n2,30,{extra}\n", encoding="utf-8")
                for skip_bad_lines in (False, True):
                    for usecols in (None, [0, 1]):
                        with (
                            self.subTest(extra=extra, skip_bad_lines=skip_bad_lines, usecols=usecols),
                            self.assertRaisesRegex(UserVisibleError, "measurement.csv.*表头列数少于数据列数"),
                        ):
                            read_table(path, csv_options(skip_bad_lines=skip_bad_lines), usecols=usecols)

    def test_auto_delimiter_preserves_bad_line_handling_and_rejects_implicit_indices(self) -> None:
        options = replace(csv_options(skip_bad_lines=True), delimiter_label="自动")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "measurement.csv"
            prefix = 'x,y\n"broken"quote,note\n'
            path.write_text(prefix + "0,10\n1,20\n", encoding="utf-8")
            pd.testing.assert_frame_equal(read_table(path, options), pd.DataFrame({"x": [0, 1], "y": [10, 20]}))

            path.write_text(prefix + "0,10,\n1,20,\n", encoding="utf-8")
            with self.assertRaisesRegex(UserVisibleError, "表头列数少于数据列数"):
                read_table(path, options)

            path.write_text("x,y\nindex\n0,10,extra\n1,20,extra\n", encoding="utf-8")
            with self.assertRaisesRegex(UserVisibleError, "表头列数少于数据列数"):
                read_table(path, options, usecols=[0, 1])

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
