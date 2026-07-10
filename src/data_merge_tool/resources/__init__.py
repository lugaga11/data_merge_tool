from __future__ import annotations

from ..constants import resource_path


def load_stylesheet(name: str) -> str:
    return resource_path(name).read_text(encoding="utf-8")


__all__ = ["load_stylesheet"]
