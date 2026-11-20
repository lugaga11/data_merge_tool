from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from matplotlib import rc_context
from matplotlib.backend_bases import MouseButton, MouseEvent

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.data_types import OriginImportData, ReadDetection, ReadOptions
from data_merge_tool.origin.client import OriginWorkerClient
from data_merge_tool.origin.panel import OriginPanelWidget
from data_merge_tool.ui.file_queue import FileQueuePanel
from data_merge_tool.ui.main_window import MainWindow
from data_merge_tool.ui.merge_panel import MergePanel
from data_merge_tool.ui.plot_preview import PlotPreviewPanel
from data_merge_tool.ui.preview_panel import PreviewPanel
from data_merge_tool.ui.read_options_panel import ReadOptionsPanel
from data_merge_tool.ui.task_runner import TaskRunner


class UiComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_file_queue_owns_files_but_only_reports_dropped_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            path10 = folder / "sample10.csv"
            path2 = folder / "sample2.csv"
            unsupported = folder / "notes.md"
            for path in (path10, path2, unsupported):
                path.write_text("x,y\n1,2\n", encoding="utf-8")

            panel = FileQueuePanel()
            statuses: list[tuple[str, int]] = []
            queue_changes: list[None] = []
            dropped: list[list[str]] = []
            panel.status_message.connect(lambda text, timeout: statuses.append((text, timeout)))
            panel.queue_changed.connect(lambda: queue_changes.append(None))
            panel.paths_dropped.connect(dropped.append)
            try:
                panel.add_paths([str(path10), str(unsupported), str(path2)])

                self.assertEqual(panel.all_paths(), [str(path2), str(path10)])
                self.assertEqual(panel.checked_paths(), [str(path2), str(path10)])
                self.assertEqual(panel.file_count_label.text(), "2 个文件")
                self.assertEqual(len(queue_changes), 1)
                self.assertIn("已添加 2 个文件", statuses[-1][0])

                panel.clear_checks()
                self.assertEqual(panel.checked_paths(), [])
                panel.select_all()
                self.assertEqual(panel.checked_paths(), [str(path2), str(path10)])

                panel.file_list.paths_dropped.emit([str(folder)])
                self.assertEqual(dropped, [[str(folder)]])
                self.assertEqual(panel.all_paths(), [str(path2), str(path10)])
            finally:
                panel.close()

    def test_origin_layer_buttons_select_exactly_the_requested_patch_target(self) -> None:
        panel = OriginPanelWidget(OriginWorkerClient(), TaskRunner(queue_when_busy=True))
        radios = [panel.allLayersRadio, panel.singleLayerRadio, panel.customLayersRadio]
        try:
            panel.layerCombo.addItems(["Layer 1", "Layer 2", "Layer 3"])
            panel.layerCombo.setCurrentIndex(1)
            panel.customLayersEdit.setText("1,3")
            self.assertEqual([button for button in radios if button.isChecked()], [panel.singleLayerRadio])
            for button, scope, indices in (
                (panel.customLayersRadio, "selected", [1, 3]),
                (panel.allLayersRadio, "all", []),
                (panel.singleLayerRadio, "selected", [2]),
            ):
                button.click()
                self.assertEqual([radio for radio in radios if radio.isChecked()], [button])
                target = panel.build_patch().target
                self.assertEqual((target.layer_scope, target.layer_indices), (scope, indices))
        finally:
            panel.close()

    def test_origin_error_dialog_temporarily_uses_arrow_cursor(self) -> None:
        panel = OriginPanelWidget(OriginWorkerClient(), TaskRunner(queue_when_busy=True))
        cursor_shapes: list[Qt.CursorShape] = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            with patch.object(
                QMessageBox,
                "critical",
                side_effect=lambda *_args: cursor_shapes.append(QApplication.overrideCursor().shape()),
            ):
                panel.show_error("绘图失败", RuntimeError("没有选择工作表"))

            self.assertEqual(cursor_shapes, [Qt.CursorShape.ArrowCursor])
            override_cursor = QApplication.overrideCursor()
            self.assertIsNotNone(override_cursor)
            assert override_cursor is not None
            self.assertEqual(override_cursor.shape(), Qt.CursorShape.WaitCursor)
        finally:
            QApplication.restoreOverrideCursor()
            panel.close()

    def test_read_options_panel_caches_detection_and_invalidates_on_path_change(self) -> None:
        first = Path("first.csv")
        second = Path("second.csv")
        detected = ReadDetection(
            skip_rows=3,
            delimiter_label="Tab",
            encoding_label="utf-8",
            has_header=False,
            confident=True,
            message="已识别",
        )

        panel = ReadOptionsPanel()
        changes: list[None] = []
        panel.options_changed.connect(lambda: changes.append(None))
        try:
            with patch(
                "data_merge_tool.ui.read_options_panel.detect_read_options",
                return_value=detected,
            ) as detector:
                panel.set_reference_path(first)
                first_options = panel.current_options()
                second_options = panel.current_options()
                self.assertEqual(detector.call_count, 1)
                self.assertEqual(first_options, second_options)
                self.assertEqual(first_options.skip_rows, 3)
                self.assertEqual(first_options.delimiter_label, "Tab")
                self.assertEqual(first_options.encoding_label, "utf-8")
                self.assertFalse(first_options.has_header)
                self.assertTrue(first_options.skip_bad_lines)

                panel.set_reference_path(second)
                panel.current_options()
                self.assertEqual(detector.call_count, 2)

            panel.skip_mode_box.setCurrentText("手动")
            self.assertEqual(panel.skip_spin.value(), 0)
            panel.skip_spin.setValue(7)
            self.assertTrue(panel.skip_spin.isEnabled())
            self.assertGreaterEqual(len(changes), 1)
        finally:
            panel.close()

    def test_unconfident_preview_uses_saved_manual_settings_and_shows_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / "a.csv"
            first.write_text("仪器设置\n" * 30 + "x,y\n0,10\n1,20\n2,30\n", encoding="utf-8")
            second = Path(folder) / "b.txt"
            second.write_text("单列测量\n" + "\n".join(map(str, range(50))), encoding="utf-8")

            window = MainWindow()
            panel = window.read_options_panel
            try:
                modes = (
                    panel.skip_mode_box, panel.header_mode_box, panel.delimiter_mode_box, panel.encoding_mode_box
                )
                for mode in modes:
                    mode.setCurrentText("手动")
                panel.skip_spin.setValue(1)
                panel.header_check.setChecked(False)
                panel.delimiter_box.setCurrentText("Tab")
                panel.encoding_box.setCurrentText("latin1")
                for mode in modes:
                    mode.setCurrentText("自动")

                window.file_queue.add_paths([str(first), str(second)])
                self.assertEqual(panel.current_options(), ReadOptions(30, "逗号 ,", "utf-8", True, True))
                window.file_queue.file_list.setCurrentRow(1)
                self.assertEqual(panel.current_options(), ReadOptions(1, "Tab", "自动", False, True))
                model = window.preview_panel.input_model
                self.assertEqual((model.rowCount(), model.columnCount()), (50, 1))
                self.assertEqual(model._df.iloc[:, 0].tolist(), list(range(50)))
                self.assertIn("b.txt：未能可靠识别", window.statusBar().currentMessage())

                window.file_queue.file_list.setCurrentRow(0)
                for mode in modes:
                    mode.setCurrentText("手动")
                self.assertEqual(panel.current_options(), ReadOptions(1, "Tab", "latin1", False, True))
            finally:
                window.close()

    def test_merge_panel_maps_state_without_reading_files(self) -> None:
        panel = MergePanel()
        read_options = ReadOptions(
            skip_rows=2,
            delimiter_label="Tab",
            encoding_label="utf-8",
            has_header=True,
            skip_bad_lines=True,
        )
        try:
            panel.set_columns("sample.csv", ["x", "a", "b"])
            panel.select_all_y()
            self.assertEqual(panel.selected_y_columns(), [1, 2])

            options = panel.current_options(read_options)
            self.assertIsNotNone(options)
            assert options is not None
            self.assertEqual(options.read, read_options)
            self.assertEqual(options.x_column, 1)
            self.assertEqual(options.y_columns, [1, 2])
            self.assertTrue(options.keep_single_x)
            self.assertTrue(panel.selected_only())

            panel.keep_x_check.setChecked(False)
            self.assertEqual(panel.selected_y_columns(), [0, 1, 2])
            self.assertFalse(panel.validate_x_check.isEnabled())

            panel.set_data_actions_enabled(False)
            self.assertFalse(panel.preview_button.isEnabled())
            self.assertFalse(panel.copy_button.isEnabled())
            self.assertFalse(panel.export_button.isEnabled())
            self.assertTrue(panel.origin_button.isEnabled())
            panel.set_origin_action_enabled(False)
            self.assertFalse(panel.origin_button.isEnabled())
        finally:
            panel.close()

    def test_preview_panel_only_updates_models_and_titles(self) -> None:
        panel = PreviewPanel()
        input_data = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        output_data = pd.DataFrame({"merged": [5]})
        try:
            panel.set_input(input_data, "输入完成")
            panel.set_output(output_data, "合并完成")
            self.assertIs(panel.input_model._df, input_data)
            self.assertEqual(panel.input_model.rowCount(), 2)
            self.assertEqual(panel.input_title.text(), "输入完成")
            self.assertEqual(panel.output_model.rowCount(), 1)
            self.assertEqual(panel.output_title.text(), "合并完成")

            panel.clear_input()
            panel.reset_output()
            self.assertEqual(panel.input_model.rowCount(), 0)
            self.assertEqual(panel.output_model.rowCount(), 0)
            self.assertIn("合并结果未生成", panel.output_title.text())
        finally:
            panel.close()

    def test_preview_legend_clicks_toggle_matching_line_after_redraw(self) -> None:
        panel = PlotPreviewPanel()
        self.addCleanup(panel.close)
        frame = pd.DataFrame([[0, 2, 4], [1, 3, 5]], columns=["x", "_signal", "_signal"])
        data = OriginImportData(frame, "xyy", [], [], "sample")

        def click(artist) -> None:
            box = artist.get_window_extent(panel.canvas.get_renderer())
            event = MouseEvent("button_press_event", panel.canvas, *box.get_points().mean(axis=0), MouseButton.LEFT)
            panel.canvas.callbacks.process(event.name, event)
            up = MouseEvent("button_release_event", panel.canvas, event.x, event.y, MouseButton.LEFT)
            panel.canvas.callbacks.process(up.name, up)

        for _ in range(2):
            self.assertTrue(panel.render_origin_data(data))
            panel.canvas.draw()
            axis = panel.figure.axes[0]
            legend = axis.get_legend()
            self.assertEqual([t.get_text() for t in legend.get_texts()], ["_signal", "_signal"])
            click(legend.get_texts()[1])
            self.assertTrue(axis.lines[0].get_visible())
            self.assertFalse(axis.lines[1].get_visible())
            self.assertLess(legend.get_texts()[1].get_alpha(), 1)
            click(legend.get_lines()[1])
            self.assertTrue(axis.lines[1].get_visible())

    def test_preview_toolbar_zoom_pan_restore_and_save(self) -> None:
        panel = PlotPreviewPanel()
        self.addCleanup(panel.close)
        data = OriginImportData(pd.DataFrame({"x": [0, 10], "y": [0, 10]}), "xy", [], [], "test")
        self.assertTrue(panel.render_origin_data(data))
        panel.canvas.draw()
        actions = {action.text(): action for action in panel.toolbar.actions()}
        axis = panel.figure.axes[0]
        original = axis.get_xlim()

        def drag(start, end) -> None:
            for name, point in (("button_press_event", start), ("motion_notify_event", end), ("button_release_event", end)):
                ev = MouseEvent(name, panel.canvas, *axis.transData.transform(point), button=MouseButton.LEFT)
                panel.canvas.callbacks.process(name, ev)
            panel.canvas.draw()

        actions["框选缩放"].trigger()
        drag((2, 2), (8, 8))
        zoomed = axis.get_xlim()
        self.assertGreater(zoomed[0], original[0])
        self.assertLess(zoomed[1], original[1])
        actions["平移"].trigger()
        drag((4, 4), (5, 5))
        self.assertNotEqual(axis.get_xlim(), zoomed)
        actions["后退"].trigger()
        self.assertEqual(axis.get_xlim(), zoomed)
        actions["还原视图"].trigger()
        self.assertEqual(axis.get_xlim(), original)

        with tempfile.TemporaryDirectory() as folder, rc_context():
            target = Path(folder) / "preview.png"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "PNG")):
                actions["保存图片"].trigger()
            self.assertFalse(QImage(str(target)).isNull())

    def test_plot_preview_renders_only_prebuilt_origin_data(self) -> None:
        panel = PlotPreviewPanel()
        statuses: list[tuple[str, int]] = []
        information: list[tuple[str, str]] = []
        panel.status_message.connect(lambda text, timeout: statuses.append((text, timeout)))
        panel.information_requested.connect(lambda title, text: information.append((title, text)))
        try:
            origin_data = OriginImportData(
                dataframe=pd.DataFrame({"x": [1, 2], "y": [3, 4]}),
                axis_spec="xy",
                long_names=["x", "y"],
                comments=["共享 X", "sample"],
                workbook_label="sample",
            )
            self.assertTrue(panel.render_origin_data(origin_data))
            axis = panel.figure.axes[0]
            self.assertEqual(axis.get_xlabel(), "x")
            self.assertEqual(len(axis.lines), 1)
            self.assertIn("1 条曲线", statuses[-1][0])

            invalid = OriginImportData(
                dataframe=origin_data.dataframe,
                axis_spec="yy",
                long_names=origin_data.long_names,
                comments=origin_data.comments,
                workbook_label=origin_data.workbook_label,
            )
            self.assertFalse(panel.render_origin_data(invalid))
            self.assertEqual(information[-1][0], "无 X 数据")
        finally:
            panel.close()


if __name__ == "__main__":
    unittest.main()
