from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from ..data_types import MergeOptions, OriginImportData
from ..errors import UserVisibleError
from ..data_reading.readers import read_table, read_table_columns
from .labels import (
    ColumnLabelInfo,
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
    long_names: List[str]
    comments: List[str]

def _build_merged_table(paths: Sequence[str], options: MergeOptions) -> MergedTable:
    if not paths:
        raise UserVisibleError("请先添加要合并的数据文件。")

    pieces: List[pd.DataFrame] = []
    long_names: List[str] = []
    comments: List[str] = []
    reference_x: Optional[pd.Series] = None
    reference_len: Optional[int] = None
    source_labels = build_source_labels(paths, options.label_mode)
    x_index = options.x_column - 1

    for file_index, raw_path in enumerate(paths):
        path = Path(raw_path)
        source_label = source_labels.get(raw_path, path.stem)
        columns = read_table_columns(path, options.read)
        column_count = len(columns)
        if column_count == 0:
            raise UserVisibleError(f"{path.name} 读取后没有数据。")

        if options.keep_single_x:
            if x_index < 0 or x_index >= column_count:
                raise UserVisibleError(f"{path.name} 的 X 列 {options.x_column} 超出范围。")

            if options.y_columns_auto:
                y_columns = [idx for idx in range(column_count) if idx != x_index]
            else:
                y_columns = [idx for idx in options.y_columns if idx != x_index]
            if not y_columns:
                raise UserVisibleError("保留单个 X 列时，Y 列不能只包含 X 列。")
        else:
            y_columns = list(range(column_count)) if options.y_columns_auto else list(options.y_columns)
            if not y_columns:
                raise UserVisibleError("未保留 X 列时，请至少选择一个要合并的列。")

        invalid = [idx + 1 for idx in y_columns if idx < 0 or idx >= column_count]
        if invalid:
            raise UserVisibleError(f"{path.name} 的列号超出范围：{invalid}")

        columns_to_read = sorted(set(([x_index] if options.keep_single_x else []) + y_columns))
        df = read_table(path, options.read, usecols=columns_to_read)
        if df.empty:
            raise UserVisibleError(f"{path.name} 读取后没有数据。")
        column_positions = {column_index: position for position, column_index in enumerate(columns_to_read)}

        output_columns: List[str] = []
        column_label_infos: List[ColumnLabelInfo] = []
        if options.keep_single_x:
            current_x = df.iloc[:, column_positions[x_index]].reset_index(drop=True)
            if file_index == 0:
                reference_x = current_x.copy()
                reference_len = len(df)
                selected_columns = [x_index] + y_columns
                x_info = shared_x_label_info(path, columns, x_index, options)
                output_columns.append(x_info.output_name)
                column_label_infos.append(x_info)
            else:
                if reference_len is not None and reference_x is not None and options.validate_x:
                    validate_x_series(path, current_x, reference_x, reference_len)
                elif reference_len is not None and len(df) != reference_len:
                    raise UserVisibleError(f"{path.name} 的行数与第一个文件不同：{len(df)} != {reference_len}")
                selected_columns = y_columns
        else:
            selected_columns = y_columns

        for column_index in y_columns:
            label_info = source_column_label_info(path, source_label, columns, column_index, options)
            output_columns.append(label_info.output_name)
            column_label_infos.append(label_info)

        selected_positions = [column_positions[idx] for idx in selected_columns]
        part = df.iloc[:, selected_positions].reset_index(drop=True).copy()
        part.columns = output_columns
        pieces.append(part)
        long_names.extend(label_info.origin_long_name for label_info in column_label_infos)
        comments.extend(label_info.origin_comment for label_info in column_label_infos)

    merged = pd.concat(pieces, axis=1)
    merged.columns = make_unique_columns(list(merged.columns))
    return MergedTable(dataframe=merged, long_names=long_names, comments=comments)

def build_origin_import_table(paths: Sequence[str], options: MergeOptions) -> OriginImportData:
    workbook_label = derive_source_group_label(paths)
    if options.keep_single_x:
        table = build_prechecked_merged_table(paths, options)
        axis_spec = "x" + ("y" * max(table.dataframe.shape[1] - 1, 0))
        return OriginImportData(
            dataframe=table.dataframe,
            axis_spec=axis_spec,
            long_names=table.long_names,
            comments=table.comments,
            workbook_label=workbook_label,
        )

    if not paths:
        raise UserVisibleError("请先添加要导入 Origin 的数据文件。")

    x_index = options.x_column - 1
    if x_index < 0:
        raise UserVisibleError("X 列号必须从 1 开始。")

    if not options.y_columns_auto and x_index not in options.y_columns:
        table = build_prechecked_merged_table(paths, options)
        return OriginImportData(
            dataframe=table.dataframe,
            axis_spec="y" * table.dataframe.shape[1],
            long_names=table.long_names,
            comments=table.comments,
            workbook_label=workbook_label,
        )

    pieces: List[pd.DataFrame] = []
    axis_parts: List[str] = []
    long_names: List[str] = []
    comments: List[str] = []
    source_labels = build_source_labels(paths, options.label_mode)

    for raw_path in paths:
        path = Path(raw_path)
        source_label = source_labels.get(raw_path, path.stem)
        columns = read_table_columns(path, options.read)
        column_count = len(columns)
        if column_count == 0:
            raise UserVisibleError(f"{path.name} 读取后没有数据。")
        if x_index >= column_count:
            raise UserVisibleError(f"{path.name} 的 X 列 {options.x_column} 超出范围。")

        if options.y_columns_auto:
            origin_y_columns = [idx for idx in range(column_count) if idx != x_index]
        else:
            origin_y_columns = [idx for idx in options.y_columns if idx != x_index]
        if not origin_y_columns:
            raise UserVisibleError("不保留单个 X 列且勾选了 X 列时，请至少再勾选一个非 X 列作为 Y。")

        invalid = [idx + 1 for idx in origin_y_columns if idx < 0 or idx >= column_count]
        if invalid:
            raise UserVisibleError(f"{path.name} 的列号超出范围：{invalid}")

        selected_columns = [x_index] + origin_y_columns
        label_infos = [
            source_column_label_info(path, source_label, columns, column_index, options)
            for column_index in selected_columns
        ]
        columns_to_read = sorted(set(selected_columns))
        df = read_table(path, options.read, usecols=columns_to_read)
        if df.empty:
            raise UserVisibleError(f"{path.name} 读取后没有数据。")

        column_positions = {column_index: position for position, column_index in enumerate(columns_to_read)}
        selected_positions = [column_positions[idx] for idx in selected_columns]
        part = df.iloc[:, selected_positions].reset_index(drop=True).copy()
        part.columns = [label_info.output_name for label_info in label_infos]
        pieces.append(part)
        axis_parts.append("x" + ("y" * len(origin_y_columns)))
        long_names.extend(label_info.origin_long_name for label_info in label_infos)
        comments.extend(label_info.origin_comment for label_info in label_infos)

    dataframe = pd.concat(pieces, axis=1)
    dataframe.columns = make_unique_columns(list(dataframe.columns))
    return OriginImportData(
        dataframe=dataframe,
        axis_spec="".join(axis_parts),
        long_names=long_names,
        comments=comments,
        workbook_label=workbook_label,
    )

def build_prechecked_merged_table(paths: Sequence[str], options: MergeOptions) -> MergedTable:
    preflight_merge_columns(paths, options)
    return _build_merged_table(paths, options)
