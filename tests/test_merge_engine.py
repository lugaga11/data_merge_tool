from __future__ import annotations

from dataclasses import replace
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

from data_merge_tool.data_types import MergeOptions, ReadOptions
from data_merge_tool.errors import UserVisibleError
from data_merge_tool.data_reading.readers import read_table_columns
from data_merge_tool.merge.engine import build_origin_import_table, build_prechecked_merged_table


READ_OPTIONS = ReadOptions(
    skip_rows=0,
    delimiter_label="逗号 ,",
    encoding_label="utf-8",
    has_header=True,
    skip_bad_lines=False,
)


def merge_options(
    *,
    keep_single_x: bool,
    y_columns: list[int],
    validate_x: bool = True,
    label_mode: str = "smart",
) -> MergeOptions:
    return MergeOptions(
        read=READ_OPTIONS,
        y_columns=y_columns,
        keep_single_x=keep_single_x,
        x_column=1,
        validate_x=validate_x,
        label_mode=label_mode,
    )


def write_series(path: Path, rows: list[tuple[float, float]]) -> None:
    lines = ["x,signal", *(f"{x},{signal}" for x, signal in rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class MergeEngineTests(unittest.TestCase):
    def test_per_file_x_uses_one_header_read_and_keeps_selected_order_for_plain_merge(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "series 1.csv", root / "series 2.csv"
            first.write_text("a,x,b\n1,10,11\n2,20,22\n", encoding="utf-8")
            second.write_text("a,x,b\n3,30,33\n", encoding="utf-8")
            paths = [str(first), str(second)]
            options = replace(merge_options(keep_single_x=False, y_columns=[2, 1, 0]), x_column=2)
            plain = build_prechecked_merged_table(paths, options)
            with patch("data_merge_tool.merge.validation.read_table_columns", wraps=read_table_columns) as read_headers:
                origin = build_origin_import_table(paths, options)

        self.assertEqual([call.args[0] for call in read_headers.call_args_list], [first, second])
        self.assertEqual(plain.long_names, ["b", "x", "a"] * 2)
        self.assertEqual(origin.long_names, ["x", "b", "a"] * 2)
        self.assertEqual(origin.axis_spec, "xyyxyy")
        self.assertEqual(origin.dataframe.iloc[0].tolist(), [10, 11, 1, 30, 33, 3])
        self.assertTrue(origin.dataframe.iloc[1, 3:].isna().all())
        self.assertEqual(options.y_columns, [2, 1, 0])

    def test_per_file_x_reports_all_incompatible_sources_before_reading_data(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / name for name in ("first.csv", "second.csv")]
            for path in paths:
                write_series(path, [(0, 1)])
            with patch("data_merge_tool.merge.engine.read_table") as read_data, self.assertRaises(UserVisibleError) as error:
                build_origin_import_table(
                    [str(path) for path in paths],
                    replace(merge_options(keep_single_x=False, y_columns=[2, 3]), x_column=3),
                )
            read_data.assert_not_called()
        self.assertIn("1. first.csv", str(error.exception))
        self.assertIn("2. second.csv", str(error.exception))
        self.assertEqual(str(error.exception).count("X 列 3 超出范围"), 2)
        self.assertEqual(str(error.exception).count("Y 列 4 超出范围"), 2)

    def test_shared_numeric_x_still_matches_after_a_text_footer_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "series 1.csv"
            second = Path(folder) / "series 2.csv"
            write_series(first, [(0, 10), (1, 11)])
            second.write_text("x,signal\n0,20\n1,21\nend,of run\n", encoding="utf-8")
            options = replace(
                merge_options(keep_single_x=True, y_columns=[1]),
                read=replace(READ_OPTIONS, skip_bad_lines=True),
            )
            result = build_origin_import_table([str(first), str(second)], options)

        pd.testing.assert_frame_equal(
            result.dataframe,
            pd.DataFrame({"x": [0, 1], "1_signal": [10, 11], "2_signal": [20, 21]}),
        )

    def test_shared_x_origin_table_has_one_x_and_metadata_for_each_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "series 1.csv"
            second = root / "series 2.csv"
            write_series(first, [(0, 10), (1, 11)])
            write_series(second, [(0, 20), (1, 21)])

            result = build_origin_import_table(
                [str(first), str(second)],
                merge_options(keep_single_x=True, y_columns=[1]),
            )

        pd.testing.assert_frame_equal(
            result.dataframe,
            pd.DataFrame(
                {
                    "x": [0, 1],
                    "1_signal": [10, 11],
                    "2_signal": [20, 21],
                }
            ),
        )
        self.assertEqual(result.axis_spec, "xyy")
        self.assertEqual(result.long_names, ["x", "signal", "signal"])
        self.assertEqual(result.comments, ["共享 X", "1", "2"])
        self.assertEqual(result.workbook_label, "series")

    def test_per_file_xy_origin_table_repeats_axis_pair_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "series 1.csv"
            second = root / "series 2.csv"
            write_series(first, [(0, 10), (1, 11)])
            write_series(second, [(5, 20), (6, 21)])

            result = build_origin_import_table(
                [str(first), str(second)],
                merge_options(keep_single_x=False, y_columns=[0, 1]),
            )

        self.assertEqual(
            list(result.dataframe.columns),
            ["1_x", "1_signal", "2_x", "2_signal"],
        )
        self.assertEqual(result.axis_spec, "xyxy")
        self.assertEqual(result.long_names, ["x", "signal", "x", "signal"])
        self.assertEqual(result.comments, ["1", "1", "2", "2"])
        self.assertEqual(result.dataframe.iloc[:, 2].tolist(), [5, 6])

    def test_explicit_y_only_selection_produces_y_axes_without_x_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "series 1.csv"
            second = root / "series 2.csv"
            write_series(first, [(0, 10), (1, 11)])
            write_series(second, [(0, 20), (1, 21)])

            result = build_origin_import_table(
                [str(first), str(second)],
                merge_options(keep_single_x=False, y_columns=[1]),
            )

        pd.testing.assert_frame_equal(
            result.dataframe,
            pd.DataFrame({"1_signal": [10, 11], "2_signal": [20, 21]}),
        )
        self.assertEqual(result.axis_spec, "yy")
        self.assertEqual(result.long_names, ["signal", "signal"])
        self.assertEqual(result.comments, ["1", "2"])

    def test_duplicate_source_and_column_names_are_made_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first = first_dir / "sample.csv"
            second = second_dir / "sample.csv"
            write_series(first, [(0, 10), (1, 11)])
            write_series(second, [(0, 20), (1, 21)])

            result = build_origin_import_table(
                [str(first), str(second)],
                merge_options(
                    keep_single_x=False,
                    y_columns=[1],
                    label_mode="full",
                ),
            )

        self.assertEqual(list(result.dataframe.columns), ["sample_signal", "sample_signal_2"])
        self.assertEqual(len(result.dataframe.columns), len(set(result.dataframe.columns)))

    def test_shared_x_mismatch_surfaces_file_and_first_bad_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "series 1.csv"
            second = root / "series 2.csv"
            write_series(first, [(0, 10), (1, 11)])
            write_series(second, [(0, 20), (2, 21)])

            with self.assertRaisesRegex(
                UserVisibleError,
                "series 2.csv 的 X 列与第一个文件不一致：第 2 行",
            ):
                build_origin_import_table(
                    [str(first), str(second)],
                    merge_options(keep_single_x=True, y_columns=[1]),
                )


if __name__ == "__main__":
    unittest.main()
