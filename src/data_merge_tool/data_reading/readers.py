from __future__ import annotations
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence, cast

import pandas as pd

from ..constants import SUPPORTED_EXTENSIONS
from ..data_types import ReadOptions
from ..errors import UserVisibleError
from .detection import delimiter_value, detect_encoding, require_excel_reader, _is_numeric_token, _split_fields


def natural_sort_key(value: str) -> List[object]:
    parts = re.split(r"(\d+)", value.casefold())
    return [int(part) if part.isdigit() else part for part in parts]

def is_supported_data_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS

def scan_data_files(folder: Path) -> List[str]:
    paths = [path for path in folder.rglob("*") if is_supported_data_file(path)]
    paths.sort(key=lambda path: natural_sort_key(str(path.relative_to(folder))))
    return [str(path) for path in paths]

def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in list(result.columns):
        if result[column].dtype == object:
            converted = cast(pd.Series, pd.to_numeric(result[column], errors="coerce"))
            if converted.notna().sum() == result[column].notna().sum():
                result[column] = converted
    return result

def drop_malformed_data_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    numeric = df.apply(lambda column: pd.to_numeric(column, errors="coerce"))
    valid_rows = numeric.notna().any(axis=1)
    return df.loc[valid_rows].reset_index(drop=True)

def _is_plain_header_token(token: str) -> bool:
    return bool(re.fullmatch(r"[^\W\d_]+", token, re.UNICODE))

def _combine_wide_whitespace_header_tokens(tokens: Sequence[str], data_width: int) -> Optional[List[str]]:
    if len(tokens) <= data_width:
        return None

    groups: List[str] = []
    for token in tokens:
        if _is_numeric_token(token) and groups and not _is_numeric_token(groups[-1]):
            groups[-1] = f"{groups[-1]} {token}"
        else:
            groups.append(token)

    while len(groups) > data_width:
        pair_index: Optional[int] = None
        for index in range(len(groups) - 1):
            if _is_plain_header_token(groups[index]) and _is_plain_header_token(groups[index + 1]):
                pair_index = index
                break
        if pair_index is None:
            for index in range(len(groups) - 1):
                if not _is_numeric_token(groups[index]) and not _is_numeric_token(groups[index + 1]):
                    pair_index = index
                    break
        if pair_index is None:
            pair_index = 0

        groups[pair_index] = f"{groups[pair_index]} {groups[pair_index + 1]}"
        del groups[pair_index + 1]

    return groups if len(groups) == data_width else None

def _wide_whitespace_header_names(path: Path, options: ReadOptions) -> Optional[List[str]]:
    if not options.has_header or delimiter_value(options.delimiter_label) != r"\s+":
        return None

    encoding = detect_encoding(path, options.encoding_label)
    header_tokens: Optional[List[str]] = None
    data_tokens: List[str] = []
    with path.open("r", encoding=encoding, errors="replace") as handle:
        for index, line in enumerate(handle):
            text = line.rstrip("\r\n")
            if index == options.skip_rows:
                header_tokens = _split_fields(text, "whitespace")
                continue
            if index <= options.skip_rows:
                continue
            data_tokens = _split_fields(text, "whitespace")
            if data_tokens:
                break

    if header_tokens is None or not data_tokens or not all(_is_numeric_token(token) for token in data_tokens):
        return None

    return _combine_wide_whitespace_header_tokens(header_tokens, len(data_tokens))

def read_table(
    path: Path,
    options: ReadOptions,
    *,
    nrows: Optional[int] = None,
    usecols: Optional[Sequence[int]] = None,
) -> pd.DataFrame:
    header = 0 if options.has_header else None
    suffix = path.suffix.lower()
    selected_columns = list(usecols) if usecols is not None else None

    try:
        if suffix in {".xlsx", ".xls"}:
            require_excel_reader(suffix)
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            df = pd.read_excel(
                path,
                header=header,
                skiprows=options.skip_rows,
                engine=engine,
                nrows=nrows,
                usecols=cast(Any, selected_columns),
            )
        else:
            header_names = _wide_whitespace_header_names(path, options)
            sep = delimiter_value(options.delimiter_label)
            engine = "python" if sep is None or sep == r"\s+" else "c"
            df = pd.read_csv(
                path,
                header=None if header_names is not None else header,
                names=header_names,
                skiprows=options.skip_rows + 1 if header_names is not None else options.skip_rows,
                nrows=nrows,
                usecols=cast(Any, selected_columns),
                sep=sep,
                encoding=detect_encoding(path, options.encoding_label),
                engine=engine,
                on_bad_lines="skip" if options.skip_bad_lines else "error",
            )
            if options.skip_bad_lines:
                df = drop_malformed_data_rows(df)
    except UserVisibleError:
        raise
    except Exception as exc:
        raise UserVisibleError(f"{path.name} 读取失败：\n{exc}") from exc

    return coerce_numeric_columns(df)

def read_table_columns(path: Path, options: ReadOptions) -> List[object]:
    df = read_table(path, options, nrows=1)
    return list(df.columns)
