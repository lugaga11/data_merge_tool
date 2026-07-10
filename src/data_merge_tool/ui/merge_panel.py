from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..constants import CHECKED, SELECTION_NONE, UNCHECKED, USER_ROLE
from ..data_types import MergeOptions, ReadOptions
from .controls import NoWheelComboBox, make_button


class MergePanel(QWidget):
    """Own X/Y selection and merge parameters without reading source files."""

    options_changed = Signal()
    preview_requested = Signal()
    copy_requested = Signal()
    export_requested = Signal()
    import_origin_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("MergePanel")
        self.setMinimumWidth(330)
        self.setMaximumWidth(460)
        self._updating_columns = False
        self._column_source_signature: Optional[tuple[str, tuple[str, ...]]] = None
        self._build_ui()
        self._connect_signals()
        self._sync_x_controls()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        settings_group = QGroupBox()
        layout = QGridLayout(settings_group)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(5)

        self.scope_box = NoWheelComboBox()
        self.scope_box.addItems(["全部文件", "仅选中文件"])
        self.scope_box.setCurrentIndex(1)

        self.keep_x_check = QCheckBox("保留单个 X 列")
        self.keep_x_check.setChecked(True)

        self.x_column_box = NoWheelComboBox()

        self.y_column_list = QListWidget()
        self.y_column_list.setObjectName("YColumnList")
        self.y_column_list.setMinimumHeight(240)
        self.y_column_list.setSelectionMode(SELECTION_NONE)
        self.y_column_list.setAlternatingRowColors(True)

        self.validate_x_check = QCheckBox("校验所有文件 X 一致")
        self.validate_x_check.setChecked(True)

        self.label_mode_box = NoWheelComboBox()
        self.label_mode_box.addItem("自动差异", "auto")
        self.label_mode_box.addItem("完整文件名", "full")
        self.label_mode_box.setToolTip("自动差异会提取文件名中不同的片段；完整文件名会直接使用整个文件名。")

        layout.addWidget(QLabel("合并范围"), 0, 0)
        layout.addWidget(self.scope_box, 0, 1)
        layout.addWidget(self.keep_x_check, 1, 0)
        layout.addWidget(self.validate_x_check, 1, 1)
        layout.addWidget(QLabel("X 列"), 2, 0)
        layout.addWidget(self.x_column_box, 2, 1)
        layout.addWidget(self.y_column_list, 3, 0, 1, 2)

        y_button_row = QHBoxLayout()
        y_button_row.setSpacing(8)
        y_button_row.addWidget(make_button("全选 Y", self.select_all_y), 1)
        y_button_row.addWidget(make_button("清空 Y", self.clear_y), 1)
        layout.addLayout(y_button_row, 4, 0, 1, 2)
        layout.addWidget(QLabel("文件标签"), 5, 0)
        layout.addWidget(self.label_mode_box, 5, 1)
        root_layout.addWidget(settings_group, 1)

        action_frame = QFrame()
        action_frame.setObjectName("ActionFrame")
        action_layout = QVBoxLayout(action_frame)
        action_layout.setContentsMargins(10, 10, 10, 10)
        action_layout.setSpacing(6)

        self.preview_button = make_button("预览合并结果", self.preview_requested.emit, "primary")
        action_layout.addWidget(self.preview_button)

        action_row = QHBoxLayout()
        self.copy_button = make_button("复制到剪贴板", self.copy_requested.emit)
        self.export_button = make_button("导出文件", self.export_requested.emit, "primary")
        self.origin_button = make_button("导入 Origin", self.import_origin_requested.emit, "primary")
        action_row.addWidget(self.copy_button)
        action_row.addWidget(self.export_button)
        action_row.addWidget(self.origin_button)
        action_layout.addLayout(action_row)
        root_layout.addWidget(action_frame)

    def _connect_signals(self) -> None:
        self.scope_box.currentIndexChanged.connect(self._emit_options_changed)
        self.keep_x_check.stateChanged.connect(self._on_keep_x_changed)
        self.validate_x_check.stateChanged.connect(self._emit_options_changed)
        self.label_mode_box.currentIndexChanged.connect(self._emit_options_changed)
        self.x_column_box.currentIndexChanged.connect(self._on_x_column_changed)
        self.y_column_list.itemChanged.connect(self._on_y_column_changed)

    def set_columns(self, source: str | Path, columns: Sequence[object]) -> None:
        signature = (str(source), tuple(str(column) for column in columns))
        if signature == self._column_source_signature:
            return

        previous_x = int(self.x_column_box.currentData()) if self.x_column_box.count() else 0
        previous_y = set(self.selected_y_columns())
        had_previous_columns = self.y_column_list.count() > 0

        self._updating_columns = True
        try:
            self.x_column_box.clear()
            self.y_column_list.clear()
            for index, column in enumerate(columns):
                label = f"{index + 1}. {column}"
                self.x_column_box.addItem(label, index)

                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(USER_ROLE, index)
                checked_by_default = had_previous_columns and index in previous_y
                item.setCheckState(CHECKED if checked_by_default else UNCHECKED)
                self.y_column_list.addItem(item)

            x_index = previous_x if 0 <= previous_x < self.x_column_box.count() else 0
            self.x_column_box.setCurrentIndex(x_index)
            self._column_source_signature = signature
        finally:
            self._updating_columns = False

        self._sync_current_x_check_state()
        self.options_changed.emit()

    def selected_y_columns(self) -> list[int]:
        selected: list[int] = []
        for row in range(self.y_column_list.count()):
            item = self.y_column_list.item(row)
            if item.checkState() == CHECKED:
                selected.append(int(item.data(USER_ROLE)))
        return selected

    def set_y_columns_checked(self, checked: bool) -> None:
        self._updating_columns = True
        try:
            state = CHECKED if checked else UNCHECKED
            for row in range(self.y_column_list.count()):
                self.y_column_list.item(row).setCheckState(state)
        finally:
            self._updating_columns = False
        self._sync_current_x_check_state()
        self.options_changed.emit()

    def select_all_y(self) -> None:
        self.set_y_columns_checked(True)

    def clear_y(self) -> None:
        self.set_y_columns_checked(False)

    def selected_only(self) -> bool:
        return self.scope_box.currentText() == "仅选中文件"

    def current_options(
        self,
        read_options: ReadOptions,
        show_errors: bool = False,
    ) -> Optional[MergeOptions]:
        if self.x_column_box.count() == 0:
            if show_errors:
                QMessageBox.information(self, "提示", "请先添加文件，列选择器会根据当前预览文件自动加载。")
            return None

        return MergeOptions(
            read=read_options,
            y_columns=self.selected_y_columns(),
            y_columns_auto=False,
            keep_single_x=self.keep_x_check.isChecked(),
            x_column=int(self.x_column_box.currentData()) + 1,
            validate_x=self.validate_x_check.isChecked(),
            label_mode=str(self.label_mode_box.currentData()),
        )

    def set_data_actions_enabled(self, enabled: bool) -> None:
        self.preview_button.setEnabled(enabled)
        self.copy_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def set_origin_action_enabled(self, enabled: bool) -> None:
        self.origin_button.setEnabled(enabled)

    def _on_y_column_changed(self, _item: QListWidgetItem) -> None:
        if not self._updating_columns:
            self.options_changed.emit()

    def _on_x_column_changed(self, *_args) -> None:
        if self._updating_columns or self.x_column_box.count() == 0:
            return
        self._sync_current_x_check_state()
        self.options_changed.emit()

    def _on_keep_x_changed(self, *_args) -> None:
        self._sync_x_controls()
        self.options_changed.emit()

    def _sync_x_controls(self) -> None:
        self.x_column_box.setEnabled(True)
        self.y_column_list.setEnabled(True)
        self.validate_x_check.setEnabled(self.keep_x_check.isChecked())
        self._sync_current_x_check_state()

    def _sync_current_x_check_state(self) -> None:
        if self.x_column_box.count() == 0:
            return
        x_index = int(self.x_column_box.currentData())
        if not 0 <= x_index < self.y_column_list.count():
            return

        self._updating_columns = True
        try:
            state = UNCHECKED if self.keep_x_check.isChecked() else CHECKED
            self.y_column_list.item(x_index).setCheckState(state)
        finally:
            self._updating_columns = False

    def _emit_options_changed(self, *_args) -> None:
        if not self._updating_columns:
            self.options_changed.emit()
