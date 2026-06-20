import math

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.simpleholography.pistoning.phase_preview import PhasePreview
from utilities.simpleHolography import (
    REGION_ALL,
    REGION_BL,
    REGION_BOTTOM,
    REGION_BR,
    REGION_LEFT,
    REGION_RIGHT,
    REGION_TL,
    REGION_TOP,
    REGION_TR,
    pistoning_phase_mask,
    region_keys,
)

PI = math.pi
PISTON_INTERVAL_MS = 250
PISTON_STEP = 0.2

_REGION_LABELS = {
    REGION_ALL: "All",
    REGION_LEFT: "Left",
    REGION_RIGHT: "Right",
    REGION_TOP: "Top",
    REGION_BOTTOM: "Bottom",
    REGION_TL: "Top-Left",
    REGION_TR: "Top-Right",
    REGION_BL: "Bottom-Left",
    REGION_BR: "Bottom-Right",
}


def _migrate_phases(old_keys: list[str], new_keys: list[str], phases: dict[str, float]) -> dict[str, float]:
    """Carry phase values forward when the active region layout changes."""
    if old_keys == new_keys:
        return {k: phases.get(k, 0.0) for k in new_keys}

    migrated = {k: 0.0 for k in new_keys}

    if REGION_ALL in new_keys:
        for key in (REGION_ALL, REGION_TL, REGION_LEFT, REGION_TOP):
            if key in phases:
                migrated[REGION_ALL] = phases[key]
                break
        return migrated

    if REGION_ALL in old_keys:
        value = phases.get(REGION_ALL, 0.0)
        for key in new_keys:
            migrated[key] = value
        return migrated

    if new_keys == [REGION_LEFT, REGION_RIGHT]:
        migrated[REGION_LEFT] = phases.get(REGION_TL, phases.get(REGION_LEFT, phases.get(REGION_BL, 0.0)))
        migrated[REGION_RIGHT] = phases.get(REGION_TR, phases.get(REGION_RIGHT, phases.get(REGION_BR, 0.0)))
        return migrated

    if new_keys == [REGION_TOP, REGION_BOTTOM]:
        migrated[REGION_TOP] = phases.get(REGION_TL, phases.get(REGION_TOP, phases.get(REGION_TR, 0.0)))
        migrated[REGION_BOTTOM] = phases.get(REGION_BL, phases.get(REGION_BOTTOM, phases.get(REGION_BR, 0.0)))
        return migrated

    if new_keys == [REGION_TL, REGION_TR, REGION_BL, REGION_BR]:
        if old_keys == [REGION_LEFT, REGION_RIGHT]:
            migrated[REGION_TL] = phases.get(REGION_LEFT, 0.0)
            migrated[REGION_TR] = phases.get(REGION_RIGHT, 0.0)
            migrated[REGION_BL] = phases.get(REGION_LEFT, 0.0)
            migrated[REGION_BR] = phases.get(REGION_RIGHT, 0.0)
        elif old_keys == [REGION_TOP, REGION_BOTTOM]:
            migrated[REGION_TL] = phases.get(REGION_TOP, 0.0)
            migrated[REGION_TR] = phases.get(REGION_TOP, 0.0)
            migrated[REGION_BL] = phases.get(REGION_BOTTOM, 0.0)
            migrated[REGION_BR] = phases.get(REGION_BOTTOM, 0.0)
        else:
            for key in new_keys:
                migrated[key] = phases.get(key, 0.0)
        return migrated

    for key in new_keys:
        migrated[key] = phases.get(key, 0.0)
    return migrated


class _RegionControl:
    __slots__ = ("key", "spin", "auto", "direction", "row_widget")

    def __init__(self, key: str):
        self.key = key
        self.direction = 1
        self.row_widget = QWidget()
        row = QHBoxLayout(self.row_widget)
        row.setContentsMargins(0, 0, 0, 0)

        row.addWidget(QLabel(_REGION_LABELS[key]))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-PI, PI)
        self.spin.setSingleStep(0.01)
        self.spin.setDecimals(2)
        self.spin.setMinimumWidth(90)
        row.addWidget(self.spin)

        self.auto = QCheckBox("Auto")
        row.addWidget(self.auto)
        row.addStretch(1)


