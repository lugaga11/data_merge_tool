from __future__ import annotations

import sys

import pandas as pd
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    pd.set_option("mode.copy_on_write", True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
