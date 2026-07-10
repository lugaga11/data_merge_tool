from __future__ import annotations
import csv
import re
from dataclasses import dataclass
from importlib import metadata, util
from pathlib import Path
from typing import Any, List, Optional, Sequence, cast

import pandas as pd

from ..constants import EXCEL_READER_DEPENDENCIES
from ..data_types import ReadDetection
from ..errors import UserVisibleError


_NUMERIC_TOKEN = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")
_AUTO_DELIMITER_CANDIDATES = [",", "\t", ";", "whitespace"]
_ENCODING_SAMPLE_BYTES = 32 * 1024
_EXCEL_ENCODING_LABEL = "Excel 内置"
_DELIMITER_LABELS = {
    ",": "逗号 ,",
    "\t": "Tab",
    ";": "分号 ;",
    "whitespace": "空格/连续空白",
}

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

def _active_delimiter_candidates(label: str, lines: Sequence[str]) -> List[str]:
    candidates = _delimiter_candidates(label)
    if label != "自动":
        return candidates

    active: List[str] = []
    for delimiter in candidates:
        if delimiter == "whitespace" or any(delimiter in line for line in lines):
            active.append(delimiter)
    return active

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
                fallback_encoding_label=_EXCEL_ENCODING_LABEL,
                fallback_has_header=fallback_has_header,
                delimiter_label=delimiter_label,
                encoding_label=_EXCEL_ENCODING_LABEL,
                allow_partial_header=True,
            ).detection

        encoding = detect_encoding(path, encoding_label)
        with path.open("r", encoding=encoding, errors="replace") as handle:
            lines = [line.rstrip("\r\n") for _, line in zip(range(max_rows), handle)]

        candidates: List[_DetectionCandidate] = []
        for delimiter in _active_delimiter_candidates(delimiter_label, lines):
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
    except UserVisibleError:
        raise
    except Exception as exc:
        raise UserVisibleError(f"{path.name} 自动检测读入设置失败：\n{exc}") from exc

    return ReadDetection(
        skip_rows=fallback_skip_rows,
        delimiter_label=delimiter_label,
        encoding_label=encoding_label,
        has_header=fallback_has_header,
        confident=False,
        message="未能可靠识别数据起点，继续使用手动读入设置。",
    )

def _count_cjk(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")

def detect_encoding(path: Path, label: str) -> str:
    if label == "自动":
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return _EXCEL_ENCODING_LABEL
        with path.open("rb") as handle:
            raw = handle.read(_ENCODING_SAMPLE_BYTES)
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if not raw or raw.isascii():
            return "utf-8"
        for encoding in ("utf-8", "gbk"):
            try:
                text = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            if encoding == "gbk" and _count_cjk(text) < 2:
                continue
            return encoding
        return "latin1"
    if label == "ANSI/系统默认":
        return "mbcs"
    if label == _EXCEL_ENCODING_LABEL:
        return "utf-8"
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
