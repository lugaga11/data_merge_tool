from __future__ import annotations

import re
import time
from typing import Any, Sequence, cast

import pandas as pd

from .errors import UserVisibleError


def connect_origin(op: Any) -> None:
    try:
        op.attach()
    except Exception:
        op.set_show(True)
        return
    op.set_show(True)


def safe_origin_long_name(label: str | None, max_base_length: int = 56) -> str:
    clean_label = re.sub(r"[\r\n\t]+", " ", label or "")
    clean_label = re.sub(r"\s+", " ", clean_label).strip()
    clean_label = re.sub(r'[\\/:*?"<>|]+', "-", clean_label)
    clean_label = clean_label.strip(" -_.") or "合并数据"

    if len(clean_label) > max_base_length:
        tail_length = max(8, (max_base_length - 3) // 3)
        head_length = max_base_length - tail_length - 3
        head = clean_label[:head_length].rstrip(" -_.")
        tail = clean_label[-tail_length:].lstrip(" -_.")
        clean_label = f"{head}...{tail}"

    return f"{clean_label} {time.strftime('%H%M')}"


def import_dataframe_to_origin(
    df: pd.DataFrame,
    axis_spec: str = "",
    long_names: Sequence[str] | None = None,
    comments: Sequence[str] | None = None,
    workbook_label: str | None = None,
) -> str:
    try:
        import originpro as op
    except ImportError as exc:
        raise UserVisibleError(
            "缺少连接 Origin 所需的 originpro 组件。\n"
            "请先在当前 Python 环境中安装：pip install originpro"
        ) from exc

    try:
        try:
            connect_origin(op)
            worksheet = op.new_sheet("w", lname=safe_origin_long_name(workbook_label))
            if worksheet is None:
                raise UserVisibleError("Origin 已连接，但没有成功创建新的工作簿。")
            worksheet = cast(Any, worksheet)
            worksheet.from_df(df)
            if axis_spec:
                worksheet.cols_axis(axis_spec)
            if long_names is not None:
                worksheet.set_labels(list(long_names), "L")
            if comments is not None:
                worksheet.set_labels(list(comments), "C")
            worksheet.activate()

            book = worksheet.get_book()
            book_name = getattr(book, "name", "")
            sheet_name = getattr(worksheet, "name", "")
            return f"{book_name}/{sheet_name}" if book_name and sheet_name else "Origin 工作簿"
        finally:
            try:
                op.detach()
            except Exception:
                pass
    except UserVisibleError:
        raise
    except Exception as exc:
        raise UserVisibleError(
            "originpro 导入失败。请确认 Origin/OriginPro 已安装、许可可用，并且允许外部 Python 连接。\n\n"
            f"原始错误：{exc}"
        ) from exc
