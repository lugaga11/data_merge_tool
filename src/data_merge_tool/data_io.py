from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from importlib import metadata, util
from pathlib import Path
from typing import Any, List, Optional, Sequence, cast

import pandas as pd
from charset_normalizer import from_path

from .constants import EXCEL_READER_DEPENDENCIES, SUPPORTED_EXTENSIONS
from .data_types import MergeOptions, OriginImportData, ReadDetection, ReadOptions
from .errors import UserVisibleError


@dataclass(frozen=True)
class ColumnLabelInfo:
    source_label: str
    original_column_label: str
    output_name: str
    origin_long_name: str
    origin_comment: str


@dataclass(frozen=True)
class MergedTable:
    dataframe: pd.DataFrame
    long_names: List[str]
    comments: List[str]


@dataclass(frozen=True)
class _RowProfile:
    index: int
    field_count: int
    non_empty_count: int
    numeric_count: int
    has_text: bool


@dataclass(frozen=True)
class _DetectionCandidate:
    detection: ReadDetection
    score: tuple[int, int, int, int]


_NUMERIC_TOKEN = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")
_AUTO_DELIMITER_CANDIDATES = [",", "\t", ";", "whitespace"]
_DELIMITER_LABELS = {
    ",": "逗号 ,",
    "\t": "Tab",
    ";": "分号 ;",
    "whitespace": "空格/连续空白",
}


def delimiter_value(label: str) -> Optional[str]:
    mapping = {
        "自动": None,
        "逗号 ,": ",",
        "Tab": "\t",
        "空格/连续空白": r"\s+",
        "分号 ;": ";",
    }
    return mapping[label]


def _delimiter_candidates(label: str) -> List[str]:
    mapping = {
        "逗号 ,": [","],
        "Tab": ["\t"],
        "空格/连续空白": ["whitespace"],
        "分号 ;": [";"],
    }
    return mapping.get(label, _AUTO_DELIMITER_CANDIDATES)


def _delimiter_label(delimiter: str) -> str:
    return _DELIMITER_LABELS.get(delimiter, "自动")


def _clean_text_field(value: str) -> str:
    return value.strip().lstrip("\ufeff")


def _split_fields(text: str, delimiter: str) -> List[str]:
    if not text.strip():
        return []
    if delimiter == "whitespace":
        return [_clean_text_field(field) for field in re.split(r"\s+", text.strip()) if field.strip()]

    line = text.lstrip("\ufeff")
    fields = next(csv.reader([line], delimiter=delimiter, skipinitialspace=True))
    return [_clean_text_field(field) for field in fields]


