from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, TypeVar

from PySide6.QtCore import QObject, QThread, Signal

TaskResult = TypeVar("TaskResult")


@dataclass(frozen=True)
class TaskSpec:
    message: str
    error_title: str
    reset_output_on_error: bool = False


class DataTask(QThread, Generic[TaskResult]):
    def __init__(
        self,
        work: Callable[[], TaskResult],
        on_success: Callable[[TaskResult], None],
        spec: TaskSpec,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._work = work
        self.on_success = on_success
        self.spec = spec
        self.result: TaskResult
        self.error: Exception | None = None

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
        error_handler: Callable[[TaskSpec, Exception], None] | None = None,
        busy_message: str = "当前任务还在处理，请稍等。",
        queue_when_busy: bool = False,
    ) -> None:
        super().__init__(parent)
        self._active_task: DataTask[Any] | None = None
        self._busy_changed = busy_changed
        self._message_handler = message_handler
        self._error_handler = error_handler
        self._busy_message = busy_message
        self._queue_when_busy = queue_when_busy
        self._pending_tasks: deque[DataTask[Any]] = deque()

    def has_active_task(self) -> bool:
        return self._active_task is not None or bool(self._pending_tasks)

    def run(
        self,
        spec: TaskSpec,
        work: Callable[[], TaskResult],
        on_success: Callable[[TaskResult], None],
    ) -> bool:
        busy = self.has_active_task()
        if busy and not self._queue_when_busy:
            self._show_message(self._busy_message, 4000)
            return False
        task = DataTask(work, on_success, spec, self)
        if busy:
            self._pending_tasks.append(task)
            self._show_message(f"{spec.message}（已加入队列）", 4000)
        else:
            self._start_task(task, set_busy=True)
        return True

    def _start_task(self, task: DataTask[Any], *, set_busy: bool) -> None:
        self._active_task = task
        if set_busy:
            self._set_busy(True)
        self._show_message(task.spec.message, 0)
        task.finished.connect(lambda finished_task=task: self._finish_task(finished_task))
        task.start()

    def _finish_task(self, task: DataTask[TaskResult]) -> None:
        self._active_task = None
        if task.error is not None:
            self._fail(task.spec, task.error)
        else:
            try:
                task.on_success(task.result)
            except Exception as exc:
                self._fail(task.spec, exc)

        # A success callback may already have started the next data operation.
        if self._active_task is None:
            if self._pending_tasks:
                self._start_task(self._pending_tasks.popleft(), set_busy=False)
            else:
                self._set_busy(False)
        task.destroyed.connect(lambda *_args: self.finished.emit())
        task.deleteLater()

    def _fail(self, spec: TaskSpec, error: Exception) -> None:
        if self._error_handler is not None:
            self._error_handler(spec, error)

    def _set_busy(self, busy: bool) -> None:
        if self._busy_changed is not None:
            self._busy_changed(busy)

    def _show_message(self, message: str, timeout: int) -> None:
        if self._message_handler is not None:
            self._message_handler(message, timeout)
