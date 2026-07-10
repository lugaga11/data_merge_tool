from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any

from .style_registry import filter_known_style_paths


SCHEMA_VERSION = 1


def _app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "DataMergeTool"
    return Path.home() / ".data_merge_tool"


APP_DATA_DIR = _app_data_dir()
USER_PRESETS_PATH = APP_DATA_DIR / "user_presets.json"
DEFAULT_EXPORT_DIR = APP_DATA_DIR / "origin_exports"
PRESETS: dict[str, dict[str, Any]] = {}

DEFAULT_PRESET: dict[str, Any] = {
    "enabled_paths": [],
    "page": {
        "width_in": 3.5,
        "height_in": 2.6,
        "anti_alias": False,
    },
    "layer": {
        "left_in": 0.55,
        "top_in": 0.24,
        "width_in": 2.60,
        "height_in": 1.89,
        "line_width_pt": 0.8,
        "scale_fixed": False,
        "scale_factor": 1.0,
        "frame": {
            "left": True,
            "bottom": True,
            "top": True,
            "right": True,
        },
    },
    "plot": {
        "line_width_pt": 1.2,
        "symbol_size_pt": 4.0,
    },
    "text": {
        "title_font_size_pt": 8.0,
        "tick_font_size_pt": 7.0,
        "legend_font_size_pt": 7.0,
    },
    "axis": {
        "x_scale": "keep",
        "y_scale": "keep",
        "show_grid": False,
    },
    "legend": {
        "visibility": "keep",
        "frame": False,
        "position": "keep",
    },
    "export": {
        "width_px": 2400,
        "formats": ["png", "pdf"],
    },
}


@dataclass(frozen=True)
class PresetLoadResult:
    presets: dict[str, dict[str, Any]]
    warning: str | None = None
    quarantined_path: Path | None = None


@dataclass(frozen=True)
class PresetImportResult:
    presets: dict[str, dict[str, Any]]
    errors: dict[str, str]


