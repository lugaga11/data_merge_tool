from __future__ import annotations

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

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._reference_path: Optional[Path] = None
        self._detection_signature: Optional[tuple[str, str, str, int, bool]] = None
        self._detection: Optional[ReadDetection] = None
        self._updating_controls = False
        self._build_ui()
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
            self.delimiter_box,
            self.encoding_mode_box,
            self.encoding_box,
        ):
            combo.currentIndexChanged.connect(self._on_settings_changed)
        self.skip_spin.valueChanged.connect(self._on_settings_changed)
        self.header_check.stateChanged.connect(self._on_settings_changed)
        self.skip_bad_check.stateChanged.connect(self._on_settings_changed)

    def set_reference_path(self, path: Optional[Path]) -> None:
        normalized = Path(path) if path is not None else None
        if normalized == self._reference_path:
            return
        self._reference_path = normalized
        self.invalidate_detection()

    def reference_path(self) -> Optional[Path]:
        return self._reference_path

    def invalidate_detection(self) -> None:
        self._detection_signature = None
        self._detection = None

    def current_detection(self) -> ReadDetection:
        fallback = ReadDetection(
            skip_rows=self.skip_spin.value(),
            delimiter_label=self.delimiter_box.currentText(),
            encoding_label=self.encoding_box.currentText(),
            has_header=self.header_check.isChecked(),
            confident=False,
            message="未选择预览文件，继续使用手动读入设置。",
        )
        if self._reference_path is None:
            return fallback

        signature = self._current_detection_signature()
        if signature != self._detection_signature or self._detection is None:
            self._detection = detect_read_options(
                self._reference_path,
                self._detection_delimiter_label(),
                self._detection_encoding_label(),
                self.skip_spin.value(),
                self.header_check.isChecked(),
            )

        self._apply_detection(self._detection)
        # Auto detection updates disabled controls to show the detected values.
        # Cache that displayed state so a second read does not immediately
        # repeat the same file probe.
        self._detection_signature = self._current_detection_signature()
        return self._detection

    def current_options(self) -> ReadOptions:
        detection = self.current_detection()
        use_auto_skip = self.skip_mode_box.currentText() == "自动" and detection.confident
        use_auto_header = self.header_mode_box.currentText() == "自动" and detection.confident
        use_auto_delimiter = self.delimiter_mode_box.currentText() == "自动" and detection.confident
        use_auto_encoding = self.encoding_mode_box.currentText() == "自动"
        return ReadOptions(
            skip_rows=detection.skip_rows if use_auto_skip else self.skip_spin.value(),
            delimiter_label=(
                detection.delimiter_label if use_auto_delimiter else self.delimiter_box.currentText()
            ),
            encoding_label=detection.encoding_label if use_auto_encoding else self.encoding_box.currentText(),
            has_header=detection.has_header if use_auto_header else self.header_check.isChecked(),
            skip_bad_lines=self.skip_bad_check.isChecked(),
        )

    def _detection_delimiter_label(self) -> str:
        return "自动" if self.delimiter_mode_box.currentText() == "自动" else self.delimiter_box.currentText()

    def _detection_encoding_label(self) -> str:
        return "自动" if self.encoding_mode_box.currentText() == "自动" else self.encoding_box.currentText()

    def _current_detection_signature(self) -> tuple[str, str, str, int, bool]:
        assert self._reference_path is not None
        return (
            str(self._reference_path),
            self._detection_delimiter_label(),
            self._detection_encoding_label(),
            self.skip_spin.value(),
            self.header_check.isChecked(),
        )

    def _apply_detection(self, detection: ReadDetection) -> None:
        self._updating_controls = True
        try:
            if self.skip_mode_box.currentText() == "自动" and detection.confident:
                self.skip_spin.setValue(detection.skip_rows)
            if self.header_mode_box.currentText() == "自动" and detection.confident:
                self.header_check.setChecked(detection.has_header)
            if self.delimiter_mode_box.currentText() == "自动" and detection.confident:
                self._add_or_select_combo_text(self.delimiter_box, detection.delimiter_label)
            if self.encoding_mode_box.currentText() == "自动" and detection.encoding_label:
                self._add_or_select_combo_text(self.encoding_box, detection.encoding_label)
            self._sync_control_state()
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
        if self._updating_controls:
            return
        self.invalidate_detection()
        self._sync_control_state()
        self.options_changed.emit()
