from __future__ import annotations

from abc import ABC, abstractmethod
import math
import re
from typing import Any

from .protocol import ApplyResult, FigureStylePatch, OriginAutomationError, StyleSnapshot


class OriginStyleFieldsMixin(ABC):
    """Read, apply, and restore Origin graph style fields."""

    @abstractmethod
    def connect(self, *, start_if_missing: bool = False) -> Any:
        """Return the connected originpro module supplied by the adapter."""

    @abstractmethod
    def _find_graph(self, op: Any) -> Any:
        """Return the active graph supplied by the adapter."""

    def read_style_snapshot(self, patch: FigureStylePatch) -> StyleSnapshot:
        op = self.connect()
        graph = self._find_graph(op)
        layer_indices = self._resolve_layers(graph, patch)
        if not layer_indices:
            raise OriginAutomationError("没有可读取的目标图层。")
        return StyleSnapshot(
            target_name=getattr(graph, "name", "Active Graph"),
            layer_indices=layer_indices,
            enabled_paths=set(patch.enabled_paths),
            styles={index: self._read_graph_layer_style(op, graph, index) for index in layer_indices},
        )

    def apply_style_patch(self, patch: FigureStylePatch) -> ApplyResult:
        op = self.connect()
        graph = self._find_graph(op)
        return self._apply_style_patch_to_graph(graph, patch)

    def restore_style_snapshot(self, snapshot: StyleSnapshot) -> ApplyResult:
        op = self.connect()
        graph = self._find_graph(op)

        applied: list[str] = []
        failed: list[str] = []

        def run(base_path: str, path: str, callback: Any) -> None:
            if base_path not in snapshot.enabled_paths:
                return
            try:
                callback()
                applied.append(path)
            except Exception as exc:
                failed.append(f"{path}: {exc}")

        first_style = next(iter(snapshot.styles.values()), None)
        if first_style is not None:
            page = first_style.get("page", {})
            if isinstance(page, dict):
                run("page.size_in", "page.size_in", lambda: self._apply_page_size(graph, self._require_page_size(page)))
                run("page.anti_alias", "page.anti_alias", lambda: self._apply_page_antialias(graph, page))

        for layer_index in snapshot.layer_indices:
            if layer_index < 1 or layer_index > len(graph):
                failed.append(f"layer[{layer_index}]: current graph does not contain this layer")
                continue
            style = snapshot.styles.get(layer_index, {})
            layer = graph[layer_index - 1]
            layer_values = style.get("layer", {})
            plot_values = style.get("plot", {})
            text_values = style.get("text", {})
            axis_values = style.get("axis", {})
            legend_values = style.get("legend", {})
            if isinstance(layer_values, dict):
                run(
                    "layer.geometry_in",
                    f"layer.geometry_in[{layer_index}]",
                    lambda layer=layer, values=layer_values: self._apply_layer_geometry(layer, self._require_layer_geometry(values)),
                )
                run(
                    "layer.frame",
                    f"layer.frame[{layer_index}]",
                    lambda layer=layer, values=layer_values: self._apply_layer_frame(layer, values),
                )
                run(
                    "layer.line_width_pt",
                    f"layer.line_width_pt[{layer_index}]",
                    lambda layer=layer, values=layer_values: self._apply_layer_line_width(layer, self._require_layer_line_width(values)),
                )
                run(
                    "layer.scale_elements",
                    f"layer.scale_elements[{layer_index}]",
                    lambda layer=layer, values=layer_values: self._apply_layer_scale_elements(layer, self._require_layer_scale(values)),
                )
            if isinstance(plot_values, dict):
                run(
                    "plot.line_width_pt",
                    f"plot.line_width_pt[{layer_index}]",
                    lambda layer=layer, values=plot_values: self._apply_plot_line_width(layer, self._require_plot_line_width(values)),
                )
                run(
                    "plot.symbol_size_pt",
                    f"plot.symbol_size_pt[{layer_index}]",
                    lambda layer=layer, values=plot_values: self._apply_plot_symbol_size(layer, self._require_plot_symbol_size(values)),
                )
            if isinstance(text_values, dict):
                restore_text = {
                    "x_title": text_values.get("x_title_raw", text_values.get("x_title", "")),
                    "y_title": text_values.get("y_title_raw", text_values.get("y_title", "")),
                    "legend_text": text_values.get("legend_text_raw", text_values.get("legend_text", "")),
                    "title_font_size_pt": text_values.get("title_font_size_pt"),
                    "tick_font_size_pt": text_values.get("tick_font_size_pt"),
                    "legend_font_size_pt": text_values.get("legend_font_size_pt"),
                }
                run(
                    "text.x_title",
                    f"text.x_title[{layer_index}]",
                    lambda layer=layer, values=restore_text: self._apply_axis_title(layer, "x", values),
                )
                run(
                    "text.y_title",
                    f"text.y_title[{layer_index}]",
                    lambda layer=layer, values=restore_text: self._apply_axis_title(layer, "y", values),
                )
                run(
                    "text.legend_text",
                    f"text.legend_text[{layer_index}]",
                    lambda layer=layer, values=restore_text: self._apply_legend_text(layer, values),
                )
                run(
                    "text.title_size_pt",
                    f"text.title_size_pt[{layer_index}]",
                    lambda layer=layer, values=restore_text: self._apply_axis_title_size(layer, self._require_text_size(values, "title_font_size_pt")),
                )
                run(
                    "text.tick_size_pt",
                    f"text.tick_size_pt[{layer_index}]",
                    lambda layer=layer, values=restore_text: self._apply_axis_tick_size(layer, self._require_text_size(values, "tick_font_size_pt")),
                )
                run(
                    "text.legend_size_pt",
                    f"text.legend_size_pt[{layer_index}]",
                    lambda layer=layer, values=restore_text: self._apply_legend_size(layer, self._require_text_size(values, "legend_font_size_pt")),
                )
            if isinstance(axis_values, dict):
                run(
                    "axis.x_scale",
                    f"axis.x_scale[{layer_index}]",
                    lambda layer=layer, values=axis_values: self._apply_axis_scale(layer, "x", self._require_axis_scale(values, "x")),
                )
                run(
                    "axis.y_scale",
                    f"axis.y_scale[{layer_index}]",
                    lambda layer=layer, values=axis_values: self._apply_axis_scale(layer, "y", self._require_axis_scale(values, "y")),
                )
                run(
                    "axis.grid",
                    f"axis.grid[{layer_index}]",
                    lambda layer=layer, values=axis_values: self._apply_axis_grid(layer, values),
                )
            if isinstance(legend_values, dict):
                restore_legend = {
                    "visibility": "show" if legend_values.get("visibility") else "hide",
                    "frame": bool(legend_values.get("frame")),
                    "x": legend_values.get("x"),
                    "y": legend_values.get("y"),
                }
                run(
                    "legend.visibility",
                    f"legend.visibility[{layer_index}]",
                    lambda layer=layer, values=restore_legend: self._apply_legend_visibility(layer, values),
                )
                run(
                    "legend.frame",
                    f"legend.frame[{layer_index}]",
                    lambda layer=layer, values=restore_legend: self._apply_legend_frame(layer, values),
                )
                run(
                    "legend.position",
                    f"legend.position[{layer_index}]",
                    lambda layer=layer, values=restore_legend: self._restore_legend_xy(layer, values),
                )

        return ApplyResult(
            target_name=getattr(graph, "name", "Active Graph"),
            layer_indices=snapshot.layer_indices,
            applied=applied,
            failed=failed,
        )

    def _read_graph_layer_style(self, op: Any, graph: Any, layer_index: int) -> dict[str, Any]:
        layer = graph[layer_index - 1]
        try:
            layer.activate()
        except Exception:
            pass
        legend = layer.label("legend") or layer.label("Legend")
        plots = layer.plot_list()
        first_plot = plots[0] if plots else None
        x_title = layer.axis("x").title or ""
        y_title = layer.axis("y").title or ""
        legend_text = self._read_legend_raw_text(op, legend)

        return {
            "page": {
                "width_in": self._try_page_in(graph, "width", "resx"),
                "height_in": self._try_page_in(graph, "height", "resy"),
                "anti_alias": self._try_get_int(graph, "aa"),
            },
            "layer": self._read_layer_style_in_inches(layer),
            "text": {
                "x_title": self._resolve_origin_text(op, x_title),
                "y_title": self._resolve_origin_text(op, y_title),
                "legend_text": self._resolve_origin_text(op, legend_text),
                "x_title_raw": x_title,
                "y_title_raw": y_title,
                "legend_text_raw": legend_text,
                "title_font_size_pt": self._try_label_float(layer, "xb", "fsize"),
                "tick_font_size_pt": self._try_get_float(layer, "x.label.pt"),
                "legend_font_size_pt": self._try_label_float(layer, "legend", "fsize"),
            },
            "axis": {
                "x_scale": self._scale_name(self._try_axis_scale(layer, "x")),
                "y_scale": self._scale_name(self._try_axis_scale(layer, "y")),
                "show_grid": self._try_get_int(layer, "x.showGrids"),
            },
            "plot": {
                "line_width_pt": self._try_plot_line_width(layer, first_plot),
                "symbol_size_pt": self._try_plot_attr(first_plot, "symbol_size"),
            },
            "legend": {
                "visibility": self._try_get_int(layer, "legend.show"),
                "frame": self._try_get_int(layer, "legend.background"),
                "x": self._try_label_float(layer, "legend", "x"),
                "y": self._try_label_float(layer, "legend", "y"),
            },
        }

    @staticmethod
    def _require_number(values: dict[str, Any], key: str) -> float:
        value = values.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise OriginAutomationError(f"cannot restore unreadable value: {key}")
        return float(value)

    def _require_page_size(self, page: dict[str, Any]) -> dict[str, Any]:
        restored = dict(page)
        restored["width_in"] = self._require_number(page, "width_in")
        restored["height_in"] = self._require_number(page, "height_in")
        return restored

    def _require_layer_geometry(self, layer_values: dict[str, Any]) -> dict[str, Any]:
        restored = dict(layer_values)
        for key in ("left_in", "top_in", "width_in", "height_in"):
            restored[key] = self._require_number(layer_values, key)
        return restored

    def _require_layer_line_width(self, layer_values: dict[str, Any]) -> dict[str, Any]:
        restored = dict(layer_values)
        restored["line_width_pt"] = self._require_number(layer_values, "line_width_pt")
        return restored

    def _require_layer_scale(self, layer_values: dict[str, Any]) -> dict[str, Any]:
        restored = dict(layer_values)
        if restored.get("scale_fixed", False):
            restored["scale_factor"] = self._require_number(layer_values, "scale_factor")
        else:
            restored["scale_factor"] = 1.0
        return restored

    def _require_plot_line_width(self, plot_values: dict[str, Any]) -> dict[str, Any]:
        restored = dict(plot_values)
        restored["line_width_pt"] = self._require_number(plot_values, "line_width_pt")
        return restored

    def _require_plot_symbol_size(self, plot_values: dict[str, Any]) -> dict[str, Any]:
        restored = dict(plot_values)
        restored["symbol_size_pt"] = self._require_number(plot_values, "symbol_size_pt")
        return restored

    def _require_text_size(self, text_values: dict[str, Any], key: str) -> dict[str, Any]:
        restored = dict(text_values)
        restored[key] = self._require_number(text_values, key)
        return restored

    def _require_axis_scale(self, axis_values: dict[str, Any], axis_name: str) -> dict[str, Any]:
        key = f"{axis_name}_scale"
        value = axis_values.get(key)
        if value not in {"linear", "log10"}:
            raise OriginAutomationError(f"cannot restore unreadable value: {key}")
        return {key: value}

    def _restore_legend_xy(self, layer: Any, legend_values: dict[str, Any]) -> None:
        x = self._require_number(legend_values, "x")
        y = self._require_number(legend_values, "y")
        layer.lt_exec(f"legend.x={x:.8g};legend.y={y:.8g};")

    def _read_layer_style_in_inches(self, layer: Any) -> dict[str, Any]:
        original_unit = self._try_get_int(layer, "unit")
        try:
            layer.lt_exec("layer.unit=2;")
            return {
                "left_in": self._try_get_float(layer, "left"),
                "top_in": self._try_get_float(layer, "top"),
                "width_in": self._try_get_float(layer, "width"),
                "height_in": self._try_get_float(layer, "height"),
                "line_width_pt": self._try_get_float(layer, "x.thickness"),
                "frame": self._read_layer_frame(layer),
                "scale_fixed": bool(self._try_get_int(layer, "fixed")),
                "scale_factor": self._try_get_float(layer, "factor"),
            }
        finally:
            if original_unit is not None:
                try:
                    layer.lt_exec(f"layer.unit={original_unit};")
                except Exception:
                    pass

    def _read_layer_frame(self, layer: Any) -> dict[str, bool]:
        x_axes = self._try_get_int(layer, "x.showAxes")
        y_axes = self._try_get_int(layer, "y.showAxes")
        return {
            "bottom": True if x_axes is None else bool(x_axes & 1),
            "top": True if x_axes is None else bool(x_axes & 2),
            "left": True if y_axes is None else bool(y_axes & 1),
            "right": True if y_axes is None else bool(y_axes & 2),
        }

    def _read_legend_raw_text(self, op: Any, legend: Any | None) -> str:
        fallback = str(getattr(legend, "text", "") or "") if legend is not None else ""
        for expression in ("legend.text$", "Legend.text$"):
            value = self._evaluate_origin_string_expression(op, expression)
            if "\\l(" in value or "\\L(" in value or "%(" in value:
                return value
        return fallback

    def _resolve_origin_text(self, op: Any, text: str) -> str:
        if not text:
            return text
        resolved = text
        for token in sorted(set(re.findall(r"%\([^()]+\)", text)), key=len, reverse=True):
            value = self._evaluate_origin_string_expression(op, token)
            if value and value != token:
                resolved = resolved.replace(token, value)
        return self._clean_origin_text_markup(resolved)

    @staticmethod
    def _evaluate_origin_string_expression(op: Any, expression: str) -> str:
        try:
            var_name = "__opanel_text"
            op.lt_exec(f"{var_name}$={expression};")
            return str(op.get_lt_str(var_name)).strip()
        except Exception:
            return ""

    @staticmethod
    def _clean_origin_text_markup(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
        text = re.sub(r"\\[lL]\([^)]*\)", "", text)
        text = re.sub(r"\\[ib+\-]\((.*?)\)", r"\1", text)
        return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()

    @staticmethod
    def _try_get_float(obj: Any, prop: str) -> float | None:
        try:
            return float(obj.get_float(prop))
        except Exception:
            return None

    @staticmethod
    def _try_get_int(obj: Any, prop: str) -> int | None:
        try:
            return int(obj.get_int(prop))
        except Exception:
            return None

    def _try_page_in(self, graph: Any, size_prop: str, resolution_prop: str) -> float | None:
        size = self._try_get_float(graph, size_prop)
        resolution = self._try_get_float(graph, resolution_prop)
        if size is None or not resolution:
            return None
        return size / resolution

    @staticmethod
    def _try_plot_line_width(layer: Any, plot: Any) -> float | None:
        if plot is None:
            return None
        try:
            return float(layer.get_float(f"plot{plot.index() + 1}.line.width"))
        except Exception:
            try:
                return float(plot.get_float("line.width"))
            except Exception:
                return None

    @staticmethod
    def _try_axis_scale(layer: Any, axis_name: str) -> int | None:
        try:
            return int(layer.axis(axis_name).scale)
        except Exception:
            return None

    @staticmethod
    def _try_label_float(layer: Any, name: str, prop: str) -> float | None:
        try:
            label = layer.label(name) or layer.label(name.capitalize())
            if label is None:
                return None
            return float(label.get_float(prop))
        except Exception:
            return None

    @staticmethod
    def _try_plot_attr(plot: Any, attr: str) -> float | int | None:
        if plot is None:
            return None
        try:
            return getattr(plot, attr)
        except Exception:
            return None

    @staticmethod
    def _scale_name(value: int | None) -> str | None:
        if value == 1:
            return "linear"
        if value == 2:
            return "log10"
        return None

    def _apply_style_patch_to_graph(self, graph: Any, patch: FigureStylePatch) -> ApplyResult:
        layer_indices = self._resolve_layers(graph, patch)
        if not layer_indices:
            raise OriginAutomationError("没有可应用的目标图层。")

        applied: list[str] = []
        failed: list[str] = []

        def run(path: str, callback: Any) -> None:
            base_path = path.split("[", 1)[0]
            if base_path not in patch.enabled_paths:
                return
            try:
                callback()
                applied.append(path)
            except Exception as exc:
                failed.append(f"{path}: {exc}")

        run("page.size_in", lambda: self._apply_page_size(graph, patch.page))
        run("page.anti_alias", lambda: self._apply_page_antialias(graph, patch.page))

        for layer_index in layer_indices:
            layer = graph[layer_index - 1]
            run(
                f"layer.geometry_in[{layer_index}]",
                lambda layer=layer: self._apply_layer_geometry(layer, patch.layer),
            )
            run(
                f"layer.frame[{layer_index}]",
                lambda layer=layer: self._apply_layer_frame(layer, patch.layer),
            )
            run(
                f"layer.line_width_pt[{layer_index}]",
                lambda layer=layer: self._apply_layer_line_width(layer, patch.layer),
            )
            run(
                f"layer.scale_elements[{layer_index}]",
                lambda layer=layer: self._apply_layer_scale_elements(layer, patch.layer),
            )
            run(
                f"plot.line_width_pt[{layer_index}]",
                lambda layer=layer: self._apply_plot_line_width(layer, patch.plot),
            )
            run(
                f"plot.symbol_size_pt[{layer_index}]",
                lambda layer=layer: self._apply_plot_symbol_size(layer, patch.plot),
            )
            run(
                f"text.x_title[{layer_index}]",
                lambda layer=layer: self._apply_axis_title(layer, "x", patch.text),
            )
            run(
                f"text.y_title[{layer_index}]",
                lambda layer=layer: self._apply_axis_title(layer, "y", patch.text),
            )
            run(
                f"text.legend_text[{layer_index}]",
                lambda layer=layer: self._apply_legend_text(layer, patch.text),
            )
            run(
                f"text.title_size_pt[{layer_index}]",
                lambda layer=layer: self._apply_axis_title_size(layer, patch.text),
            )
            run(
                f"text.tick_size_pt[{layer_index}]",
                lambda layer=layer: self._apply_axis_tick_size(layer, patch.text),
            )
            run(
                f"text.legend_size_pt[{layer_index}]",
                lambda layer=layer: self._apply_legend_size(layer, patch.text),
            )
            run(
                f"axis.x_scale[{layer_index}]",
                lambda layer=layer: self._apply_axis_scale(layer, "x", patch.axis),
            )
            run(
                f"axis.y_scale[{layer_index}]",
                lambda layer=layer: self._apply_axis_scale(layer, "y", patch.axis),
            )
            run(
                f"axis.grid[{layer_index}]",
                lambda layer=layer: self._apply_axis_grid(layer, patch.axis),
            )
            run(
                f"legend.visibility[{layer_index}]",
                lambda layer=layer: self._apply_legend_visibility(layer, patch.legend),
            )
            run(
                f"legend.frame[{layer_index}]",
                lambda layer=layer: self._apply_legend_frame(layer, patch.legend),
            )
            run(
                f"legend.position[{layer_index}]",
                lambda layer=layer: self._apply_legend_position(layer, patch.legend),
            )

        return ApplyResult(
            target_name=getattr(graph, "name", "Active Graph"),
            layer_indices=layer_indices,
            applied=applied,
            failed=failed,
        )

    def _resolve_layers(self, graph: Any, patch: FigureStylePatch) -> list[int]:
        count = len(graph)
        if patch.target.layer_scope == "all":
            return list(range(1, count + 1))
        indices = [idx for idx in patch.target.layer_indices if 1 <= idx <= count]
        return sorted(set(indices))

    def _apply_page_size(self, graph: Any, page: dict[str, Any]) -> None:
        width_in = float(page["width_in"])
        height_in = float(page["height_in"])
        graph.lt_exec(
            "page.kar=0;"
            f"page.width=page.resx*{width_in:.8g};"
            f"page.height=page.resy*{height_in:.8g};"
        )

    def _apply_page_antialias(self, graph: Any, page: dict[str, Any]) -> None:
        graph.lt_exec(f"page.aa={1 if page.get('anti_alias', False) else 0};")

    def _apply_layer_geometry(self, layer: Any, layer_values: dict[str, Any]) -> None:
        left = float(layer_values["left_in"])
        top = float(layer_values["top_in"])
        width = float(layer_values["width_in"])
        height = float(layer_values["height_in"])
        layer.lt_exec(
            "layer.unit=2;"
            f"layer.left={left:.8g};"
            f"layer.top={top:.8g};"
            f"layer.width={width:.8g};"
            f"layer.height={height:.8g};"
        )

    def _apply_layer_scale_elements(self, layer: Any, layer_values: dict[str, Any]) -> None:
        if layer_values.get("scale_fixed", False):
            factor = float(layer_values.get("scale_factor", 1.0))
            layer.lt_exec(f"layer.fixed=1;layer.factor={factor:.8g};")
        else:
            layer.lt_exec("layer.fixed=0;")

    def _apply_layer_frame(self, layer: Any, layer_values: dict[str, Any]) -> None:
        frame = layer_values["frame"]
        x_axes = (1 if frame.get("bottom", True) else 0) + (2 if frame.get("top", True) else 0)
        y_axes = (1 if frame.get("left", True) else 0) + (2 if frame.get("right", True) else 0)
        layer.lt_exec(f"layer.x.showAxes={x_axes};layer.y.showAxes={y_axes};")

    def _apply_layer_line_width(self, layer: Any, layer_values: dict[str, Any]) -> None:
        width = float(layer_values["line_width_pt"])
        layer.lt_exec(
            f"layer.x.thickness={width:.8g};"
            f"layer.x2.thickness={width:.8g};"
            f"layer.y.thickness={width:.8g};"
            f"layer.y2.thickness={width:.8g};"
            f"layer.x.tickthickness={width:.8g};"
            f"layer.x2.tickthickness={width:.8g};"
            f"layer.y.tickthickness={width:.8g};"
            f"layer.y2.tickthickness={width:.8g};"
        )

    def _apply_plot_line_width(self, layer: Any, plot_values: dict[str, Any]) -> None:
        width = float(plot_values["line_width_pt"])
        for plot in layer.plot_list():
            plot.set_cmd(f"-wp {width:.8g}")

    def _apply_plot_symbol_size(self, layer: Any, plot_values: dict[str, Any]) -> None:
        size = float(plot_values["symbol_size_pt"])
        for plot in layer.plot_list():
            plot.symbol_size = size

    def _apply_axis_title(self, layer: Any, axis_name: str, text_values: dict[str, Any]) -> None:
        title = text_values[f"{axis_name}_title"]
        layer.axis(axis_name).title = str(title)

    def _apply_legend_text(self, layer: Any, text_values: dict[str, Any]) -> None:
        legend = layer.label("legend") or layer.label("Legend")
        if legend is None:
            layer.lt_exec("legend;")
            legend = layer.label("legend") or layer.label("Legend")
        if legend is None:
            raise OriginAutomationError("当前图层没有可编辑的 legend 文本对象。")
        legend_text = str(text_values.get("legend_text", "")).strip()
        if not legend_text:
            return
        legend.text = legend_text

    def _apply_axis_title_size(self, layer: Any, text_values: dict[str, Any]) -> None:
        size = float(text_values["title_font_size_pt"])
        layer.lt_exec(
            f"xb.fsize={size:.8g};"
            f"xt.fsize={size:.8g};"
            f"yl.fsize={size:.8g};"
            f"yr.fsize={size:.8g};"
        )

    def _apply_axis_tick_size(self, layer: Any, text_values: dict[str, Any]) -> None:
        size = float(text_values["tick_font_size_pt"])
        layer.lt_exec(
            f"layer.x.label.pt={size:.8g};"
            f"layer.y.label.pt={size:.8g};"
        )

    def _apply_axis_scale(self, layer: Any, axis_name: str, axis_values: dict[str, Any]) -> None:
        scale = axis_values.get(f"{axis_name}_scale", "keep")
        if scale == "keep":
            return
        layer.axis(axis_name).scale = "log10" if scale == "log10" else "linear"

    def _apply_axis_grid(self, layer: Any, axis_values: dict[str, Any]) -> None:
        value = 1 if axis_values.get("show_grid", False) else 0
        layer.lt_exec(f"layer.x.showGrids={value};layer.y.showGrids={value};")

    def _apply_legend_visibility(self, layer: Any, legend_values: dict[str, Any]) -> None:
        visibility = legend_values.get("visibility", "keep")
        if visibility == "keep":
            return
        layer.lt_exec(f"legend.show={1 if visibility == 'show' else 0};")

    def _apply_legend_frame(self, layer: Any, legend_values: dict[str, Any]) -> None:
        layer.lt_exec(f"legend.background={1 if legend_values.get('frame', False) else 0};")

    def _apply_legend_size(self, layer: Any, text_values: dict[str, Any]) -> None:
        size = float(text_values["legend_font_size_pt"])
        layer.lt_exec(f"legend.fsize={size:.8g};")

    def _apply_legend_position(self, layer: Any, legend_values: dict[str, Any]) -> None:
        position = legend_values.get("position", "keep")
        if position == "keep":
            return
        if position == "upper_left":
            layer.lt_exec("legend.x=layer.x.from+legend.dx/2;legend.y=layer.y.to-legend.dy/2;")
        elif position == "upper_right":
            layer.lt_exec("legend.x=layer.x.to-legend.dx/2;legend.y=layer.y.to-legend.dy/2;")
        elif position == "lower_left":
            layer.lt_exec("legend.x=layer.x.from+legend.dx/2;legend.y=layer.y.from+legend.dy/2;")
        elif position == "lower_right":
            layer.lt_exec("legend.x=layer.x.to-legend.dx/2;legend.y=layer.y.from+legend.dy/2;")
        elif position == "best":
            layer.lt_exec("legend.smartpos=1;")
