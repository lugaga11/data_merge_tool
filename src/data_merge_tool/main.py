from __future__ import annotations

import sys


def main() -> int:
    if "--origin-worker" in sys.argv:
        from .origin.worker import main as origin_worker_main

        return origin_worker_main()

    import pandas as pd
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    pd.set_option("mode.copy_on_write", True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
