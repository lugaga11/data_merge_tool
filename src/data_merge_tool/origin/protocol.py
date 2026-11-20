from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    plot_count: int


@dataclass(frozen=True)
class GraphInfo:
    name: str
    layers: list[LayerInfo]


@dataclass
class PatchTarget:
    layer_scope: str
    layer_indices: list[int]


@dataclass(kw_only=True)
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


def graph_info_from_dict(data: dict[str, Any]) -> GraphInfo:
    return GraphInfo(
        name=str(data["name"]),
        layers=[LayerInfo(**layer) for layer in data["layers"]],
    )


def patch_to_dict(patch: FigureStylePatch) -> dict[str, Any]:
    return {
        "target": asdict(patch.target),
        "enabled_paths": sorted(patch.enabled_paths),
        "page": patch.page,
        "layer": patch.layer,
        "text": patch.text,
        "plot": patch.plot,
        "axis": patch.axis,
        "legend": patch.legend,
    }


def patch_from_dict(data: dict[str, Any]) -> FigureStylePatch:
    target = data["target"]
    scope = target["layer_scope"]
    if scope not in {"all", "selected"}:
        raise OriginAutomationError(f"未知目标图层范围：{scope}")
    return FigureStylePatch(
        target=PatchTarget(scope, target["layer_indices"]),
        enabled_paths=set(data["enabled_paths"]),
        page=data["page"],
        layer=data["layer"],
        text=data["text"],
        plot=data["plot"],
        axis=data["axis"],
        legend=data["legend"],
    )


def apply_result_from_dict(data: dict[str, Any]) -> ApplyResult:
    return ApplyResult(**data)


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
        layer_indices=data["layer_indices"],
        enabled_paths=set(data["enabled_paths"]),
        styles={int(index): style for index, style in data["styles"].items()},
    )


def paths_to_dict(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths]


def paths_from_dict(paths: list[str]) -> list[Path]:
    return [Path(path) for path in paths]
