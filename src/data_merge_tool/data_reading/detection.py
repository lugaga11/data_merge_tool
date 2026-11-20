from __future__ import annotations
import codecs
import csv
import re
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, List, Optional, Sequence, cast

import pandas as pd

from ..data_types import ReadDetection
from ..errors import UserVisibleError


_NUMERIC_TOKEN = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$")
_DETECTION_ROWS = 500
_MIN_DATA_STREAK = 3
_ENCODING_SAMPLE_BYTES = 32 * 1024
_EXCEL_ENCODING_LABEL = "Excel 内置"
_DELIMITERS = {
    "逗号 ,": ",",
    "Tab": "\t",
    "分号 ;": ";",
    "空格/连续空白": r"\s+",
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
    return None if label == "自动" else _DELIMITERS[label]

def _clean_text_field(value: str) -> str:
    return value.strip().lstrip("\ufeff")

def _split_fields(text: str, delimiter: str) -> List[str]:
    if not text.strip():
        return []
    if delimiter == r"\s+":
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
    *,
    delimiter_label: str,
    encoding_label: str,
    allow_wide_header: bool = False,
    allow_partial_header: bool = False,
) -> _DetectionCandidate | None:
    best: Optional[_DetectionCandidate] = None

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
        if run_length < _MIN_DATA_STREAK:
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
        if best is None or score > best.score:
            best = _DetectionCandidate(detection=detection, score=score)

        start = end

    return best

def detect_read_options(
    path: Path,
    delimiter_label: str,
    encoding_label: str,
    fallback_skip_rows: int,
    fallback_has_header: bool,
) -> ReadDetection:
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xls"}:
            engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
            preview = pd.read_excel(path, header=None, nrows=_DETECTION_ROWS, engine=engine)
            profiles = [_excel_row_profile(index, row) for index, (_, row) in enumerate(preview.iterrows())]
            encoding_label = _EXCEL_ENCODING_LABEL
            candidate = _detect_from_profiles(
                profiles, delimiter_label=delimiter_label, encoding_label=encoding_label, allow_partial_header=True,
            )
            if candidate is not None:
                return candidate.detection
        else:
            encoding = detect_encoding(path, encoding_label)
            with path.open("r", encoding=encoding, errors="replace") as handle:
                lines = [line.rstrip("\r\n") for line in islice(handle, _DETECTION_ROWS)]

            candidates: list[_DetectionCandidate] = []
            for label, delimiter in _DELIMITERS.items():
                if delimiter_label != "自动" and label != delimiter_label:
                    continue
                if delimiter_label == "自动" and delimiter != r"\s+" and not any(delimiter in line for line in lines):
                    continue
                profiles = [_text_row_profile(index, line, delimiter) for index, line in enumerate(lines)]
                candidate = _detect_from_profiles(
                    profiles, delimiter_label=label, encoding_label=encoding, allow_wide_header=delimiter == r"\s+",
                )
                if candidate is not None:
                    candidates.append(candidate)
            if candidates:
                return max(candidates, key=lambda item: item.score).detection
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
            # A UTF-8 character split at the sample boundary can need up to three more bytes.
            lookahead = handle.read(3)
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if not raw or raw.isascii():
            return "utf-8"
        for encoding in ("utf-8", "gbk"):
            try:
                decoder = codecs.getincrementaldecoder(encoding)()
                text = decoder.decode(raw, final=not lookahead)
                if decoder.getstate()[0]:
                    text += decoder.decode(lookahead, final=len(lookahead) < 3)
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
