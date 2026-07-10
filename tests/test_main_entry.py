from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class MainEntryTests(unittest.TestCase):
    def test_importing_entry_does_not_eagerly_load_gui_stack(self) -> None:
        script = (
            "import sys; import data_merge_tool.main; "
            "loaded = [name for name in ('pandas', 'PySide6', 'matplotlib') if name in sys.modules]; "
            "print(loaded); raise SystemExit(0 if not loaded else 1)"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        self.assertEqual(result.stdout.strip(), "[]")

    def test_gui_module_does_not_import_origin_automation_runtime(self) -> None:
        script = (
            "import sys; import data_merge_tool.ui.main_window; "
            "loaded = [name for name in ('originpro', 'OriginExt') if name in sys.modules]; "
            "print(loaded); raise SystemExit(0 if not loaded else 1)"
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
        self.assertEqual(result.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
