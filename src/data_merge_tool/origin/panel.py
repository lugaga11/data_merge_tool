from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
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
from .client import OriginWorkerClient
from .panel_actions import OriginPanelActionsMixin
from .panel_presets import OriginPanelPresetsMixin
from .protocol import GraphInfo, OriginWorkerError, StyleSnapshot
from .presets import DEFAULT_EXPORT_DIR, USER_PRESETS_PATH, PresetStore
from .style_registry import STYLE_FIELDS
from ..ui.task_runner import TaskRunner, TaskSpec
from ..ui.controls import (
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


class OriginPanelWidget(OriginPanelPresetsMixin, OriginPanelActionsMixin, QWidget):
    def __init__(
        self,
        origin_client: OriginWorkerClient | None = None,
        task_runner: TaskRunner | None = None,
    ) -> None:
        super().__init__()

        self.origin_client = origin_client or OriginWorkerClient()
        self._owns_origin_client = origin_client is None
        self.task_runner = task_runner or TaskRunner(
            self,
            busy_changed=lambda busy: self.setEnabled(not busy),
            message_handler=lambda message, timeout=0: self.set_status(message, timeout),
            error_handler=self._handle_origin_task_error,
            queue_when_busy=True,
        )
        self.path_checks: dict[str, QCheckBox] = {}
        self.last_text_editor: QLineEdit | None = None
        self.last_text_selection: dict[QLineEdit, tuple[int, int, str]] = {}
        self.preset_store = PresetStore(USER_PRESETS_PATH)
        preset_load = self.preset_store.load()
        self.user_presets: dict[str, dict[str, Any]] = preset_load.presets
        self._preset_load_warning = preset_load.warning
        self.last_apply_snapshot: StyleSnapshot | None = None

        self._build_ui()
        self.refresh_preset_combo()
        if self.presetCombo.count():
            self.load_preset_values(self.presetCombo.currentText())
        self.clear_enabled_checks(show_status=False)
        if self._preset_load_warning:
            self.set_status(self._preset_load_warning, 10000)
        else:
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
        if path not in STYLE_FIELDS:
            raise KeyError(f"未注册的 Origin 样式字段：{path}")
        check = QCheckBox(text)
        check.setToolTip(path)
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
    ) -> bool:
        return self.task_runner.run(TaskSpec(message=message, error_title=error_title), work, on_success)

    def _handle_origin_task_error(self, spec: TaskSpec, error: object) -> None:
        self.show_error(spec.error_title, error if isinstance(error, Exception) else RuntimeError(str(error)))

    def has_active_origin_task(self) -> bool:
        return self.task_runner.has_active_task()

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
        self.last_apply_snapshot = None
        self.layerCombo.clear()
        self.graphInfoLabel.setText("未读取到当前图。")
        self._set_widget_state(self.graphInfoLabel, "empty")
        self.update_enabled_summary()

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
        override_cursor = QApplication.overrideCursor()
        wait_cursor_active = override_cursor is not None and override_cursor.shape() == Qt.CursorShape.WaitCursor
        if wait_cursor_active:
            QApplication.setOverrideCursor(Qt.CursorShape.ArrowCursor)
        try:
            QMessageBox.critical(self, title, detail)
        finally:
            if wait_cursor_active:
                QApplication.restoreOverrideCursor()

    def detach(self) -> None:
        if self._owns_origin_client:
            self.origin_client.shutdown()
