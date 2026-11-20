from __future__ import annotations

from typing import Optional

import pandas as pd
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# isort: split
# Load PySide6 first so Matplotlib selects the application's Qt binding.
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.backend_bases import MouseButton, MouseEvent
from matplotlib.figure import Figure

from ..data_types import OriginImportData
from .controls import make_button


class _PreviewToolbar(NavigationToolbar2QT):
    toolitems = (
        ("还原视图", "恢复初始坐标范围", "home", "home"),
        ("后退", "返回上一个视图", "back", "back"),
        ("前进", "前往下一个视图", "forward", "forward"),
        (None, None, None, None),
        ("平移", "拖动平移，再次点击退出", "move", "pan"),
        ("框选缩放", "拖出矩形放大，再次点击退出", "zoom_to_rect", "zoom"),
        ("保存图片", "保存当前图像", "filesave", "save_figure"),
    )


class PlotPreviewPanel(QWidget):
    """Render an already-built OriginImportData result with matplotlib."""

    plot_requested = Signal()
    status_message = Signal(str, int)
    information_requested = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        note = QLabel("绘图用于快速检查曲线趋势；保留单个 X 时共用 X，不保留时需勾选 X 列并按每个文件自己的 X 列绘制。")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        controls = QHBoxLayout()
        self.log_x_check = QCheckBox("Log X")
        self.log_y_check = QCheckBox("Log Y")
        self.legend_check = QCheckBox("显示图例")
        self.legend_check.setToolTip("绘图后，单击图例的线段或名称可隐藏或显示对应曲线。请先退出平移或缩放模式。")
        self.legend_check.setChecked(True)
        controls.addWidget(self.log_x_check)
        controls.addWidget(self.log_y_check)
        controls.addWidget(self.legend_check)
        controls.addStretch(1)
        self.plot_button = make_button("绘制当前结果", self.plot_requested.emit, "primary")
        controls.addWidget(self.plot_button)
        layout.addLayout(controls)

        self.figure = Figure(figsize=(7, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar = _PreviewToolbar(self.canvas, self)
        self.toolbar.setEnabled(False)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect("button_press_event", self._on_canvas_press)

    def _on_canvas_press(self, event: MouseEvent) -> None:
        if event.button != MouseButton.LEFT or self.toolbar.mode or not self.figure.axes:
            return
        axis = self.figure.axes[0]
        legend = axis.get_legend()
        if legend is None or not legend.contains(event)[0]:
            return
        for line, sample, label in zip(axis.lines, legend.get_lines(), legend.get_texts(), strict=True):
            if sample.contains(event)[0] or label.contains(event)[0]:
                visible = not line.get_visible()
                line.set_visible(visible)
                sample.set_alpha(line.get_alpha() if visible else 0.3)
                label.set_alpha(1.0 if visible else 0.4)
                self.canvas.draw_idle()
                return

    def render_origin_data(self, origin_data: OriginImportData) -> bool:
        dataframe = origin_data.dataframe
        if dataframe.empty:
            self.information_requested.emit("无数据", "当前合并结果为空，无法绘图。")
            return False

        axis_spec = origin_data.axis_spec
        if len(axis_spec) != dataframe.shape[1] or "x" not in axis_spec:
            self.information_requested.emit("无 X 数据", "当前导入数据中没有可用于绘图的 X 列。")
            return False

        if "y" in axis_spec.partition("x")[0]:
            self.information_requested.emit("无 X 数据", "当前导入数据的 Y 列前没有对应的 X 列。")
            return False
        if "y" not in axis_spec:
            self.information_requested.emit("无 Y 数据", "没有可绘制的 Y 列。")
            return False

        self.figure.clear()
        self.toolbar.update()
        axis = self.figure.add_subplot(111)
        axis.set_facecolor("#fbfcfe")
        axis.grid(True, color="#e2e8f0", linewidth=0.8)

        numeric = dataframe.apply(pd.to_numeric, errors="coerce")
        current_x: Optional[pd.Series] = None
        x_label = "X"
        line_count = 0

        for column_index, axis_role in enumerate(axis_spec):
            column_name = str(dataframe.columns[column_index])
            if axis_role == "x":
                current_x = numeric.iloc[:, column_index]
                if x_label == "X":
                    x_label = column_name
                continue
            if axis_role != "y":
                continue
            assert current_x is not None
            axis.plot(
                current_x,
                numeric.iloc[:, column_index],
                linewidth=1.2,
                alpha=0.9,
                label=column_name,
            )
            line_count += 1

        axis.set_xlabel(x_label)
        axis.set_ylabel("Y")
        axis.set_title("Merged Data Preview" if axis_spec.count("x") <= 1 else "Per-file X Data Preview")
        self._finish_plot(axis, line_count)
        self.toolbar.setEnabled(True)
        return True

    def set_action_enabled(self, enabled: bool) -> None:
        self.plot_button.setEnabled(enabled)

    def _finish_plot(self, axis, line_count: int) -> None:
        if self.log_x_check.isChecked():
            axis.set_xscale("log")
        if self.log_y_check.isChecked():
            axis.set_yscale("log")

        message = f"绘图已更新：{line_count} 条曲线。"
        if self.legend_check.isChecked():
            if line_count <= 30:
                # Older Matplotlib versions omit labels beginning with an underscore.
                legend = axis.legend(axis.lines, [" "] * line_count, loc="best", fontsize=8)
                for text, line in zip(legend.get_texts(), axis.lines, strict=True):
                    text.set_text(line.get_label())
                message += " 单击图例可切换曲线显隐。"
            else:
                message += " 曲线数量超过 30，已自动隐藏图例。"

        self.canvas.draw_idle()
        self.status_message.emit(message, 5000)
