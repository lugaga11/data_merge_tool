from __future__ import annotations

from ..constants import resource_path


def load_stylesheet(name: str) -> str:
    path = resource_path(name)
    return path.read_text(encoding="utf-8").replace("__RESOURCE_DIR__", path.parent.as_posix())


__all__ = ["load_stylesheet"]
