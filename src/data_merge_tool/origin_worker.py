from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import UserVisibleError
from .origin_automation import OriginAdapter, import_dataframe_to_origin
from .origin_protocol import (
    OriginAutomationError,
    apply_result_to_dict,
    graph_info_to_dict,
    patch_from_dict,
    paths_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)


def _error_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if isinstance(exc, (OriginAutomationError, UserVisibleError)):
        return message
    if isinstance(exc, SystemError):
        return (
            "Origin 自动化底层组件返回异常。请确认 Origin 当前活动窗口正确，"
            "必要时关闭当前 Origin 项目后重试。\n\n"
            f"原始错误：{message}"
        )
    return message or type(exc).__name__


def dispatch(adapter: OriginAdapter, command: str, payload: dict[str, Any]) -> Any:
    if command == "ping":
        return {"status": "ok"}
    if command == "shutdown":
        adapter.detach(force=True)
        return {"status": "bye"}
    if command == "import_dataframe":
        df = pd.read_pickle(Path(str(payload["pickle_path"])))
        return import_dataframe_to_origin(
            df,
            str(payload.get("axis_spec", "")),
            [str(value) for value in payload.get("long_names", [])],
            [str(value) for value in payload.get("comments", [])],
            str(payload.get("workbook_label", "")),
        )
    if command == "plot_active_sheet":
        message = adapter.plot_active_sheet(str(payload.get("plot_kind", "")))
        graph = adapter.scan_active_graph()
        return {"message": message, "graph": graph_info_to_dict(graph)}
    if command == "scan_active_graph":
        return graph_info_to_dict(adapter.scan_active_graph())
    if command == "read_active_layer_style":
        return adapter.read_active_layer_style(int(payload.get("layer_index", 1)))
    if command == "apply_patch":
        patch = patch_from_dict(dict(payload["patch"]))
        snapshot = adapter.read_style_snapshot(patch)
        result = adapter.apply_style_patch(patch)
        return {"snapshot": snapshot_to_dict(snapshot), "result": apply_result_to_dict(result)}
    if command == "restore_style_snapshot":
        snapshot = snapshot_from_dict(dict(payload["snapshot"]))
        return apply_result_to_dict(adapter.restore_style_snapshot(snapshot))
    if command == "export_active_graph":
        files = adapter.export_active_graph(
            Path(str(payload["directory"])),
            [str(fmt) for fmt in payload.get("formats", [])],
            int(payload.get("width_px", 2400)),
        )
        return paths_to_dict(files)
    raise OriginAutomationError(f"未知 Origin worker 命令：{command}")


def main() -> int:
    adapter = OriginAdapter()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        request_id: object = None
        command = ""
        try:
            request = json.loads(line)
            request_id = request.get("id")
            command = str(request.get("command", ""))
            payload = request.get("payload") or {}
            if not isinstance(payload, dict):
                raise OriginAutomationError("Origin worker payload 必须是对象。")
            result = dispatch(adapter, command, payload)
            response = {"id": request_id, "ok": True, "result": result}
        except Exception as exc:
            response = {
                "id": request_id,
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": _error_message(exc),
                    "traceback": traceback.format_exc(),
                },
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        if command == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
