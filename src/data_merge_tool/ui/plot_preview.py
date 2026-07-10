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

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except Exception:
    FigureCanvas = None
    Figure = None
    MATPLOTLIB_AVAILABLE = False

from ..constants import ALIGN_CENTER
from ..data_types import OriginImportData
from .controls import make_button


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
        self.legend_check.setChecked(True)
        controls.addWidget(self.log_x_check)
        controls.addWidget(self.log_y_check)
        controls.addWidget(self.legend_check)
        controls.addStretch(1)
        self.plot_button = make_button("绘制当前结果", self.plot_requested.emit, "primary")
        controls.addWidget(self.plot_button)
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

    def is_available(self) -> bool:
        return MATPLOTLIB_AVAILABLE and self.figure is not None and self.canvas is not None

    def render_origin_data(self, origin_data: OriginImportData) -> bool:
        if not self.is_available():
            self.information_requested.emit("绘图不可用", "当前环境未安装 matplotlib。")
            return False

        dataframe = origin_data.dataframe
        if dataframe.empty:
            self.information_requested.emit("无数据", "当前合并结果为空，无法绘图。")
            return False

        axis_spec = origin_data.axis_spec
        if len(axis_spec) != dataframe.shape[1] or "x" not in axis_spec:
            self.information_requested.emit("无 X 数据", "当前导入数据中没有可用于绘图的 X 列。")
            return False

        assert self.figure is not None
        self.figure.clear()
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
            if current_x is None:
                self.information_requested.emit("无 X 数据", "当前导入数据的 Y 列前没有对应的 X 列。")
                return False
            axis.plot(
                current_x,
                numeric.iloc[:, column_index],
                linewidth=1.2,
                alpha=0.9,
                label=column_name,
            )
            line_count += 1

        if line_count == 0:
            self.information_requested.emit("无 Y 数据", "没有可绘制的 Y 列。")
            return False

        axis.set_xlabel(x_label)
        axis.set_ylabel("Y")
        axis.set_title("Merged Data Preview" if axis_spec.count("x") <= 1 else "Per-file X Data Preview")
        self._finish_plot(axis, line_count)
        return True

    def clear(self) -> None:
        if self.figure is None or self.canvas is None:
            return
        self.figure.clear()
        self.canvas.draw_idle()

    def set_action_enabled(self, enabled: bool) -> None:
        self.plot_button.setEnabled(enabled)

    def _finish_plot(self, axis, line_count: int) -> None:
        if self.canvas is None:
            return
        if self.log_x_check.isChecked():
            axis.set_xscale("log")
        if self.log_y_check.isChecked():
            axis.set_yscale("log")

        if self.legend_check.isChecked():
            if line_count <= 30:
                axis.legend(loc="best", fontsize=8)
            else:
                self.status_message.emit("曲线数量超过 30，已自动隐藏图例。", 5000)

        self.canvas.draw_idle()
        self.status_message.emit(f"绘图已更新：{line_count} 条曲线。", 4000)
