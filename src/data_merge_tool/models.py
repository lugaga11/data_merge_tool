from __future__ import annotations

from typing import Any, Optional, cast

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex
from PySide6.QtWidgets import QWidget

from .constants import ALIGN_LEFT_CENTER, DISPLAY_ROLE, HORIZONTAL, TEXT_ALIGNMENT_ROLE


class DataFrameModel(QAbstractTableModel):
    """A small Qt table model for pandas DataFrame previews."""

    def __init__(self, df: Optional[pd.DataFrame] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._df = df.copy() if df is not None else pd.DataFrame()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = DISPLAY_ROLE):
        if not index.isValid():
            return None
        if role == DISPLAY_ROLE:
            value = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(cast(Any, value)) else str(value)
        if role == TEXT_ALIGNMENT_ROLE:
            return ALIGN_LEFT_CENTER
        return None

    def headerData(self, section: int, orientation, role: int = DISPLAY_ROLE):
        if role != DISPLAY_ROLE:
            return None
        if orientation == HORIZONTAL:
            return f"{section + 1}\n{self._df.columns[section]}"
        return str(section + 1)

    def set_dataframe(self, df: Optional[pd.DataFrame]) -> None:
        self.beginResetModel()
        self._df = df.copy() if df is not None else pd.DataFrame()
        self.endResetModel()