class PistoningWidget(QWidget):
    """Interactive pistoning control with draggable LCOS quadrant cuts."""

    def __init__(self, slm, parent=None):
        super().__init__(parent)
        self.slm = slm
        self.height, self.width = slm.LCOSsize
        self.cut_x = self.width // 2
        self.cut_y = self.height // 2
        self.enable_v_cut = True
        self.enable_h_cut = True
        self._phases: dict[str, float] = {k: 0.0 for k in region_keys(True, True)}
        self._region_controls: dict[str, _RegionControl] = {}

        self.setWindowTitle("Pistoning")
        self.resize(1100, 720)

        self._piston_timer = QTimer(self)
        self._piston_timer.setInterval(PISTON_INTERVAL_MS)
        self._piston_timer.timeout.connect(self._piston_tick)

        self._build_ui()
        self._rebuild_region_controls()
        self._update_display()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        cut_row = QHBoxLayout()
        self.v_cut_cb = QCheckBox("Vertical cut")
        self.v_cut_cb.setChecked(True)
        self.h_cut_cb = QCheckBox("Horizontal cut")
        self.h_cut_cb.setChecked(True)
        cut_row.addWidget(self.v_cut_cb)
        cut_row.addWidget(self.h_cut_cb)
        cut_row.addStretch(1)
        left.addLayout(cut_row)

        self._controls_box = QGroupBox("Phase")
        self._controls_layout = QVBoxLayout(self._controls_box)
        left.addWidget(self._controls_box)
        left.addStretch(1)

        self._preview = PhasePreview(self.width, self.height, self.slm.ch)
        self._preview.cut_x = self.cut_x
        self._preview.cut_y = self.cut_y
        self._preview.cutsChanged.connect(self._on_cuts_moved)

        preview_box = QGroupBox("LCOS Panel Viewer")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(4, 8, 4, 4)
        preview_layout.addWidget(self._preview)

        root.addLayout(left, stretch=0)
        root.addWidget(preview_box, stretch=1)

        self.v_cut_cb.toggled.connect(self._on_cut_toggled)
        self.h_cut_cb.toggled.connect(self._on_cut_toggled)

    def _rebuild_region_controls(self) -> None:
        old_keys = list(self._region_controls.keys())
        old_phases = self._current_phases()
        new_keys = region_keys(self.enable_v_cut, self.enable_h_cut)
        self._phases = _migrate_phases(old_keys, new_keys, old_phases)

        while self._controls_layout.count():
            item = self._controls_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._region_controls.clear()
        for key in new_keys:
            control = _RegionControl(key)
            control.spin.setValue(self._phases[key])
            control.spin.valueChanged.connect(self._update_display)
            control.auto.toggled.connect(self._on_auto_toggled)
            self._region_controls[key] = control
            self._controls_layout.addWidget(control.row_widget)

        self._sync_cut_lines()

    def _current_phases(self) -> dict[str, float]:
        if self._region_controls:
            return {key: ctrl.spin.value() for key, ctrl in self._region_controls.items()}
        return dict(self._phases)

    def _sync_cut_lines(self) -> None:
        self._preview.update_cuts(self.cut_x, self.cut_y, self.enable_v_cut, self.enable_h_cut)

    def _on_cut_toggled(self, _checked: bool) -> None:
        self.enable_v_cut = self.v_cut_cb.isChecked()
        self.enable_h_cut = self.h_cut_cb.isChecked()
        self._rebuild_region_controls()
        self._update_display()

    def _on_cuts_moved(self) -> None:
        self.cut_x = self._preview.cut_x
        self.cut_y = self._preview.cut_y
        self._update_display()

    def _on_auto_toggled(self, _checked: bool) -> None:
        if any(ctrl.auto.isChecked() for ctrl in self._region_controls.values()):
            self._piston_timer.start()
        else:
            self._piston_timer.stop()
        self._update_display()

    def _piston_tick(self) -> None:
        for control in self._region_controls.values():
            if not control.auto.isChecked():
                continue
            value = control.spin.value() + control.direction * PISTON_STEP
            if value >= PI:
                value = PI
                control.direction = -1
            elif value <= -PI:
                value = -PI
                control.direction = 1
            control.spin.blockSignals(True)
            control.spin.setValue(value)
            control.spin.blockSignals(False)
        self._update_display()

    def _update_display(self) -> None:
        phases = self._current_phases()
        phase = pistoning_phase_mask(
            (self.height, self.width),
            self.cut_x,
            self.cut_y,
            self.enable_v_cut,
            self.enable_h_cut,
            phases,
        )
        self._preview.set_phase(phase)
        level = self.slm.phaseTolevel(phase)
        self.slm.LCOS_Display(level, ch=self.slm.ch)

    def closeEvent(self, event) -> None:
        self._piston_timer.stop()
        super().closeEvent(event)
