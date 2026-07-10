from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..constants import APP_TITLE, CHECKMARK_ICON, HORIZONTAL
from ..data_reading.readers import read_table, scan_data_files
from ..data_types import MergeOptions, OriginImportData
from ..errors import UserVisibleError
from ..merge.engine import build_origin_import_table
from ..origin.client import OriginWorkerClient
from ..origin.panel import OriginPanelWidget
from ..origin.windowing import activate_visible_origin_window
from ..resources import load_stylesheet
from ..version import APP_VERSION
from .controls import make_button
from .file_queue import FileQueuePanel
from .merge_panel import MergePanel
from .plot_preview import PlotPreviewPanel
from .preview_panel import PreviewPanel
from .read_options_panel import ReadOptionsPanel
from .task_runner import TaskRunner, TaskSpec


class MainWindow(QMainWindow):
    """Compose the application panels and coordinate cross-panel workflows."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setStatusBar(QStatusBar(self))

        self.last_origin_data: Optional[OriginImportData] = None
        self.output_dirty = True
        self._data_generation = 0
        self._data_busy = False
        self._origin_busy = False
        self._origin_wait_cursor_active = False

        self.origin_worker = OriginWorkerClient()
        self.task_runner = TaskRunner(
            self,
            busy_changed=self.set_data_busy,
            message_handler=self.statusBar().showMessage,
            error_handler=self._handle_data_task_error,
        )
        self.origin_task_runner = TaskRunner(
            self,
            busy_changed=self.set_origin_busy,
            message_handler=self.statusBar().showMessage,
            error_handler=self._handle_origin_task_error,
            queue_when_busy=True,
        )

        self.file_queue = FileQueuePanel()
        self.read_options_panel = ReadOptionsPanel()
        file_queue_layout = self.file_queue.layout()
        assert file_queue_layout is not None
        file_queue_layout.addWidget(self.read_options_panel)
        self.merge_panel = MergePanel()
        self.preview_panel = PreviewPanel()
        self.plot_preview = PlotPreviewPanel()
        self.origin_panel = OriginPanelWidget(self.origin_worker, self.origin_task_runner)

        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self.refresh_input_preview()
        self.mark_output_dirty()
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), self, self.copy_to_clipboard)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_mode_bar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_data_merge_view())
        self.stack.addWidget(self.origin_panel)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def _build_mode_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("ModeBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        title = QLabel(f"{APP_TITLE} {APP_VERSION}")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        layout.addStretch(1)
        self.release_origin_button = make_button(
            "释放 Origin 控制",
            self.release_origin_control,
            "quiet",
            width=150,
        )
        layout.addWidget(self.release_origin_button)
        self.mode_button = make_button(
            "切换到 Origin 绘图面板",
            self.toggle_main_view,
            "primary",
            width=190,
        )
        layout.addWidget(self.mode_button)
        return bar

    def _build_data_merge_view(self) -> QWidget:
        workspace = QTabWidget()
        workspace.addTab(self.preview_panel, "数据预览")
        workspace.addTab(self.plot_preview, "轻量绘图")

        splitter = QSplitter(HORIZONTAL)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.file_queue)
        splitter.addWidget(self.merge_panel)
        splitter.addWidget(workspace)
        splitter.setSizes([340, 360, 720])
        return splitter

    def _connect_signals(self) -> None:
        self.file_queue.paths_dropped.connect(self.handle_dropped_paths)
        self.file_queue.queue_changed.connect(self.mark_output_dirty)
        self.file_queue.preview_reference_changed.connect(self.refresh_input_preview)
        self.file_queue.status_message.connect(self.statusBar().showMessage)

        self.read_options_panel.options_changed.connect(self._on_read_options_changed)

        self.merge_panel.options_changed.connect(self.mark_output_dirty)
        self.merge_panel.preview_requested.connect(self.preview_merge)
        self.merge_panel.copy_requested.connect(self.copy_to_clipboard)
        self.merge_panel.export_requested.connect(self.export_merged)
        self.merge_panel.import_origin_requested.connect(self.import_to_origin)

        self.plot_preview.plot_requested.connect(self.plot_data)
        self.plot_preview.status_message.connect(self.statusBar().showMessage)
        self.plot_preview.information_requested.connect(
            lambda title, message: QMessageBox.information(self, title, message)
        )

    def _apply_style(self) -> None:
        stylesheet = load_stylesheet("app.qss") + "\n" + load_stylesheet("origin_panel.qss")
        self.setStyleSheet(stylesheet.replace("__CHECKMARK_ICON__", CHECKMARK_ICON))

    def toggle_main_view(self) -> None:
        self.stack.setCurrentIndex(1 if self.stack.currentIndex() == 0 else 0)
        if self.stack.currentIndex() == 0:
            self.mode_button.setText("切换到 Origin 绘图面板")
            self.statusBar().showMessage("当前面板：数据合并。", 2500)
        else:
            self.mode_button.setText("返回数据合并")
            self.statusBar().showMessage("当前面板：Origin 绘图面板。", 2500)

    def _on_read_options_changed(self) -> None:
        self.refresh_input_preview()
        self.mark_output_dirty()

    def refresh_input_preview(self) -> None:
        path = self.file_queue.preview_path()
        self.read_options_panel.set_reference_path(path)
        if path is None:
            self.preview_panel.clear_input()
            self.merge_panel.set_columns("", [])
            return

        try:
            options = self.read_options_panel.current_options()
            dataframe = read_table(path, options)
        except UserVisibleError as exc:
            self.preview_panel.clear_input(f"{path.name} 预览失败")
            self.statusBar().showMessage(str(exc), 6000)
            return

        read_hint = f"跳过 {options.skip_rows} 行，{'表头' if options.has_header else '无表头'}"
        title = f"{path.name}：预览 {dataframe.shape[0]} 行 x {dataframe.shape[1]} 列（{read_hint}）"
        self.preview_panel.set_input(dataframe, title)
        self.merge_panel.set_columns(path, list(dataframe.columns))

    def mark_output_dirty(self) -> None:
        self._data_generation += 1
        self.output_dirty = True
        self.last_origin_data = None
        self.preview_panel.reset_output()

    def current_merge_request(
        self,
        show_errors: bool = False,
    ) -> Optional[tuple[list[str], MergeOptions]]:
        try:
            read_options = self.read_options_panel.current_options()
            options = self.merge_panel.current_options(read_options, show_errors=show_errors)
        except UserVisibleError as exc:
            if not show_errors:
                raise
            message = str(exc)
            self.statusBar().showMessage(message, 8000)
            QMessageBox.warning(self, "无法读取数据", message)
            return None
        if options is None:
            return None

        paths = self.file_queue.checked_paths() if self.merge_panel.selected_only() else self.file_queue.all_paths()
        if not paths and show_errors and self.merge_panel.selected_only():
            QMessageBox.information(self, "提示", "当前合并范围是“仅选中文件”，请先勾选要合并的文件。")
        return (paths, options) if paths else None

    def handle_dropped_paths(self, paths: Sequence[str]) -> None:
        files: list[str] = []
        folders: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            if path.is_dir():
                folders.append(path)
            elif path.is_file():
                files.append(str(path))

        if not folders:
            if files:
                self.file_queue.add_paths(files)
            else:
                self.statusBar().showMessage("拖放内容中没有可读取的文件或文件夹。", 5000)
            return

        def scan_folders() -> list[str]:
            discovered = list(files)
            for folder in folders:
                discovered.extend(scan_data_files(folder))
            return discovered

        def finish_scan(result: object) -> None:
            if not isinstance(result, list):
                raise TypeError("文件夹扫描任务没有返回有效路径列表。")
            if result:
                self.file_queue.add_paths([str(path) for path in result])
            else:
                self.statusBar().showMessage("文件夹中没有找到支持的数据文件。", 5000)

        self.start_data_task(
            f"正在后台扫描 {len(folders)} 个文件夹...",
            scan_folders,
            finish_scan,
            "扫描文件夹失败",
        )

    def set_data_busy(self, busy: bool) -> None:
        self._data_busy = busy
        self._update_busy_state()

    def set_origin_busy(self, busy: bool) -> None:
        self._origin_busy = busy
        if busy and not self._origin_wait_cursor_active:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._origin_wait_cursor_active = True
        elif not busy and self._origin_wait_cursor_active:
            QApplication.restoreOverrideCursor()
            self._origin_wait_cursor_active = False
        self._update_busy_state()

    def _update_busy_state(self) -> None:
        data_enabled = not self._data_busy
        self.merge_panel.set_data_actions_enabled(data_enabled)
        self.plot_preview.set_action_enabled(data_enabled)
        self.copy_shortcut.setEnabled(data_enabled)

        origin_enabled = data_enabled and not self._origin_busy
        self.merge_panel.set_origin_action_enabled(origin_enabled)
        self.release_origin_button.setEnabled(origin_enabled)
        self.origin_panel.setEnabled(not self._origin_busy)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.task_runner.has_active_task() or self.origin_task_runner.has_active_task():
            event.ignore()
            message = "当前仍有后台任务正在处理，暂时无法关闭窗口。请等待任务完成后再次关闭。"
            self.statusBar().showMessage(message, 8000)
            QMessageBox.information(self, "任务正在进行", message)
            return
        self.origin_panel.detach()
        self.origin_worker.shutdown()
        super().closeEvent(event)

    def release_origin_control(self) -> None:
        if self.task_runner.has_active_task():
            self.statusBar().showMessage("当前任务还在处理，请稍后释放 Origin 控制。", 4000)
            return
        if self.origin_task_runner.has_active_task():
            self.statusBar().showMessage("Origin 自动化任务仍在执行，请稍后释放控制。", 4000)
            return

        def finish_release(_result: object) -> None:
            self.origin_panel.clear_origin_connection_state()
            self.statusBar().showMessage(
                "已释放 Origin 控制；现在可以关闭 Origin，下一次操作会自动重新连接。",
                8000,
            )

        self.start_origin_task(
            "正在释放 Origin 控制...",
            self.origin_worker.release_origin,
            finish_release,
            "释放 Origin 控制失败",
        )

    def start_data_task(
        self,
        message: str,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        error_title: str,
        reset_output_on_error: bool = False,
    ) -> bool:
        return self.task_runner.run(
            TaskSpec(
                message=message,
                error_title=error_title,
                reset_output_on_error=reset_output_on_error,
            ),
            work,
            on_success,
        )

    def start_origin_task(
        self,
        message: str,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        error_title: str,
    ) -> bool:
        return self.origin_task_runner.run(
            TaskSpec(message=message, error_title=error_title),
            work,
            on_success,
        )

    def _handle_data_task_error(self, spec: TaskSpec, error: object) -> None:
        if spec.reset_output_on_error:
            self.output_dirty = True
            self.last_origin_data = None
            self.preview_panel.reset_output()
        if isinstance(error, UserVisibleError):
            QMessageBox.warning(self, spec.error_title, str(error))
        else:
            QMessageBox.critical(self, spec.error_title, str(error))
        self.statusBar().showMessage(f"{spec.error_title}。", 5000)

    def _handle_origin_task_error(self, spec: TaskSpec, error: object) -> None:
        exc = error if isinstance(error, Exception) else RuntimeError(str(error))
        self.origin_panel.show_error(spec.error_title, exc)

    def set_merged_result(self, origin_data: OriginImportData) -> None:
        dataframe = origin_data.dataframe
        self.last_origin_data = origin_data
        self.output_dirty = False
        self.preview_panel.set_output(
            dataframe,
            f"合并结果：{dataframe.shape[0]} 行 x {dataframe.shape[1]} 列",
        )

    def ensure_import_data(
        self,
        action_name: str,
        on_ready: Callable[[OriginImportData], object],
    ) -> None:
        if self.last_origin_data is not None and not self.output_dirty:
            on_ready(self.last_origin_data)
            return

        request = self.current_merge_request(show_errors=True)
        if request is None:
            return
        paths, options = request
        generation = self._data_generation

        def finish_merge_then_continue(result: object) -> None:
            if generation != self._data_generation:
                QMessageBox.information(
                    self,
                    "结果已过期",
                    f"合并期间参数或文件选择发生了变化，本次结果已丢弃。请再次点击“{action_name}”。",
                )
                self.statusBar().showMessage("参数已变化，未继续使用过期合并结果。", 5000)
                return
            if not isinstance(result, OriginImportData):
                QMessageBox.critical(self, "合并失败", "后台合并没有返回有效结果。")
                return
            self.set_merged_result(result)
            self.statusBar().showMessage(f"合并完成，正在继续{action_name}...", 3000)
            on_ready(result)

        started = self.start_data_task(
            f"正在后台合并数据，完成后继续{action_name}...",
            lambda: build_origin_import_table(paths, options),
            finish_merge_then_continue,
            "无法合并",
            reset_output_on_error=True,
        )
        if started:
            self.preview_panel.reset_output(f"正在后台合并，完成后继续{action_name}...")

    def preview_merge(self) -> None:
        request = self.current_merge_request(show_errors=True)
        if request is None:
            return
        paths, options = request
        generation = self._data_generation

        def finish_preview(result: object) -> None:
            if generation != self._data_generation:
                self.statusBar().showMessage("设置已变化，本次合并结果已忽略。", 5000)
                return
            if isinstance(result, OriginImportData):
                self.set_merged_result(result)
                self.statusBar().showMessage("合并预览已更新。", 4000)

        started = self.start_data_task(
            "正在后台合并数据...",
            lambda: build_origin_import_table(paths, options),
            finish_preview,
            "无法合并",
            reset_output_on_error=True,
        )
        if started:
            self.preview_panel.reset_output("正在后台合并，请稍候...")

    def copy_to_clipboard(self) -> None:
        self.ensure_import_data("复制", self.copy_ready_dataframe_to_clipboard)

    def copy_ready_dataframe_to_clipboard(self, origin_data: OriginImportData) -> None:
        QApplication.clipboard().setText(
            origin_data.dataframe.to_csv(sep="\t", index=False, lineterminator="\n")
        )
        self.statusBar().showMessage("已复制为 Tab 分隔文本，可直接粘贴到 Excel。", 5000)
        QMessageBox.information(self, "已复制", "合并结果已复制到剪贴板，可直接粘贴到 Excel。")

    def export_merged(self) -> None:
        self.ensure_import_data("导出", self.export_ready_dataframe)

    def export_ready_dataframe(self, origin_data: OriginImportData) -> None:
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出合并结果",
            "merged.xlsx",
            "Excel (*.xlsx);;CSV UTF-8 (*.csv)",
        )
        if not filename:
            return

        path = Path(filename)
        if path.suffix == "":
            path = path.with_suffix(".csv" if "CSV" in selected_filter else ".xlsx")
        dataframe = origin_data.dataframe.copy()

        def do_export() -> Path:
            if path.suffix.lower() == ".xlsx":
                dataframe.to_excel(path, index=False)
            else:
                dataframe.to_csv(path, index=False, encoding="utf-8-sig")
            return path

        def finish_export(result: object) -> None:
            if not isinstance(result, Path):
                raise TypeError("导出任务没有返回有效路径。")
            self.statusBar().showMessage(f"已导出：{result}", 6000)
            QMessageBox.information(self, "导出完成", f"文件已保存到：\n{result}")

        self.start_data_task("正在后台导出文件...", do_export, finish_export, "导出失败")

    def import_to_origin(self) -> None:
        self.ensure_import_data("导入 Origin", self.import_ready_dataframe_to_origin)

    def import_ready_dataframe_to_origin(self, origin_data: OriginImportData) -> None:
        dataframe = origin_data.dataframe.copy()
        axis_spec = origin_data.axis_spec
        long_names = list(origin_data.long_names)
        comments = list(origin_data.comments)
        workbook_label = origin_data.workbook_label

        def do_import() -> str:
            return self.origin_worker.import_dataframe(
                dataframe,
                axis_spec,
                long_names,
                comments,
                workbook_label,
            )

        def finish_import(result: object) -> None:
            page_name = str(result)
            self.statusBar().showMessage(f"已导入 Origin：{page_name}", 6000)
            activate_visible_origin_window()

        self.start_origin_task(
            "正在启动或连接 Origin 并导入合并数据...",
            do_import,
            finish_import,
            "导入 Origin 失败",
        )

    @staticmethod
    def can_plot_from_import_data(options: MergeOptions) -> bool:
        if options.keep_single_x:
            return True
        return options.y_columns_auto or options.x_column - 1 in options.y_columns

    def plot_data(self) -> None:
        if not self.plot_preview.is_available():
            QMessageBox.information(self, "绘图不可用", "当前环境未安装 matplotlib。")
            return
        request = self.current_merge_request(show_errors=True)
        if request is None:
            return
        _paths, options = request
        if not self.can_plot_from_import_data(options):
            QMessageBox.information(self, "无 X 数据", "请在 Y 列选择器中勾选当前 X 列后再绘图。")
            return
        self.ensure_import_data("绘图", self.plot_preview.render_origin_data)


__all__ = ["MainWindow"]
