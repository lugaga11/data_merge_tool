from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from typing import Any
from uuid import uuid4

import pandas as pd

from .origin_protocol import (
    DEFAULT_ORIGIN_TIMEOUT_SECONDS,
    LONG_ORIGIN_TIMEOUT_SECONDS,
    ApplyResult,
    FigureStylePatch,
    GraphInfo,
    OriginWorkerError,
    StyleSnapshot,
    apply_result_from_dict,
    graph_info_from_dict,
    patch_to_dict,
    paths_from_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)


class OriginWorkerClient:
    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    def _command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--origin-worker"]
        return [sys.executable, "-m", "data_merge_tool.origin_worker"]

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        src_root = str(Path(__file__).resolve().parents[1])
        current = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_root if not current else src_root + os.pathsep + current
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return env

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        cwd = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
        self._process = subprocess.Popen(
            self._command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._environment(),
            cwd=str(cwd),
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        return self._process

    def _kill_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            self._close_process_pipes(process)

    @staticmethod
    def _close_process_pipes(process: subprocess.Popen[str]) -> None:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass

    def _readline_with_timeout(self, process: subprocess.Popen[str], timeout_seconds: float) -> str:
        if process.stdout is None:
            raise OriginWorkerError("Origin 自动化子进程 stdout 不可用。")
        stdout = process.stdout
        holder: dict[str, str] = {}

        def read() -> None:
            holder["line"] = stdout.readline()

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reader.join(timeout_seconds)
        if reader.is_alive():
            self._kill_process()
            raise OriginWorkerError("Origin 自动化子进程响应超时，已重置连接，请重试。")
        line = holder.get("line", "")
        if not line:
            self._kill_process()
            raise OriginWorkerError("Origin 自动化子进程已退出，已重置连接，请重试。")
        return line

    def request(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_seconds: float = DEFAULT_ORIGIN_TIMEOUT_SECONDS,
    ) -> Any:
        with self._lock:
            process = self._ensure_process()
            if process.stdin is None:
                self._kill_process()
                raise OriginWorkerError("Origin 自动化子进程 stdin 不可用。")
            stdin = process.stdin
            request_id = self._next_id
            self._next_id += 1
            request = {"id": request_id, "command": command, "payload": payload or {}}
            try:
                stdin.write(json.dumps(request, ensure_ascii=True) + "\n")
                stdin.flush()
            except Exception as exc:
                self._kill_process()
                raise OriginWorkerError("Origin 自动化子进程写入失败，已重置连接，请重试。") from exc
            line = self._readline_with_timeout(process, timeout_seconds)
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                self._kill_process()
                raise OriginWorkerError("Origin 自动化子进程返回了无效响应，已重置连接，请重试。") from exc
            if response.get("id") != request_id:
                self._kill_process()
                raise OriginWorkerError("Origin 自动化子进程响应序号不匹配，已重置连接，请重试。")
            if not response.get("ok"):
                error = response.get("error") or {}
                raise OriginWorkerError(str(error.get("message") or "Origin 自动化失败。"))
            return response.get("result")

    def ping(self) -> dict[str, Any]:
        return dict(self.request("ping", timeout_seconds=10))

    def import_dataframe(
        self,
        df: pd.DataFrame,
        axis_spec: str,
        long_names: list[str],
        comments: list[str],
        workbook_label: str,
    ) -> str:
        temp_dir = Path(tempfile.gettempdir()) / "DataMergeTool" / "origin_worker"
        temp_dir.mkdir(parents=True, exist_ok=True)
        pickle_path = temp_dir / f"{uuid4().hex}.pkl"
        df.to_pickle(pickle_path)
        try:
            result = self.request(
                "import_dataframe",
                {
                    "pickle_path": str(pickle_path),
                    "axis_spec": axis_spec,
                    "long_names": long_names,
                    "comments": comments,
                    "workbook_label": workbook_label,
                },
                timeout_seconds=LONG_ORIGIN_TIMEOUT_SECONDS,
            )
            return str(result)
        finally:
            try:
                pickle_path.unlink()
            except OSError:
                pass

    def plot_active_sheet(self, plot_kind: str) -> tuple[str, GraphInfo]:
        result = dict(self.request("plot_active_sheet", {"plot_kind": plot_kind}))
        return str(result["message"]), graph_info_from_dict(dict(result["graph"]))

    def scan_active_graph(self) -> GraphInfo:
        return graph_info_from_dict(dict(self.request("scan_active_graph")))

    def read_active_layer_style(self, layer_index: int) -> dict[str, Any]:
        return dict(self.request("read_active_layer_style", {"layer_index": layer_index}))

    def apply_patch(self, patch: FigureStylePatch) -> tuple[StyleSnapshot, ApplyResult]:
        result = dict(self.request("apply_patch", {"patch": patch_to_dict(patch)}, timeout_seconds=LONG_ORIGIN_TIMEOUT_SECONDS))
        return snapshot_from_dict(dict(result["snapshot"])), apply_result_from_dict(dict(result["result"]))

    def restore_style_snapshot(self, snapshot: StyleSnapshot) -> ApplyResult:
        return apply_result_from_dict(
            dict(
                self.request(
                    "restore_style_snapshot",
                    {"snapshot": snapshot_to_dict(snapshot)},
                    timeout_seconds=LONG_ORIGIN_TIMEOUT_SECONDS,
                )
            )
        )

    def export_active_graph(self, directory: Path, formats: list[str], width_px: int) -> list[Path]:
        result = self.request(
            "export_active_graph",
            {"directory": str(directory), "formats": formats, "width_px": width_px},
            timeout_seconds=LONG_ORIGIN_TIMEOUT_SECONDS,
        )
        return paths_from_dict([str(path) for path in result])

    def shutdown(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            self._close_process_pipes(process)
            self._process = None
            return
        try:
            self.request("shutdown", timeout_seconds=5)
        except Exception:
            self._kill_process()
        finally:
            self._process = None
