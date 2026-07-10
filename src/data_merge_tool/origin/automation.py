from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Any, Sequence

import pandas as pd

from ..errors import UserVisibleError
from .field_handlers import OriginStyleFieldsMixin
from .protocol import (
    GraphInfo,
    LayerInfo,
    OriginAutomationError,
)
from .windowing import (
    activate_visible_origin_window as _activate_visible_origin_window,
    visible_origin_window_titles as _visible_origin_windows,
)


def _require_visible_origin_window() -> None:
    if _visible_origin_windows():
        return
    raise OriginAutomationError(
        "未检测到已打开且可见的 Origin/OriginPro 窗口。请先手动启动 Origin，"
        "确认主窗口已显示并许可可用后再重试。"
    )


def _wait_for_visible_origin_window(timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _visible_origin_windows():
            return True
        time.sleep(0.1)
    return bool(_visible_origin_windows())


def safe_origin_long_name(label: str | None, max_base_length: int = 56) -> str:
    clean_label = re.sub(r"[\r\n\t]+", " ", label or "")
    clean_label = re.sub(r"\s+", " ", clean_label).strip()
    clean_label = re.sub(r'[\\/:*?"<>|]+', "-", clean_label)
    clean_label = clean_label.strip(" -_.") or "合并数据"

    if len(clean_label) > max_base_length:
        tail_length = max(8, (max_base_length - 3) // 3)
        head_length = max_base_length - tail_length - 3
        head = clean_label[:head_length].rstrip(" -_.")
        tail = clean_label[-tail_length:].lstrip(" -_.")
        clean_label = f"{head}...{tail}"

    return f"{clean_label} {time.strftime('%H%M')}"


def _write_dataframe_to_origin(
    op: Any,
    df: pd.DataFrame,
    axis_spec: str = "",
    long_names: Sequence[str] | None = None,
    comments: Sequence[str] | None = None,
    workbook_label: str | None = None,
) -> str:
    worksheet = op.new_sheet("w", lname=safe_origin_long_name(workbook_label))
    if worksheet is None:
        raise UserVisibleError("Origin 已连接，但没有成功创建新的工作簿。")
    worksheet.from_df(df)
    if axis_spec:
        worksheet.cols_axis(axis_spec)
    if long_names is not None:
        worksheet.set_labels(list(long_names), "L")
    if comments is not None:
        worksheet.set_labels(list(comments), "C")
    worksheet.activate()

    book = worksheet.get_book()
    book_name = getattr(book, "name", "")
    sheet_name = getattr(worksheet, "name", "")
    return f"{book_name}/{sheet_name}" if book_name and sheet_name else "Origin 工作簿"


class OriginAdapter(OriginStyleFieldsMixin):
    def __init__(self) -> None:
        self._op: Any | None = None
        self._connected = False

    def _origin(self) -> Any:
        if self._op is not None:
            return self._op
        try:
            import originpro as op
        except ImportError as exc:
            raise OriginAutomationError("当前 Python 环境缺少 originpro。") from exc
        self._op = op
        return op

    def connect(self, *, start_if_missing: bool = False) -> Any:
        try:
            _require_visible_origin_window()
        except OriginAutomationError:
            self._connected = False
            if not start_if_missing:
                raise
            op = self._origin()
            try:
                op.set_show(True)
            except Exception as start_exc:
                raise OriginAutomationError(
                    "无法启动 Origin/OriginPro。请确认已安装且许可可用。"
                ) from start_exc
            if not _wait_for_visible_origin_window():
                raise OriginAutomationError(
                    "已尝试启动 Origin/OriginPro，但未检测到可见主窗口。请检查许可或启动提示。"
                )
            self._connected = True
            _activate_visible_origin_window()
            return op

        op = self._origin()
        if self._connected:
            return op
        try:
            op.attach()
        except Exception as exc:
            raise OriginAutomationError(
                "未检测到可连接的 Origin/OriginPro 实例。请先手动启动 Origin，"
                "确认主窗口已显示并许可可用后再重试。"
            ) from exc
        op.set_show(True)
        _require_visible_origin_window()
        self._connected = True
        _activate_visible_origin_window()
        return op

    def import_dataframe(
        self,
        df: pd.DataFrame,
        axis_spec: str = "",
        long_names: Sequence[str] | None = None,
        comments: Sequence[str] | None = None,
        workbook_label: str | None = None,
    ) -> str:
        op = self.connect(start_if_missing=True)
        try:
            result = _write_dataframe_to_origin(op, df, axis_spec, long_names, comments, workbook_label)
            _activate_visible_origin_window()
            return result
        except UserVisibleError:
            raise
        except Exception as exc:
            raise UserVisibleError(
                "originpro 导入失败。请确认 Origin/OriginPro 已安装、许可可用，并且允许外部 Python 连接。\n\n"
                f"原始错误：{exc}"
            ) from exc

    def active_context(self, op: Any | None = None) -> str:
        origin: Any = self._origin() if op is None else op
        pieces: list[str] = []
        try:
            project = str(origin.po.GetProjectName()).strip()
            if project:
                pieces.append(f"项目：{project}")
        except Exception:
            pass
        try:
            active_page = origin.po.ActivePage
            page_name = str(active_page.GetName()).strip() if active_page is not None else ""
            if page_name:
                pieces.append(f"活动窗口：{page_name}")
        except Exception:
            pass
        return "；".join(pieces)

    def _active_window_error(self, op: Any, expected: str) -> OriginAutomationError:
        context = self.active_context(op)
        suffix = f"当前连接到：{context}。" if context else "未能取得当前连接信息。"
        return OriginAutomationError(f"当前 Origin 活动窗口不是 {expected}。{suffix}请先切到目标 Origin 文件中的对应窗口，再重试。")

    def detach(self, force: bool = False) -> None:
        if self._op is None:
            return
        if not force:
            return
        try:
            self._op.detach()
        finally:
            self._op = None
            self._connected = False


    def _find_graph(self, op: Any) -> Any:
        try:
            graph = op.find_graph()
        except Exception as exc:
            raise self._active_window_error(op, "图窗口") from exc
        if graph is None:
            raise self._active_window_error(op, "图窗口")
        return graph

    def _find_sheet(self, op: Any) -> Any:
        try:
            worksheet = op.find_sheet()
        except Exception as exc:
            raise self._active_window_error(op, "worksheet") from exc
        if worksheet is None:
            raise self._active_window_error(op, "worksheet")
        return worksheet
    def scan_active_graph(self) -> GraphInfo:
        op = self.connect()
        graph = self._find_graph(op)

        layers: list[LayerInfo] = []
        for zero_index in range(len(graph)):
            layer = graph[zero_index]
            plots = layer.plot_list()
            layers.append(
                LayerInfo(
                    index=zero_index + 1,
                    plot_count=len(plots),
                )
            )

        return GraphInfo(
            name=getattr(graph, "name", "Active Graph"),
            layers=layers,
        )

    def read_active_layer_style(self, layer_index: int = 1) -> dict[str, Any]:
        op = self.connect()
        graph = self._find_graph(op)
        if layer_index < 1 or layer_index > len(graph):
            raise OriginAutomationError(f"当前图没有 Layer {layer_index}。")
        return self._read_graph_layer_style(op, graph, layer_index)

    def plot_active_sheet(self, plot_kind: str) -> str:
        op = self.connect()
        worksheet = self._find_sheet(op)

        plot_id = {"线图": 200, "散点图": 201, "线+符号": 202}.get(plot_kind, 200)
        try:
            if not self._has_worksheet_selection(op):
                self._select_entire_worksheet(worksheet)
            worksheet.lt_exec(f"worksheet -p {plot_id};")
        except Exception as exc:
            raise OriginAutomationError("Origin 未能根据当前 worksheet 选区绘图。请确认已选中要绘制的数据列或数据范围。") from exc
        return f"已调用 Origin 当前选区绘图：{plot_kind}。"

    @staticmethod
    def _has_worksheet_selection(op: Any) -> bool:
        c1 = op.lt_int("SELC1")
        c2 = op.lt_int("SELC2")
        r1 = op.lt_int("SELR1")
        r2 = op.lt_int("SELR2")
        return any(value > 0 for value in (c1, c2, r1, r2))

    @staticmethod
    def _select_entire_worksheet(worksheet: Any) -> None:
        column_count = int(getattr(worksheet, "cols", 0))
        if column_count <= 0:
            raise OriginAutomationError("当前 worksheet 没有可绘制的列。")
        worksheet.lt_exec(f"worksheet -s 1 0 {column_count} 0;")

    def export_active_graph(self, directory: Path, formats: list[str], width_px: int) -> list[Path]:
        op = self.connect()
        graph = self._find_graph(op)
        directory.mkdir(parents=True, exist_ok=True)
        graph_name = getattr(graph, "name", "graph")
        exported: list[Path] = []
        for fmt in formats:
            path = directory / f"{graph_name}.{fmt}"
            result = graph.save_fig(str(path), type=fmt, replace=True, width=width_px)
            if result:
                exported.append(Path(result))
        if not exported:
            raise OriginAutomationError("Origin 没有返回成功导出的文件。")
        return exported
