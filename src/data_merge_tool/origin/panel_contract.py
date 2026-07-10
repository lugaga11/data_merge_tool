from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QWidget,
)

from .client import OriginWorkerClient
from .presets import PresetStore
from .protocol import StyleSnapshot


class OriginPanelContract(QWidget):
    """Typed state shared by the Origin panel mixins."""

    origin_client: OriginWorkerClient
    preset_store: PresetStore
    user_presets: dict[str, dict[str, Any]]
    path_checks: dict[str, QCheckBox]
    last_apply_snapshot: StyleSnapshot | None
    last_text_editor: QLineEdit | None
    last_text_selection: dict[QLineEdit, tuple[int, int, str]]

    actionContextLabel: QLabel
    formatSummaryLabel: QLabel
    allLayersRadio: QRadioButton
    singleLayerRadio: QRadioButton
    layerCombo: QComboBox
    customLayersEdit: QLineEdit
    presetCombo: QComboBox

    pageWidthSpin: QDoubleSpinBox
    pageHeightSpin: QDoubleSpinBox
    pageAntiAliasCheck: QCheckBox
    layerLeftSpin: QDoubleSpinBox
    layerTopSpin: QDoubleSpinBox
    layerWidthSpin: QDoubleSpinBox
    layerHeightSpin: QDoubleSpinBox
    layerLineWidthSpin: QDoubleSpinBox
    scaleFixedCheck: QCheckBox
    scaleFactorSpin: QDoubleSpinBox
    frameLeftCheck: QCheckBox
    frameBottomCheck: QCheckBox
    frameTopCheck: QCheckBox
    frameRightCheck: QCheckBox
    lineWidthSpin: QDoubleSpinBox
    symbolSizeSpin: QDoubleSpinBox
    xTitleEdit: QLineEdit
    yTitleEdit: QLineEdit
    legendTextEdit: QLineEdit
    axisTitleSizeSpin: QDoubleSpinBox
    axisTickSizeSpin: QDoubleSpinBox
    legendFontSizeSpin: QDoubleSpinBox
    xScaleCombo: QComboBox
    yScaleCombo: QComboBox
    gridCheck: QCheckBox
    legendVisibilityCombo: QComboBox
    legendFrameCheck: QCheckBox
    legendPositionCombo: QComboBox

    exportDirEdit: QLineEdit
    exportPngCheck: QCheckBox
    exportPdfCheck: QCheckBox
    exportSvgCheck: QCheckBox
    exportTiffCheck: QCheckBox
    exportWidthSpin: QSpinBox

    if TYPE_CHECKING:
        @staticmethod
        def _combo_value(combo: QComboBox) -> str: ...

        @staticmethod
        def _set_combo_value(combo: QComboBox, value: object) -> None: ...

        def set_status(self, message: str, timeout_ms: int = 6000) -> None: ...

        def show_error(self, title: str, exc: Exception) -> None: ...

        def start_origin_task(
            self,
            message: str,
            work: Callable[[], object],
            on_success: Callable[[object], None],
            error_title: str,
        ) -> bool: ...

        def selected_enabled_paths(self) -> list[str]: ...

        def apply_enabled_paths(self, enabled_paths: object) -> None: ...

        def selected_export_formats(self) -> list[str]: ...
