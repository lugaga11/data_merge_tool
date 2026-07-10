from __future__ import annotations
from pathlib import Path
from typing import Any, List, Sequence, cast

import pandas as pd

from ..data_types import MergeOptions
from ..errors import UserVisibleError
from ..data_reading.readers import read_table_columns


def format_cell_value(value: object) -> str:
    if pd.isna(cast(Any, value)):
        return "<空>"
    return repr(value)

def validate_x_series(path: Path, current_x: pd.Series, reference_x: pd.Series, reference_len: int) -> None:
    if len(current_x) != reference_len:
        raise UserVisibleError(f"{path.name} 的行数与第一个文件不同：{len(current_x)} != {reference_len}")

    if current_x.equals(reference_x):
        return

    current_values = current_x.reset_index(drop=True)
    reference_values = reference_x.reset_index(drop=True)
    both_empty = current_values.isna() & reference_values.isna()
    same_values = current_values.eq(reference_values).fillna(False)
    mismatch = ~(same_values | both_empty)
    mismatch_positions = mismatch[mismatch].index
    if len(mismatch_positions) == 0:
        return

    row = int(mismatch_positions[0])
    raise UserVisibleError(
        f"{path.name} 的 X 列与第一个文件不一致：第 {row + 1} 行，"
        f"第一个文件为 {format_cell_value(reference_values.iloc[row])}，"
        f"当前文件为 {format_cell_value(current_values.iloc[row])}。"
    )

def format_column_numbers(columns: Sequence[int]) -> str:
    return ", ".join(str(column) for column in columns)

def preflight_merge_columns(paths: Sequence[str], options: MergeOptions) -> None:
    if not paths:
        raise UserVisibleError("请先添加要合并的数据文件。")

    x_index = options.x_column - 1
    if options.keep_single_x and x_index < 0:
        raise UserVisibleError("X 列号必须从 1 开始。")

    if options.keep_single_x:
        selected_y_columns = [idx for idx in options.y_columns if idx != x_index]
        if not selected_y_columns:
            raise UserVisibleError("保留单个 X 列时，Y 列不能只包含 X 列。")
    else:
        selected_y_columns = list(options.y_columns)
        if not selected_y_columns and not options.y_columns_auto:
            raise UserVisibleError("未保留 X 列时，请至少选择一个要合并的列。")

    issues: List[str] = []
    for file_number, raw_path in enumerate(paths, start=1):
        path = Path(raw_path)
        try:
            columns = read_table_columns(path, options.read)
        except UserVisibleError as exc:
            issues.append(f"{file_number}. {path.name}：读取列结构失败：{exc}")
            continue
        except Exception as exc:
            issues.append(f"{file_number}. {path.name}：读取列结构失败：{exc}")
            continue

        column_count = len(columns)
        file_issues: List[str] = []
        if column_count == 0:
            file_issues.append("未读到任何列")

        if options.keep_single_x and x_index >= column_count:
            file_issues.append(f"X 列 {options.x_column} 超出范围（当前 {column_count} 列）")

        if options.y_columns_auto:
            y_columns = [idx for idx in range(column_count) if not (options.keep_single_x and idx == x_index)]
        else:
            y_columns = selected_y_columns
        invalid_y_columns = [idx + 1 for idx in y_columns if idx < 0 or idx >= column_count]
        if invalid_y_columns:
            file_issues.append(
                f"Y 列 {format_column_numbers(invalid_y_columns)} 超出范围（当前 {column_count} 列）"
            )

        if file_issues:
            issues.append(f"{file_number}. {path.name}：" + "；".join(file_issues))

    if issues:
        detail = "\n".join(issues)
        raise UserVisibleError(
            "以下文件的列结构不支持当前 X/Y 列选择，请调整列选择或文件列表后再合并：\n\n"
            f"{detail}"
        )
