from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except Exception:
    FigureCanvas = None
    Figure = None
    MATPLOTLIB_AVAILABLE = False

from .constants import (
    ALIGN_CENTER,
    APP_STYLE,
    APP_TITLE,
    APP_VERSION,
    CHECKED,
    CHECKMARK_ICON,
    HEADER_INTERACTIVE,
    HORIZONTAL,
    NO_EDIT_TRIGGERS,
    SELECT_ROWS,
    SELECTION_NONE,
    SUPPORTED_FILES,
    UNCHECKED,
    USER_ROLE,
    VERTICAL,
)
from .data_io import (
    build_origin_import_table,
    build_source_labels,
    detect_read_options,
    is_supported_data_file,
    natural_sort_key,
    read_table,
    source_label_sort_key,
)
from .data_types import MergeOptions, OriginImportData, ReadDetection, ReadOptions
from .errors import UserVisibleError
from .models import DataFrameModel
from .origin_client import OriginWorkerClient
from .origin_panel import PANEL_STYLE as ORIGIN_PANEL_STYLE
from .origin_panel import OriginPanelWidget
from .widgets import (
    DataTask,
    DropFileList,
    NoWheelComboBox,
    NoWheelSpinBox,
    make_button,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.last_merged: Optional[pd.DataFrame] = None
        self.last_origin_data: Optional[OriginImportData] = None
        self.output_dirty = True
        self._updating_file_list = False
        self._updating_column_selector = False
        self._updating_read_controls = False
        self._column_source_signature: Optional[tuple[str, tuple[str, ...]]] = None
        self._read_detection_signature: Optional[tuple[str, str, str, int, bool]] = None
        self._read_detection: Optional[ReadDetection] = None
        self._active_tasks: List[DataTask] = []
        self._data_generation = 0
        self.origin_worker = OriginWorkerClient()
        self.originPanel: OriginPanelWidget | None = None

        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setStatusBar(QStatusBar(self))
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self.update_file_count()
        self.refresh_input_preview()
        self.mark_output_dirty()

        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self.copy_to_clipboard)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_mode_bar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_data_merge_view())
        self.originPanel = OriginPanelWidget(self.origin_worker)
        self.stack.addWidget(self.originPanel)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def _build_mode_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("ModeBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        title = QLabel(f"{APP_TITLE} {APP_VERSION}")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        layout.addStretch(1)
        self.modeButton = make_button("切换到 Origin 绘图面板", self.toggle_main_view, "primary", width=190)
        layout.addWidget(self.modeButton)
        return bar

    def _build_data_merge_view(self) -> QWidget:
        splitter = QSplitter(HORIZONTAL)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_merge_panel())
        splitter.addWidget(self._build_workspace())
        splitter.setSizes([340, 360, 720])
        return splitter

    def toggle_main_view(self) -> None:
        self.stack.setCurrentIndex(1 if self.stack.currentIndex() == 0 else 0)
        self.update_mode_button()

    def update_mode_button(self) -> None:
        if self.stack.currentIndex() == 0:
            self.modeButton.setText("切换到 Origin 绘图面板")
            self.statusBar().showMessage("当前面板：数据合并。", 2500)
        else:
            self.modeButton.setText("返回数据合并")
            self.statusBar().showMessage("当前面板：Origin 绘图面板。", 2500)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(310)
        sidebar.setMaximumWidth(380)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        file_header = QHBoxLayout()
        file_header.addWidget(QLabel("文件队列"))
        file_header.addStretch(1)
        self.fileCountLabel = QLabel("0 个文件")
        self.fileCountLabel.setObjectName("Muted")
        file_header.addWidget(self.fileCountLabel)
        layout.addLayout(file_header)

        self.fileList = DropFileList()
        self.fileList.setObjectName("FileQueue")
        self.fileList.setMinimumHeight(120)
        self.fileList.setToolTip("可拖放文件，也可拖动列表项调整合并顺序。")
        layout.addWidget(self.fileList, 1)

        row1 = QHBoxLayout()
        row1.addWidget(make_button("添加文件", self.choose_files, "primary"), 1)
        row1.addWidget(make_button("全选", self.select_all_files), 1)
        row1.addWidget(make_button("取消全选", self.clear_file_checks), 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(make_button("删除选中", self.delete_selected_files))
        row2.addWidget(make_button("自然排序", self.sort_files_naturally))
        row2.addWidget(make_button("清空", self.clear_files, "danger"))
        layout.addLayout(row2)

        row4 = QHBoxLayout()
        self.shortNameCheck = QCheckBox("只显示文件名")
        self.shortNameCheck.setChecked(True)
        row4.addWidget(self.shortNameCheck)
        row4.addStretch(1)
        layout.addLayout(row4)
        layout.addWidget(self._build_read_group())

        return sidebar

    def _build_merge_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("MergePanel")
        panel.setMinimumWidth(330)
        panel.setMaximumWidth(460)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(self._build_merge_group(), 1)
        layout.addWidget(self._build_action_frame())
        return panel

    def _build_read_group(self) -> QGroupBox:
        group = QGroupBox()
        grid = QGridLayout(group)
        grid.setContentsMargins(10, 10, 10, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)

        self.skipSpin = NoWheelSpinBox()
        self.skipSpin.setRange(0, 9999)
        self.skipSpin.setToolTip("手动模式下从文件开头跳过的行数；自动模式下显示识别结果。")

        self.skipModeBox = NoWheelComboBox()
        self.skipModeBox.addItems(["自动", "手动"])
        self.skipModeBox.setToolTip("自动按当前预览文件识别数据起点；手动使用右侧数值。")

        self.delimBox = NoWheelComboBox()
        self.delimBox.addItems(["自动", "逗号 ,", "Tab", "空格/连续空白", "分号 ;"])

        self.delimModeBox = NoWheelComboBox()
        self.delimModeBox.addItems(["自动", "手动"])
        self.delimModeBox.setToolTip("自动识别分隔符；手动使用右侧选择。")

        self.encBox = NoWheelComboBox()
        self.encBox.addItems(["自动", "utf-8", "utf-8-sig", "ANSI/系统默认", "gbk", "cp950", "latin1"])

        self.encModeBox = NoWheelComboBox()
        self.encModeBox.addItems(["自动", "手动"])
        self.encModeBox.setToolTip("自动识别编码；手动使用右侧选择。")

        self.headerModeBox = NoWheelComboBox()
        self.headerModeBox.addItems(["自动", "手动"])
        self.headerModeBox.setToolTip("自动识别表头；不可靠时退回手动勾选状态。")

        for mode_box in (self.headerModeBox, self.skipModeBox, self.delimModeBox, self.encModeBox):
            mode_box.setMinimumWidth(93)

        self.headerCheck = QCheckBox("第一行为表头")
        self.headerCheck.setChecked(True)

        grid.addWidget(QLabel("表头"), 0, 0)
        grid.addWidget(self.headerModeBox, 0, 1)
        grid.addWidget(self.headerCheck, 0, 2)
        grid.addWidget(QLabel("跳过行"), 1, 0)
        grid.addWidget(self.skipModeBox, 1, 1)
        grid.addWidget(self.skipSpin, 1, 2)
        grid.addWidget(QLabel("分隔符"), 2, 0)
        grid.addWidget(self.delimModeBox, 2, 1)
        grid.addWidget(self.delimBox, 2, 2)
        grid.addWidget(QLabel("编码"), 3, 0)
        grid.addWidget(self.encModeBox, 3, 1)
        grid.addWidget(self.encBox, 3, 2)
        self.update_auto_read_control_state()
        return group

    def _build_merge_group(self) -> QGroupBox:
        group = QGroupBox()
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(5)

        self.scopeBox = NoWheelComboBox()
        self.scopeBox.addItems(["全部文件", "仅选中文件"])
        self.scopeBox.setCurrentIndex(1)

        self.keepXCheck = QCheckBox("保留单个 X 列")
        self.keepXCheck.setChecked(True)

        self.xColumnBox = NoWheelComboBox()

        self.yColumnList = QListWidget()
        self.yColumnList.setObjectName("YColumnList")
        self.yColumnList.setMinimumHeight(240)
        self.yColumnList.setSelectionMode(SELECTION_NONE)
        self.yColumnList.setAlternatingRowColors(True)

        self.validateXCheck = QCheckBox("校验所有文件 X 一致")
        self.validateXCheck.setChecked(True)

        self.skipBadCheck = QCheckBox("跳过异常行")
        self.skipBadCheck.setChecked(True)
        self.skipBadCheck.setToolTip("读取文本数据时跳过数据区内没有任何数值的尾标、空行或纯文本行。")

        self.labelModeBox = NoWheelComboBox()
        self.labelModeBox.addItem("自动差异", "auto")
        self.labelModeBox.addItem("完整文件名", "full")
        self.labelModeBox.setToolTip("自动差异会提取文件名中不同的片段；完整文件名会直接使用整个文件名。")

        layout.addWidget(QLabel("合并范围"), 0, 0)
        layout.addWidget(self.scopeBox, 0, 1)
        layout.addWidget(self.keepXCheck, 1, 0)
        layout.addWidget(self.validateXCheck, 1, 1)
        layout.addWidget(QLabel("X 列"), 2, 0)
        layout.addWidget(self.xColumnBox, 2, 1)
        layout.addWidget(self.yColumnList, 3, 0, 1, 2)
        y_button_row = QHBoxLayout()
        y_button_row.setSpacing(8)
        y_button_row.addWidget(make_button("全选 Y", self.select_all_y_columns), 1)
        y_button_row.addWidget(make_button("清空 Y", self.clear_y_columns), 1)
        layout.addLayout(y_button_row, 4, 0, 1, 2)
        layout.addWidget(QLabel("文件标签"), 5, 0)
        layout.addWidget(self.labelModeBox, 5, 1)
        layout.addWidget(self.skipBadCheck, 6, 0, 1, 2)

        return group

    def _build_action_frame(self) -> QFrame:
        action_frame = QFrame()
        action_frame.setObjectName("ActionFrame")
        action_layout = QVBoxLayout(action_frame)
        action_layout.setContentsMargins(10, 10, 10, 10)
        action_layout.setSpacing(6)
        self.previewButton = make_button("预览合并结果", self.preview_merge, "primary")
        action_layout.addWidget(self.previewButton)
        action_row = QHBoxLayout()
        self.copyButton = make_button("复制到剪贴板", self.copy_to_clipboard)
        self.exportButton = make_button("导出文件", self.export_merged, "primary")
        self.originButton = make_button("导入 Origin", self.import_to_origin, "primary")
        action_row.addWidget(self.copyButton)
        action_row.addWidget(self.exportButton)
        action_row.addWidget(self.originButton)
        action_layout.addLayout(action_row)
        return action_frame

    def _build_workspace(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_preview_tab(), "数据预览")
        tabs.addTab(self._build_plot_tab(), "轻量绘图")
        return tabs

    def _build_preview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        preview_splitter = QSplitter(VERTICAL)
        preview_splitter.setChildrenCollapsible(False)
        preview_splitter.addWidget(self._table_card("输入预览", "选中文件或第一个文件的全部数据", "input"))
        preview_splitter.addWidget(self._table_card("合并结果预览", "当前规则生成的完整结果", "output"))
        preview_splitter.setSizes([360, 420])
        layout.addWidget(preview_splitter)
        return page

    def _build_plot_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        note = QLabel("绘图用于快速检查曲线趋势；保留单个 X 时共用 X，不保留时需勾选 X 列并按每个文件自己的 X 列绘制。")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        controls = QHBoxLayout()
        self.plotLogXCheck = QCheckBox("Log X")
        self.plotLogYCheck = QCheckBox("Log Y")
        self.plotLegendCheck = QCheckBox("显示图例")
        self.plotLegendCheck.setChecked(True)
        controls.addWidget(self.plotLogXCheck)
        controls.addWidget(self.plotLogYCheck)
        controls.addWidget(self.plotLegendCheck)
        controls.addStretch(1)
        controls.addWidget(make_button("绘制当前结果", self.plot_data, "primary"))
        layout.addLayout(controls)

        if MATPLOTLIB_AVAILABLE and Figure is not None and FigureCanvas is not None:
            self.figure = Figure(figsize=(7, 5), tight_layout=True)
            self.canvas = FigureCanvas(self.figure)
            self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self.canvas, 1)
        else:
            missing = QLabel("当前环境未安装 matplotlib，绘图预览不可用；数据合并、复制和导出仍可正常使用。")
            missing.setObjectName("EmptyState")
            missing.setAlignment(ALIGN_CENTER)
            layout.addWidget(missing, 1)
            self.figure = None
            self.canvas = None
        return page

    def _table_card(self, title: str, subtitle: str, kind: str) -> QWidget:
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
        layout.addWidget(table, 1)

        if kind == "input":
            self.inputTitle = subtitle_label
            self.inputModel = DataFrameModel()
            self.inputTable = table
            table.setModel(self.inputModel)
        else:
            self.outputTitle = subtitle_label
            self.outputModel = DataFrameModel()
            self.outputTable = table
            table.setModel(self.outputModel)
        return frame

    def _connect_signals(self) -> None:
        self.fileList.files_dropped.connect(self.add_paths)
        self.fileList.itemDoubleClicked.connect(self.open_source_file)
        self.fileList.itemSelectionChanged.connect(self.refresh_input_preview)
        self.fileList.itemChanged.connect(self.on_file_item_changed)
        self.fileList.model().rowsInserted.connect(lambda *args: self.on_files_changed())
        self.fileList.model().rowsRemoved.connect(lambda *args: self.on_files_changed())
        self.fileList.model().rowsMoved.connect(lambda *args: self.on_files_changed())

        self.shortNameCheck.stateChanged.connect(self.update_filename_display)
        self.shortNameCheck.stateChanged.connect(self.refresh_input_preview)

        for widget in [
            self.skipModeBox,
            self.skipSpin,
            self.headerModeBox,
            self.headerCheck,
            self.delimModeBox,
            self.delimBox,
            self.encModeBox,
            self.encBox,
            self.skipBadCheck,
        ]:
            signal = (
                widget.currentIndexChanged
                if isinstance(widget, QComboBox)
                else widget.valueChanged
                if isinstance(widget, QSpinBox)
                else widget.stateChanged
            )
            signal.connect(self.on_read_settings_changed)

        for widget in [
            self.scopeBox,
            self.keepXCheck,
            self.validateXCheck,
            self.labelModeBox,
        ]:
            signal = (
                widget.currentIndexChanged
                if isinstance(widget, QComboBox)
                else widget.valueChanged
                if isinstance(widget, QSpinBox)
                else widget.stateChanged
            )
            signal.connect(self.on_settings_changed)

        self.xColumnBox.currentIndexChanged.connect(self.on_x_column_changed)
        self.yColumnList.itemChanged.connect(self.on_y_column_changed)
        self.keepXCheck.stateChanged.connect(self.toggle_x_controls)
        self.toggle_x_controls()

    def _apply_style(self) -> None:
        merged_style = APP_STYLE + "\n" + ORIGIN_PANEL_STYLE
        self.setStyleSheet(merged_style.replace("__CHECKMARK_ICON__", CHECKMARK_ICON))

    def file_item_text(self, path: Path, row: int) -> str:
        name = path.name if self.shortNameCheck.isChecked() else str(path)
        return f"{row + 1}. {name}"

    def make_file_item(self, path: Path, checked: bool = True) -> QListWidgetItem:
        item = QListWidgetItem(self.file_item_text(path, self.fileList.count()))
        item.setToolTip(str(path))
        item.setData(USER_ROLE, str(path))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(CHECKED if checked else UNCHECKED)
        return item

    def all_paths(self) -> List[str]:
        return [self.fileList.item(i).data(USER_ROLE) for i in range(self.fileList.count())]

    def selected_paths(self) -> List[str]:
        checked_items = [
            self.fileList.item(row)
            for row in range(self.fileList.count())
            if self.fileList.item(row).checkState() == CHECKED
        ]
        return [item.data(USER_ROLE) for item in checked_items]

    def set_file_checks(self, checked: bool) -> None:
        if self.fileList.count() == 0:
            return
        self._updating_file_list = True
        previous_blocked = self.fileList.blockSignals(True)
        try:
            state = CHECKED if checked else UNCHECKED
            for row in range(self.fileList.count()):
                self.fileList.item(row).setCheckState(state)
        finally:
            self.fileList.blockSignals(previous_blocked)
            self._updating_file_list = False
        action = "选中" if checked else "取消选中"
        self.statusBar().showMessage(f"已{action} {self.fileList.count()} 个文件。", 3000)
        self.mark_output_dirty()

    def select_all_files(self) -> None:
        self.set_file_checks(True)

    def clear_file_checks(self) -> None:
        self.set_file_checks(False)

    def paths_to_merge(self, show_errors: bool = False) -> List[str]:
        if self.scopeBox.currentText() == "仅选中文件":
            paths = self.selected_paths()
            if not paths and show_errors:
                QMessageBox.information(self, "提示", "当前合并范围是“仅选中文件”，请先勾选要合并的文件。")
            return paths
        return self.all_paths()

    def open_source_file(self, item: QListWidgetItem) -> None:
        path = Path(item.data(USER_ROLE))
        if not path.exists():
            QMessageBox.warning(self, "无法打开", f"文件不存在：\n{path}")
            return

        try:
            os.startfile(path)
        except OSError as exc:
            QMessageBox.critical(self, "无法打开", f"{path}\n\n{exc}")

    def selected_y_columns(self) -> List[int]:
        columns: List[int] = []
        for row in range(self.yColumnList.count()):
            item = self.yColumnList.item(row)
            if item.checkState() == CHECKED:
                columns.append(int(item.data(USER_ROLE)))
        return columns

    def set_y_columns_checked(self, checked: bool) -> None:
        self._updating_column_selector = True
        try:
            state = CHECKED if checked else UNCHECKED
            for row in range(self.yColumnList.count()):
                self.yColumnList.item(row).setCheckState(state)
        finally:
            self._updating_column_selector = False
        self.mark_output_dirty()

    def select_all_y_columns(self) -> None:
        self.set_y_columns_checked(True)

    def clear_y_columns(self) -> None:
        self.set_y_columns_checked(False)

    def on_y_column_changed(self, _item: QListWidgetItem) -> None:
        if not self._updating_column_selector:
            self.mark_output_dirty()

    def on_x_column_changed(self) -> None:
        if self._updating_column_selector or self.xColumnBox.count() == 0:
            return

        self.sync_current_x_column_check_state()
        self.mark_output_dirty()

    def sync_current_x_column_check_state(self) -> None:
        if self.xColumnBox.count() == 0:
            return
        x_index = int(self.xColumnBox.currentData())
        if not 0 <= x_index < self.yColumnList.count():
            return

        self._updating_column_selector = True
        try:
            state = UNCHECKED if self.keepXCheck.isChecked() else CHECKED
            self.yColumnList.item(x_index).setCheckState(state)
        finally:
            self._updating_column_selector = False

    def populate_column_selector(self, path: Path, df: pd.DataFrame) -> None:
        signature = (str(path), tuple(str(column) for column in df.columns))
        if signature == self._column_source_signature:
            return

        previous_x = int(self.xColumnBox.currentData()) if self.xColumnBox.count() else 0
        previous_y = set(self.selected_y_columns())
        had_previous_columns = self.yColumnList.count() > 0
        self._updating_column_selector = True
        try:
            self.xColumnBox.clear()
            self.yColumnList.clear()
            for index, column in enumerate(df.columns):
                label = f"{index + 1}. {column}"
                self.xColumnBox.addItem(label, index)

                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(USER_ROLE, index)
                checked_by_default = had_previous_columns and index in previous_y
                item.setCheckState(CHECKED if checked_by_default else UNCHECKED)
                self.yColumnList.addItem(item)

            x_index = previous_x if 0 <= previous_x < self.xColumnBox.count() else 0
            self.xColumnBox.setCurrentIndex(x_index)
            self._column_source_signature = signature
        finally:
            self._updating_column_selector = False
        self.sync_current_x_column_check_state()

    def preview_reference_item(self) -> Optional[QListWidgetItem]:
        selected = sorted(self.fileList.selectedItems(), key=lambda entry: self.fileList.row(entry))
        if selected:
            return selected[0]
        if self.fileList.currentItem() is not None:
            return self.fileList.currentItem()
        if self.fileList.count() > 0:
            return self.fileList.item(0)
        return None

    def preview_reference_path(self) -> Optional[Path]:
        item = self.preview_reference_item()
        if item is None:
            return None
        return Path(item.data(USER_ROLE))

    def update_auto_read_control_state(self) -> None:
        skip_manual = self.skipModeBox.currentText() == "手动"
        header_manual = self.headerModeBox.currentText() == "手动"
        delimiter_manual = self.delimModeBox.currentText() == "手动"
        encoding_manual = self.encModeBox.currentText() == "手动"
        self.skipSpin.setEnabled(skip_manual)
        self.headerCheck.setEnabled(header_manual)
        self.delimBox.setEnabled(delimiter_manual)
        self.encBox.setEnabled(encoding_manual)

    def add_or_select_combo_text(self, combo: QComboBox, text: str) -> None:
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index)

    def detection_delimiter_label(self) -> str:
        return "自动" if self.delimModeBox.currentText() == "自动" else self.delimBox.currentText()

    def detection_encoding_label(self) -> str:
        return "自动" if self.encModeBox.currentText() == "自动" else self.encBox.currentText()

    def current_auto_read_detection(self) -> ReadDetection:
        path = self.preview_reference_path()
        fallback = ReadDetection(
            skip_rows=self.skipSpin.value(),
            delimiter_label=self.delimBox.currentText(),
            encoding_label=self.encBox.currentText(),
            has_header=self.headerCheck.isChecked(),
            confident=False,
            message="未选择预览文件，继续使用手动读入设置。",
        )
        if path is None:
            return fallback

        signature = (
            str(path),
            self.detection_delimiter_label(),
            self.detection_encoding_label(),
            self.skipSpin.value(),
            self.headerCheck.isChecked(),
        )
        if self._read_detection_signature != signature or self._read_detection is None:
            self._read_detection = detect_read_options(
                path,
                self.detection_delimiter_label(),
                self.detection_encoding_label(),
                self.skipSpin.value(),
                self.headerCheck.isChecked(),
            )
            self._read_detection_signature = signature

        self.apply_auto_read_detection(self._read_detection)
        return self._read_detection

    def apply_auto_read_detection(self, detection: ReadDetection) -> None:
        self._updating_read_controls = True
        try:
            if self.skipModeBox.currentText() == "自动" and detection.confident:
                self.skipSpin.setValue(detection.skip_rows)
            if self.headerModeBox.currentText() == "自动" and detection.confident:
                self.headerCheck.setChecked(detection.has_header)
            if self.delimModeBox.currentText() == "自动" and detection.confident:
                self.add_or_select_combo_text(self.delimBox, detection.delimiter_label)
            if self.encModeBox.currentText() == "自动" and detection.encoding_label:
                self.add_or_select_combo_text(self.encBox, detection.encoding_label)
            self.update_auto_read_control_state()
        finally:
            self._updating_read_controls = False

    def current_read_options(self) -> ReadOptions:
        detection = self.current_auto_read_detection()
        use_auto_skip = self.skipModeBox.currentText() == "自动" and detection.confident
        use_auto_header = self.headerModeBox.currentText() == "自动" and detection.confident
        use_auto_delimiter = self.delimModeBox.currentText() == "自动" and detection.confident
        use_auto_encoding = self.encModeBox.currentText() == "自动"
        return ReadOptions(
            skip_rows=detection.skip_rows if use_auto_skip else self.skipSpin.value(),
            delimiter_label=detection.delimiter_label if use_auto_delimiter else self.delimBox.currentText(),
            encoding_label=detection.encoding_label if use_auto_encoding else self.encBox.currentText(),
            has_header=detection.has_header if use_auto_header else self.headerCheck.isChecked(),
            skip_bad_lines=self.skipBadCheck.isChecked(),
        )

    def current_options(self, show_errors: bool = False) -> Optional[MergeOptions]:
        if self.xColumnBox.count() == 0:
            if show_errors:
                QMessageBox.information(self, "提示", "请先添加文件，列选择器会根据当前预览文件自动加载。")
            return None

        x_column = int(self.xColumnBox.currentData()) + 1
        y_columns = self.selected_y_columns()

        return MergeOptions(
            read=self.current_read_options(),
            y_columns=y_columns,
            y_columns_auto=False,
            keep_single_x=self.keepXCheck.isChecked(),
            x_column=x_column,
            validate_x=self.validateXCheck.isChecked(),
            label_mode=str(self.labelModeBox.currentData()),
        )

    def current_merge_request(self, show_errors: bool = False) -> Optional[tuple[List[str], MergeOptions]]:
        options = self.current_options(show_errors=show_errors)
        if options is None:
            return None

        paths = self.paths_to_merge(show_errors=show_errors)
        if not paths:
            return None
        return paths, options

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择数据文件", "", SUPPORTED_FILES)
        self.add_paths(paths)

    def add_paths(self, paths: Sequence[str], sort_input: bool = True) -> None:
        existing = set(self.all_paths())
        added = 0
        skipped = 0
        ordered_paths = sorted(paths, key=natural_sort_key) if sort_input else list(paths)
        self._updating_file_list = True
        self.fileList.blockSignals(True)
        try:
            for raw_path in ordered_paths:
                path = Path(raw_path)
                if not is_supported_data_file(path) or str(path) in existing:
                    skipped += 1
                    continue
                self.fileList.addItem(self.make_file_item(path))
                existing.add(str(path))
                added += 1
        finally:
            self.fileList.blockSignals(False)
            self._updating_file_list = False

        if added:
            self.statusBar().showMessage(f"已添加 {added} 个文件。", 4000)
        elif skipped:
            self.statusBar().showMessage("没有新增文件，可能是重复项或非文件路径。", 5000)
        self.update_filename_display()
        self.refresh_input_preview()
        self.mark_output_dirty()

    def sort_files_naturally(self) -> None:
        paths = self.all_paths()
        if len(paths) < 2:
            return
        checked_paths = set(self.selected_paths())
        source_labels = build_source_labels(paths, "auto")
        sorted_paths = sorted(
            paths,
            key=lambda path: (
                source_label_sort_key(source_labels.get(path, Path(path).stem)),
                natural_sort_key(Path(path).name),
            ),
        )
        descending = paths == sorted_paths
        paths = list(reversed(sorted_paths)) if descending else sorted_paths
        self._updating_file_list = True
        self.fileList.blockSignals(True)
        self.fileList.clear()
        try:
            for raw_path in paths:
                path = Path(raw_path)
                self.fileList.addItem(self.make_file_item(path, str(path) in checked_paths))
        finally:
            self.fileList.blockSignals(False)
            self._updating_file_list = False
        direction = "倒序" if descending else "正序"
        self.statusBar().showMessage(f"文件队列已按自动差异标签{direction}排序。", 4000)
        self.update_filename_display()
        self.refresh_input_preview()
        self.mark_output_dirty()

    def delete_selected_files(self) -> None:
        selected_rows = sorted((self.fileList.row(item) for item in self.fileList.selectedItems()), reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选择要删除的文件。")
            return
        for row in selected_rows:
            self.fileList.takeItem(row)
        self.statusBar().showMessage(f"已删除 {len(selected_rows)} 个文件。", 4000)
        self.refresh_input_preview()
        self.mark_output_dirty()

    def clear_files(self) -> None:
        if self.fileList.count() == 0:
            return
        self.fileList.clear()
        self.statusBar().showMessage("文件队列已清空。", 4000)
        self.refresh_input_preview()
        self.mark_output_dirty()

    def update_filename_display(self) -> None:
        previous_blocked = self.fileList.blockSignals(True)
        try:
            for index in range(self.fileList.count()):
                item = self.fileList.item(index)
                path = Path(item.data(USER_ROLE))
                item.setText(self.file_item_text(path, index))
                item.setToolTip(str(path))
        finally:
            self.fileList.blockSignals(previous_blocked)

    def update_file_count(self) -> None:
        self.fileCountLabel.setText(f"{self.fileList.count()} 个文件")

    def on_files_changed(self) -> None:
        if self._updating_file_list:
            return
        self.update_file_count()
        self.update_filename_display()
        self.mark_output_dirty()

    def on_file_item_changed(self, _item: QListWidgetItem) -> None:
        if self._updating_file_list:
            return
        self.mark_output_dirty()

    def toggle_x_controls(self) -> None:
        enabled = self.keepXCheck.isChecked()
        self.xColumnBox.setEnabled(True)
        self.yColumnList.setEnabled(True)
        self.validateXCheck.setEnabled(enabled)
        self.sync_current_x_column_check_state()

    def on_settings_changed(self) -> None:
        self.mark_output_dirty()

    def on_read_settings_changed(self) -> None:
        if self._updating_read_controls:
            return
        self._read_detection_signature = None
        self.update_auto_read_control_state()
        self.refresh_input_preview()
        self.mark_output_dirty()

    def refresh_input_preview(self) -> None:
        self.update_file_count()
        self.update_input_preview()

    def mark_output_dirty(self) -> None:
        self._data_generation += 1
        self.output_dirty = True
        self.last_merged = None
        self.last_origin_data = None
        self.outputModel.set_dataframe(pd.DataFrame())
        self.reset_output_placeholder()

    def reset_output_placeholder(self) -> None:
        self.outputTitle.setText("合并结果未生成，点击左侧“预览合并结果”开始合并")

    def update_input_preview(self) -> None:
        item = self.preview_reference_item()

        if item is None:
            self.inputModel.set_dataframe(pd.DataFrame())
            self.inputTitle.setText("选中文件或第一个文件的全部数据")
            self._read_detection_signature = None
            return

        if not item.isSelected():
            self.fileList.blockSignals(True)
            try:
                self.fileList.clearSelection()
                self.fileList.setCurrentItem(item)
                item.setSelected(True)
            finally:
                self.fileList.blockSignals(False)

        path = Path(item.data(USER_ROLE))
        try:
            options = self.current_read_options()
            df = read_table(path, options)
        except UserVisibleError as exc:
            self.inputModel.set_dataframe(pd.DataFrame())
            self.inputTitle.setText(f"{path.name} 预览失败")
            self.statusBar().showMessage(str(exc), 6000)
            return

        self.inputModel.set_dataframe(df)
        read_hint = f"跳过 {options.skip_rows} 行，{'表头' if options.has_header else '无表头'}"
        self.inputTitle.setText(f"{path.name}：预览 {df.shape[0]} 行 x {df.shape[1]} 列（{read_hint}）")
        self.populate_column_selector(path, df)

    def set_busy(self, busy: bool) -> None:
        for button in (self.previewButton, self.copyButton, self.exportButton, self.originButton):
            button.setEnabled(not busy)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.originPanel is not None:
            self.originPanel.detach()
        self.origin_worker.shutdown()
        super().closeEvent(event)

    def start_data_task(
        self,
        message: str,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        error_title: str,
        reset_output_on_error: bool = False,
    ) -> None:
        if self._active_tasks:
            self.statusBar().showMessage("当前任务还在处理，请稍等。", 4000)
            return

        task = DataTask(work, on_success, error_title, reset_output_on_error, self)
        self._active_tasks.append(task)
        self.set_busy(True)
        self.statusBar().showMessage(message)
        task.completed.connect(lambda result, error, finished_task=task: self.finish_data_task(finished_task, result, error))
        task.start()

    def finish_data_task(self, task: DataTask, result: object, error: object) -> None:
        if task in self._active_tasks:
            self._active_tasks.remove(task)
        self.set_busy(bool(self._active_tasks))

        error_title = task.error_title
        on_success = task.on_success
        reset_output_on_error = task.reset_output_on_error
        task.deleteLater()

        if error is not None:
            if reset_output_on_error:
                self.output_dirty = True
                self.last_merged = None
                self.last_origin_data = None
                self.outputModel.set_dataframe(pd.DataFrame())
                self.reset_output_placeholder()
            if isinstance(error, UserVisibleError):
                QMessageBox.warning(self, error_title, str(error))
            else:
                QMessageBox.critical(self, error_title, str(error))
            self.statusBar().showMessage(f"{error_title}。", 5000)
            return

        on_success(result)

    def set_merged_result(self, origin_data: OriginImportData) -> None:
        df = origin_data.dataframe
        self.last_origin_data = origin_data
        self.last_merged = df
        self.output_dirty = False
        self.outputModel.set_dataframe(df)
        self.outputTitle.setText(f"合并结果：{df.shape[0]} 行 x {df.shape[1]} 列")

    def ensure_import_data(self, action_name: str, on_ready: Callable[[OriginImportData], None]) -> None:
        if self.last_origin_data is not None and not self.output_dirty:
            on_ready(self.last_origin_data)
            return

        request = self.current_merge_request(show_errors=True)
        if request is None:
            return
        paths, options = request

        generation = self._data_generation
        self.outputModel.set_dataframe(pd.DataFrame())
        self.outputTitle.setText(f"正在后台合并，完成后继续{action_name}...")

        def finish_merge_then_continue(result: object) -> None:
            if generation != self._data_generation:
                QMessageBox.information(
                    self,
                    "结果已过期",
                    f"合并期间参数或文件选择发生了变化，本次结果已丢弃。请再次点击“{action_name}”。",
                )
                self.statusBar().showMessage("参数已变化，未继续使用过期合并结果。", 5000)
                return

            if not isinstance(result, OriginImportData):
                QMessageBox.critical(self, "合并失败", "后台合并没有返回有效结果。")
                return

            self.set_merged_result(result)
            self.statusBar().showMessage(f"合并完成，正在继续{action_name}...", 3000)
            on_ready(result)

        self.start_data_task(
            f"正在后台合并数据，完成后继续{action_name}...",
            lambda: build_origin_import_table(paths, options),
            finish_merge_then_continue,
            "无法合并",
            reset_output_on_error=True,
        )

    def preview_merge(self) -> None:
        request = self.current_merge_request(show_errors=True)
        if request is None:
            return
        paths, options = request

        generation = self._data_generation
        self.outputModel.set_dataframe(pd.DataFrame())
        self.outputTitle.setText("正在后台合并，请稍候...")

        def finish_preview(result: object) -> None:
            if generation != self._data_generation:
                self.statusBar().showMessage("设置已变化，本次合并结果已忽略。", 5000)
                return

            origin_data = result
            if not isinstance(origin_data, OriginImportData):
                return
            self.set_merged_result(origin_data)
            self.statusBar().showMessage("合并预览已更新。", 4000)

        self.start_data_task(
            "正在后台合并数据...",
            lambda: build_origin_import_table(paths, options),
            finish_preview,
            "无法合并",
            reset_output_on_error=True,
        )

    def copy_to_clipboard(self) -> None:
        self.ensure_import_data("复制", self.copy_ready_dataframe_to_clipboard)

    def copy_ready_dataframe_to_clipboard(self, origin_data: OriginImportData) -> None:
        QApplication.clipboard().setText(origin_data.dataframe.to_csv(sep="\t", index=False, lineterminator="\n"))
        self.statusBar().showMessage("已复制为 Tab 分隔文本，可直接粘贴到 Excel。", 5000)
        QMessageBox.information(self, "已复制", "合并结果已复制到剪贴板，可直接粘贴到 Excel。")

    def export_merged(self) -> None:
        self.ensure_import_data("导出", self.export_ready_dataframe)

    def export_ready_dataframe(self, origin_data: OriginImportData) -> None:
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出合并结果",
            "merged.xlsx",
            "Excel (*.xlsx);;CSV UTF-8 (*.csv)",
        )
        if not filename:
            return

        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".csv" if "CSV" in selected_filter else ".xlsx")

        df = origin_data.dataframe.copy()

        def do_export() -> Path:
            if path.suffix.lower() == ".xlsx":
                df.to_excel(path, index=False)
            else:
                df.to_csv(path, index=False, encoding="utf-8-sig")
            return path

        def finish_export(result: object) -> None:
            if not isinstance(result, Path):
                raise TypeError("导出任务没有返回有效路径。")
            exported_path = result
            self.statusBar().showMessage(f"已导出：{exported_path}", 6000)
            QMessageBox.information(self, "导出完成", f"文件已保存到：\n{exported_path}")

        self.start_data_task("正在后台导出文件...", do_export, finish_export, "导出失败")

    def import_to_origin(self) -> None:
        self.ensure_import_data("导入 Origin", self.import_ready_dataframe_to_origin)

    def import_ready_dataframe_to_origin(self, origin_data: OriginImportData) -> None:
        df = origin_data.dataframe.copy()
        axis_spec = origin_data.axis_spec
        long_names = list(origin_data.long_names)
        comments = list(origin_data.comments)
        workbook_label = origin_data.workbook_label

        def do_import() -> str:
            return self.origin_worker.import_dataframe(df, axis_spec, long_names, comments, workbook_label)

        def finish_import(result: object) -> None:
            page_name = str(result)
            self.statusBar().showMessage(f"已导入 Origin：{page_name}", 6000)
            QMessageBox.information(self, "导入完成", f"合并结果已导入 Origin 工作簿：\n{page_name}")

        self.start_data_task("正在连接 Origin 并导入合并数据...", do_import, finish_import, "导入 Origin 失败")

    def can_plot_from_import_data(self, options: MergeOptions) -> bool:
        if options.keep_single_x:
            return True
        x_index = options.x_column - 1
        return options.y_columns_auto or x_index in options.y_columns

    def plot_data(self) -> None:
        if not MATPLOTLIB_AVAILABLE or self.figure is None or self.canvas is None:
            QMessageBox.information(self, "绘图不可用", "当前环境未安装 matplotlib。")
            return

        request = self.current_merge_request(show_errors=True)
        if request is None:
            return
        _paths, options = request

        if not self.can_plot_from_import_data(options):
            QMessageBox.information(self, "无 X 数据", "请在 Y 列选择器中勾选当前 X 列后再绘图。")
            return

        self.ensure_import_data("绘图", self.plot_ready_import_data)

    def plot_ready_import_data(self, origin_data: OriginImportData) -> None:
        if self.figure is None or self.canvas is None:
            return

        df = origin_data.dataframe
        if df.empty:
            QMessageBox.information(self, "无数据", "当前合并结果为空，无法绘图。")
            return

        axis_spec = origin_data.axis_spec
        if len(axis_spec) != df.shape[1] or "x" not in axis_spec:
            QMessageBox.information(self, "无 X 数据", "当前导入数据中没有可用于绘图的 X 列。")
            return

        self.figure.clear()
        axis = self.figure.add_subplot(111)
        axis.set_facecolor("#fbfcfe")
        axis.grid(True, color="#e2e8f0", linewidth=0.8)

        numeric = df.apply(pd.to_numeric, errors="coerce")
        current_x: Optional[pd.Series] = None
        x_label = "X"
        line_count = 0

        for column_index, axis_role in enumerate(axis_spec):
            column_name = str(df.columns[column_index])
            if axis_role == "x":
                current_x = numeric.iloc[:, column_index]
                if x_label == "X":
                    x_label = column_name
                continue
            if axis_role != "y":
                continue
            if current_x is None:
                QMessageBox.information(self, "无 X 数据", "当前导入数据的 Y 列前没有对应的 X 列。")
                return
            axis.plot(current_x, numeric.iloc[:, column_index], linewidth=1.2, alpha=0.9, label=column_name)
            line_count += 1

        if line_count == 0:
            QMessageBox.information(self, "无 Y 数据", "没有可绘制的 Y 列。")
            return

        axis.set_xlabel(x_label)
        axis.set_ylabel("Y")
        axis.set_title("Merged Data Preview" if axis_spec.count("x") <= 1 else "Per-file X Data Preview")
        self.finish_plot(axis, line_count)

    def finish_plot(self, axis: Any, line_count: int) -> None:
        if self.canvas is None:
            return

        if self.plotLogXCheck.isChecked():
            axis.set_xscale("log")
        if self.plotLogYCheck.isChecked():
            axis.set_yscale("log")

        if self.plotLegendCheck.isChecked():
            if line_count <= 30:
                axis.legend(loc="best", fontsize=8)
            else:
                self.statusBar().showMessage("曲线数量超过 30，已自动隐藏图例。", 5000)

        self.canvas.draw_idle()
        self.statusBar().showMessage(f"绘图已更新：{line_count} 条曲线。", 4000)
