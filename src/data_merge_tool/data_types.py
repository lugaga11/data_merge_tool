from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass(frozen=True)
class ReadOptions:
    skip_rows: int
    delimiter_label: str
    encoding_label: str
    has_header: bool
    skip_bad_lines: bool


@dataclass(frozen=True)
class ReadDetection:
    skip_rows: int
    delimiter_label: str
    encoding_label: str
    has_header: bool
    confident: bool
    message: str


@dataclass(frozen=True)
class MergeOptions:
    read: ReadOptions
    y_columns: List[int]
    y_columns_auto: bool
    keep_single_x: bool
    x_column: int
    validate_x: bool
    label_mode: str


@dataclass(frozen=True)
class OriginImportData:
    dataframe: pd.DataFrame
    axis_spec: str
    long_names: List[str]
    comments: List[str]
    workbook_label: str
