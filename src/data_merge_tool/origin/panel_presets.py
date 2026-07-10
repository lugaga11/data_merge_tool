from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .presets import DEFAULT_EXPORT_DIR, PRESETS, SCHEMA_VERSION, USER_PRESETS_PATH


class OriginPanelPresetsMixin:
    def load_selected_preset(self) -> None:
        name = self.presetCombo.currentText()
        if name not in self.all_presets():
            return
        self.load_preset_values(name)
        self.set_status(f"已载入预设：{name}。")

    def write_user_presets(self, presets: dict[str, dict[str, Any]]) -> bool:
        try:
            self.preset_store.save_atomic(presets)
        except Exception as exc:
            self.show_error("保存预设失败", exc)
            return False
        return True

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
        candidate = deepcopy(self.user_presets)
        candidate[name] = self.current_preset_values()
        if not self.write_user_presets(candidate):
            return
        self.user_presets = candidate
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
        candidate = deepcopy(self.user_presets)
        candidate.pop(name)
        if not self.write_user_presets(candidate):
            return
        self.user_presets = candidate
        self.refresh_preset_combo()
        self.set_status(f"已删除自定义预设：{name}")

    def import_presets_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入 preset JSON", str(USER_PRESETS_PATH.parent), "JSON Files (*.json)")
        if not path:
            return
        try:
            result = self.preset_store.load_import_file(Path(path))
            imported = {name: preset for name, preset in result.presets.items() if name not in PRESETS}
            if not imported:
                raise ValueError("没有可导入的自定义预设")
            candidate = deepcopy(self.user_presets)
            candidate.update(imported)
            if not self.write_user_presets(candidate):
                return
            self.user_presets = candidate
            self.refresh_preset_combo(next(iter(imported)))
            if result.errors:
                detail = "\n".join(f"{name}: {reason}" for name, reason in result.errors.items())
                QMessageBox.warning(self, "部分预设未导入", detail)
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
        target.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "presets": {name: preset}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.set_status(f"已导出预设：{target}")

    def load_preset_values(self, name: str) -> None:
        preset = self.preset_store.validate(deepcopy(self.all_presets()[name]))
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
