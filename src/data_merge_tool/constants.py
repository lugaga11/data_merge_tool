from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView

APP_TITLE = "数据合并工具"
TEXT_DATA_EXTENSIONS = {
    ".csv",
    ".txt",
    ".tsv",
    ".xy",
    ".xyd",
    ".dat",
    ".asc",
    ".prn",
    ".uxd",
    ".ras",
    ".raw",
}
EXCEL_DATA_EXTENSIONS = {".xls", ".xlsx"}
SUPPORTED_EXTENSIONS = TEXT_DATA_EXTENSIONS | EXCEL_DATA_EXTENSIONS
SUPPORTED_FILES = (
    "Data Files (*.csv *.txt *.tsv *.xy *.xyd *.dat *.asc *.prn *.uxd *.ras *.raw *.xls *.xlsx);;"
    "Text Data (*.csv *.txt *.tsv *.xy *.xyd *.dat *.asc *.prn *.uxd *.ras *.raw);;"
    "Excel (*.xls *.xlsx);;"
    "All Files (*)"
)
def resource_path(name: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / "resources" / name
    return Path(__file__).resolve().parent / "resources" / name


CHECKMARK_ICON = resource_path("ui_checkmark.svg").as_posix()

EXCEL_READER_DEPENDENCIES = {
    ".xlsx": ("openpyxl", "3.1", "openpyxl>=3.1", "Excel .xlsx"),
    ".xls": ("xlrd", "2.0.1", "xlrd>=2.0.1", "旧版 Excel .xls"),
}

DISPLAY_ROLE = Qt.ItemDataRole.DisplayRole
TEXT_ALIGNMENT_ROLE = Qt.ItemDataRole.TextAlignmentRole
HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical
COPY_ACTION = Qt.DropAction.CopyAction
MOVE_ACTION = Qt.DropAction.MoveAction
USER_ROLE = Qt.ItemDataRole.UserRole
ALIGN_LEFT_CENTER = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked
SELECTION_EXTENDED = QAbstractItemView.SelectionMode.ExtendedSelection
SELECTION_NONE = QAbstractItemView.SelectionMode.NoSelection
DRAG_DROP = QAbstractItemView.DragDropMode.DragDrop
NO_EDIT_TRIGGERS = QAbstractItemView.EditTrigger.NoEditTriggers
SELECT_ROWS = QAbstractItemView.SelectionBehavior.SelectRows
HEADER_INTERACTIVE = QHeaderView.ResizeMode.Interactive
