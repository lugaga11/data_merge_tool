from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView


APP_TITLE = "数据合并工具"
APP_VERSION = "v2.2.2"
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
        base = Path(getattr(sys, "_MEIPASS"))
        candidates = [base / "assets" / name, base / name]
    else:
        package_root = Path(__file__).resolve().parent
        project_root = Path(__file__).resolve().parents[2]
        candidates = [
            package_root / "assets" / name,
            project_root / "assets" / name,
            Path(__file__).with_name(name),
        ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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

APP_STYLE = """
QMainWindow {
    background: #eef2f7;
}
QWidget#Sidebar, QWidget#MergePanel {
    background: #ffffff;
    border-right: 1px solid #d7dee8;
}
QLabel#AppTitle {
    color: #102033;
    font-size: 20px;
    font-weight: 700;
}
QLabel#Muted {
    color: #657386;
}
QLabel#SectionTitle {
    color: #172235;
    font-size: 15px;
    font-weight: 700;
}
QLabel#EmptyState {
    color: #657386;
    border: 1px dashed #b8c2d2;
    border-radius: 16px;
    background: #f8fafc;
    padding: 24px;
}
QGroupBox, QFrame#Card, QFrame#ActionFrame {
    border: 1px solid #dbe2ec;
    border-radius: 8px;
    background: #fbfcfe;
}
QGroupBox {
    margin-top: 0;
    padding-top: 0;
}
QGroupBox::title {
    height: 0;
    width: 0;
    padding: 0;
}
QListWidget, QTableView, QLineEdit, QComboBox {
    border: 1px solid #cfd8e6;
    border-radius: 8px;
    background: #ffffff;
    padding: 4px;
}
QListWidget:focus, QTableView:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #7fb0f1;
}
QComboBox {
    min-height: 24px;
    padding: 3px 6px 3px 8px;
}
QComboBox::drop-down {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid #cfd8e6;
    border-top-right-radius: 7px;
    border-bottom-right-radius: 7px;
    background: #e9eff7;
}
QComboBox::drop-down:hover {
    background: #dbeafe;
}
QComboBox::drop-down:pressed {
    background: #bfdbfe;
}
QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
}
QComboBox QAbstractItemView {
    border: 1px solid #cfd8e6;
    border-radius: 6px;
    background: #ffffff;
    outline: 0;
    padding: 4px;
    selection-background-color: #e8f1ff;
    selection-color: #172235;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 4px 8px;
}
QSpinBox, QDoubleSpinBox {
    border: 1px solid #cfd8e6;
    border-radius: 8px;
    background: #ffffff;
    min-height: 24px;
    padding: 3px 2px 3px 8px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid #cfd8e6;
    border-bottom: 1px solid #d8e1ec;
    border-top-right-radius: 7px;
    background: #e9eff7;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 26px;
    border-left: 1px solid #cfd8e6;
    border-bottom-right-radius: 7px;
    background: #e9eff7;
}
QSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover {
    background: #dbeafe;
}
QSpinBox::up-button:pressed,
QSpinBox::down-button:pressed,
QDoubleSpinBox::up-button:pressed,
QDoubleSpinBox::down-button:pressed {
    background: #bfdbfe;
}
QListWidget::item {
    padding: 5px 4px;
}
QListWidget::item:hover {
    background: #f0f6ff;
    color: #172235;
}
QListWidget#FileQueue {
    selection-background-color: #2f80ed;
    selection-color: #ffffff;
}
QListWidget#FileQueue::item:selected {
    background: #2f80ed;
    color: #ffffff;
}
QListWidget#FileQueue::item {
    padding: 2px 4px;
}
QListWidget#YColumnList::item:checked {
    background: #eef6ff;
    color: #17324d;
    font-weight: 700;
}
QListWidget#YColumnList::item:selected {
    background: transparent;
    color: #172235;
}
QListWidget#YColumnList::item:focus {
    outline: 0;
    border: 0;
}
QCheckBox::indicator,
QAbstractItemView::indicator,
QListWidget::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #8fa1b8;
    border-radius: 5px;
    background: #ffffff;
    image: none;
}
QCheckBox::indicator:hover,
QAbstractItemView::indicator:hover,
QListWidget::indicator:hover {
    border-color: #256fce;
    background: #f4f8ff;
}
QCheckBox::indicator:checked,
QAbstractItemView::indicator:checked,
QListWidget::indicator:checked {
    background: #2f80ed;
    border: 1px solid #1f6fd1;
    image: url("__CHECKMARK_ICON__");
}
QCheckBox::indicator:checked:hover,
QAbstractItemView::indicator:checked:hover,
QListWidget::indicator:checked:hover {
    background: #256fce;
}
QCheckBox::indicator:checked:disabled,
QAbstractItemView::indicator:checked:disabled,
QListWidget::indicator:checked:disabled {
    background: #9bb8e8;
    border-color: #8aa8d8;
}
QTableView {
    gridline-color: #e6ebf2;
    alternate-background-color: #f7f9fc;
    selection-background-color: #dbeafe;
    selection-color: #172235;
}
QHeaderView::section {
    background: #eef4fb;
    color: #243247;
    border: 0;
    border-right: 1px solid #d7e0ec;
    border-bottom: 1px solid #cfd8e6;
    padding: 5px 8px;
    font-weight: 700;
}
QHeaderView::section:hover {
    background: #e4effc;
}
QTableCornerButton::section {
    background: #eef4fb;
    border: 0;
    border-right: 1px solid #d7e0ec;
    border-bottom: 1px solid #cfd8e6;
}
QPushButton {
    border: 1px solid #c7d2e2;
    border-radius: 8px;
    padding: 7px 10px;
    background: #ffffff;
    color: #203047;
    font-weight: 600;
}
QPushButton:hover {
    background: #f0f5ff;
    border-color: #9bb8e8;
}
QPushButton:pressed {
    background: #dbeafe;
    padding-top: 8px;
    padding-bottom: 6px;
}
QPushButton[role="primary"] {
    color: #ffffff;
    border-color: #1f6fd1;
    background: #256fce;
}
QPushButton[role="primary"]:hover {
    background: #1e5fb2;
}
QPushButton[role="primary"]:pressed {
    background: #1d4f95;
}
QPushButton[role="danger"] {
    color: #8f1d2c;
    border-color: #f0b8c1;
    background: #fff5f7;
}
QPushButton[role="danger"]:hover {
    background: #ffe7ec;
    border-color: #e69aaa;
}
QPushButton:disabled {
    color: #94a3b8;
    border-color: #d8e0ea;
    background: #f3f6fa;
}
QTabWidget::pane {
    border: 0;
}
QTabBar::tab {
    background: #dfe6f1;
    color: #415168;
    padding: 10px 18px;
    margin-right: 4px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
QTabBar::tab:hover {
    background: #edf3fb;
    color: #243247;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #172235;
    font-weight: 700;
}
QScrollBar:vertical {
    background: transparent;
    width: 11px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #c2cfdf;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #9fb2ca;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 11px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #c2cfdf;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #9fb2ca;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    background: transparent;
}
"""
# fmt: on
