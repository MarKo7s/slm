"""Meadowlark Blink SDK control panel."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from slm.meadowlark import MeadowlarkSDK, MeadowlarkSDKError
from .lut_plot import LutPlot
from .settings import LUT_DIR, load_settings, save_settings

_CHANNEL_NAMES = ("Red", "Green", "Blue")
_INVALID_READ = -1.0
_DEFAULT_PRE_RAMP = 7
_DEFAULT_POST_RAMP = 24


class MeadowlarkWidget(QWidget):
    """Connect to Meadowlark SDK: monitoring, channel, LUT, coverglass, ramps."""

    channel_changed = Signal(int)

    def __init__(self, slm=None, parent=None):
        super().__init__(parent)
        self.slm = slm
        self._sdk: MeadowlarkSDK | None = None
        self._connected = False
        self._settings = load_settings()
        self._migrate_settings()

        self.setWindowTitle("Meadowlark")

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._toggle_connection)

        self._status_labels = {
            "resolution": QLabel("—"),
            "shape": QLabel("—"),
            "bit_depth": QLabel("—"),
            "slm_found": QLabel("—"),
            "com_found": QLabel("—"),
            "temperature": QLabel("—"),
            "coverglass_read": QLabel("—"),
            "last_loaded_lut": QLabel("—"),
            "in_flash_lut": QLabel("—"),
            "pre_ramp_slope": QLabel("—"),
            "post_ramp_slope": QLabel("—"),
        }

        status_box = QGroupBox("Status")
        status_form = QFormLayout(status_box)
        status_form.addRow("Resolution", self._status_labels["resolution"])
        status_form.addRow("Shape", self._status_labels["shape"])
        status_form.addRow("Bit depth", self._status_labels["bit_depth"])
        status_form.addRow("SLM found (HDMI)", self._status_labels["slm_found"])
        status_form.addRow("USB found (COM)", self._status_labels["com_found"])
        status_form.addRow("Temperature", self._status_labels["temperature"])
        status_form.addRow("Coverglass (read)", self._status_labels["coverglass_read"])
        status_form.addRow("Last loaded LUT", self._status_labels["last_loaded_lut"])
        status_form.addRow("In-flash LUT", self._status_labels["in_flash_lut"])
        status_form.addRow("Pre ramp slope", self._status_labels["pre_ramp_slope"])
        status_form.addRow("Post ramp slope", self._status_labels["post_ramp_slope"])

        self._refresh_status_btn = QPushButton("Refresh")
        self._refresh_status_btn.clicked.connect(self._refresh_monitoring)
        status_form.addRow(self._refresh_status_btn)

        self._channel_combo = QComboBox()
        self._channel_combo.addItems(_CHANNEL_NAMES)
        self._channel_combo.currentIndexChanged.connect(self._on_channel_combo_changed)

        channel_box = QGroupBox("Channel")
        channel_layout = QVBoxLayout(channel_box)
        channel_layout.addWidget(self._channel_combo)

        self._load_lut_btn = QPushButton("Load LUT…")
        self._load_lut_btn.clicked.connect(self._load_lut)
        self._store_lut_btn = QPushButton("Store Current LUT into FLASH")
        self._store_lut_btn.clicked.connect(self._store_lut)
        self._lut_plot = LutPlot()

        self._coverglass_enable = QCheckBox("Enable setpoint")
        self._coverglass_enable.toggled.connect(self._on_coverglass_enable_toggled)
        self._coverglass_combo = QComboBox()
        self._coverglass_combo.setEditable(True)
        self._coverglass_combo.setEnabled(False)
        self._coverglass_combo.lineEdit().returnPressed.connect(self._apply_coverglass_setpoint)

        coverglass_box = QGroupBox("Coverglass")
        coverglass_form = QFormLayout(coverglass_box)
        coverglass_form.addRow(self._coverglass_enable)
        coverglass_form.addRow("Setpoint (V)", self._coverglass_combo)

        self._pre_ramp_spin = QSpinBox()
        self._pre_ramp_spin.setRange(0, 255)
        self._post_ramp_spin = QSpinBox()
        self._post_ramp_spin.setRange(0, 255)
        self._apply_ramp_btn = QPushButton("Apply")
        self._apply_ramp_btn.clicked.connect(self._apply_ramp_slopes)

        ramp_box = QGroupBox("Delay voltage ramp")
        ramp_form = QFormLayout(ramp_box)
        ramp_form.addRow("Pre ramp slope", self._pre_ramp_spin)
        ramp_form.addRow("Post ramp slope", self._post_ramp_spin)
        ramp_form.addRow(self._apply_ramp_btn)

        self._controls = [
            self._refresh_status_btn,
            self._channel_combo,
            self._load_lut_btn,
            self._store_lut_btn,
            self._coverglass_enable,
            self._coverglass_combo,
            self._pre_ramp_spin,
            self._post_ramp_spin,
            self._apply_ramp_btn,
        ]

        left = QVBoxLayout()
        left.addWidget(self._connect_btn)
        left.addWidget(status_box)
        left.addWidget(channel_box)
        left.addWidget(self._load_lut_btn)
        left.addWidget(self._store_lut_btn)
        left.addWidget(self._lut_plot)
        left.addWidget(coverglass_box)
        left.addWidget(ramp_box)
        left.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(left)

        self._restore_settings_ui()
        self._refresh_tracked_status()
        self._set_controls_enabled(False)

    def _migrate_settings(self) -> None:
        """Rename legacy last_lut -> last_loaded_lut once."""
        if "last_loaded_lut" not in self._settings and "last_lut" in self._settings:
            self._settings["last_loaded_lut"] = self._settings.pop("last_lut")
            save_settings(self._settings)

    def _restore_settings_ui(self) -> None:
        enabled = bool(self._settings.get("coverglass_enabled", False))
        self._coverglass_enable.setChecked(enabled)

        setpoint = self._settings.get("coverglass_setpoint_V")
        history = self._settings.get("coverglass_history_V", [])
        for value in history:
            text = f"{float(value):.2f}"
            if self._coverglass_combo.findText(text) < 0:
                self._coverglass_combo.addItem(text)
        if setpoint is not None:
            text = f"{float(setpoint):.2f}"
            if self._coverglass_combo.findText(text) < 0:
                self._coverglass_combo.addItem(text)
            self._coverglass_combo.setCurrentText(text)

        pre = self._settings.get("pre_ramp_slope", _DEFAULT_PRE_RAMP)
        post = self._settings.get("post_ramp_slope", _DEFAULT_POST_RAMP)
        self._pre_ramp_spin.setValue(int(pre))
        self._post_ramp_spin.setValue(int(post))

    def _set_path_status(self, key: str, path) -> None:
        label = self._status_labels[key]
        if not path:
            label.setText("—")
            label.setToolTip("")
            return
        p = Path(str(path))
        label.setText(p.name)
        label.setToolTip(str(p))

    def _refresh_tracked_status(self) -> None:
        """Refresh LUT / ramp status rows from persisted controller-apply state."""
        self._set_path_status("last_loaded_lut", self._settings.get("last_loaded_lut"))
        self._set_path_status("in_flash_lut", self._settings.get("in_flash_lut"))

        pre = self._settings.get("pre_ramp_slope")
        post = self._settings.get("post_ramp_slope")
        self._status_labels["pre_ramp_slope"].setText("—" if pre is None else str(int(pre)))
        self._status_labels["post_ramp_slope"].setText("—" if post is None else str(int(post)))

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in self._controls:
            widget.setEnabled(enabled)
        self._on_coverglass_enable_toggled(self._coverglass_enable.isChecked())

    def _toggle_connection(self) -> None:
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        try:
            self._sdk = MeadowlarkSDK(init_sdk=False)
            self._sdk.open()
        except (MeadowlarkSDKError, OSError) as exc:
            self._status_labels["resolution"].setText(str(exc))
            return

        if self.slm is not None:
            self.slm.hide()

        self._connected = True
        self._connect_btn.setText("Disconnect")
        self._set_controls_enabled(True)
        self._refresh_static_status()
        self._refresh_tracked_status()
        self._push_sdk_channel(self._channel_combo.currentIndex(), emit=False)

    def _disconnect(self) -> None:
        if self._sdk is not None:
            self._sdk.close()
            self._sdk = None
        self._connected = False
        self._connect_btn.setText("Connect")
        self._set_controls_enabled(False)

        if self.slm is not None:
            self.slm.show()

    def _refresh_static_status(self) -> None:
        """Fast SDK queries (geometry and connection flags)."""
        if self._sdk is None:
            return
        w, h = self._sdk.resolution
        shape = self._sdk.shape
        self._status_labels["resolution"].setText(f"{w} × {h}")
        self._status_labels["shape"].setText(f"({shape[0]}, {shape[1]})")
        self._status_labels["bit_depth"].setText(str(self._sdk.bit_depth))
        self._status_labels["slm_found"].setText(str(self._sdk.slm_found))
        self._status_labels["com_found"].setText(str(self._sdk.com_found))

    def _refresh_monitoring(self) -> None:
        """Slow USB reads — temperature and coverglass voltage."""
        if self._sdk is None:
            return
        self._refresh_status_btn.setEnabled(False)
        try:
            temp = self._sdk.get_temperature()
            vcom = self._sdk.get_coverglass_voltage()
        except MeadowlarkSDKError as exc:
            self._status_labels["temperature"].setText(str(exc))
            return
        finally:
            if self._connected:
                self._refresh_status_btn.setEnabled(True)

        self._format_monitor_value("temperature", temp, "°C")
        self._format_monitor_value("coverglass_read", vcom, " V")

        if self._coverglass_combo.currentText().strip() == "" and vcom != _INVALID_READ:
            text = f"{vcom:.2f}"
            if self._coverglass_combo.findText(text) < 0:
                self._coverglass_combo.addItem(text)
            self._coverglass_combo.setCurrentText(text)

    def _format_monitor_value(self, key: str, value: float, suffix: str) -> None:
        if value == _INVALID_READ:
            self._status_labels[key].setText("—")
        else:
            self._status_labels[key].setText(f"{value:.2f}{suffix}")

    def set_channel(self, channel: int, emit: bool = True) -> None:
        """Update SDK channel UI; optionally emit channel_changed."""
        channel = int(channel)
        if channel not in (0, 1, 2):
            raise ValueError("channel must be 0, 1, or 2")

        self._channel_combo.blockSignals(True)
        self._channel_combo.setCurrentIndex(channel)
        self._channel_combo.blockSignals(False)

        if self._connected:
            self._push_sdk_channel(channel, emit=emit)
        elif emit:
            self.channel_changed.emit(channel)

    def _push_sdk_channel(self, channel: int, emit: bool = True) -> None:
        """Set SDK HDMI channel, show R/G/B tint on SLM, optionally notify ModMux."""
        if self._sdk is None:
            return
        try:
            self._sdk.write_channel_indicator(channel)
        except MeadowlarkSDKError as exc:
            self._status_labels["resolution"].setText(str(exc))
            return
        if emit:
            self.channel_changed.emit(channel)

    def _on_channel_combo_changed(self, index: int) -> None:
        if not self._connected or self._sdk is None:
            return
        self._push_sdk_channel(index, emit=True)

    def _load_lut(self) -> None:
        if self._sdk is None:
            return
        start_dir = str(LUT_DIR if LUT_DIR.is_dir() else Path.cwd())
        last = self._settings.get("last_loaded_lut")
        if last and Path(last).is_file():
            start_dir = str(Path(last).parent)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Meadowlark LUT",
            start_dir,
            "LUT files (*.lut *.blt *.txt);;All files (*)",
        )
        if not path:
            return
        try:
            self._sdk.load_lut(path)
            inputs, outputs = MeadowlarkSDK.parse_lut_file(path)
            self._lut_plot.set_lut(inputs, outputs)
            self._settings["last_loaded_lut"] = path
            self._settings.pop("last_lut", None)
            save_settings(self._settings)
            self._refresh_tracked_status()
        except (MeadowlarkSDKError, OSError, ValueError) as exc:
            self._status_labels["resolution"].setText(str(exc))

    def _store_lut(self) -> None:
        if self._sdk is None:
            return
        loaded = self._settings.get("last_loaded_lut")
        if not loaded:
            self._status_labels["in_flash_lut"].setText("No last_loaded_lut to flash")
            self._status_labels["in_flash_lut"].setToolTip("")
            return
        try:
            self._sdk.store_lut()
        except MeadowlarkSDKError as exc:
            self._status_labels["in_flash_lut"].setText(str(exc))
            self._status_labels["in_flash_lut"].setToolTip("")
            return
        self._settings["in_flash_lut"] = loaded
        save_settings(self._settings)
        self._refresh_tracked_status()

    def _apply_ramp_slopes(self) -> None:
        if self._sdk is None:
            return
        pre = int(self._pre_ramp_spin.value())
        post = int(self._post_ramp_spin.value())
        try:
            self._sdk.set_pre_ramp_slope(pre)
            self._sdk.set_post_ramp_slope(post)
        except (MeadowlarkSDKError, ValueError) as exc:
            self._status_labels["pre_ramp_slope"].setText(str(exc))
            return
        self._settings["pre_ramp_slope"] = pre
        self._settings["post_ramp_slope"] = post
        save_settings(self._settings)
        self._refresh_tracked_status()

    def _on_coverglass_enable_toggled(self, enabled: bool) -> None:
        self._coverglass_combo.setEnabled(enabled and self._connected)
        self._settings["coverglass_enabled"] = enabled
        save_settings(self._settings)

    def _apply_coverglass_setpoint(self) -> None:
        if not self._coverglass_enable.isChecked() or self._sdk is None:
            return
        text = self._coverglass_combo.currentText().strip()
        try:
            volts = float(text)
        except ValueError:
            return
        try:
            self._sdk.set_coverglass_voltage(volts)
        except MeadowlarkSDKError as exc:
            self._status_labels["coverglass_read"].setText(str(exc))
            return

        formatted = f"{volts:.2f}"
        if self._coverglass_combo.findText(formatted) < 0:
            self._coverglass_combo.addItem(formatted)
        self._coverglass_combo.setCurrentText(formatted)

        history = self._settings.get("coverglass_history_V", [])
        if volts not in history:
            history.append(volts)
        self._settings["coverglass_history_V"] = history[-20:]
        self._settings["coverglass_setpoint_V"] = volts
        self._settings["coverglass_enabled"] = self._coverglass_enable.isChecked()
        save_settings(self._settings)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._disconnect()
        super().closeEvent(event)
