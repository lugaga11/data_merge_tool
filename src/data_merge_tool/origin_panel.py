from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from .origin_client import OriginWorkerClient
from .origin_protocol import (
    ApplyResult,
    FigureStylePatch,
    GraphInfo,
    OriginWorkerError,
    PatchTarget,
    StyleSnapshot,
)
from .widgets import (
    DataTask,
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    NoWheelSpinBox,
    make_button,
    make_panel,
    make_section_title,
    make_titled_group,
)

DEFAULT_FLOAT_MIN = -1_000_000_000.0
DEFAULT_FLOAT_MAX = 1_000_000_000.0
EXPORT_WIDTH_MAX = 1_000_000


def _app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "DataMergeTool"
    return Path.home() / ".data_merge_tool"


APP_DATA_DIR = _app_data_dir()
USER_PRESETS_PATH = APP_DATA_DIR / "user_presets.json"
DEFAULT_EXPORT_DIR = APP_DATA_DIR / "origin_exports"
LEGEND_LINE_SEPARATOR = " | "
SCALE_OPTIONS = (("keep", "保持不变"), ("linear", "线性"), ("log10", "对数 10"))
LEGEND_VISIBILITY_OPTIONS = (("keep", "保持不变"), ("show", "显示"), ("hide", "隐藏"))
LEGEND_POSITION_OPTIONS = (
    ("keep", "保持不变"),
    ("best", "自动最佳"),
    ("upper_left", "左上"),
    ("upper_right", "右上"),
    ("lower_left", "左下"),
    ("lower_right", "右下"),
)
PANEL_STYLE = """
QMainWindow {
    background: #eef2f7;
}
QWidget#SidePanel, QWidget#FormatPanel {
    background: #ffffff;
}
QWidget#SidePanel {
    background: #f6f8fb;
    border-right: 1px solid #d8e1ec;
}
QLabel#SectionTitle {
    color: #172235;
    font-size: 15px;
    font-weight: 700;
}
QLabel#SideCardTitle {
    color: #172235;
    font-size: 13px;
    font-weight: 800;
}
QLabel#SideCardSubtitle {
    color: #6b7788;
}
QLabel#SideStatus {
    color: #3f4e63;
    background: #eef4fb;
    border: 1px solid #d7e3f0;
    border-radius: 7px;
    padding: 8px 10px;
}
QLabel#SideStatus[state="ready"] {
    color: #24513a;
    background: #edf8f1;
    border-color: #cce8d6;
}
QLabel#SideStatus[state="error"] {
    color: #7f2d2d;
    background: #fff1f0;
    border-color: #f1c9c5;
}
QLabel#Muted {
    color: #657386;
}
QLabel#FieldLabel {
    color: #26364d;
    font-weight: 600;
}
QLabel#FormatSummary,
QLabel#ActionContext {
    color: #526173;
}
QWidget#SettingCluster {
    background: transparent;
}
QWidget#SideCard {
    background: #ffffff;
    border: 1px solid #dde5ef;
    border-radius: 8px;
}
QWidget#SideActionBar {
    background: #ffffff;
    border-top: 1px solid #d8e1ec;
}
QWidget#FormatPanel {
    background: #ffffff;
}
QWidget#FormatHeader {
    background: #ffffff;
    border-bottom: 1px solid #d8e1ec;
}
QWidget#InlineCluster {
    background: transparent;
}
QWidget#RangeManualControls {
    background: transparent;
}
QGroupBox#TitledGroup {
    border: 1px solid #dbe2ec;
    border-radius: 8px;
    background: #fbfcfe;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox#TitledGroup::title {
    color: #172235;
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    font-weight: 700;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    border: 1px solid #cfd8e6;
    border-radius: 8px;
    background: #ffffff;
    min-height: 24px;
}
QLineEdit {
    padding: 3px 8px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #7fb0f1;
}
QComboBox {
    padding: 3px 6px 3px 8px;
}
QSpinBox, QDoubleSpinBox {
    padding: 3px 2px 3px 8px;
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
QSpinBox::up-arrow,
QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow,
QDoubleSpinBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
}
QCheckBox::indicator,
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #8fa1b8;
    border-radius: 5px;
    background: #ffffff;
    image: none;
}
QCheckBox::indicator:hover,
QRadioButton::indicator:hover {
    border-color: #256fce;
    background: #f4f8ff;
}
QCheckBox::indicator:checked,
QRadioButton::indicator:checked {
    background: #2f80ed;
    border: 1px solid #1f6fd1;
    image: url("__CHECKMARK_ICON__");
}
QCheckBox::indicator:checked:hover,
QRadioButton::indicator:checked:hover {
    background: #256fce;
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
}
QPushButton[role="primary"] {
    color: #ffffff;
    border-color: #1f6fd1;
    background: #256fce;
}
QPushButton[role="primary"]:hover {
    background: #1e5fb2;
}
QPushButton[role="secondary"] {
    color: #1f4f86;
    border-color: #bfd3eb;
    background: #eef6ff;
}
QPushButton[role="secondary"]:hover {
    background: #dcecff;
    border-color: #8fb7e6;
}
QPushButton[role="quiet"] {
    color: #334155;
    border-color: #d8e1ec;
    background: #f8fafc;
}
QPushButton[role="quiet"]:hover {
    background: #eef2f7;
    border-color: #bdcad9;
}
QScrollArea,
QScrollArea#FormatScroll,
QScrollArea#SideScroll,
QWidget#FormatScrollViewport,
QWidget#FormatScrollContent,
QWidget#SideScrollViewport,
QSplitter {
    border: 0;
    background: #ffffff;
}
QWidget#SideScrollContent,
QScrollArea#SideScroll,
QWidget#SideScrollViewport {
    border: 0;
    background: #f6f8fb;
}
QWidget#FormatScrollContent,
QScrollArea#FormatScroll,
QWidget#FormatScrollViewport {
    border: 0;
    background: #ffffff;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #d7dee8;
    color: #526173;
}
"""

PRESETS: dict[str, dict[str, Any]] = {}


