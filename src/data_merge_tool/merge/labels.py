from __future__ import annotations
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from ..data_types import MergeOptions


@dataclass(frozen=True)
class ColumnLabelInfo:
    source_label: str
    original_column_label: str
    output_name: str
    origin_long_name: str
    origin_comment: str

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
    used: set[str] = set()
    next_suffix: dict[str, int] = {}
    unique: List[str] = []
    for column in columns:
        base = str(column)
        candidate = base
        if candidate in used:
            suffix = next_suffix.get(base, 2)
            candidate = f"{base}_{suffix}"
            while candidate in used:
                suffix += 1
                candidate = f"{base}_{suffix}"
            next_suffix[base] = suffix + 1
        else:
            next_suffix.setdefault(base, 2)

        used.add(candidate)
        unique.append(candidate)
    return unique

def unique_preserving_order(values: Sequence[int]) -> List[int]:
    seen: set[int] = set()
    result: List[int] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
