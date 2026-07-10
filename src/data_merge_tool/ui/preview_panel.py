from __future__ import annotations

from typing import Any, Optional, cast

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    ALIGN_CENTER,
    ALIGN_LEFT_CENTER,
    DISPLAY_ROLE,
    HEADER_INTERACTIVE,
    HORIZONTAL,
    NO_EDIT_TRIGGERS,
    SELECT_ROWS,
    TEXT_ALIGNMENT_ROLE,
    VERTICAL,
)


DEFAULT_INPUT_TITLE = "选中文件或第一个文件的全部数据"
DEFAULT_OUTPUT_TITLE = "合并结果未生成，点击左侧“预览合并结果”开始合并"


class DataFrameModel(QAbstractTableModel):
    """Read-only Qt model that keeps the supplied DataFrame reference."""

    def __init__(self, df: Optional[pd.DataFrame] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()

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
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()


class PreviewPanel(QWidget):
    """Display input and merged-output tables without doing data I/O."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        splitter = QSplitter(VERTICAL)
        splitter.setChildrenCollapsible(False)
        input_card, self.input_title, self.input_model = self._table_card(
            "输入预览",
            DEFAULT_INPUT_TITLE,
        )
        output_card, self.output_title, self.output_model = self._table_card(
            "合并结果预览",
            DEFAULT_OUTPUT_TITLE,
        )
        splitter.addWidget(input_card)
        splitter.addWidget(output_card)
        splitter.setSizes([360, 420])
        layout.addWidget(splitter)

    @staticmethod
    def _table_card(title: str, subtitle: str) -> tuple[QWidget, QLabel, DataFrameModel]:
        frame = QFrame()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("Muted")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)

        table = QTableView()
        table.setAlternatingRowColors(True)
        table.setEditTriggers(NO_EDIT_TRIGGERS)
        table.setSelectionBehavior(SELECT_ROWS)
        table.horizontalHeader().setSectionResizeMode(HEADER_INTERACTIVE)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setDefaultAlignment(ALIGN_CENTER)
        table.horizontalHeader().setMinimumHeight(38)
        table.verticalHeader().setDefaultSectionSize(26)
        model = DataFrameModel(parent=table)
        table.setModel(model)
        layout.addWidget(table, 1)
        return frame, subtitle_label, model

    def set_input(self, dataframe: pd.DataFrame, title: str) -> None:
        self.input_model.set_dataframe(dataframe)
        self.input_title.setText(title)

    def clear_input(self, title: str = DEFAULT_INPUT_TITLE) -> None:
        self.set_input(pd.DataFrame(), title)

    def set_output(self, dataframe: pd.DataFrame, title: str) -> None:
        self.output_model.set_dataframe(dataframe)
        self.output_title.setText(title)

    def reset_output(self, title: str = DEFAULT_OUTPUT_TITLE) -> None:
        self.set_output(pd.DataFrame(), title)
