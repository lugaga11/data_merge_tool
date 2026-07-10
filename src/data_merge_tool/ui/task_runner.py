from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal


@dataclass(frozen=True)
class TaskSpec:
    message: str
    error_title: str
    reset_output_on_error: bool = False


class DataTask(QThread):
    def __init__(
        self,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        spec: TaskSpec,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._work = work
        self.on_success = on_success
        self.spec = spec
        self.result: object = None
        self.error: object = None

    def run(self) -> None:
        try:
            self.result = self._work()
        except Exception as exc:
            self.error = exc


class TaskRunner(QObject):
    finished = Signal()

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        busy_changed: Callable[[bool], None] | None = None,
        message_handler: Callable[[str, int], None] | None = None,
        error_handler: Callable[[TaskSpec, object], None] | None = None,
        busy_message: str = "当前任务还在处理，请稍等。",
        queue_when_busy: bool = False,
    ) -> None:
        super().__init__(parent)
        self._active_tasks: list[DataTask] = []
        self._busy_changed = busy_changed
        self._message_handler = message_handler
        self._error_handler = error_handler
        self._busy_message = busy_message
        self._queue_when_busy = queue_when_busy
        self._pending_tasks: list[
            tuple[TaskSpec, Callable[[], object], Callable[[object], None]]
        ] = []

    def has_active_task(self) -> bool:
        return bool(self._active_tasks or self._pending_tasks)

    def run(
        self,
        spec: TaskSpec,
        work: Callable[[], object],
        on_success: Callable[[object], None],
    ) -> bool:
        if self.has_active_task():
            if self._queue_when_busy:
                self._pending_tasks.append((spec, work, on_success))
                self._show_message(f"{spec.message}（已加入队列）", 4000)
                return True
            self._show_message(self._busy_message, 4000)
            return False

        self._start_task(spec, work, on_success, set_busy=True)
        return True

    def _start_task(
        self,
        spec: TaskSpec,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        *,
        set_busy: bool,
    ) -> None:
        task = DataTask(work, on_success, spec, self)
        self._active_tasks.append(task)
        if set_busy:
            self._set_busy(True)
        self._show_message(spec.message, 0)
        task.finished.connect(lambda finished_task=task: self._finish_task(finished_task))
        task.start()

    def _finish_task(self, task: DataTask) -> None:
        if task in self._active_tasks:
            self._active_tasks.remove(task)

        spec = task.spec
        on_success = task.on_success
        result = task.result
        error = task.error

        if error is not None:
            self._fail(spec, error)
        else:
            try:
                on_success(result)
            except Exception as exc:
                self._fail(spec, exc)

        if self._active_tasks:
            pass
        elif self._pending_tasks:
            next_spec, next_work, next_success = self._pending_tasks.pop(0)
            self._start_task(next_spec, next_work, next_success, set_busy=False)
        else:
            self._set_busy(False)
        task.destroyed.connect(lambda *_args: self.finished.emit())
        task.deleteLater()

    def _fail(self, spec: TaskSpec, error: object) -> None:
        if self._error_handler is not None:
            self._error_handler(spec, error)

    def _set_busy(self, busy: bool) -> None:
        if self._busy_changed is not None:
            self._busy_changed(busy)

    def _show_message(self, message: str, timeout: int) -> None:
        if self._message_handler is not None:
            self._message_handler(message, timeout)
