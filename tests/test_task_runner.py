from __future__ import annotations

from pathlib import Path
import os
import sys
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.ui.task_runner import TaskRunner, TaskSpec


class TaskRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_success_callback_exception_is_reported_as_failure(self) -> None:
        failures: list[tuple[str, str]] = []
        runner = TaskRunner(
            error_handler=lambda spec, error: failures.append((spec.error_title, str(error))),
        )
        loop = QEventLoop()
        runner.finished.connect(loop.quit)

        started = runner.run(
            TaskSpec(message="working", error_title="任务失败"),
            lambda: "ok",
            lambda _result: (_ for _ in ()).throw(RuntimeError("callback exploded")),
        )

        self.assertTrue(started)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()

        self.assertEqual(failures, [("任务失败", "callback exploded")])
        self.assertFalse(runner.has_active_task())

    def test_queue_when_busy_runs_tasks_in_fifo_order_with_one_busy_window(self) -> None:
        results: list[str] = []
        busy_states: list[bool] = []
        runner = TaskRunner(
            busy_changed=busy_states.append,
            queue_when_busy=True,
        )
        loop = QEventLoop()
        runner.finished.connect(lambda: loop.quit() if not runner.has_active_task() else None)

        first_started = runner.run(
            TaskSpec(message="first", error_title="first failed"),
            lambda: (time.sleep(0.05), "first")[1],
            results.append,
        )
        second_started = runner.run(
            TaskSpec(message="second", error_title="second failed"),
            lambda: "second",
            results.append,
        )

        self.assertTrue(first_started)
        self.assertTrue(second_started)
        self.assertTrue(runner.has_active_task())
        QTimer.singleShot(3000, loop.quit)
        loop.exec()

        self.assertEqual(results, ["first", "second"])
        self.assertEqual(busy_states, [True, False])
        self.assertFalse(runner.has_active_task())


if __name__ == "__main__":
    unittest.main()
