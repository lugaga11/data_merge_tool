from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QLineEdit,
    QMessageBox,
)

from .panel_contract import OriginPanelContract
from .presets import DEFAULT_EXPORT_DIR
from .protocol import ApplyResult, FigureStylePatch, PatchTarget, StyleSnapshot
from .style_registry import filter_known_style_paths


LEGEND_LINE_SEPARATOR = " | "


class OriginPanelActionsMixin(OriginPanelContract):
    def selected_enabled_paths(self) -> list[str]:
        return sorted(path for path, check in self.path_checks.items() if check.isChecked())

    def apply_enabled_paths(self, enabled_paths: object) -> None:
        enabled = set(filter_known_style_paths(enabled_paths))
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
        self.formatSummaryLabel.setText(summary)
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

        def finish(result: dict[str, Any]) -> None:
            self.apply_readback_style(result)
            self.set_status(f"已读取 Layer {layer_index} 的可回读设置；未自动启用任何格式项。")

        self.start_origin_task(
            "正在通过 Origin worker 读取样式...",
            lambda: self.origin_client.read_active_layer_style(layer_index),
            finish,
            "读取设置失败",
        )

    def apply_readback_style(self, style: dict[str, Any]) -> None:
        page = style["page"]
        self.set_spin_if_number(self.pageWidthSpin, page["width_in"])
        self.set_spin_if_number(self.pageHeightSpin, page["height_in"])
        if page["anti_alias"] is not None:
            self.pageAntiAliasCheck.setChecked(bool(page["anti_alias"]))

        layer = style["layer"]
        self.set_spin_if_number(self.layerLeftSpin, layer["left_in"])
        self.set_spin_if_number(self.layerTopSpin, layer["top_in"])
        self.set_spin_if_number(self.layerWidthSpin, layer["width_in"])
        self.set_spin_if_number(self.layerHeightSpin, layer["height_in"])
        self.set_spin_if_number(self.layerLineWidthSpin, layer["line_width_pt"])
        self.set_spin_if_number(self.scaleFactorSpin, layer["scale_factor"])
        if layer["scale_fixed"] is not None:
            self.scaleFixedCheck.setChecked(bool(layer["scale_fixed"]))
        frame = layer["frame"]
        for key, checkbox in (
            ("left", self.frameLeftCheck), ("bottom", self.frameBottomCheck),
            ("top", self.frameTopCheck), ("right", self.frameRightCheck),
        ):
            if frame[key] is not None:
                checkbox.setChecked(frame[key])

        text = style["text"]
        self.xTitleEdit.setText(self._display_text_to_edit_text(str(text["x_title"] or "")))
        self.yTitleEdit.setText(self._display_text_to_edit_text(str(text["y_title"] or "")))
        self.legendTextEdit.setText(
            self._legend_readback_to_edit_text(
                str(text["legend_text"] or ""),
                str(text["legend_text_raw"] or ""),
            )
        )
        self.set_spin_if_number(self.axisTitleSizeSpin, text["title_font_size_pt"])
        self.set_spin_if_number(self.axisTickSizeSpin, text["tick_font_size_pt"])
        self.set_spin_if_number(self.legendFontSizeSpin, text["legend_font_size_pt"])

        axis = style["axis"]
        if axis["x_scale"] in {"keep", "linear", "log10"}:
            self._set_combo_value(self.xScaleCombo, axis["x_scale"])
        if axis["y_scale"] in {"keep", "linear", "log10"}:
            self._set_combo_value(self.yScaleCombo, axis["y_scale"])
        if axis["show_grid"] is not None:
            self.gridCheck.setChecked(bool(axis["show_grid"]))

        plot = style["plot"]
        self.set_spin_if_number(self.lineWidthSpin, plot["line_width_pt"])
        self.set_spin_if_number(self.symbolSizeSpin, plot["symbol_size_pt"])

        legend = style["legend"]
        visibility = legend["visibility"]
        if visibility == 1:
            self._set_combo_value(self.legendVisibilityCombo, "show")
        elif visibility == 0:
            self._set_combo_value(self.legendVisibilityCombo, "hide")
        if legend["frame"] is not None:
            self.legendFrameCheck.setChecked(bool(legend["frame"]))

    @staticmethod
    def set_spin_if_number(spin: QDoubleSpinBox, value: object) -> None:
        if isinstance(value, (int, float)):
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

        def finish(result: tuple[StyleSnapshot, ApplyResult]) -> None:
            snapshot, apply_result = result
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

        def finish(result: ApplyResult) -> None:
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

        def finish(files: list[Path]) -> None:
            self.set_status("已导出：" + "; ".join(str(path) for path in files))

        self.start_origin_task(
            "正在通过 Origin worker 导出当前图...",
            lambda: self.origin_client.export_active_graph(directory, formats, width_px),
            finish,
            "导出失败",
        )