def _is_numeric_token(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and not pd.isna(cast(Any, value)):
        return True
    text = _clean_text_field(str(value))
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = _clean_text_field(text[1:-1])
    return bool(_NUMERIC_TOKEN.fullmatch(text))


def _text_row_profile(index: int, line: str, delimiter: str) -> _RowProfile:
    fields = _split_fields(line, delimiter)
    non_empty_fields = [field for field in fields if field]
    numeric_flags = [_is_numeric_token(field) for field in non_empty_fields]
    numeric_count = sum(1 for is_numeric in numeric_flags if is_numeric)
    return _RowProfile(
        index=index,
        field_count=len(fields),
        non_empty_count=len(non_empty_fields),
        numeric_count=numeric_count,
        has_text=any(not is_numeric for is_numeric in numeric_flags),
    )


def _excel_row_profile(index: int, row: pd.Series) -> _RowProfile:
    fields = [value for value in row.tolist() if not pd.isna(cast(Any, value))]
    numeric_flags = [_is_numeric_token(value) for value in fields]
    numeric_count = sum(1 for is_numeric in numeric_flags if is_numeric)
    return _RowProfile(
        index=index,
        field_count=len(fields),
        non_empty_count=len(fields),
        numeric_count=numeric_count,
        has_text=any(not is_numeric for is_numeric in numeric_flags),
    )


def _is_data_profile(profile: _RowProfile) -> bool:
    return (
        profile.field_count >= 2
        and profile.numeric_count >= 2
        and profile.numeric_count == profile.non_empty_count
    )


def _is_header_profile(
    profile: _RowProfile,
    data_width: int,
    *,
    allow_wide_header: bool = False,
    allow_partial_header: bool = False,
) -> bool:
    if not profile.has_text or profile.numeric_count >= profile.non_empty_count:
        return False
    if profile.field_count == data_width:
        return True
    if (
        allow_partial_header
        and 2 <= profile.field_count < data_width
        and profile.numeric_count == 0
        and profile.field_count >= max(2, (data_width + 1) // 2)
    ):
        return True
    return allow_wide_header and profile.field_count > data_width and profile.numeric_count < data_width


def _detect_from_profiles(
    profiles: Sequence[_RowProfile],
    fallback_skip_rows: int,
    fallback_delimiter_label: str,
    fallback_encoding_label: str,
    fallback_has_header: bool,
    *,
    delimiter_label: str,
    encoding_label: str,
    min_streak: int = 3,
    allow_wide_header: bool = False,
    allow_partial_header: bool = False,
) -> _DetectionCandidate:
    best: Optional[_DetectionCandidate] = None
    best_score: tuple[int, int, int, int] = (-1, -1, -1, -10_000)

    start = 0
    while start < len(profiles):
        first = profiles[start]
        if not _is_data_profile(first):
            start += 1
            continue

        data_width = first.field_count
        end = start
        while (
            end < len(profiles)
            and _is_data_profile(profiles[end])
            and profiles[end].field_count == data_width
        ):
            end += 1

        run_length = end - start
        if run_length < min_streak:
            start = end
            continue

        data_start = first.index
        header = profiles[start - 1] if start > 0 else None
        has_header = bool(
            header is not None
            and _is_header_profile(
                header,
                data_width,
                allow_wide_header=allow_wide_header,
                allow_partial_header=allow_partial_header,
            )
        )
        skip_rows = header.index if has_header and header is not None else data_start
        message = f"自动识别：跳过 {skip_rows} 行，{'使用表头' if has_header else '无表头'}。"
        detection = ReadDetection(
            skip_rows=skip_rows,
            delimiter_label=delimiter_label,
            encoding_label=encoding_label,
            has_header=has_header,
            confident=True,
            message=message,
        )
        score = (1 if has_header else 0, data_width, run_length, -skip_rows)
        if score > best_score:
            best = _DetectionCandidate(detection=detection, score=score)
            best_score = score

        start = end

    if best is not None:
        return best

    return _DetectionCandidate(
        detection=ReadDetection(
            skip_rows=fallback_skip_rows,
            delimiter_label=fallback_delimiter_label,
            encoding_label=fallback_encoding_label,
            has_header=fallback_has_header,
            confident=False,
            message="未能可靠识别数据起点，继续使用手动读入设置。",
        ),
        score=(-1, -1, -1, -10_000),
    )


def detect_read_options(
    path: Path,
    delimiter_label: str,
    encoding_label: str,
    fallback_skip_rows: int,
    fallback_has_header: bool,
    *,
    max_rows: int = 500,
) -> ReadDetection:
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xls"}:
            require_excel_reader(suffix)
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            preview = pd.read_excel(path, header=None, nrows=max_rows, engine=engine)
            profiles = [_excel_row_profile(index, row) for index, (_, row) in enumerate(preview.iterrows())]
            return _detect_from_profiles(
                profiles,
                fallback_skip_rows,
                fallback_delimiter_label=delimiter_label,
                fallback_encoding_label=encoding_label,
                fallback_has_header=fallback_has_header,
                delimiter_label=delimiter_label,
                encoding_label=encoding_label,
                allow_partial_header=True,
            ).detection

        encoding = detect_encoding(path, encoding_label)
        with path.open("r", encoding=encoding, errors="replace") as handle:
            lines = [line.rstrip("\r\n") for _, line in zip(range(max_rows), handle)]

        candidates: List[_DetectionCandidate] = []
        for delimiter in _delimiter_candidates(delimiter_label):
            profiles = [_text_row_profile(index, line, delimiter) for index, line in enumerate(lines)]
            candidate = _detect_from_profiles(
                profiles,
                fallback_skip_rows,
                fallback_delimiter_label=delimiter_label,
                fallback_encoding_label=encoding_label,
                fallback_has_header=fallback_has_header,
                delimiter_label=_delimiter_label(delimiter),
                encoding_label=encoding,
                allow_wide_header=delimiter == "whitespace",
            )
            if candidate.detection.confident:
                candidates.append(candidate)

        if candidates:
            return max(candidates, key=lambda candidate: candidate.score).detection
    except Exception:
        pass

    return ReadDetection(
        skip_rows=fallback_skip_rows,
        delimiter_label=delimiter_label,
        encoding_label=encoding_label,
        has_header=fallback_has_header,
        confident=False,
        message="未能可靠识别数据起点，继续使用手动读入设置。",
    )


def natural_sort_key(value: str) -> List[object]:
    parts = re.split(r"(\d+)", value.casefold())
    return [int(part) if part.isdigit() else part for part in parts]


def source_label_sort_key(label: str) -> List[tuple[int, float, str]]:
    parts = re.split(r"(\d+(?:\.\d+)?)", label.casefold())
    result: List[tuple[int, float, str]] = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", part):
            result.append((0, float(part), ""))
        else:
            result.append((1, 0.0, part))
    return result


def is_supported_data_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def scan_data_files(folder: Path) -> List[str]:
    paths = [path for path in folder.rglob("*") if is_supported_data_file(path)]
    paths.sort(key=lambda path: natural_sort_key(str(path.relative_to(folder))))
    return [str(path) for path in paths]


def detect_encoding(path: Path, label: str) -> str:
    if label == "自动":
        try:
            best = from_path(str(path)).best()
            return best.encoding if best and best.encoding else "utf-8"
        except Exception:
            return "utf-8"
    if label == "ANSI/系统默认":
        return "mbcs"
    return label


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version)
    return tuple(int(part) for part in parts[:3])


def _is_version_at_least(installed: str, minimum: str) -> bool:
    installed_parts = _version_tuple(installed)
    minimum_parts = _version_tuple(minimum)
    width = max(len(installed_parts), len(minimum_parts))
    installed_parts += (0,) * (width - len(installed_parts))
    minimum_parts += (0,) * (width - len(minimum_parts))
    return installed_parts >= minimum_parts


def require_excel_reader(suffix: str) -> None:
    package, minimum, requirement, label = EXCEL_READER_DEPENDENCIES[suffix]
    if util.find_spec(package) is None:
        raise UserVisibleError(
            f"缺少读取 {label} 文件所需依赖：{requirement}。\n"
            "请运行：pip install -r requirements_desktop.txt\n"
            f"或单独运行：pip install \"{requirement}\""
        )

    try:
        installed = metadata.version(package)
    except metadata.PackageNotFoundError:
        return

    if not _is_version_at_least(installed, minimum):
        raise UserVisibleError(
            f"读取 {label} 文件需要 {requirement}，当前安装的是 {package}=={installed}。\n"
            "请运行：pip install -U -r requirements_desktop.txt\n"
            f"或单独运行：pip install -U \"{requirement}\""
        )


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for column in list(result.columns):
        if result[column].dtype == object:
            converted = pd.to_numeric(result[column], errors="coerce")
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
        if suffix == ".xlsx":
            require_excel_reader(suffix)
            df = pd.read_excel(
                path,
                header=header,
                skiprows=options.skip_rows,
                engine="openpyxl",
                nrows=nrows,
                usecols=selected_columns,
            )
        elif suffix == ".xls":
            require_excel_reader(suffix)
            # .xls is the legacy Excel BIFF format; openpyxl only reads the
            # newer Office Open XML formats such as .xlsx, so pandas needs xlrd.
            df = pd.read_excel(
                path,
                header=header,
                skiprows=options.skip_rows,
                engine="xlrd",
                nrows=nrows,
                usecols=selected_columns,
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
                usecols=selected_columns,
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


def fallback_source_labels(paths: Sequence[str]) -> dict[str, str]:
    return {raw_path: Path(raw_path).stem for raw_path in paths}


def derive_source_labels(paths: Sequence[str]) -> dict[str, str]:
    if not paths:
        return {}

    stems = [Path(raw_path).stem for raw_path in paths]
    fallback = fallback_source_labels(paths)
    if len(stems) < 2:
        return fallback

    common_prefix = os.path.commonprefix(stems)
    common_suffix = os.path.commonprefix([stem[::-1] for stem in stems])[::-1]
    if common_suffix and common_suffix[0] not in " -_":
        separator_positions = [common_suffix.find(separator) for separator in " -_" if separator in common_suffix]
        if separator_positions:
            common_suffix = common_suffix[min(separator_positions):]
        else:
            common_suffix = ""
    suffix_len = len(common_suffix)

    labels: List[str] = []
    for stem in stems:
        start = len(common_prefix)
        end = len(stem) - suffix_len if suffix_len else len(stem)
        raw_label = stem[start:end] if end >= start else ""
        labels.append(raw_label.strip(" -_."))

    if any(not label for label in labels) or len(set(labels)) != len(labels):
        return fallback
    return dict(zip(paths, labels))


def derive_source_group_label(paths: Sequence[str]) -> str:
    if not paths:
        return "合并数据"

    stems = [Path(raw_path).stem for raw_path in paths]
    if len(stems) == 1:
        return stems[0].strip(" -_.") or "合并数据"
    if len(set(stems)) == 1:
        return stems[0].strip(" -_.") or "合并数据"

    common_prefix = os.path.commonprefix(stems)
    common_suffix = os.path.commonprefix([stem[::-1] for stem in stems])[::-1]
    if common_suffix and common_suffix[0] not in " -_.":
        separator_positions = [
            common_suffix.find(separator)
            for separator in " -_."
            if separator in common_suffix
        ]
        common_suffix = common_suffix[min(separator_positions):] if separator_positions else ""

    prefix = common_prefix.strip(" -_.")
    suffix = common_suffix.strip(" -_.")
    if prefix and suffix:
        return f"{prefix}...{suffix}"
    if prefix:
        return prefix
    if suffix:
        return suffix
    return "合并数据"


def build_source_labels(paths: Sequence[str], mode: str) -> dict[str, str]:
    if mode == "full":
        return fallback_source_labels(paths)
    return derive_source_labels(paths)


def source_column_label_info(
    path: Path,
    source_label: str,
    columns: Sequence[object],
    column_index: int,
    options: MergeOptions,
) -> ColumnLabelInfo:
    if options.read.has_header:
        original_column_label = str(columns[column_index])
    else:
        original_column_label = f"C{column_index + 1}"
    return ColumnLabelInfo(
        source_label=source_label,
        original_column_label=original_column_label,
        output_name=f"{source_label}_{original_column_label}",
        origin_long_name=original_column_label,
        origin_comment=source_label,
    )


def shared_x_label_info(path: Path, columns: Sequence[object], column_index: int, options: MergeOptions) -> ColumnLabelInfo:
    original_column_label = str(columns[column_index]) if options.read.has_header else "X"
    return ColumnLabelInfo(
        source_label=Path(path).stem,
        original_column_label=original_column_label,
        output_name=original_column_label,
        origin_long_name=original_column_label,
        origin_comment="共享 X",
    )


def make_unique_columns(columns: Sequence[object]) -> List[str]:
    seen: dict[str, int] = {}
    unique: List[str] = []
    for column in columns:
        base = str(column)
        count = seen.get(base, 0)
        unique.append(base if count == 0 else f"{base}_{count + 1}")
        seen[base] = count + 1
    return unique


def unique_preserving_order(values: Sequence[int]) -> List[int]:
    seen: set[int] = set()
    result: List[int] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def format_cell_value(value: object) -> str:
    if pd.isna(cast(Any, value)):
        return "<空>"
    return repr(value)


def validate_x_series(path: Path, current_x: pd.Series, reference_x: pd.Series, reference_len: int) -> None:
    if len(current_x) != reference_len:
        raise UserVisibleError(f"{path.name} 的行数与第一个文件不同：{len(current_x)} != {reference_len}")

    if current_x.equals(reference_x):
        return

    both_empty = current_x.isna() & reference_x.isna()
    mismatch = ~(current_x.eq(reference_x) | both_empty)
    mismatch_positions = mismatch[mismatch].index
    if len(mismatch_positions) == 0:
        raise UserVisibleError(f"{path.name} 的 X 列与第一个文件不一致。")

    row = int(mismatch_positions[0])
    raise UserVisibleError(
        f"{path.name} 的 X 列与第一个文件不一致：第 {row + 1} 行，"
        f"第一个文件为 {format_cell_value(reference_x.iloc[row])}，"
        f"当前文件为 {format_cell_value(current_x.iloc[row])}。"
    )


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

        columns_to_read = sorted(unique_preserving_order(([x_index] if options.keep_single_x else []) + y_columns))
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


def build_merged_dataframe(paths: Sequence[str], options: MergeOptions) -> pd.DataFrame:
    return _build_merged_table(paths, options).dataframe


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
        columns_to_read = sorted(unique_preserving_order(selected_columns))
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


def build_prechecked_merged_table(paths: Sequence[str], options: MergeOptions) -> MergedTable:
    preflight_merge_columns(paths, options)
    return _build_merged_table(paths, options)


def build_prechecked_merged_dataframe(paths: Sequence[str], options: MergeOptions) -> pd.DataFrame:
    return build_prechecked_merged_table(paths, options).dataframe
