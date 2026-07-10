from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_merge_tool.origin.automation import OriginAdapter, safe_origin_long_name
from data_merge_tool.origin.protocol import (
    ApplyResult,
    FigureStylePatch,
    GraphInfo,
    LayerInfo,
    OriginAutomationError,
    PatchTarget,
    StyleSnapshot,
    graph_info_from_dict,
    graph_info_to_dict,
    patch_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)
from data_merge_tool.origin.worker import dispatch
from data_merge_tool.origin.windowing import activate_visible_origin_window


class FakeOrigin:
    def __init__(self, *, attach_error: Exception | None = None) -> None:
        self.attach_error = attach_error
        self.attach_calls = 0
        self.set_show_calls: list[bool] = []

    def attach(self) -> None:
        self.attach_calls += 1
        if self.attach_error is not None:
            raise self.attach_error

    def set_show(self, visible: bool) -> None:
        self.set_show_calls.append(visible)


class FakeGraph:
    def __init__(self, name: str) -> None:
        self.name = name


class OriginAdapterConnectionTests(unittest.TestCase):
    def test_window_activation_returns_false_without_visible_origin(self) -> None:
        with (
            patch("data_merge_tool.origin.windowing.sys.platform", "win32"),
            patch("data_merge_tool.origin.windowing.visible_origin_window_handles", return_value=[]),
        ):
            self.assertFalse(activate_visible_origin_window())

    def test_safe_origin_long_name_sanitizes_invalid_characters(self) -> None:
        name = safe_origin_long_name('  sample:/name?  ')

        self.assertRegex(name, r"^sample-name \d{4}$")

    def test_connect_does_not_start_origin_when_attach_fails(self) -> None:
        adapter = OriginAdapter()
        fake = FakeOrigin(attach_error=RuntimeError("not running"))
        adapter._op = fake

        with patch("data_merge_tool.origin.automation._visible_origin_windows", return_value=[]):
            with self.assertRaisesRegex(OriginAutomationError, "请先手动启动 Origin"):
                adapter.connect()

        self.assertEqual(fake.attach_calls, 0)
        self.assertEqual(fake.set_show_calls, [])
        self.assertFalse(adapter._connected)

    def test_connected_adapter_rejects_missing_visible_origin_window(self) -> None:
        adapter = OriginAdapter()
        adapter._op = FakeOrigin()
        adapter._connected = True

        with patch("data_merge_tool.origin.automation._visible_origin_windows", return_value=[]):
            with self.assertRaisesRegex(OriginAutomationError, "未检测到已打开且可见"):
                adapter.connect()

        self.assertFalse(adapter._connected)

    def test_connect_succeeds_after_attach_and_visible_window(self) -> None:
        adapter = OriginAdapter()
        fake = FakeOrigin()
        adapter._op = fake

        with (
            patch("data_merge_tool.origin.automation._visible_origin_windows", return_value=["Origin"]),
            patch("data_merge_tool.origin.automation._activate_visible_origin_window") as activate,
        ):
            self.assertIs(adapter.connect(), fake)

        self.assertEqual(fake.attach_calls, 1)
        self.assertEqual(fake.set_show_calls, [True])
        self.assertTrue(adapter._connected)
        activate.assert_called_once_with()

    def test_import_connection_starts_visible_origin_without_hidden_attach(self) -> None:
        adapter = OriginAdapter()
        fake = FakeOrigin()
        adapter._op = fake

        with (
            patch("data_merge_tool.origin.automation._visible_origin_windows", return_value=[]),
            patch("data_merge_tool.origin.automation._wait_for_visible_origin_window", return_value=True),
            patch("data_merge_tool.origin.automation._activate_visible_origin_window") as activate,
        ):
            self.assertIs(adapter.connect(start_if_missing=True), fake)

        self.assertEqual(fake.attach_calls, 0)
        self.assertEqual(fake.set_show_calls, [True])
        self.assertTrue(adapter._connected)
        activate.assert_called_once_with()

    def test_import_connection_does_not_start_second_origin_after_attach_failure(self) -> None:
        adapter = OriginAdapter()
        fake = FakeOrigin(attach_error=RuntimeError("attach failed"))
        adapter._op = fake

        with patch("data_merge_tool.origin.automation._visible_origin_windows", return_value=["Origin"]):
            with self.assertRaisesRegex(OriginAutomationError, "未检测到可连接"):
                adapter.connect(start_if_missing=True)

        self.assertEqual(fake.attach_calls, 1)
        self.assertEqual(fake.set_show_calls, [])
        self.assertFalse(adapter._connected)

    def test_import_reactivates_origin_window_after_writing(self) -> None:
        adapter = OriginAdapter()
        dataframe = pd.DataFrame({"x": [1], "y": [2]})

        with (
            patch.object(adapter, "connect", return_value=FakeOrigin()),
            patch("data_merge_tool.origin.automation._write_dataframe_to_origin", return_value="Book1/Sheet1"),
            patch("data_merge_tool.origin.automation._activate_visible_origin_window") as activate,
        ):
            result = adapter.import_dataframe(dataframe, "xy", ["x", "y"], ["", ""], "sample")

        self.assertEqual(result, "Book1/Sheet1")
        activate.assert_called_once_with()


class OriginAdapterSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patch = FigureStylePatch(target=PatchTarget(), enabled_paths=set())

    def test_snapshot_records_graph_name_without_project_lookup(self) -> None:
        adapter = OriginAdapter()
        graph = FakeGraph("Graph1")

        with (
            patch.object(adapter, "connect", return_value=object()),
            patch.object(adapter, "_find_graph", return_value=graph),
            patch.object(adapter, "_resolve_layers", return_value=[1]),
            patch.object(adapter, "_read_graph_layer_style", return_value={}),
        ):
            snapshot = adapter.read_style_snapshot(self.patch)

        self.assertEqual(snapshot.target_name, "Graph1")

    def test_snapshot_survives_protocol_round_trip(self) -> None:
        snapshot = StyleSnapshot("Graph1", [1], {"axis.grid"}, {1: {"axis": {"show_grid": True}}})

        restored = snapshot_from_dict(snapshot_to_dict(snapshot))

        self.assertEqual(restored, snapshot)

    def test_graph_info_protocol_contains_only_consumed_fields(self) -> None:
        info = GraphInfo("Graph1", [LayerInfo(1, 2)])

        payload = graph_info_to_dict(info)

        self.assertEqual(payload, {"name": "Graph1", "layers": [{"index": 1, "plot_count": 2}]})
        self.assertEqual(graph_info_from_dict(payload), info)

    def test_restore_uses_current_active_graph_without_identity_check(self) -> None:
        adapter = OriginAdapter()
        graph = FakeGraph("CurrentGraph")
        snapshot = StyleSnapshot("OriginalGraph", [], set(), {})

        with (
            patch.object(adapter, "connect", return_value=object()),
            patch.object(adapter, "_find_graph", return_value=graph),
        ):
            result = adapter.restore_style_snapshot(snapshot)

        self.assertEqual(result.target_name, "CurrentGraph")

    def test_worker_dispatch_reads_snapshot_then_applies_patch(self) -> None:
        snapshot = StyleSnapshot("Graph1", [1], set(), {1: {}})
        result = ApplyResult("Graph1", [1], [], [])

        class FakeAdapter:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def read_style_snapshot(self, style_patch: FigureStylePatch) -> StyleSnapshot:
                self.calls.append("snapshot")
                self.asserted_patch = style_patch
                return snapshot

            def apply_style_patch(self, style_patch: FigureStylePatch) -> ApplyResult:
                self.calls.append("apply")
                self.asserted_patch = style_patch
                return result

        adapter = FakeAdapter()
        response = dispatch(adapter, "apply_patch", {"patch": patch_to_dict(self.patch)})  # type: ignore[arg-type]

        self.assertEqual(adapter.calls, ["snapshot", "apply"])
        self.assertEqual(response["snapshot"]["target_name"], "Graph1")


if __name__ == "__main__":
    unittest.main()
