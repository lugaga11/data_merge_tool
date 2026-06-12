from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_ORIGIN_TIMEOUT_SECONDS = 90.0
LONG_ORIGIN_TIMEOUT_SECONDS = 180.0


class OriginAutomationError(RuntimeError):
    """User-facing Origin automation error."""


class OriginWorkerError(RuntimeError):
    """Raised in the GUI process when the Origin worker reports or hits an error."""


@dataclass(frozen=True)
class LayerInfo:
    index: int
    name: str
    plot_count: int
    plot_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphInfo:
    name: str
    long_name: str
    layers: list[LayerInfo]


@dataclass
class PatchTarget:
    layer_scope: str = "all"
    layer_indices: list[int] = field(default_factory=list)


@dataclass
class FigureStylePatch:
    target: PatchTarget
    enabled_paths: set[str]
    page: dict[str, Any] = field(default_factory=dict)
    layer: dict[str, Any] = field(default_factory=dict)
    text: dict[str, Any] = field(default_factory=dict)
    plot: dict[str, Any] = field(default_factory=dict)
    axis: dict[str, Any] = field(default_factory=dict)
    legend: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApplyResult:
    target_name: str
    layer_indices: list[int]
    applied: list[str]
    failed: list[str]


@dataclass
class StyleSnapshot:
    target_name: str
    layer_indices: list[int]
    enabled_paths: set[str]
    styles: dict[int, dict[str, Any]]


def layer_info_to_dict(info: LayerInfo) -> dict[str, Any]:
    return {
        "index": info.index,
        "name": info.name,
        "plot_count": info.plot_count,
        "plot_names": list(info.plot_names),
    }


def layer_info_from_dict(data: dict[str, Any]) -> LayerInfo:
    return LayerInfo(
        index=int(data["index"]),
        name=str(data["name"]),
        plot_count=int(data["plot_count"]),
        plot_names=[str(name) for name in data.get("plot_names", [])],
    )


def graph_info_to_dict(info: GraphInfo) -> dict[str, Any]:
    return {
        "name": info.name,
        "long_name": info.long_name,
        "layers": [layer_info_to_dict(layer) for layer in info.layers],
    }


def graph_info_from_dict(data: dict[str, Any]) -> GraphInfo:
    return GraphInfo(
        name=str(data["name"]),
        long_name=str(data.get("long_name", "")),
        layers=[layer_info_from_dict(layer) for layer in data.get("layers", [])],
    )


def patch_to_dict(patch: FigureStylePatch) -> dict[str, Any]:
    return {
        "target": {
            "layer_scope": patch.target.layer_scope,
            "layer_indices": list(patch.target.layer_indices),
        },
        "enabled_paths": sorted(patch.enabled_paths),
        "page": patch.page,
        "layer": patch.layer,
        "text": patch.text,
        "plot": patch.plot,
        "axis": patch.axis,
        "legend": patch.legend,
    }


def patch_from_dict(data: dict[str, Any]) -> FigureStylePatch:
    target = data.get("target", {})
    return FigureStylePatch(
        target=PatchTarget(
            layer_scope=str(target.get("layer_scope", "all")),
            layer_indices=[int(index) for index in target.get("layer_indices", [])],
        ),
        enabled_paths={str(path) for path in data.get("enabled_paths", [])},
        page=dict(data.get("page", {})),
        layer=dict(data.get("layer", {})),
        text=dict(data.get("text", {})),
        plot=dict(data.get("plot", {})),
        axis=dict(data.get("axis", {})),
        legend=dict(data.get("legend", {})),
    )


def apply_result_to_dict(result: ApplyResult) -> dict[str, Any]:
    return {
        "target_name": result.target_name,
        "layer_indices": list(result.layer_indices),
        "applied": list(result.applied),
        "failed": list(result.failed),
    }


def apply_result_from_dict(data: dict[str, Any]) -> ApplyResult:
    return ApplyResult(
        target_name=str(data["target_name"]),
        layer_indices=[int(index) for index in data.get("layer_indices", [])],
        applied=[str(path) for path in data.get("applied", [])],
        failed=[str(path) for path in data.get("failed", [])],
    )


def snapshot_to_dict(snapshot: StyleSnapshot) -> dict[str, Any]:
    return {
        "target_name": snapshot.target_name,
        "layer_indices": list(snapshot.layer_indices),
        "enabled_paths": sorted(snapshot.enabled_paths),
        "styles": {str(index): style for index, style in snapshot.styles.items()},
    }


def snapshot_from_dict(data: dict[str, Any]) -> StyleSnapshot:
    return StyleSnapshot(
        target_name=str(data["target_name"]),
        layer_indices=[int(index) for index in data.get("layer_indices", [])],
        enabled_paths={str(path) for path in data.get("enabled_paths", [])},
        styles={int(index): dict(style) for index, style in dict(data.get("styles", {})).items()},
    )


def paths_to_dict(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths]


def paths_from_dict(paths: list[str]) -> list[Path]:
    return [Path(path) for path in paths]