class PresetStore:
    def __init__(self, path: Path = USER_PRESETS_PATH) -> None:
        self.path = path

    def load(self) -> PresetLoadResult:
        if not self.path.exists():
            return PresetLoadResult({})

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw_presets = self._extract_presets(data)
        except Exception as exc:
            quarantined = self._quarantine_bad_file()
            return PresetLoadResult(
                {},
                f"用户 preset 文件已损坏，已重命名为 {quarantined.name}，本次启动使用空 preset。原因：{exc}",
                quarantined,
            )

        result = self.validate_many(raw_presets)
        warning = None
        if result.errors:
            names = "、".join(result.errors)
            warning = f"已跳过 {len(result.errors)} 个无效 preset：{names}。"
        return PresetLoadResult(result.presets, warning)

    def save_atomic(self, presets: dict[str, dict[str, Any]]) -> None:
        validated = self.validate_many(presets)
        if validated.errors:
            detail = "；".join(f"{name}: {reason}" for name, reason in validated.errors.items())
            raise ValueError(f"存在无效 preset，未保存：{detail}")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA_VERSION, "presets": validated.presets}
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def load_import_file(self, path: Path) -> PresetImportResult:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_presets = self._extract_presets(data)
        return self.validate_many(raw_presets)

    def validate_many(self, presets: dict[str, Any]) -> PresetImportResult:
        valid: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        for raw_name, raw_preset in presets.items():
            name = str(raw_name).strip()
            if not name:
                errors[str(raw_name)] = "名称不能为空"
                continue
            try:
                valid[name] = self.validate(raw_preset)
            except Exception as exc:
                errors[name] = str(exc)
        return PresetImportResult(valid, errors)

    def validate(self, preset: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(preset, dict):
            raise ValueError("preset 应为 JSON 对象")

        result = deepcopy(DEFAULT_PRESET)
        result["enabled_paths"] = filter_known_style_paths(preset.get("enabled_paths", []))

        page = self._section(preset, "page")
        result["page"]["width_in"] = self._positive_float(page, "width_in", result["page"]["width_in"])
        result["page"]["height_in"] = self._positive_float(page, "height_in", result["page"]["height_in"])
        result["page"]["anti_alias"] = self._bool(page, "anti_alias", result["page"]["anti_alias"])

        layer = self._section(preset, "layer")
        for key in ("left_in", "top_in"):
            result["layer"][key] = self._nonnegative_float(layer, key, result["layer"][key])
        for key in ("width_in", "height_in", "line_width_pt", "scale_factor"):
            result["layer"][key] = self._positive_float(layer, key, result["layer"][key])
        result["layer"]["scale_fixed"] = self._bool(layer, "scale_fixed", result["layer"]["scale_fixed"])
        frame = self._section(layer, "frame")
        for key in ("left", "bottom", "top", "right"):
            result["layer"]["frame"][key] = self._bool(frame, key, result["layer"]["frame"][key])

        plot = self._section(preset, "plot")
        result["plot"]["line_width_pt"] = self._positive_float(plot, "line_width_pt", result["plot"]["line_width_pt"])
        result["plot"]["symbol_size_pt"] = self._positive_float(plot, "symbol_size_pt", result["plot"]["symbol_size_pt"])

        text = self._section(preset, "text")
        result["text"]["title_font_size_pt"] = self._positive_float(
            text, "title_font_size_pt", result["text"]["title_font_size_pt"]
        )
        result["text"]["tick_font_size_pt"] = self._positive_float(
            text, "tick_font_size_pt", result["text"]["tick_font_size_pt"]
        )
        result["text"]["legend_font_size_pt"] = self._positive_float(
            text, "legend_font_size_pt", result["text"]["legend_font_size_pt"]
        )

        axis = self._section(preset, "axis")
        result["axis"]["x_scale"] = self._choice(axis, "x_scale", {"keep", "linear", "log10"}, result["axis"]["x_scale"])
        result["axis"]["y_scale"] = self._choice(axis, "y_scale", {"keep", "linear", "log10"}, result["axis"]["y_scale"])
        result["axis"]["show_grid"] = self._bool(axis, "show_grid", result["axis"]["show_grid"])

        legend = self._section(preset, "legend")
        result["legend"]["visibility"] = self._choice(
            legend, "visibility", {"keep", "show", "hide"}, result["legend"]["visibility"]
        )
        result["legend"]["frame"] = self._bool(legend, "frame", result["legend"]["frame"])
        result["legend"]["position"] = self._choice(
            legend,
            "position",
            {"keep", "best", "upper_left", "upper_right", "lower_left", "lower_right"},
            result["legend"]["position"],
        )

        export = self._section(preset, "export")
        result["export"]["width_px"] = self._positive_int(export, "width_px", result["export"]["width_px"])
        result["export"]["formats"] = self._formats(export.get("formats", result["export"]["formats"]))
        return result

    def _quarantine_bad_file(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.stem}.bad-{timestamp}{self.path.suffix}")
        suffix = 1
        while target.exists():
            target = self.path.with_name(f"{self.path.stem}.bad-{timestamp}-{suffix}{self.path.suffix}")
            suffix += 1
        self.path.replace(target)
        return target

    @staticmethod
    def _extract_presets(data: object) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("JSON 顶层应为对象")
        presets = data.get("presets", data)
        if not isinstance(presets, dict):
            raise ValueError("presets 应为对象")
        return presets

    @staticmethod
    def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
        value = data.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(f"{key} 应为对象")
        return value

    @staticmethod
    def _bool(data: dict[str, Any], key: str, default: bool) -> bool:
        value = data.get(key, default)
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} 应为布尔值")

    @staticmethod
    def _positive_float(data: dict[str, Any], key: str, default: float) -> float:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} 应为数字")
        value = float(value)
        if value <= 0:
            raise ValueError(f"{key} 应大于 0")
        return value

    @staticmethod
    def _nonnegative_float(data: dict[str, Any], key: str, default: float) -> float:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} 应为数字")
        value = float(value)
        if value < 0:
            raise ValueError(f"{key} 应大于等于 0")
        return value

    @staticmethod
    def _positive_int(data: dict[str, Any], key: str, default: int) -> int:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} 应为整数")
        if value <= 0:
            raise ValueError(f"{key} 应大于 0")
        return value

    @staticmethod
    def _choice(data: dict[str, Any], key: str, choices: set[str], default: str) -> str:
        value = data.get(key, default)
        if value in choices:
            return str(value)
        raise ValueError(f"{key} 取值无效：{value}")

    @staticmethod
    def _formats(value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("formats 应为数组")
        allowed = {"png", "pdf", "svg", "tiff"}
        formats = [str(item).lower() for item in value if str(item).lower() in allowed]
        if not formats:
            raise ValueError("formats 至少需要一个合法格式")
        return formats
