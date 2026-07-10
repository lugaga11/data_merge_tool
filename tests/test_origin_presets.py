from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.origin.presets import SCHEMA_VERSION, PresetStore
from data_merge_tool.origin.panel import OriginPanelWidget


class PresetStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "user_presets.json"
        self.store = PresetStore(self.path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_legacy_load_applies_defaults(self) -> None:
        self.path.write_text(
            json.dumps({"partial": {"page": {"width_in": 5.0}, "export": {"formats": ["png"]}}}),
            encoding="utf-8",
        )

        result = self.store.load()

        self.assertIsNone(result.warning)
        preset = result.presets["partial"]
        self.assertEqual(preset["page"]["width_in"], 5.0)
        self.assertEqual(preset["page"]["height_in"], 2.6)
        self.assertEqual(preset["layer"]["frame"]["left"], True)
        self.assertEqual(preset["export"]["formats"], ["png"])

    def test_corrupt_json_is_quarantined(self) -> None:
        self.path.write_text("{not-json", encoding="utf-8")

        result = self.store.load()

        self.assertEqual(result.presets, {})
        self.assertIsNotNone(result.warning)
        self.assertIsNotNone(result.quarantined_path)
        assert result.quarantined_path is not None
        self.assertFalse(self.path.exists())
        self.assertTrue(result.quarantined_path.exists())
        self.assertRegex(result.quarantined_path.name, r"user_presets\.bad-\d{8}-\d{6}\.json")

    def test_save_atomic_writes_schema_format(self) -> None:
        self.store.save_atomic({"saved": {"page": {"height_in": 3.25}, "export": {"formats": ["pdf"]}}})

        data = json.loads(self.path.read_text(encoding="utf-8"))

        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        self.assertEqual(data["presets"]["saved"]["page"]["height_in"], 3.25)
        self.assertEqual(data["presets"]["saved"]["export"]["formats"], ["pdf"])

    def test_preset_does_not_persist_axis_titles_or_legend_text(self) -> None:
        preset = self.store.validate(
            {
                "text": {
                    "x_title": "X title",
                    "y_title": "Y title",
                    "legend_text": "Legend",
                }
            }
        )

        self.assertNotIn("x_title", preset["text"])
        self.assertNotIn("y_title", preset["text"])
        self.assertNotIn("legend_text", preset["text"])

    def test_import_validation_keeps_valid_entries_and_reports_invalid_entries(self) -> None:
        import_path = Path(self.temp_dir.name) / "import.json"
        import_path.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "presets": {
                        "ok": {"axis": {"x_scale": "linear"}, "export": {"formats": ["svg"]}},
                        "bad": {"axis": {"x_scale": "not-a-scale"}, "export": {"formats": ["png"]}},
                    },
                }
            ),
            encoding="utf-8",
        )

        result = self.store.load_import_file(import_path)

        self.assertIn("ok", result.presets)
        self.assertNotIn("bad", result.presets)
        self.assertIn("bad", result.errors)

    def test_failed_existing_preset_overwrite_keeps_previous_in_memory_value(self) -> None:
        previous = {"page": {"width_in": 4.0}}
        replacement = {"page": {"width_in": 8.0}}

        class FakeCombo:
            @staticmethod
            def currentText() -> str:
                return "existing"

        class FakePanel:
            def __init__(self) -> None:
                self.presetCombo = FakeCombo()
                self.user_presets = {"existing": previous}
                self.saved_candidate: dict[str, dict[str, object]] | None = None

            @staticmethod
            def current_preset_values() -> dict[str, object]:
                return replacement

            def write_user_presets(self, presets: dict[str, dict[str, object]]) -> bool:
                self.saved_candidate = presets
                return False

        panel = FakePanel()
        with patch("data_merge_tool.origin.panel_presets.QInputDialog.getText", return_value=("existing", True)):
            OriginPanelWidget.save_current_preset(panel)  # type: ignore[arg-type]

        self.assertEqual(panel.user_presets, {"existing": previous})
        self.assertIsNotNone(panel.saved_candidate)
        assert panel.saved_candidate is not None
        self.assertEqual(panel.saved_candidate["existing"], replacement)
        self.assertIsNot(panel.saved_candidate, panel.user_presets)


if __name__ == "__main__":
    unittest.main()
