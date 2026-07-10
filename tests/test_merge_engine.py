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

from data_merge_tool.data_types import MergeOptions, ReadOptions
from data_merge_tool.errors import UserVisibleError
from data_merge_tool.merge.engine import build_origin_import_table


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
    y_columns_auto: bool = False,
    validate_x: bool = True,
    label_mode: str = "smart",
) -> MergeOptions:
    return MergeOptions(
        read=READ_OPTIONS,
        y_columns=y_columns,
        y_columns_auto=y_columns_auto,
        keep_single_x=keep_single_x,
        x_column=1,
        validate_x=validate_x,
        label_mode=label_mode,
    )


def write_series(path: Path, rows: list[tuple[float, float]]) -> None:
    lines = ["x,signal", *(f"{x},{signal}" for x, signal in rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class MergeEngineTests(unittest.TestCase):
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
                merge_options(keep_single_x=False, y_columns=[], y_columns_auto=True),
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
