from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def textFromValue(self, value: float) -> str:
        text = f"{value:.{self.decimals()}f}".rstrip("0").rstrip(".")
        return text if text and text != "-0" else "0"


def make_button(
    text: str,
    slot: Callable[[], None],
    role: str = "",
    *,
    keep_text_focus: bool = False,
    width: int | None = None,
) -> QPushButton:
    button = QPushButton(text)
    button.setMinimumHeight(32)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if width is not None:
        button.setMinimumWidth(width)
        button.setMaximumWidth(width)
    if role:
        button.setProperty("role", role)
    if keep_text_focus:
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.clicked.connect(slot)
    return button


def make_panel(
    name: str,
    margins: tuple[int, int, int, int] = (14, 14, 14, 14),
    spacing: int = 10,
) -> QWidget:
    panel = QWidget()
    panel.setObjectName(name)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return panel


def make_section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def make_titled_group(title: str) -> QGroupBox:
    group = QGroupBox(title)
    group.setObjectName("TitledGroup")
    return group
