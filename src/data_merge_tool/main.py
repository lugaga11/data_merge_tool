from __future__ import annotations

import sys


def main() -> int:
    if "--origin-worker" in sys.argv:
        from .origin.worker import main as origin_worker_main

        return origin_worker_main()

    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