class OriginPanelWidget(QWidget):
    def __init__(self, origin_client: OriginWorkerClient | None = None) -> None:
        super().__init__()

        self.origin_client = origin_client or OriginWorkerClient()
        self._owns_origin_client = origin_client is None
        self._active_tasks: list[DataTask] = []
        self.current_graph: GraphInfo | None = None
        self.path_checks: dict[str, QCheckBox] = {}
        self.last_text_editor: QLineEdit | None = None
        self.last_text_selection: dict[QLineEdit, tuple[int, int, str]] = {}
        self.user_presets: dict[str, dict[str, Any]] = {}
        if USER_PRESETS_PATH.exists():
            preset_data = json.loads(USER_PRESETS_PATH.read_text(encoding="utf-8"))
            if not isinstance(preset_data, dict):
                raise ValueError("用户 preset 文件格式错误，应为 JSON 对象。")
            presets = preset_data.get("presets", preset_data)
            if not isinstance(presets, dict):
                raise ValueError("用户 preset 文件格式错误，presets 应为对象。")
            invalid_names = [str(name) for name, preset in presets.items() if not isinstance(preset, dict)]
            if invalid_names:
                raise ValueError(f"用户 preset 条目格式错误：{', '.join(invalid_names)}")
            self.user_presets = {str(name): preset for name, preset in presets.items()}
        self.last_apply_snapshot: StyleSnapshot | None = None

        self._build_ui()
        self.refresh_preset_combo()
        if self.presetCombo.count():
            self.load_preset_values(self.presetCombo.currentText())
        self.clear_enabled_checks(show_status=False)
        self.set_status("Origin 绘图面板已就绪；需要时再连接 Origin。")

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_format_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([350, 1030])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)

    def _build_left_panel(self) -> QWidget:
        panel = make_panel("SidePanel", margins=(0, 0, 0, 0), spacing=0)
        layout = panel.layout()
        assert isinstance(layout, QVBoxLayout)

        workflow_scroll = QScrollArea()
        workflow_scroll.setObjectName("SideScroll")
        workflow_scroll.viewport().setObjectName("SideScrollViewport")
        workflow_scroll.setWidgetResizable(True)
        workflow_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        workflow_content = QWidget()
        workflow_content.setObjectName("SideScrollContent")
        workflow_layout = QVBoxLayout(workflow_content)
        workflow_layout.setContentsMargins(16, 14, 16, 14)
        workflow_layout.setSpacing(12)
        workflow_layout.addWidget(self._build_plot_card())
        workflow_layout.addWidget(self._build_graph_card())
        workflow_layout.addWidget(self._build_target_card())
        workflow_layout.addWidget(self._build_preset_card())
        workflow_layout.addWidget(self._build_export_card())
        workflow_layout.addStretch(1)
        workflow_scroll.setWidget(workflow_content)
        layout.addWidget(workflow_scroll, 1)
        layout.addWidget(self._build_side_action_bar())
        return panel

    def _side_card(self, title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
        card = QWidget()
        card.setObjectName("SideCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("SideCardTitle")
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("SideCardSubtitle")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)
        return card, layout

    def _side_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    def _side_row(self, *widgets: QWidget, expand: QWidget | None = None) -> QWidget:
        row = QWidget()
        row.setObjectName("InlineCluster")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for widget in widgets:
            layout.addWidget(widget, 1 if widget is expand else 0)
        if expand is None:
            layout.addStretch(1)
        return row

    def _build_plot_card(self) -> QWidget:
        card, layout = self._side_card("当前选区绘图", "从活动 worksheet 的当前选区快速生成图。")
        form = self._side_form()
        self.plotKindCombo = NoWheelComboBox()
        self.plotKindCombo.addItems(["线图", "散点图", "线+符号"])
        form.addRow("图形类型", self.plotKindCombo)
        layout.addLayout(form)
        layout.addWidget(make_button("绘制当前选区", self.plot_active_sheet, role="primary"))
        return card

    def _build_graph_card(self) -> QWidget:
        card, layout = self._side_card("当前图", "同步图层后再读取样式，目标会更准确。")
        sync_button = make_button("同步图层", lambda: self.refresh_graph(), role="secondary")
        read_button = make_button("读取样式", self.read_current_style, role="quiet")
        sync_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        read_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        graph_actions = QWidget()
        graph_actions.setObjectName("InlineCluster")
        graph_action_layout = QHBoxLayout(graph_actions)
        graph_action_layout.setContentsMargins(0, 0, 0, 0)
        graph_action_layout.setSpacing(8)
        graph_action_layout.addWidget(sync_button, 1)
        graph_action_layout.addWidget(read_button, 1)
        layout.addWidget(graph_actions)
        self.graphInfoLabel = QLabel("未读取到当前图。")
        self.graphInfoLabel.setObjectName("SideStatus")
        self.graphInfoLabel.setWordWrap(True)
        self._set_widget_state(self.graphInfoLabel, "empty")
        layout.addWidget(self.graphInfoLabel)
        return card

    def _build_target_card(self) -> QWidget:
        card, layout = self._side_card("目标图层", "选择这次要应用格式的图层范围。")
        self.allLayersRadio = QRadioButton("全部图层")
        self.singleLayerRadio = QRadioButton("单个图层")
        self.customLayersRadio = QRadioButton("自定义多选")
        self.singleLayerRadio.setChecked(True)
        self.layerCombo = NoWheelComboBox()
        self.customLayersEdit = QLineEdit()
        self.customLayersEdit.setPlaceholderText("例如 1,3")
        self.allLayersRadio.toggled.connect(self.update_enabled_summary)
        self.singleLayerRadio.toggled.connect(self.update_enabled_summary)
        self.customLayersRadio.toggled.connect(self.update_enabled_summary)
        self.layerCombo.currentIndexChanged.connect(self.update_enabled_summary)
        self.customLayersEdit.textChanged.connect(self.update_enabled_summary)
        layout.addWidget(self.allLayersRadio)
        layout.addWidget(self._side_row(self.singleLayerRadio, self.layerCombo, expand=self.layerCombo))
        layout.addWidget(self._side_row(self.customLayersRadio, self.customLayersEdit, expand=self.customLayersEdit))
        return card

    def _build_preset_card(self) -> QWidget:
        card, layout = self._side_card("预设", "载入、保存、导入或导出自定义参数。")
        form = self._side_form()
        self.presetCombo = NoWheelComboBox()
        form.addRow("风格", self.presetCombo)
        layout.addLayout(form)
        layout.addWidget(make_button("载入预设", self.load_selected_preset, role="secondary"))
        preset_actions = QWidget()
        preset_actions.setObjectName("InlineCluster")
        action_grid = QGridLayout(preset_actions)
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(10)
        action_grid.setVerticalSpacing(8)
        buttons = [
            make_button("保存当前", self.save_current_preset, role="quiet"),
            make_button("删除", self.delete_selected_preset, role="quiet"),
            make_button("导入 JSON", self.import_presets_json, role="quiet"),
            make_button("导出 JSON", self.export_selected_preset_json, role="quiet"),
        ]
        for index, button in enumerate(buttons):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            action_grid.addWidget(button, index // 2, index % 2)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)
        layout.addWidget(preset_actions)
        return card

    def _build_export_card(self) -> QWidget:
        card, layout = self._side_card("导出", "从当前图窗口导出常用图片或矢量格式。")
        self.exportDirEdit = QLineEdit(str(DEFAULT_EXPORT_DIR))
        self.exportDirEdit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(
            self._side_row(
                self.exportDirEdit,
                make_button("选择", self.choose_export_dir, role="quiet"),
                expand=self.exportDirEdit,
            )
        )
        self.exportPngCheck = QCheckBox("PNG")
        self.exportPdfCheck = QCheckBox("PDF")
        self.exportSvgCheck = QCheckBox("SVG")
        self.exportTiffCheck = QCheckBox("TIFF")
        self.exportPngCheck.setChecked(True)
        self.exportPdfCheck.setChecked(True)
        fmt_grid = QGridLayout()
        fmt_grid.setContentsMargins(0, 0, 0, 0)
        fmt_grid.setHorizontalSpacing(10)
        fmt_grid.setVerticalSpacing(6)
        fmt_grid.addWidget(self.exportPngCheck, 0, 0)
        fmt_grid.addWidget(self.exportPdfCheck, 0, 1)
        fmt_grid.addWidget(self.exportSvgCheck, 0, 2)
        fmt_grid.addWidget(self.exportTiffCheck, 0, 3)
        fmt_grid.setColumnStretch(4, 1)
        layout.addLayout(fmt_grid)
        self.exportWidthSpin = NoWheelSpinBox()
        self.exportWidthSpin.setRange(1, EXPORT_WIDTH_MAX)
        self.exportWidthSpin.setValue(2400)
        self._fit_input(self.exportWidthSpin, 104)
        layout.addWidget(
            self._side_row(
                self._label("宽度"),
                self.exportWidthSpin,
                self._label("px"),
                make_button("导出", self.export_active_graph, role="quiet"),
            )
        )
        return card

    def _build_side_action_bar(self) -> QWidget:
        action_box = QWidget()
        action_box.setObjectName("SideActionBar")
        action_layout = QVBoxLayout(action_box)
        action_layout.setContentsMargins(16, 12, 16, 14)
        action_layout.setSpacing(8)
        apply_button = make_button("应用启用项", self.apply_patch, role="primary")
        apply_button.setMinimumHeight(40)
        action_layout.addWidget(apply_button)
        action_layout.addWidget(make_button("撤销上次应用", self.undo_last_apply, role="quiet"))
        self.actionContextLabel = QLabel("目标：Layer 1 · 已启用 0 项")
        self.actionContextLabel.setObjectName("ActionContext")
        self.actionContextLabel.setWordWrap(True)
        action_layout.addWidget(self.actionContextLabel)
        return action_box

    def _build_format_panel(self) -> QWidget:
        panel = make_panel("FormatPanel", margins=(0, 0, 0, 0), spacing=0)
        layout = panel.layout()
        assert isinstance(layout, QVBoxLayout)

        layout.addWidget(self._build_format_header())

        scroll = QScrollArea()
        scroll.setObjectName("FormatScroll")
        scroll.viewport().setObjectName("FormatScrollViewport")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_content.setObjectName("FormatScrollContent")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(14, 14, 18, 16)
        scroll_layout.setSpacing(12)
        scroll_layout.addWidget(self._build_page_group())
        scroll_layout.addWidget(self._build_layer_group())
        scroll_layout.addWidget(self._build_axis_group())
        scroll_layout.addWidget(self._build_plot_group())
        scroll_layout.addWidget(self._build_text_group())
        scroll_layout.addWidget(self._build_legend_group())
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        return panel

    def _build_format_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("FormatHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 12)
        header_layout.setSpacing(10)

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(3)
        title_layout.addWidget(make_section_title("格式控制"))
        self.formatSummaryLabel = QLabel("已启用 0 项")
        self.formatSummaryLabel.setObjectName("FormatSummary")
        title_layout.addWidget(self.formatSummaryLabel)

        header_layout.addWidget(title_block, 1)
        header_layout.addWidget(make_button("全选启用项", self.select_all_enabled_checks, role="secondary"))
        header_layout.addWidget(make_button("清空", lambda: self.clear_enabled_checks(), role="quiet"))
        return header

    def _format_grid(self, parent: QWidget) -> QGridLayout:
        grid = QGridLayout(parent)
        grid.setContentsMargins(12, 16, 12, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0, 96)
        grid.setColumnStretch(1, 1)
        return grid

    def _path_check(self, text: str, path: str) -> QCheckBox:
        check = QCheckBox(text)
        check.setMinimumWidth(102)
        check.stateChanged.connect(self.update_enabled_summary)
        self.path_checks[path] = check
        return check

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _cluster(self, *widgets: QWidget, expand: QWidget | None = None) -> QWidget:
        widget = QWidget()
        widget.setObjectName("SettingCluster")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for child in widgets:
            layout.addWidget(child, 1 if child is expand else 0)
        if expand is None:
            layout.addStretch(1)
        return widget

    def _field_grid(self, fields: list[tuple[str, QWidget]], columns: int = 2) -> QWidget:
        widget = QWidget()
        widget.setObjectName("SettingCluster")
        grid = QGridLayout(widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        for index, (label, control) in enumerate(fields):
            row = index // columns
            col = (index % columns) * 2
            grid.addWidget(self._label(label), row, col)
            grid.addWidget(control, row, col + 1)
        grid.setColumnStretch(columns * 2, 1)
        return widget

    def _add_setting(
        self,
        grid: QGridLayout,
        row: int,
        column: int,
        path: str,
        label: str,
        controls: QWidget,
    ) -> None:
        effective_row = row * 2 + column
        grid.addWidget(self._path_check(label, path), effective_row, 0)
        grid.addWidget(controls, effective_row, 1)

    def _add_wide_setting(
        self,
        grid: QGridLayout,
        row: int,
        path: str,
        label: str,
        controls: QWidget,
    ) -> None:
        effective_row = row * 2
        grid.addWidget(self._path_check(label, path), effective_row, 0)
        grid.addWidget(controls, effective_row, 1)

    @staticmethod
    def _add_combo_options(combo: QComboBox, options: tuple[tuple[str, str], ...]) -> None:
        combo.clear()
        for value, label in options:
            combo.addItem(label, value)

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        value = combo.currentData()
        return str(value) if value is not None else combo.currentText()

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: object) -> None:
        text = str(value)
        index = combo.findData(text)
        if index < 0:
            index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _set_widget_state(widget: QWidget, state: str) -> None:
        widget.setProperty("state", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _fit_input(self, widget: QWidget, width: int = 96) -> QWidget:
        widget.setMinimumWidth(min(72, width))
        widget.setMaximumWidth(width)
        return widget

    def _fill_input(self, widget: QWidget) -> QWidget:
        widget.setMinimumWidth(140)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return widget

    def _float_spin(
        self,
        value: float,
        minimum: float = DEFAULT_FLOAT_MIN,
        maximum: float = DEFAULT_FLOAT_MAX,
        step: float = 0.1,
        width: int = 96,
    ) -> NoWheelDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(4)
        spin.setSingleStep(step)
        spin.setValue(value)
        self._fit_input(spin, width)
        return spin

    def _build_page_group(self) -> QGroupBox:
        box = make_titled_group("Page 画布")
        grid = self._format_grid(box)
        self.pageWidthSpin = self._float_spin(3.5, 0.1, 100.0, width=104)
        self.pageHeightSpin = self._float_spin(2.6, 0.1, 100.0, width=104)
        self.pageAntiAliasCheck = QCheckBox("启用")
        self._add_setting(
            grid,
            0,
            0,
            "page.size_in",
            "画布尺寸",
            self._cluster(self._label("宽"), self.pageWidthSpin, self._label("高"), self.pageHeightSpin, self._label("in")),
        )
        self._add_setting(
            grid,
            0,
            1,
            "page.anti_alias",
            "抗锯齿",
            self._cluster(self.pageAntiAliasCheck),
        )
        return box

    def _build_layer_group(self) -> QGroupBox:
        box = make_titled_group("Layer 坐标框")
        grid = self._format_grid(box)
        self.layerLeftSpin = self._float_spin(0.55, 0.0, 100.0, width=104)
        self.layerTopSpin = self._float_spin(0.24, 0.0, 100.0, width=104)
        self.layerWidthSpin = self._float_spin(2.60, 0.1, 100.0, width=104)
        self.layerHeightSpin = self._float_spin(1.89, 0.1, 100.0, width=104)
        self._add_wide_setting(
            grid,
            0,
            "layer.geometry_in",
            "位置/大小",
            self._field_grid(
                [
                    ("左 in", self.layerLeftSpin),
                    ("上 in", self.layerTopSpin),
                    ("宽 in", self.layerWidthSpin),
                    ("高 in", self.layerHeightSpin),
                ]
            ),
        )
        self.frameLeftCheck = QCheckBox("左")
        self.frameBottomCheck = QCheckBox("下")
        self.frameTopCheck = QCheckBox("上")
        self.frameRightCheck = QCheckBox("右")
        for check in (self.frameLeftCheck, self.frameBottomCheck, self.frameTopCheck, self.frameRightCheck):
            check.setChecked(True)
        self.layerLineWidthSpin = self._float_spin(0.8, 0.1, 20.0, 0.1, width=104)
        self.scaleFixedCheck = QCheckBox("固定")
        self.scaleFactorSpin = self._float_spin(1.0, 0.01, 100.0, 0.01, width=104)
        self._add_setting(
            grid,
            1,
            0,
            "layer.frame",
            "边框",
            self._cluster(self.frameLeftCheck, self.frameBottomCheck, self.frameTopCheck, self.frameRightCheck),
        )
        self._add_setting(
            grid,
            1,
            1,
            "layer.line_width_pt",
            "轴线宽",
            self._cluster(self.layerLineWidthSpin, self._label("pt")),
        )
        self._add_wide_setting(
            grid,
            2,
            "layer.scale_elements",
            "元素缩放",
            self._cluster(self.scaleFixedCheck, self._label("因子"), self.scaleFactorSpin),
        )
        return box

    def _build_axis_group(self) -> QGroupBox:
        box = make_titled_group("Axis 坐标轴")
        grid = self._format_grid(box)
        self.xScaleCombo = NoWheelComboBox()
        self._add_combo_options(self.xScaleCombo, SCALE_OPTIONS)
        self._fit_input(self.xScaleCombo, 136)
        self.yScaleCombo = NoWheelComboBox()
        self._add_combo_options(self.yScaleCombo, SCALE_OPTIONS)
        self._fit_input(self.yScaleCombo, 136)
        self.gridCheck = QCheckBox("显示主网格")
        self._add_setting(grid, 0, 0, "axis.x_scale", "X 类型", self._cluster(self.xScaleCombo))
        self._add_setting(grid, 0, 1, "axis.y_scale", "Y 类型", self._cluster(self.yScaleCombo))
        self._add_wide_setting(grid, 1, "axis.grid", "网格", self._cluster(self.gridCheck))
        return box

    def _build_plot_group(self) -> QGroupBox:
        box = make_titled_group("Plot 曲线")
        grid = self._format_grid(box)
        self.lineWidthSpin = self._float_spin(1.2, 0.1, 20.0, 0.1, width=104)
        self.symbolSizeSpin = self._float_spin(4.0, 0.1, 100.0, 0.5, width=104)
        self._add_setting(grid, 0, 0, "plot.line_width_pt", "线宽", self._cluster(self.lineWidthSpin, self._label("pt")))
        self._add_setting(grid, 0, 1, "plot.symbol_size_pt", "符号大小", self._cluster(self.symbolSizeSpin, self._label("pt")))
        return box

    def _build_text_group(self) -> QGroupBox:
        box = make_titled_group("Text 文本")
        grid = self._format_grid(box)
        self.xTitleEdit = QLineEdit()
        self._track_text_editor(self.xTitleEdit)
        self.yTitleEdit = QLineEdit()
        self._track_text_editor(self.yTitleEdit)
        self.legendTextEdit = QLineEdit()
        self.legendTextEdit.setPlaceholderText("用 | 表示换行，例如 testy1 | testy2 | D")
        self._track_text_editor(self.legendTextEdit)
        self._add_setting(
            grid,
            0,
            0,
            "text.x_title",
            "X 标题",
            self._cluster(self._fill_input(self.xTitleEdit), expand=self.xTitleEdit),
        )
        self._add_setting(
            grid,
            0,
            1,
            "text.y_title",
            "Y 标题",
            self._cluster(self._fill_input(self.yTitleEdit), expand=self.yTitleEdit),
        )
        self._add_wide_setting(
            grid,
            1,
            "text.legend_text",
            "图例文本",
            self._cluster(self._fill_input(self.legendTextEdit), expand=self.legendTextEdit),
        )
        format_row = self._cluster(
            self._label("选中文本"),
            make_button("加粗", self.insert_bold, keep_text_focus=True, role="quiet"),
            make_button("斜体", self.insert_italic, keep_text_focus=True, role="quiet"),
            make_button("上标", self.insert_superscript, keep_text_focus=True, role="quiet"),
            make_button("下标", self.insert_subscript, keep_text_focus=True, role="quiet"),
        )
        grid.addWidget(self._label("文本格式"), 5, 0)
        grid.addWidget(format_row, 5, 1)
        self.axisTitleSizeSpin = self._float_spin(8.0, 1.0, 72.0, 0.5, width=104)
        self.axisTickSizeSpin = self._float_spin(7.0, 1.0, 72.0, 0.5, width=104)
        self.legendFontSizeSpin = self._float_spin(7.0, 1.0, 72.0, 0.5, width=104)
        self._add_setting(
            grid,
            3,
            0,
            "text.title_size_pt",
            "标题字号",
            self._cluster(self.axisTitleSizeSpin, self._label("pt")),
        )
        self._add_setting(
            grid,
            4,
            0,
            "text.tick_size_pt",
            "刻度字号",
            self._cluster(self.axisTickSizeSpin, self._label("pt")),
        )
        self._add_setting(
            grid,
            4,
            1,
            "text.legend_size_pt",
            "图例字号",
            self._cluster(self.legendFontSizeSpin, self._label("pt")),
        )
        return box

    def _build_legend_group(self) -> QGroupBox:
        box = make_titled_group("Legend 图例")
        grid = self._format_grid(box)
        self.legendVisibilityCombo = NoWheelComboBox()
        self._add_combo_options(self.legendVisibilityCombo, LEGEND_VISIBILITY_OPTIONS)
        self._fit_input(self.legendVisibilityCombo, 136)
        self.legendFrameCheck = QCheckBox("显示图例框")
        self.legendPositionCombo = NoWheelComboBox()
        self._add_combo_options(self.legendPositionCombo, LEGEND_POSITION_OPTIONS)
        self._fit_input(self.legendPositionCombo, 170)
        self._add_setting(grid, 0, 0, "legend.visibility", "显示", self._cluster(self.legendVisibilityCombo))
        self._add_setting(grid, 0, 1, "legend.frame", "边框", self._cluster(self.legendFrameCheck))
        self._add_wide_setting(grid, 1, "legend.position", "位置", self._cluster(self.legendPositionCombo))
        return box

    def start_origin_task(
        self,
        message: str,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        error_title: str,
    ) -> None:
        if self._active_tasks:
            self.set_status("Origin 自动化任务仍在执行，请稍后。", 4000)
            return
        task = DataTask(work, on_success, error_title, parent=self)
        self._active_tasks.append(task)
        self.setEnabled(False)
        self.set_status(message)
        task.completed.connect(lambda result, error, finished_task=task: self.finish_origin_task(finished_task, result, error))
        task.start()

    def finish_origin_task(self, task: DataTask, result: object, error: object) -> None:
        if task in self._active_tasks:
            self._active_tasks.remove(task)
        self.setEnabled(not self._active_tasks)
        error_title = task.error_title
        on_success = task.on_success
        task.deleteLater()
        if error is not None:
            self.show_error(error_title, error if isinstance(error, Exception) else RuntimeError(str(error)))
            return
        try:
            on_success(result)
        except Exception as exc:
            self.show_error(error_title, exc)

    def has_active_origin_task(self) -> bool:
        return bool(self._active_tasks)

    def plot_active_sheet(self) -> None:
        plot_kind = self.plotKindCombo.currentText()

        def finish(result: object) -> None:
            if not isinstance(result, tuple) or len(result) != 2:
                raise TypeError("Origin worker returned an invalid plot result.")
            message, graph = result
            if not isinstance(graph, GraphInfo):
                raise TypeError("Origin worker 没有返回有效图信息。")
            self.set_status(str(message))
            self.update_graph_info(graph, update_status=False)

        self.start_origin_task(
            "正在通过 Origin worker 绘制当前选区...",
            lambda: self.origin_client.plot_active_sheet(plot_kind),
            finish,
            "绘图失败",
        )

    def refresh_graph(self) -> None:
        def finish(result: object) -> None:
            if not isinstance(result, GraphInfo):
                raise TypeError("Origin worker 没有返回有效图信息。")
            self.update_graph_info(result, update_status=True)

        self.start_origin_task(
            "正在通过 Origin worker 读取当前图...",
            self.origin_client.scan_active_graph,
            finish,
            "读取图结构失败",
        )

    def update_graph_info(self, info: GraphInfo, update_status: bool) -> None:
        previous_index = max(self.layerCombo.currentIndex(), 0)
        self.current_graph = info
        self.layerCombo.clear()
        self.layerCombo.addItems([f"Layer {layer.index} ({layer.plot_count} plot)" for layer in info.layers])
        if self.layerCombo.count():
            self.layerCombo.setCurrentIndex(min(previous_index, self.layerCombo.count() - 1))
        layer_text = "; ".join(f"L{layer.index}: {layer.plot_count} plot" for layer in info.layers)
        self.graphInfoLabel.setText(f"{info.name}：{len(info.layers)} 个图层。{layer_text}")
        self._set_widget_state(self.graphInfoLabel, "ready")
        self.update_enabled_summary()
        if update_status:
            self.set_status(f"{info.name}：{len(info.layers)} 个图层，当前目标：{self.target_description()}")

    def clear_origin_connection_state(self) -> None:
        self.current_graph = None
        self.last_apply_snapshot = None
        self.layerCombo.clear()
        self.graphInfoLabel.setText("未读取到当前图。")
        self._set_widget_state(self.graphInfoLabel, "empty")
        self.update_enabled_summary()

    def load_selected_preset(self) -> None:
        name = self.presetCombo.currentText()
        if name not in self.all_presets():
            return
        self.load_preset_values(name)
        self.set_status(f"已载入预设：{name}。")

    def write_user_presets(self) -> None:
        USER_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_PRESETS_PATH.write_text(
            json.dumps({"presets": self.user_presets}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def all_presets(self) -> dict[str, dict[str, Any]]:
        combined = deepcopy(PRESETS)
        combined.update(deepcopy(self.user_presets))
        return combined

    def refresh_preset_combo(self, selected: str | None = None) -> None:
        current = selected or self.presetCombo.currentText()
        self.presetCombo.clear()
        self.presetCombo.addItems(list(self.all_presets().keys()))
        index = self.presetCombo.findText(current)
        if index >= 0:
            self.presetCombo.setCurrentIndex(index)

    def current_preset_values(self) -> dict[str, Any]:
        return {
            "enabled_paths": self.selected_enabled_paths(),
            "page": {
                "width_in": self.pageWidthSpin.value(),
                "height_in": self.pageHeightSpin.value(),
                "anti_alias": self.pageAntiAliasCheck.isChecked(),
            },
            "layer": {
                "left_in": self.layerLeftSpin.value(),
                "top_in": self.layerTopSpin.value(),
                "width_in": self.layerWidthSpin.value(),
                "height_in": self.layerHeightSpin.value(),
                "line_width_pt": self.layerLineWidthSpin.value(),
                "scale_fixed": self.scaleFixedCheck.isChecked(),
                "scale_factor": self.scaleFactorSpin.value(),
                "frame": {
                    "left": self.frameLeftCheck.isChecked(),
                    "bottom": self.frameBottomCheck.isChecked(),
                    "top": self.frameTopCheck.isChecked(),
                    "right": self.frameRightCheck.isChecked(),
                },
            },
            "plot": {
                "line_width_pt": self.lineWidthSpin.value(),
                "symbol_size_pt": self.symbolSizeSpin.value(),
            },
            "text": {
                "title_font_size_pt": self.axisTitleSizeSpin.value(),
                "tick_font_size_pt": self.axisTickSizeSpin.value(),
                "legend_font_size_pt": self.legendFontSizeSpin.value(),
            },
            "axis": {
                "x_scale": self._combo_value(self.xScaleCombo),
                "y_scale": self._combo_value(self.yScaleCombo),
                "show_grid": self.gridCheck.isChecked(),
            },
            "legend": {
                "visibility": self._combo_value(self.legendVisibilityCombo),
                "frame": self.legendFrameCheck.isChecked(),
                "position": self._combo_value(self.legendPositionCombo),
            },
            "export": {
                "width_px": self.exportWidthSpin.value(),
                "formats": self.selected_export_formats(),
            },
        }

    def save_current_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "保存预设", "预设名称：", text=self.presetCombo.currentText())
        name = name.strip()
        if not ok or not name:
            return
        if name in PRESETS:
            QMessageBox.information(self, "内置预设", "内置预设不能覆盖，请换一个名称。")
            return
        self.user_presets[name] = self.current_preset_values()
        self.write_user_presets()
        self.refresh_preset_combo(name)
        self.set_status(f"已保存自定义预设：{name}")

    def delete_selected_preset(self) -> None:
        name = self.presetCombo.currentText()
        if name in PRESETS:
            QMessageBox.information(self, "内置预设", "内置预设不能删除。")
            return
        if name not in self.user_presets:
            return
        answer = QMessageBox.question(self, "删除预设", f"确定删除自定义预设“{name}”吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.user_presets.pop(name, None)
        self.write_user_presets()
        self.refresh_preset_combo()
        self.set_status(f"已删除自定义预设：{name}")

    def import_presets_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入 preset JSON", str(USER_PRESETS_PATH.parent), "JSON Files (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            presets = data.get("presets", data) if isinstance(data, dict) else {}
            if not isinstance(presets, dict):
                raise ValueError("JSON 顶层应为预设对象或包含 presets 对象")
            imported = {str(name): preset for name, preset in presets.items() if isinstance(preset, dict)}
            imported = {name: preset for name, preset in imported.items() if name not in PRESETS}
            if not imported:
                raise ValueError("没有可导入的自定义预设")
            self.user_presets.update(imported)
            self.write_user_presets()
            self.refresh_preset_combo(next(iter(imported)))
        except Exception as exc:
            self.show_error("导入预设失败", exc)
            return
        self.set_status(f"已导入 {len(imported)} 个自定义预设。")

    def export_selected_preset_json(self) -> None:
        name = self.presetCombo.currentText()
        if name not in self.all_presets():
            return
        preset = self.current_preset_values()
        safe_name = "".join("_" if char in '<>:"/\\|?*' else char for char in name).strip() or "preset"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出 preset JSON",
            str(DEFAULT_EXPORT_DIR / f"{safe_name}.json"),
            "JSON Files (*.json)",
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"presets": {name: preset}}, ensure_ascii=False, indent=2), encoding="utf-8")
        self.set_status(f"已导出预设：{target}")

    def load_preset_values(self, name: str) -> None:
        preset = deepcopy(self.all_presets()[name])
        page = preset["page"]
        self.pageWidthSpin.setValue(page["width_in"])
        self.pageHeightSpin.setValue(page["height_in"])
        self.pageAntiAliasCheck.setChecked(page.get("anti_alias", False))
        layer = preset["layer"]
        self.layerLeftSpin.setValue(layer["left_in"])
        self.layerTopSpin.setValue(layer["top_in"])
        self.layerWidthSpin.setValue(layer["width_in"])
        self.layerHeightSpin.setValue(layer["height_in"])
        frame = layer["frame"]
        self.frameLeftCheck.setChecked(frame["left"])
        self.frameBottomCheck.setChecked(frame["bottom"])
        self.frameTopCheck.setChecked(frame["top"])
        self.frameRightCheck.setChecked(frame["right"])
        self.layerLineWidthSpin.setValue(layer["line_width_pt"])
        self.scaleFixedCheck.setChecked(layer.get("scale_fixed", False))
        self.scaleFactorSpin.setValue(layer.get("scale_factor", 1.0))
        plot = preset["plot"]
        self.lineWidthSpin.setValue(plot["line_width_pt"])
        self.symbolSizeSpin.setValue(plot["symbol_size_pt"])
        self.xTitleEdit.clear()
        self.yTitleEdit.clear()
        self.legendTextEdit.clear()
        text = preset["text"]
        self.axisTitleSizeSpin.setValue(text["title_font_size_pt"])
        self.axisTickSizeSpin.setValue(text["tick_font_size_pt"])
        self.legendFontSizeSpin.setValue(text["legend_font_size_pt"])
        axis = preset["axis"]
        self._set_combo_value(self.xScaleCombo, axis["x_scale"])
        self._set_combo_value(self.yScaleCombo, axis["y_scale"])
        self.gridCheck.setChecked(axis["show_grid"])
        legend = preset["legend"]
        self._set_combo_value(self.legendVisibilityCombo, legend["visibility"])
        self.legendFrameCheck.setChecked(legend["frame"])
        self._set_combo_value(self.legendPositionCombo, legend["position"])
        export = preset["export"]
        self.exportWidthSpin.setValue(export["width_px"])
        self.exportPngCheck.setChecked("png" in export["formats"])
        self.exportPdfCheck.setChecked("pdf" in export["formats"])
        self.exportSvgCheck.setChecked("svg" in export["formats"])
        self.exportTiffCheck.setChecked("tiff" in export["formats"])
        self.apply_enabled_paths(preset.get("enabled_paths", []))

    def selected_enabled_paths(self) -> list[str]:
        return sorted(path for path, check in self.path_checks.items() if check.isChecked())

    def apply_enabled_paths(self, enabled_paths: object) -> None:
        enabled = set(enabled_paths) if isinstance(enabled_paths, list) else set()
        for path, check in self.path_checks.items():
            check.setChecked(path in enabled)
        self.update_enabled_summary()

    def _legend_edit_to_origin_text(self) -> str:
        return self._edit_text_to_origin_text(self.legendTextEdit.text())

    def _legend_readback_to_edit_text(self, display_text: str, raw_text: str) -> str:
        return self._display_text_to_edit_text(raw_text or display_text)

    @staticmethod
    def _edit_text_to_origin_text(text: str) -> str:
        return "\n".join(piece.strip() for piece in text.split("|") if piece.strip())

    @staticmethod
    def _display_text_to_edit_text(text: str) -> str:
        return LEGEND_LINE_SEPARATOR.join(line.strip() for line in text.splitlines() if line.strip())

    def clear_enabled_checks(self, show_status: bool = True) -> None:
        for check in self.path_checks.values():
            check.setChecked(False)
        self.update_enabled_summary()
        if show_status:
            self.set_status("已清空启用项。")

    def select_all_enabled_checks(self) -> None:
        for check in self.path_checks.values():
            check.setChecked(True)
        self.update_enabled_summary()
        self.set_status("已全选启用项。")

    def update_enabled_summary(self) -> None:
        count = sum(1 for check in self.path_checks.values() if check.isChecked())
        summary = f"已启用 {count} 项"
        if hasattr(self, "formatSummaryLabel"):
            self.formatSummaryLabel.setText(summary)
        if hasattr(self, "actionContextLabel"):
            self.actionContextLabel.setText(f"目标：{self.target_description()} · {summary}")

    def selected_layer_indices(self) -> tuple[str, list[int]]:
        if self.allLayersRadio.isChecked():
            return "all", []
        if self.singleLayerRadio.isChecked():
            index = self.layerCombo.currentIndex()
            return "selected", [index + 1] if index >= 0 else [1]
        indices: list[int] = []
        for piece in self.customLayersEdit.text().replace("，", ",").split(","):
            piece = piece.strip()
            if not piece:
                continue
            indices.append(int(piece))
        return "selected", indices

    def target_description(self) -> str:
        if self.allLayersRadio.isChecked():
            return "全部图层"
        if self.singleLayerRadio.isChecked():
            index = self.layerCombo.currentIndex()
            return f"Layer {index + 1}" if index >= 0 else "Layer 1"
        return self.customLayersEdit.text().strip() or "自定义图层"

    def build_patch(self) -> FigureStylePatch:
        scope, indices = self.selected_layer_indices()
        enabled = {path for path, check in self.path_checks.items() if check.isChecked()}
        x_title = self._edit_text_to_origin_text(self.xTitleEdit.text())
        y_title = self._edit_text_to_origin_text(self.yTitleEdit.text())
        legend_text = self._legend_edit_to_origin_text()
        if not x_title.strip():
            enabled.discard("text.x_title")
        if not y_title.strip():
            enabled.discard("text.y_title")
        if not legend_text.strip():
            enabled.discard("text.legend_text")
        return FigureStylePatch(
            target=PatchTarget(layer_scope=scope, layer_indices=indices),
            enabled_paths=enabled,
            page={
                "width_in": self.pageWidthSpin.value(),
                "height_in": self.pageHeightSpin.value(),
                "anti_alias": self.pageAntiAliasCheck.isChecked(),
            },
            layer={
                "left_in": self.layerLeftSpin.value(),
                "top_in": self.layerTopSpin.value(),
                "width_in": self.layerWidthSpin.value(),
                "height_in": self.layerHeightSpin.value(),
                "line_width_pt": self.layerLineWidthSpin.value(),
                "scale_fixed": self.scaleFixedCheck.isChecked(),
                "scale_factor": self.scaleFactorSpin.value(),
                "frame": {
                    "left": self.frameLeftCheck.isChecked(),
                    "bottom": self.frameBottomCheck.isChecked(),
                    "top": self.frameTopCheck.isChecked(),
                    "right": self.frameRightCheck.isChecked(),
                },
            },
            plot={
                "line_width_pt": self.lineWidthSpin.value(),
                "symbol_size_pt": self.symbolSizeSpin.value(),
            },
            text={
                "x_title": x_title,
                "y_title": y_title,
                "legend_text": legend_text,
                "title_font_size_pt": self.axisTitleSizeSpin.value(),
                "tick_font_size_pt": self.axisTickSizeSpin.value(),
                "legend_font_size_pt": self.legendFontSizeSpin.value(),
            },
            axis={
                "x_scale": self._combo_value(self.xScaleCombo),
                "y_scale": self._combo_value(self.yScaleCombo),
                "show_grid": self.gridCheck.isChecked(),
            },
            legend={
                "visibility": self._combo_value(self.legendVisibilityCombo),
                "frame": self.legendFrameCheck.isChecked(),
                "position": self._combo_value(self.legendPositionCombo),
            },
        )

    def read_current_style(self) -> None:
        _scope, indices = self.selected_layer_indices()
        layer_index = indices[0] if indices else 1

        def finish(result: object) -> None:
            if not isinstance(result, dict):
                raise TypeError("Origin worker 没有返回有效样式。")
            self.apply_readback_style(result)
            self.set_status(f"已读取 Layer {layer_index} 的可回读设置；未自动启用任何格式项。")

        self.start_origin_task(
            "正在通过 Origin worker 读取样式...",
            lambda: self.origin_client.read_active_layer_style(layer_index),
            finish,
            "读取设置失败",
        )

    def apply_readback_style(self, style: dict[str, object]) -> None:
        page = style.get("page", {})
        if isinstance(page, dict):
            self.set_spin_if_number(self.pageWidthSpin, page.get("width_in"))
            self.set_spin_if_number(self.pageHeightSpin, page.get("height_in"))
            if page.get("anti_alias") is not None:
                self.pageAntiAliasCheck.setChecked(bool(page.get("anti_alias")))

        layer = style.get("layer", {})
        if isinstance(layer, dict):
            self.set_spin_if_number(self.layerLeftSpin, layer.get("left_in"))
            self.set_spin_if_number(self.layerTopSpin, layer.get("top_in"))
            self.set_spin_if_number(self.layerWidthSpin, layer.get("width_in"))
            self.set_spin_if_number(self.layerHeightSpin, layer.get("height_in"))
            self.set_spin_if_number(self.layerLineWidthSpin, layer.get("line_width_pt"))
            self.set_spin_if_number(self.scaleFactorSpin, layer.get("scale_factor"))
            if layer.get("scale_fixed") is not None:
                self.scaleFixedCheck.setChecked(bool(layer.get("scale_fixed")))
            frame = layer.get("frame")
            if isinstance(frame, dict):
                self.frameLeftCheck.setChecked(bool(frame.get("left", True)))
                self.frameBottomCheck.setChecked(bool(frame.get("bottom", True)))
                self.frameTopCheck.setChecked(bool(frame.get("top", True)))
                self.frameRightCheck.setChecked(bool(frame.get("right", True)))

        text = style.get("text", {})
        if isinstance(text, dict):
            self.xTitleEdit.setText(self._display_text_to_edit_text(str(text.get("x_title") or "")))
            self.yTitleEdit.setText(self._display_text_to_edit_text(str(text.get("y_title") or "")))
            self.legendTextEdit.setText(
                self._legend_readback_to_edit_text(
                    str(text.get("legend_text") or ""),
                    str(text.get("legend_text_raw") or ""),
                )
            )
            self.set_spin_if_number(self.axisTitleSizeSpin, text.get("title_font_size_pt"))
            self.set_spin_if_number(self.axisTickSizeSpin, text.get("tick_font_size_pt"))
            self.set_spin_if_number(self.legendFontSizeSpin, text.get("legend_font_size_pt"))

        axis = style.get("axis", {})
        if isinstance(axis, dict):
            if axis.get("x_scale") in {"keep", "linear", "log10"}:
                self._set_combo_value(self.xScaleCombo, axis.get("x_scale"))
            if axis.get("y_scale") in {"keep", "linear", "log10"}:
                self._set_combo_value(self.yScaleCombo, axis.get("y_scale"))
            if axis.get("show_grid") is not None:
                self.gridCheck.setChecked(bool(axis.get("show_grid")))

        plot = style.get("plot", {})
        if isinstance(plot, dict):
            self.set_spin_if_number(self.lineWidthSpin, plot.get("line_width_pt"))
            self.set_spin_if_number(self.symbolSizeSpin, plot.get("symbol_size_pt"))

        legend = style.get("legend", {})
        if isinstance(legend, dict):
            visibility = legend.get("visibility")
            if visibility == 1:
                self._set_combo_value(self.legendVisibilityCombo, "show")
            elif visibility == 0:
                self._set_combo_value(self.legendVisibilityCombo, "hide")
            if legend.get("frame") is not None:
                self.legendFrameCheck.setChecked(bool(legend.get("frame")))

    @staticmethod
    def set_spin_if_number(spin: NoWheelDoubleSpinBox | NoWheelSpinBox, value: object) -> None:
        if isinstance(value, (int, float)):
            if isinstance(spin, NoWheelSpinBox):
                spin.setValue(int(value))
            else:
                spin.setValue(float(value))

    def active_text_editor(self) -> QLineEdit | None:
        widget = QApplication.focusWidget()
        if isinstance(widget, QLineEdit) and widget in (self.xTitleEdit, self.yTitleEdit, self.legendTextEdit):
            self.last_text_editor = widget
            return widget
        return self.last_text_editor

    def _track_text_editor(self, editor: QLineEdit) -> None:
        editor.installEventFilter(self)
        editor.selectionChanged.connect(lambda editor=editor: self.remember_text_selection(editor))

    def remember_text_selection(self, editor: QLineEdit) -> None:
        self.last_text_editor = editor
        if editor.hasSelectedText():
            self.last_text_selection[editor] = (editor.selectionStart(), len(editor.selectedText()), editor.text())
        elif QApplication.focusWidget() is editor:
            self.last_text_selection.pop(editor, None)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QLineEdit):
            if watched in (self.xTitleEdit, self.yTitleEdit, self.legendTextEdit):
                self.last_text_editor = watched
        return super().eventFilter(watched, event)

    def insert_text_format(self, prefix: str) -> None:
        editor = self.active_text_editor()
        if editor is None:
            self.set_status("请先在 X/Y/Legend 文本框中选中要格式化的文本。")
            return
        selected = editor.selectedText()
        if selected:
            editor.insert(f"\\{prefix}({selected})")
            return
        cached = self.last_text_selection.get(editor)
        if cached is not None:
            start, length, source_text = cached
            if length > 0 and editor.text() == source_text:
                editor.setSelection(start, length)
                editor.insert(f"\\{prefix}({editor.selectedText()})")
                self.last_text_selection.pop(editor, None)
                return
        if not selected:
            self.set_status("请先选中文本，再点击格式按钮。")
            return

    def insert_bold(self) -> None:
        self.insert_text_format("b")

    def insert_italic(self) -> None:
        self.insert_text_format("i")

    def insert_superscript(self) -> None:
        self.insert_text_format("+")

    def insert_subscript(self) -> None:
        self.insert_text_format("-")

    def apply_patch(self) -> None:
        try:
            patch = self.build_patch()
            if not patch.enabled_paths:
                QMessageBox.information(self, "没有启用项", "请至少启用一个要应用的格式项。")
                self.set_status("没有启用项。")
                return
        except Exception as exc:
            self.show_error("应用失败", exc)
            return

        def finish(result: object) -> None:
            if not isinstance(result, tuple) or len(result) != 2:
                raise TypeError("Origin worker returned an invalid apply result.")
            snapshot, apply_result = result
            if not isinstance(snapshot, StyleSnapshot) or not isinstance(apply_result, ApplyResult):
                raise TypeError("Origin worker 没有返回有效应用结果。")
            self.last_apply_snapshot = snapshot
            message = (
                f"已应用 {len(apply_result.applied)} 项到 {apply_result.target_name} / Layer {apply_result.layer_indices}，"
                f"失败 {len(apply_result.failed)} 项。"
            )
            self.set_status(message)
            if apply_result.failed:
                QMessageBox.warning(self, "部分格式应用失败", "\n".join(apply_result.failed))

        self.start_origin_task(
            "正在通过 Origin worker 应用格式...",
            lambda: self.origin_client.apply_patch(patch),
            finish,
            "应用失败",
        )

    def undo_last_apply(self) -> None:
        if self.last_apply_snapshot is None:
            QMessageBox.information(self, "没有可撤销状态", "还没有保存最近一次应用前状态。")
            self.set_status("没有可撤销状态。")
            return
        snapshot = self.last_apply_snapshot

        def finish(result: object) -> None:
            if not isinstance(result, ApplyResult):
                raise TypeError("Origin worker 没有返回有效撤销结果。")
            self.last_apply_snapshot = None
            message = (
                f"已撤销 {len(result.applied)} 项到 {result.target_name} / Layer {result.layer_indices}；"
                f"失败 {len(result.failed)} 项。"
            )
            self.set_status(message)
            if result.failed:
                QMessageBox.warning(self, "部分撤销失败", "\n".join(result.failed))

        self.start_origin_task(
            "正在通过 Origin worker 撤销上次应用...",
            lambda: self.origin_client.restore_style_snapshot(snapshot),
            finish,
            "撤销失败",
        )

    def choose_export_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录", self.exportDirEdit.text())
        if directory:
            self.exportDirEdit.setText(directory)

    def selected_export_formats(self) -> list[str]:
        formats = []
        if self.exportPngCheck.isChecked():
            formats.append("png")
        if self.exportPdfCheck.isChecked():
            formats.append("pdf")
        if self.exportSvgCheck.isChecked():
            formats.append("svg")
        if self.exportTiffCheck.isChecked():
            formats.append("tiff")
        return formats

    def export_active_graph(self) -> None:
        formats = self.selected_export_formats()
        if not formats:
            QMessageBox.information(self, "没有格式", "请至少选择一种导出格式。")
            self.set_status("没有选择导出格式。")
            return
        directory = Path(self.exportDirEdit.text().strip() or str(DEFAULT_EXPORT_DIR))
        self.exportDirEdit.setText(str(directory))
        width_px = self.exportWidthSpin.value()

        def finish(result: object) -> None:
            if not isinstance(result, list):
                raise TypeError("Origin worker 没有返回有效导出路径。")
            files = [Path(path) for path in result]
            self.set_status("已导出：" + "; ".join(str(path) for path in files))

        self.start_origin_task(
            "正在通过 Origin worker 导出当前图...",
            lambda: self.origin_client.export_active_graph(directory, formats, width_px),
            finish,
            "导出失败",
        )

    def set_status(self, message: str, timeout_ms: int = 6000) -> None:
        window = self.window()
        status_bar_getter = getattr(window, "statusBar", None)
        if callable(status_bar_getter):
            status_bar = status_bar_getter()
            if isinstance(status_bar, QStatusBar):
                status_bar.showMessage(message, timeout_ms)

    def show_error(self, title: str, exc: Exception) -> None:
        message = str(exc)
        if isinstance(exc, OriginWorkerError):
            detail = message
        else:
            detail = f"{type(exc).__name__}: {message}"
        self.set_status(f"{title}：{detail}", 8000)
        QMessageBox.critical(self, title, detail)

    def detach(self) -> None:
        if self._owns_origin_client:
            self.origin_client.shutdown()
