from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

import pandas as pd

from ..data_reading.readers import read_table
from ..data_types import MergeOptions, OriginImportData
from ..errors import UserVisibleError
from .labels import (
    build_source_labels,
    derive_source_group_label,
    make_unique_columns,
    shared_x_label_info,
    source_column_label_info,
)
from .validation import preflight_merge_columns, validate_x_series


@dataclass(frozen=True)
class MergedTable:
    dataframe: pd.DataFrame
    long_names: list[str]
    comments: list[str]


def build_prechecked_merged_table(paths: Sequence[str], options: MergeOptions) -> MergedTable:
    selected, headers = preflight_merge_columns(paths, options)
    source_labels = build_source_labels(paths, options.label_mode)
    read_indices = sorted(set(selected))
    positions = {source_index: position for position, source_index in enumerate(read_indices)}
    parts: list[pd.DataFrame] = []
    long_names: list[str] = []
    comments: list[str] = []
    reference_x: pd.Series | None = None

    for raw_path, columns in zip(paths, headers, strict=True):
        path = Path(raw_path)
        df = read_table(path, options.read, usecols=read_indices)
        if df.empty:
            raise UserVisibleError(f"{path.name} 读取后没有数据。")

        output_indices = selected
        if options.keep_single_x:
            current_x = df.iloc[:, positions[selected[0]]]
            if reference_x is None:
                reference_x = current_x
            else:
                if options.validate_x:
                    validate_x_series(path, current_x, reference_x, len(reference_x))
                elif len(df) != len(reference_x):
                    raise UserVisibleError(f"{path.name} 的行数与第一个文件不同：{len(df)} != {len(reference_x)}")
                output_indices = selected[1:]

        labels = [
            shared_x_label_info(columns, index, options) if options.keep_single_x and index == selected[0]
            else source_column_label_info(source_labels[raw_path], columns, index, options)
            for index in output_indices
        ]
        part = df.iloc[:, [positions[index] for index in output_indices]]
        part.columns = [label.output_name for label in labels]
        parts.append(part)
        long_names.extend(label.origin_long_name for label in labels)
        comments.extend(label.origin_comment for label in labels)

    merged = pd.concat(parts, axis=1)
    merged.columns = make_unique_columns(merged.columns.tolist())
    return MergedTable(merged, long_names, comments)


def build_origin_import_table(paths: Sequence[str], options: MergeOptions) -> OriginImportData:
    x_index = options.x_column - 1
    if not paths:
        raise UserVisibleError("请先添加要合并的数据文件。")
    if x_index < 0:
        raise UserVisibleError("X 列号必须从 1 开始。")

    per_file_x = not options.keep_single_x and x_index in options.y_columns
    if per_file_x:
        y_columns = [index for index in options.y_columns if index != x_index]
        if not y_columns:
            raise UserVisibleError("不保留单个 X 列且勾选了 X 列时，请至少再勾选一个非 X 列作为 Y。")
        options = replace(options, y_columns=[x_index, *y_columns])

    table = build_prechecked_merged_table(paths, options)
    if options.keep_single_x:
        axis_spec = "x" + "y" * (table.dataframe.shape[1] - 1)
    elif per_file_x:
        axis_spec = ("x" + "y" * (len(options.y_columns) - 1)) * len(paths)
    else:
        axis_spec = "y" * table.dataframe.shape[1]
    return OriginImportData(table.dataframe, axis_spec, table.long_names, table.comments, derive_source_group_label(paths))
