from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, TypeAlias

from .constants import DRAG_INTERNAL, MOVE_ACTION, SELECTION_EXTENDED
from .data_io import scan_data_files
from .qt import (
    QComboBox,
    QDoubleSpinBox,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QEvent,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMouseEvent,
    QObject,
    QPainter,
    QPoint,
    QPolygon,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QThread,
    Qt,
    QVBoxLayout,
    QWheelEvent,
    QWidget,
    Signal,
)


class NoWheelComboBox(QComboBox):
    """Prevent accidental value changes while scrolling the settings pane."""

    BUTTON_ZONE_WIDTH = 26

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        button_left = self.width() - self.BUTTON_ZONE_WIDTH
        if button_left < 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.black)

        center_x = button_left + self.BUTTON_ZONE_WIDTH // 2
        center_y = self.height() // 2
        painter.drawPolygon(QPolygon([
            QPoint(center_x - 4, center_y - 2),
            QPoint(center_x + 4, center_y - 2),
            QPoint(center_x, center_y + 3),
        ]))


class NoWheelSpinBox(QSpinBox):
    """Prevent accidental value changes while scrolling the settings pane."""

    BUTTON_ZONE_WIDTH = 26

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        editor = self.findChild(QLineEdit)
        if editor is not None:
            editor.setMouseTracking(True)
            editor.installEventFilter(self)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def eventFilter(self, watched, event) -> bool:
        if isinstance(event, QMouseEvent):
            pos = self.mapFromGlobal(event.globalPosition().toPoint())
            if event.type() == QEvent.Type.MouseMove:
                self._sync_button_cursor(pos)
            elif event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                step = self._button_step_at(pos)
                if step is not None:
                    self.setFocus()
                    self.stepBy(step)
                    event.accept()
                    return True
        elif event.type() == QEvent.Type.Leave:
            self.unsetCursor()
            if hasattr(watched, "unsetCursor"):
                watched.unsetCursor()
        return super().eventFilter(watched, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._sync_button_cursor(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            step = self._button_step_at(event.position().toPoint())
            if step is not None:
                self.setFocus()
                self.stepBy(step)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        button_left = self.width() - self.BUTTON_ZONE_WIDTH
        if button_left < 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.black)

        center_x = button_left + self.BUTTON_ZONE_WIDTH // 2
        upper_y = max(7, self.height() // 4)
        lower_y = min(self.height() - 7, (self.height() * 3) // 4)
        painter.drawPolygon(QPolygon([
            QPoint(center_x - 4, upper_y + 2),
            QPoint(center_x + 4, upper_y + 2),
            QPoint(center_x, upper_y - 3),
        ]))
        painter.drawPolygon(QPolygon([
            QPoint(center_x - 4, lower_y - 2),
            QPoint(center_x + 4, lower_y - 2),
            QPoint(center_x, lower_y + 3),
        ]))

    def _button_step_at(self, pos) -> Optional[int]:
        if pos.x() < self.width() - self.BUTTON_ZONE_WIDTH:
            return None
        return 1 if pos.y() < self.height() / 2 else -1

    def _sync_button_cursor(self, pos) -> None:
        if self._button_step_at(pos) is None:
            self.unsetCursor()
            editor = self.findChild(QLineEdit)
            if editor is not None:
                editor.unsetCursor()
            return
        self.setCursor(Qt.CursorShape.ArrowCursor)
        editor = self.findChild(QLineEdit)
        if editor is not None:
            editor.setCursor(Qt.CursorShape.ArrowCursor)


SPIN_BUTTON_ZONE_WIDTH = 26
SpinWidget: TypeAlias = QSpinBox | QDoubleSpinBox


def _configure_no_wheel_spin(spin: SpinWidget) -> None:
    spin.setMouseTracking(True)
    editor = spin.findChild(QLineEdit)
    if editor is not None:
        editor.setMouseTracking(True)
        editor.installEventFilter(spin)


def _spin_button_step_at(spin: SpinWidget, pos) -> Optional[int]:
    if pos.x() < spin.width() - SPIN_BUTTON_ZONE_WIDTH:
        return None
    return 1 if pos.y() < spin.height() / 2 else -1


def _sync_spin_button_cursor(spin: SpinWidget, pos) -> None:
    if _spin_button_step_at(spin, pos) is None:
        spin.unsetCursor()
        editor = spin.findChild(QLineEdit)
        if editor is not None:
            editor.unsetCursor()
        return
    spin.setCursor(Qt.CursorShape.ArrowCursor)
    editor = spin.findChild(QLineEdit)
    if editor is not None:
        editor.setCursor(Qt.CursorShape.ArrowCursor)


def _paint_spin_arrows(spin: SpinWidget) -> None:
    button_left = spin.width() - SPIN_BUTTON_ZONE_WIDTH
    if button_left < 0:
        return

    painter = QPainter(spin)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.GlobalColor.black)

    center_x = button_left + SPIN_BUTTON_ZONE_WIDTH // 2
    upper_y = max(7, spin.height() // 4)
    lower_y = min(spin.height() - 7, (spin.height() * 3) // 4)
    painter.drawPolygon(QPolygon([
        QPoint(center_x - 4, upper_y + 2),
        QPoint(center_x + 4, upper_y + 2),
        QPoint(center_x, upper_y - 3),
    ]))
    painter.drawPolygon(QPolygon([
        QPoint(center_x - 4, lower_y - 2),
        QPoint(center_x + 4, lower_y - 2),
        QPoint(center_x, lower_y + 3),
    ]))


def _handle_spin_event_filter(spin: SpinWidget, watched: QObject, event: QEvent) -> bool:
    if isinstance(event, QMouseEvent):
        pos = spin.mapFromGlobal(event.globalPosition().toPoint())
        if event.type() == QEvent.Type.MouseMove:
            _sync_spin_button_cursor(spin, pos)
        elif event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            step = _spin_button_step_at(spin, pos)
            if step is not None:
                spin.setFocus()
                spin.stepBy(step)
                event.accept()
                return True
    elif event.type() == QEvent.Type.Leave:
        spin.unsetCursor()
        if isinstance(watched, QWidget):
            watched.unsetCursor()
    return False


def _handle_spin_mouse_press(spin: SpinWidget, event: QMouseEvent) -> bool:
    if event.button() == Qt.MouseButton.LeftButton:
        step = _spin_button_step_at(spin, event.position().toPoint())
        if step is not None:
            spin.setFocus()
            spin.stepBy(step)
            event.accept()
            return True
    return False


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Prevent accidental value changes while scrolling the settings pane."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        _configure_no_wheel_spin(self)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if _handle_spin_event_filter(self, watched, event):
            return True
        return super().eventFilter(watched, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        _sync_spin_button_cursor(self, event.position().toPoint())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if _handle_spin_mouse_press(self, event):
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        _paint_spin_arrows(self)

    def textFromValue(self, value: float) -> str:
        text = f"{value:.{self.decimals()}f}".rstrip("0").rstrip(".")
        return text if text and text != "-0" else "0"


def choose_directory(parent: QWidget, title: str, initial_dir: str = "") -> str | None:
    directory = QFileDialog.getExistingDirectory(parent, title, initial_dir)
    return directory or None


def choose_open_files(parent: QWidget, title: str, file_filter: str, initial_dir: str = "") -> list[str]:
    paths, _ = QFileDialog.getOpenFileNames(parent, title, initial_dir, file_filter)
    return paths


def choose_save_file(parent: QWidget, title: str, initial_path: str, file_filter: str) -> tuple[str | None, str]:
    path, selected_filter = QFileDialog.getSaveFileName(parent, title, initial_path, file_filter)
    return path or None, selected_filter


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


def make_panel(name: str, margins: tuple[int, int, int, int] = (14, 14, 14, 14), spacing: int = 10) -> QWidget:
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


class DropFileList(QListWidget):
    files_dropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(SELECTION_EXTENDED)
        self.setDragDropMode(DRAG_INTERNAL)
        self.setDefaultDropAction(MOVE_ACTION)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasUrls():
            paths: List[str] = []
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if not local_path:
                    continue
                path = Path(local_path)
                if path.is_dir():
                    paths.extend(scan_data_files(path))
                else:
                    paths.append(str(path))
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class DataTask(QThread):
    completed = Signal(object, object)

    def __init__(
        self,
        work: Callable[[], object],
        on_success: Callable[[object], None],
        error_title: str,
        reset_output_on_error: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._work = work
        self.on_success = on_success
        self.error_title = error_title
        self.reset_output_on_error = reset_output_on_error

    def run(self) -> None:
        try:
            self.completed.emit(self._work(), None)
        except Exception as exc:
            self.completed.emit(None, exc)
