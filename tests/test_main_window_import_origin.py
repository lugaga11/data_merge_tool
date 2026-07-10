from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.ui.main_window import MainWindow
from data_merge_tool.data_types import OriginImportData
from data_merge_tool.errors import UserVisibleError


class FakeOriginClient:
    _process = None

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, int], str, list[str], list[str], str]] = []

    def import_dataframe(self, df, axis_spec, long_names, comments, workbook_label):  # type: ignore[no-untyped-def]
        self.calls.append((df.shape, axis_spec, list(long_names), list(comments), workbook_label))
        return "FakeBook/Sheet1"

    def shutdown(self) -> None:
        pass

    def release_origin(self) -> None:
        pass


class MainWindowImportOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._messagebox_methods = (
            QMessageBox.information,
            QMessageBox.warning,
            QMessageBox.critical,
        )
        QMessageBox.information = lambda *args, **kwargs: None  # type: ignore[method-assign]
        QMessageBox.warning = lambda *args, **kwargs: None  # type: ignore[method-assign]
        QMessageBox.critical = lambda *args, **kwargs: None  # type: ignore[method-assign]

    def tearDown(self) -> None:
        QMessageBox.information, QMessageBox.warning, QMessageBox.critical = self._messagebox_methods  # type: ignore[method-assign]

    def test_import_to_origin_merges_then_calls_origin_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "sample.csv"
            csv_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")

            window = MainWindow()
            fake_origin = FakeOriginClient()
            window.origin_worker = fake_origin  # type: ignore[assignment]
            window.origin_panel.origin_client = fake_origin  # type: ignore[assignment]
            try:
                self.assertIs(window.origin_panel.task_runner, window.origin_task_runner)
                window.file_queue.add_paths([str(csv_path)])
                window.refresh_input_preview()
                window.merge_panel.select_all_y()
                with patch("data_merge_tool.ui.main_window.activate_visible_origin_window") as activate:
                    window.import_to_origin()
                    self._drain_tasks(window)

                self.assertEqual(
                    fake_origin.calls,
                    [((2, 2), "xy", ["x", "y"], ["共享 X", "sample"], "sample")],
                )
                activate.assert_called_once_with()
            finally:
                window.close()

    def test_busy_task_rejection_keeps_output_and_disables_ui_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "sample.csv"
            csv_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")

            window = MainWindow()
            try:
                window.file_queue.add_paths([str(csv_path)])
                window.merge_panel.select_all_y()
                window.preview_panel.output_model.set_dataframe(pd.DataFrame({"sentinel": [1]}))
                window.preview_panel.output_title.setText("稳定结果")

                started = window.start_data_task(
                    "正在执行已有任务...",
                    lambda: time.sleep(0.2),
                    lambda _result: None,
                    "已有任务失败",
                )
                self.assertTrue(started)
                self.assertFalse(window.plot_preview.plot_button.isEnabled())
                self.assertFalse(window.copy_shortcut.isEnabled())

                window.ensure_import_data("绘图", lambda _result: self.fail("busy request unexpectedly continued"))
                window.preview_merge()

                self.assertEqual(window.preview_panel.output_title.text(), "稳定结果")
                self.assertEqual(window.preview_panel.output_model.rowCount(), 1)
                self.assertFalse(window.plot_preview.plot_button.isEnabled())
                self.assertFalse(window.copy_shortcut.isEnabled())

                self._drain_tasks(window)
                self.assertTrue(window.plot_preview.plot_button.isEnabled())
                self.assertTrue(window.copy_shortcut.isEnabled())
            finally:
                if window.task_runner.has_active_task():
                    self._drain_tasks(window)
                window.close()

    def test_merge_request_shows_detection_error_for_user_action(self) -> None:
        window = MainWindow()
        try:
            window.merge_panel.x_column_box.addItem("1. x", 0)
            error = UserVisibleError("自动检测读入设置失败：损坏的工作簿")
            with (
                patch.object(window.read_options_panel, "current_options", side_effect=error),
                patch.object(QMessageBox, "warning") as warning,
            ):
                request = window.current_merge_request(show_errors=True)

            self.assertIsNone(request)
            warning.assert_called_once_with(window, "无法读取数据", str(error))
            self.assertEqual(window.statusBar().currentMessage(), str(error))
        finally:
            window.close()

    def test_merge_request_propagates_detection_error_without_user_prompt(self) -> None:
        window = MainWindow()
        try:
            window.merge_panel.x_column_box.addItem("1. x", 0)
            error = UserVisibleError("自动检测失败")
            with patch.object(window.read_options_panel, "current_options", side_effect=error):
                with self.assertRaisesRegex(UserVisibleError, "自动检测失败"):
                    window.current_merge_request(show_errors=False)
        finally:
            window.close()

    def test_parameter_change_discards_in_flight_merge_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "sample.csv"
            csv_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
            result = OriginImportData(
                dataframe=pd.DataFrame({"x": [1, 3], "y": [2, 4]}),
                axis_spec="xy",
                long_names=["x", "y"],
                comments=["共享 X", "sample"],
                workbook_label="sample",
            )

            window = MainWindow()
            try:
                window.file_queue.add_paths([str(csv_path)])
                window.merge_panel.select_all_y()

                with patch(
                    "data_merge_tool.ui.main_window.build_origin_import_table",
                    side_effect=lambda *_args: (time.sleep(0.1), result)[1],
                ):
                    window.preview_merge()
                    window.merge_panel.label_mode_box.setCurrentIndex(1)
                    self._drain_runner(window.task_runner)

                self.assertTrue(window.output_dirty)
                self.assertEqual(window.preview_panel.output_model.rowCount(), 0)
                self.assertIn("已忽略", window.statusBar().currentMessage())
            finally:
                if window.task_runner.has_active_task():
                    self._drain_runner(window.task_runner)
                window.close()

    def test_close_while_task_active_is_ignored_until_task_finishes(self) -> None:
        script = textwrap.dedent(
            """
            import time

            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication, QMessageBox

            from data_merge_tool.ui.main_window import MainWindow

            QMessageBox.information = lambda *args, **kwargs: None
            app = QApplication([])
            window = MainWindow()
            window.show()
            state = {}

            def first_close():
                state["first_result"] = window.close()
                state["visible_after_first"] = window.isVisible()

            def second_close():
                state["active_before_second"] = window.task_runner.has_active_task()
                state["second_result"] = window.close()

            window.task_runner.finished.connect(lambda: QTimer.singleShot(0, second_close))
            window.start_data_task(
                "probe",
                lambda: time.sleep(0.3),
                lambda _result: None,
                "probe failed",
            )
            QTimer.singleShot(10, first_close)
            QTimer.singleShot(5000, lambda: app.exit(9))
            exit_code = app.exec()
            ok = (
                exit_code == 0
                and state.get("first_result") is False
                and state.get("visible_after_first") is True
                and state.get("active_before_second") is False
                and state.get("second_result") is True
            )
            print("CLOSE_PROBE", exit_code, state, flush=True)
            raise SystemExit(0 if ok else 8)
            """
        )
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = str(SRC)
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        self.assertIn("CLOSE_PROBE", result.stdout)

    def test_close_event_is_ignored_while_origin_panel_task_is_active(self) -> None:
        window = MainWindow()
        origin_panel = window.origin_panel
        try:
            self.assertIs(origin_panel.task_runner, window.origin_task_runner)
            started = origin_panel.start_origin_task(
                "Origin probe",
                lambda: time.sleep(0.2),
                lambda _result: None,
                "Origin probe failed",
            )
            self.assertTrue(started)

            event = QCloseEvent()
            window.closeEvent(event)

            self.assertFalse(event.isAccepted())
            self.assertTrue(origin_panel.has_active_origin_task())
            self.assertFalse(window.merge_panel.origin_button.isEnabled())
            self.assertFalse(window.release_origin_button.isEnabled())
            self.assertFalse(origin_panel.isEnabled())
            self.assertIsNotNone(QApplication.overrideCursor())
            assert QApplication.overrideCursor() is not None
            self.assertEqual(QApplication.overrideCursor().shape(), Qt.CursorShape.WaitCursor)
            self.assertIn("后台任务", window.statusBar().currentMessage())
            second_started = window.start_origin_task(
                "second Origin probe",
                lambda: None,
                lambda _result: None,
                "second Origin probe failed",
            )
            self.assertTrue(second_started)
            self._drain_runner(window.origin_task_runner)
            self.assertTrue(window.merge_panel.origin_button.isEnabled())
            self.assertTrue(window.release_origin_button.isEnabled())
            self.assertTrue(origin_panel.isEnabled())
            self.assertIsNone(QApplication.overrideCursor())
        finally:
            if origin_panel.has_active_origin_task():
                self._drain_runner(window.origin_task_runner)
            window.close()

    def test_import_waits_in_global_origin_queue_instead_of_being_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "sample.csv"
            csv_path.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
            result = OriginImportData(
                dataframe=pd.DataFrame({"x": [1, 3], "y": [2, 4]}),
                axis_spec="xy",
                long_names=["x", "y"],
                comments=["共享 X", "sample"],
                workbook_label="sample",
            )

            window = MainWindow()
            fake_origin = FakeOriginClient()
            window.origin_worker = fake_origin  # type: ignore[assignment]
            window.origin_panel.origin_client = fake_origin  # type: ignore[assignment]
            try:
                window.file_queue.add_paths([str(csv_path)])
                window.merge_panel.select_all_y()

                with patch(
                    "data_merge_tool.ui.main_window.build_origin_import_table",
                    side_effect=lambda *_args: (time.sleep(0.1), result)[1],
                ), patch("data_merge_tool.ui.main_window.activate_visible_origin_window") as activate:
                    window.import_to_origin()
                    panel_started = window.origin_panel.start_origin_task(
                        "先执行的 Origin 操作",
                        lambda: time.sleep(0.2),
                        lambda _result: None,
                        "Origin 操作失败",
                    )
                    self.assertTrue(panel_started)
                    self._drain_tasks(window)

                self.assertEqual(
                    fake_origin.calls,
                    [((2, 2), "xy", ["x", "y"], ["共享 X", "sample"], "sample")],
                )
                activate.assert_called_once_with()
            finally:
                if window.task_runner.has_active_task():
                    self._drain_runner(window.task_runner)
                if window.origin_task_runner.has_active_task():
                    self._drain_runner(window.origin_task_runner)
                window.close()

    def test_dropped_folder_is_scanned_on_background_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "folder"
            folder.mkdir()
            csv_path = folder / "sample.csv"
            csv_path.write_text("x,y\n1,2\n", encoding="utf-8")
            scan_threads: list[int] = []
            main_thread = threading.get_ident()

            def fake_scan(path: Path) -> list[str]:
                self.assertEqual(path, folder)
                scan_threads.append(threading.get_ident())
                time.sleep(0.05)
                return [str(csv_path)]

            window = MainWindow()
            try:
                with patch("data_merge_tool.ui.main_window.scan_data_files", side_effect=fake_scan):
                    window.handle_dropped_paths([str(folder)])
                    self.assertTrue(window.task_runner.has_active_task())
                    self._drain_runner(window.task_runner)

                self.assertEqual(len(scan_threads), 1)
                self.assertNotEqual(scan_threads[0], main_thread)
                self.assertIn(str(csv_path), window.file_queue.all_paths())
            finally:
                if window.task_runner.has_active_task():
                    self._drain_runner(window.task_runner)
                window.close()

    def _drain_tasks(self, window: MainWindow) -> None:
        self._drain_runner(window.task_runner)
        self._drain_runner(window.origin_task_runner)

    def _drain_runner(self, runner) -> None:  # type: ignore[no-untyped-def]
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.start(5000)
        while runner.has_active_task() and timeout.isActive():
            loop = QEventLoop()
            runner.finished.connect(loop.quit)
            timeout.timeout.connect(loop.quit)
            loop.exec()
        self.assertFalse(runner.has_active_task())


if __name__ == "__main__":
    unittest.main()
