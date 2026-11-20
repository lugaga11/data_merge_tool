from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel, QWidget

from ..data_reading.detection import detect_read_options
from ..data_types import ReadDetection, ReadOptions
from .controls import NoWheelComboBox, NoWheelSpinBox


class ReadOptionsPanel(QGroupBox):
    """Own read-option controls and detection state for one reference file."""

    options_changed = Signal()
    status_message = Signal(str, int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._reference_path: Optional[Path] = None
        self._detection: Optional[ReadDetection] = None
        self._updating_controls = False
        self._build_ui()
        self._manual_options = self._control_options()
        self._connect_signals()
        self._sync_control_state()

    def _build_ui(self) -> None:
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 10, 10, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)

        self.skip_spin = NoWheelSpinBox()
        self.skip_spin.setRange(0, 9999)
        self.skip_spin.setToolTip("手动模式下从文件开头跳过的行数；自动模式下显示识别结果。")

        self.skip_mode_box = NoWheelComboBox()
        self.skip_mode_box.addItems(["自动", "手动"])
        self.skip_mode_box.setToolTip("自动按当前预览文件识别数据起点；手动使用右侧数值。")

        self.delimiter_box = NoWheelComboBox()
        self.delimiter_box.addItems(["自动", "逗号 ,", "Tab", "空格/连续空白", "分号 ;"])

        self.delimiter_mode_box = NoWheelComboBox()
        self.delimiter_mode_box.addItems(["自动", "手动"])
        self.delimiter_mode_box.setToolTip("自动识别分隔符；手动使用右侧选择。")

        self.encoding_box = NoWheelComboBox()
        self.encoding_box.addItems(["自动", "utf-8", "utf-8-sig", "ANSI/系统默认", "gbk", "cp950", "latin1"])

        self.encoding_mode_box = NoWheelComboBox()
        self.encoding_mode_box.addItems(["自动", "手动"])
        self.encoding_mode_box.setToolTip("自动识别编码；手动使用右侧选择。")

        self.header_mode_box = NoWheelComboBox()
        self.header_mode_box.addItems(["自动", "手动"])
        self.header_mode_box.setToolTip("自动识别表头；不可靠时退回手动勾选状态。")

        for mode_box in (
            self.header_mode_box,
            self.skip_mode_box,
            self.delimiter_mode_box,
            self.encoding_mode_box,
        ):
            mode_box.setMinimumWidth(93)

        self.header_check = QCheckBox("第一行为表头")
        self.header_check.setChecked(True)

        self.skip_bad_check = QCheckBox("跳过异常行")
        self.skip_bad_check.setChecked(True)
        self.skip_bad_check.setToolTip("读取文本数据时跳过数据区内没有任何数值的尾标、空行或纯文本行。")

        grid.addWidget(QLabel("表头"), 0, 0)
        grid.addWidget(self.header_mode_box, 0, 1)
        grid.addWidget(self.header_check, 0, 2)
        grid.addWidget(QLabel("跳过行"), 1, 0)
        grid.addWidget(self.skip_mode_box, 1, 1)
        grid.addWidget(self.skip_spin, 1, 2)
        grid.addWidget(QLabel("分隔符"), 2, 0)
        grid.addWidget(self.delimiter_mode_box, 2, 1)
        grid.addWidget(self.delimiter_box, 2, 2)
        grid.addWidget(QLabel("编码"), 3, 0)
        grid.addWidget(self.encoding_mode_box, 3, 1)
        grid.addWidget(self.encoding_box, 3, 2)
        grid.addWidget(self.skip_bad_check, 4, 0, 1, 3)

    def _connect_signals(self) -> None:
        for combo in (
            self.skip_mode_box,
            self.header_mode_box,
            self.delimiter_mode_box,
            self.encoding_mode_box,
        ):
            combo.currentIndexChanged.connect(self._on_settings_changed)
        self.skip_spin.valueChanged.connect(lambda rows: self._set_manual_option(skip_rows=rows))
        self.header_check.toggled.connect(lambda checked: self._set_manual_option(has_header=checked))
        self.delimiter_box.currentTextChanged.connect(lambda text: self._set_manual_option(delimiter_label=text))
        self.encoding_box.currentTextChanged.connect(lambda text: self._set_manual_option(encoding_label=text))
        self.skip_bad_check.toggled.connect(lambda checked: self._set_manual_option(skip_bad_lines=checked))

    def set_reference_path(self, path: Optional[Path]) -> None:
        normalized = Path(path) if path is not None else None
        if normalized == self._reference_path:
            return
        self._reference_path = normalized
        self.invalidate_detection()

    def invalidate_detection(self) -> None:
        self._detection = None
        self._display_options(self._manual_options)

    def current_detection(self) -> ReadDetection:
        manual = self._manual_options
        if self._reference_path is None:
            return ReadDetection(
                skip_rows=manual.skip_rows,
                delimiter_label=manual.delimiter_label,
                encoding_label=manual.encoding_label,
                has_header=manual.has_header,
                confident=False,
                message="未选择预览文件，继续使用手动读入设置。",
            )

        if self._detection is not None:
            return self._detection

        auto_delimiter = self.delimiter_mode_box.currentText() == "自动"
        auto_encoding = self.encoding_mode_box.currentText() == "自动"
        auto_skip = self.skip_mode_box.currentText() == "自动"
        auto_header = self.header_mode_box.currentText() == "自动"
        detected = detect_read_options(
            self._reference_path,
            "自动" if auto_delimiter else manual.delimiter_label,
            "自动" if auto_encoding else manual.encoding_label,
            manual.skip_rows,
            manual.has_header,
        )
        self._detection = detected
        self._display_options(
            ReadOptions(
                skip_rows=detected.skip_rows if auto_skip and detected.confident else manual.skip_rows,
                delimiter_label=(
                    detected.delimiter_label if auto_delimiter and detected.confident else manual.delimiter_label
                ),
                encoding_label=detected.encoding_label if auto_encoding else manual.encoding_label,
                has_header=detected.has_header if auto_header and detected.confident else manual.has_header,
                skip_bad_lines=manual.skip_bad_lines,
            )
        )
        if not detected.confident and (auto_skip or auto_header or auto_delimiter):
            self.status_message.emit(f"{self._reference_path.name}：{detected.message}", 8000)
        return detected

    def current_options(self) -> ReadOptions:
        self.current_detection()
        return self._control_options()

    def _control_options(self) -> ReadOptions:
        return ReadOptions(
            skip_rows=self.skip_spin.value(),
            delimiter_label=self.delimiter_box.currentText(),
            encoding_label=self.encoding_box.currentText(),
            has_header=self.header_check.isChecked(),
            skip_bad_lines=self.skip_bad_check.isChecked(),
        )

    def _set_manual_option(self, **changes: object) -> None:
        if not self._updating_controls:
            self._manual_options = replace(self._manual_options, **changes)
            self._on_settings_changed()

    def _display_options(self, options: ReadOptions) -> None:
        self._updating_controls = True
        try:
            self.skip_spin.setValue(options.skip_rows)
            self.header_check.setChecked(options.has_header)
            self._add_or_select_combo_text(self.delimiter_box, options.delimiter_label)
            self._add_or_select_combo_text(self.encoding_box, options.encoding_label)
        finally:
            self._updating_controls = False

    @staticmethod
    def _add_or_select_combo_text(combo: NoWheelComboBox, text: str) -> None:
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index)

    def _sync_control_state(self) -> None:
        self.skip_spin.setEnabled(self.skip_mode_box.currentText() == "手动")
        self.header_check.setEnabled(self.header_mode_box.currentText() == "手动")
        self.delimiter_box.setEnabled(self.delimiter_mode_box.currentText() == "手动")
        self.encoding_box.setEnabled(self.encoding_mode_box.currentText() == "手动")

    def _on_settings_changed(self, *_args) -> None:
        self.invalidate_detection()
        self._sync_control_state()
        self.options_changed.emit()
