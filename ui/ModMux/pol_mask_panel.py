"""Per-polarization control panel for ModMux."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

ATT_DB_MIN = 0.0
ATT_DB_MAX = 60.0
ATT_DB_STEP = 0.1


class PolMaskPanel(QGroupBox):
    """Mask H or Mask V: master switch, enables, attenuation, and center."""

    def __init__(self, title: str, lcos_width: int, lcos_height: int, parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self.setChecked(True)

        self.pattern_cb = QCheckBox("Pattern")
        self.pattern_cb.setChecked(True)
        self.zernike_cb = QCheckBox("Zernike")
        self.zernike_cb.setChecked(True)

        self.att_box = QGroupBox("Attenuation")
        self.att_box.setCheckable(True)
        self.att_box.setChecked(False)
        self.att_spin = QDoubleSpinBox()
        self.att_spin.setRange(ATT_DB_MIN, ATT_DB_MAX)
        self.att_spin.setSingleStep(ATT_DB_STEP)
        self.att_spin.setDecimals(1)
        self.att_spin.setSuffix(" dB")
        self.att_spin.setMinimumWidth(100)

        att_row = QHBoxLayout(self.att_box)
        att_row.addStretch(1)
        att_row.addWidget(self.att_spin)

        self.center_box = QGroupBox("Center")
        self.center_x = QSpinBox()
        self.center_y = QSpinBox()
        for spin in (self.center_x, self.center_y):
            spin.setMinimum(0)
            spin.setMinimumWidth(80)
            spin.setSuffix(" px")
        self.center_x.setMaximum(lcos_width - 1)
        self.center_y.setMaximum(lcos_height - 1)

        center_form = QFormLayout(self.center_box)
        center_form.addRow("x", self.center_x)
        center_form.addRow("y", self.center_y)

        layout = QVBoxLayout(self)
        layout.addWidget(self.pattern_cb)
        layout.addWidget(self.zernike_cb)
        layout.addWidget(self.att_box)
        layout.addWidget(self.center_box)

        self.toggled.connect(self._on_master_toggled)
        self.att_box.toggled.connect(self._on_att_toggled)
        self._on_master_toggled(self.isChecked())
        self._on_att_toggled(self.att_box.isChecked())

    def user_controls(self) -> list[QWidget]:
        return [
            self,
            self.pattern_cb,
            self.zernike_cb,
            self.att_box,
            self.att_spin,
            self.center_box,
            self.center_x,
            self.center_y,
        ]

    def _on_master_toggled(self, enabled: bool) -> None:
        self.pattern_cb.setEnabled(enabled)
        self.zernike_cb.setEnabled(enabled)
        self.att_box.setEnabled(enabled)
        self.center_box.setEnabled(enabled)
        if enabled:
            self._on_att_toggled(self.att_box.isChecked())
            self.center_x.setEnabled(True)
            self.center_y.setEnabled(True)
        else:
            self.att_spin.setEnabled(False)
            self.center_x.setEnabled(False)
            self.center_y.setEnabled(False)

    def _on_att_toggled(self, enabled: bool) -> None:
        self.att_spin.setEnabled(enabled and self.isChecked())

    def read_state(self) -> dict:
        return {
            "master": self.isChecked(),
            "pattern_enabled": self.pattern_cb.isChecked(),
            "zernikes_enabled": self.zernike_cb.isChecked(),
            "att_enabled": self.att_box.isChecked(),
            "att_weight": self.att_spin.value(),
            "center": [self.center_x.value(), self.center_y.value()],
        }

    def apply_state(
        self,
        *,
        master: bool,
        pattern_enabled: bool,
        zernikes_enabled: bool,
        att_enabled: bool,
        att_weight: float,
        center: tuple[int, int],
    ) -> None:
        for widget in self.user_controls():
            widget.blockSignals(True)

        self.setChecked(master)
        self.pattern_cb.setChecked(pattern_enabled)
        self.zernike_cb.setChecked(zernikes_enabled)
        self.att_box.setChecked(att_enabled)
        self.att_spin.setValue(att_weight)
        self.center_x.setValue(center[0])
        self.center_y.setValue(center[1])

        for widget in self.user_controls():
            widget.blockSignals(False)

        self._on_master_toggled(master)

    def set_panel_enabled(self, enabled: bool) -> None:
        for widget in self.user_controls():
            widget.setEnabled(enabled)
        if enabled:
            self._on_master_toggled(self.isChecked())
