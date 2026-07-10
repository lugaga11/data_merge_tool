from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..constants import (
    CHECKED,
    COPY_ACTION,
    DRAG_DROP,
    MOVE_ACTION,
    SELECTION_EXTENDED,
    SUPPORTED_FILES,
    UNCHECKED,
    USER_ROLE,
)
from ..data_reading.readers import is_supported_data_file, natural_sort_key
from ..merge.labels import build_source_labels, source_label_sort_key
from .controls import make_button


class DropFileList(QListWidget):
    """List widget that reports external paths and keeps internal move semantics."""

    paths_dropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(SELECTION_EXTENDED)
        self.setDragDropMode(DRAG_DROP)
        self.setDefaultDropAction(MOVE_ACTION)
        self.setAlternatingRowColors(True)

    @staticmethod
    def _accept_external_file_drag(event: QDragEnterEvent | QDragMoveEvent | QDropEvent) -> bool:
        if not event.mimeData().hasUrls():
            return False
        event.setDropAction(COPY_ACTION)
        event.accept()
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._accept_external_file_drag(event):
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._accept_external_file_drag(event):
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.toLocalFile()]
            self.paths_dropped.emit(paths)
            self._accept_external_file_drag(event)
            return
        super().dropEvent(event)


class FileQueuePanel(QWidget):
    """Own the visible file queue without doing recursive directory scans."""

    paths_dropped = Signal(list)
    queue_changed = Signal()
    preview_reference_changed = Signal()
    status_message = Signal(str, int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(310)
        self.setMaximumWidth(380)
        self._updating = False
        self._build_ui()
        self._connect_signals()
        self._update_file_count()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        file_header = QHBoxLayout()
        file_header.addWidget(QLabel("文件队列"))
        file_header.addStretch(1)
        self.file_count_label = QLabel("0 个文件")
        self.file_count_label.setObjectName("Muted")
        file_header.addWidget(self.file_count_label)
        layout.addLayout(file_header)

        self.file_list = DropFileList()
        self.file_list.setObjectName("FileQueue")
        self.file_list.setMinimumHeight(120)
        self.file_list.setToolTip("可拖放文件，也可拖动列表项调整合并顺序。")
        layout.addWidget(self.file_list, 1)

        add_button = make_button("添加文件", self.choose_files, "primary")
        select_button = make_button("全选", self.select_all)
        clear_checks_button = make_button("取消全选", self.clear_checks)
        row1 = QHBoxLayout()
        row1.addWidget(add_button, 1)
        row1.addWidget(select_button, 1)
        row1.addWidget(clear_checks_button, 1)
        layout.addLayout(row1)

        delete_button = make_button("删除选中", self.delete_selected)
        sort_button = make_button("自然排序", self.sort_naturally)
        clear_button = make_button("清空", self.clear, "danger")
        row2 = QHBoxLayout()
        row2.addWidget(delete_button)
        row2.addWidget(sort_button)
        row2.addWidget(clear_button)
        layout.addLayout(row2)

        self.short_name_check = QCheckBox("只显示文件名")
        self.short_name_check.setChecked(True)
        display_row = QHBoxLayout()
        display_row.addWidget(self.short_name_check)
        display_row.addStretch(1)
        layout.addLayout(display_row)

    def _connect_signals(self) -> None:
        self.file_list.paths_dropped.connect(self.paths_dropped.emit)
        self.file_list.itemDoubleClicked.connect(self._open_source_file)
        self.file_list.itemSelectionChanged.connect(self.preview_reference_changed.emit)
        self.file_list.itemChanged.connect(self._on_item_changed)
        self.file_list.model().rowsInserted.connect(self._on_model_changed)
        self.file_list.model().rowsRemoved.connect(self._on_model_changed)
        self.file_list.model().rowsMoved.connect(self._on_model_changed)
        self.short_name_check.stateChanged.connect(self._update_filename_display)

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择数据文件", "", SUPPORTED_FILES)
        self.add_paths(paths)

    def all_paths(self) -> list[str]:
        return [str(self.file_list.item(row).data(USER_ROLE)) for row in range(self.file_list.count())]

    def checked_paths(self) -> list[str]:
        return [
            str(self.file_list.item(row).data(USER_ROLE))
            for row in range(self.file_list.count())
            if self.file_list.item(row).checkState() == CHECKED
        ]

    def preview_path(self) -> Optional[Path]:
        item = self._preview_reference_item()
        return None if item is None else Path(str(item.data(USER_ROLE)))

    def add_paths(self, paths: Sequence[str], sort_input: bool = True) -> None:
        existing = set(self.all_paths())
        added = 0
        skipped = 0
        ordered_paths = sorted(paths, key=natural_sort_key) if sort_input else list(paths)

        self._updating = True
        previous_blocked = self.file_list.blockSignals(True)
        try:
            for raw_path in ordered_paths:
                path = Path(raw_path)
                if not is_supported_data_file(path) or str(path) in existing:
                    skipped += 1
                    continue
                self.file_list.addItem(self._make_file_item(path))
                existing.add(str(path))
                added += 1
        finally:
            self.file_list.blockSignals(previous_blocked)
            self._updating = False

        if added:
            self.status_message.emit(f"已添加 {added} 个文件。", 4000)
            self._finish_queue_change()
        elif skipped:
            self.status_message.emit("没有新增文件，可能是重复项或非文件路径。", 5000)

    def set_all_checked(self, checked: bool) -> None:
        if self.file_list.count() == 0:
            return
        self._updating = True
        previous_blocked = self.file_list.blockSignals(True)
        try:
            state = CHECKED if checked else UNCHECKED
            for row in range(self.file_list.count()):
                self.file_list.item(row).setCheckState(state)
        finally:
            self.file_list.blockSignals(previous_blocked)
            self._updating = False
        action = "选中" if checked else "取消选中"
        self.status_message.emit(f"已{action} {self.file_list.count()} 个文件。", 3000)
        self.queue_changed.emit()

    def select_all(self) -> None:
        self.set_all_checked(True)

    def clear_checks(self) -> None:
        self.set_all_checked(False)

    def sort_naturally(self) -> None:
        paths = self.all_paths()
        if len(paths) < 2:
            return
        checked_paths = set(self.checked_paths())
        source_labels = build_source_labels(paths, "auto")
        sorted_paths = sorted(
            paths,
            key=lambda path: (
                source_label_sort_key(source_labels.get(path, Path(path).stem)),
                natural_sort_key(Path(path).name),
            ),
        )
        descending = paths == sorted_paths
        ordered_paths = list(reversed(sorted_paths)) if descending else sorted_paths

        self._updating = True
        previous_blocked = self.file_list.blockSignals(True)
        try:
            self.file_list.clear()
            for raw_path in ordered_paths:
                self.file_list.addItem(self._make_file_item(Path(raw_path), raw_path in checked_paths))
        finally:
            self.file_list.blockSignals(previous_blocked)
            self._updating = False

        direction = "倒序" if descending else "正序"
        self.status_message.emit(f"文件队列已按自动差异标签{direction}排序。", 4000)
        self._finish_queue_change()

    def delete_selected(self) -> None:
        selected_rows = sorted(
            (self.file_list.row(item) for item in self.file_list.selectedItems()),
            reverse=True,
        )
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择要删除的文件。")
            return

        self._updating = True
        try:
            for row in selected_rows:
                self.file_list.takeItem(row)
        finally:
            self._updating = False
        self.status_message.emit(f"已删除 {len(selected_rows)} 个文件。", 4000)
        self._finish_queue_change()

    def clear(self) -> None:
        if self.file_list.count() == 0:
            return
        self._updating = True
        try:
            self.file_list.clear()
        finally:
            self._updating = False
        self.status_message.emit("文件队列已清空。", 4000)
        self._finish_queue_change()

    def _file_item_text(self, path: Path, row: int) -> str:
        name = path.name if self.short_name_check.isChecked() else str(path)
        return f"{row + 1}. {name}"

    def _make_file_item(self, path: Path, checked: bool = True) -> QListWidgetItem:
        item = QListWidgetItem(self._file_item_text(path, self.file_list.count()))
        item.setToolTip(str(path))
        item.setData(USER_ROLE, str(path))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(CHECKED if checked else UNCHECKED)
        return item

    def _preview_reference_item(self) -> Optional[QListWidgetItem]:
        selected = sorted(self.file_list.selectedItems(), key=lambda item: self.file_list.row(item))
        if selected:
            return selected[0]
        if self.file_list.currentItem() is not None:
            return self.file_list.currentItem()
        if self.file_list.count() > 0:
            return self.file_list.item(0)
        return None

    def _open_source_file(self, item: QListWidgetItem) -> None:
        path = Path(str(item.data(USER_ROLE)))
        if not path.exists():
            QMessageBox.warning(self, "无法打开", f"文件不存在：\n{path}")
            return
        try:
            os.startfile(path)
        except OSError as exc:
            QMessageBox.critical(self, "无法打开", f"{path}\n\n{exc}")

    def _update_filename_display(self, _state: int = 0) -> None:
        previous_blocked = self.file_list.blockSignals(True)
        try:
            for row in range(self.file_list.count()):
                item = self.file_list.item(row)
                path = Path(str(item.data(USER_ROLE)))
                item.setText(self._file_item_text(path, row))
                item.setToolTip(str(path))
        finally:
            self.file_list.blockSignals(previous_blocked)

    def _update_file_count(self) -> None:
        self.file_count_label.setText(f"{self.file_list.count()} 个文件")

    def _on_model_changed(self, *_args) -> None:
        if self._updating:
            return
        self._finish_queue_change()

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        if not self._updating:
            self.queue_changed.emit()

    def _finish_queue_change(self) -> None:
        self._update_file_count()
        self._update_filename_display()
        self.queue_changed.emit()
        self.preview_reference_changed.emit()
