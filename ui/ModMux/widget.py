"""ModMux control widget — routing and composition flags for an existing LCOS instance."""

import numpy as np
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QTimer

from ...pyLCOS import modmux_config_default_path
from ..utilities.saveWidget import SaveLoad
from .centers_panel import display_center_to_user
from .channel_panel import ChannelPanel
from .extra_functionalities import create_extra_widgets
from .pol_mask_panel import PolMaskPanel
from .preview import LcosPreview, LcosPreviewHost

def pol_from_masters(h_on: bool, v_on: bool) -> str | None:
    if h_on and v_on:
        return "HV"
    if h_on:
        return "H"
    if v_on:
        return "V"
    return None


def masters_from_pol(pol: str) -> tuple[bool, bool]:
    return pol in ("H", "HV"), pol in ("V", "HV")

UI_LOCKED_TEXT = "UI locked (Remote Control)"

class ModMuxWidget(QWidget):
    """Controls ModMux enable flags, attenuation, and centers on an existing LCOS instance."""

    def __init__(self, slm, parent=None):
        super().__init__(parent)
        self.slm = slm
        self.height, self.width = slm.LCOSsize
        self._ui_locked = False

        self.setWindowTitle("ModMux")
        self.resize(1100, 720)

        self._panel_h = PolMaskPanel("Mask H", self.width, self.height)
        self._panel_v = PolMaskPanel("Mask V", self.width, self.height)
        self._backup_btn = QPushButton("Backup")
        self._restore_btn = QPushButton("Restore")
        self._restore_btn.setEnabled(False)
        self._channels = ChannelPanel(self.slm.ch)
        self._save_load = SaveLoad(orientation="vertical")
        self._extra_functionality = create_extra_widgets(self.slm.alias, parent = self) #Pass self so we can connect signals
        self._preview = LcosPreview(self.width, self.height, self.slm.ch)
        self._preview_host = LcosPreviewHost(self._preview)

        #! Build a list encapsulating all the user controls, so it is easy to enable and dissable them
        self._user_controls = (
            self._panel_h.user_controls()
            + self._panel_v.user_controls()
            + [self._backup_btn, self._restore_btn]
            + self._channels.user_controls()
            + self._save_load.user_controls()
        )
        for extra in self._extra_functionality:
            self._user_controls.extend(extra.user_controls())

        self._info_label = QLabel("")
        self._info_label.setWordWrap(False)
        self._config_label = QLabel("No config file")
        self._config_label.setWordWrap(False)
        self._config_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._auto_preview_refresh_timer = QTimer(self)
        self._auto_preview_refresh_timer.setInterval(100)
        self._build_ui()
        self._connect_signals()
        self.refresh_gui_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        body = QHBoxLayout()
        controls = QVBoxLayout()
        controls.addWidget(self._panel_h)
        controls.addWidget(self._panel_v)

        backup_row = QHBoxLayout()
        backup_row.addWidget(self._backup_btn)
        backup_row.addWidget(self._restore_btn)
        controls.addLayout(backup_row)

        controls.addWidget(self._channels)
        controls.addWidget(self._save_load)
        controls.addStretch(1)

        for widget in self._extra_functionality:
            controls.addWidget(widget)

        preview_box = QGroupBox("LCOS Panel Viewer")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(4, 8, 4, 4)
        preview_layout.addWidget(self._preview_host, stretch=1)

        self._hover_label = QLabel("")
        self._hover_label.setWordWrap(True)
        preview_layout.addWidget(self._hover_label)
        self._preview.hoverChanged.connect(self._hover_label.setText)

        body.addLayout(controls, stretch=0)
        body.addWidget(preview_box, stretch=1)
        root.addLayout(body, stretch=1)

        status = QHBoxLayout()
        status.addWidget(self._info_label, stretch=0)
        status.addStretch(1)
        status.addWidget(self._config_label, stretch=0)
        root.addLayout(status)

    def _connect_signals(self) -> None:
        #! Here connect controls to signals as you need. ie: panels do _on_user_change while channels do _sync_channel
        for widget in self._panel_h.user_controls() + self._panel_v.user_controls():
            if hasattr(widget, "toggled"):
                widget.toggled.connect(self._on_user_change)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._on_user_change)

        self._channels.channelChanged.connect(self._sync_channel)
        self._backup_btn.clicked.connect(self._backup_centers)
        self._restore_btn.clicked.connect(self._restore_centers)
        self._save_load.browseClicked.connect(self._browse_config)
        self._save_load.reloadClicked.connect(self._load_config)
        self._save_load.saveClicked.connect(self._save_config)
        self._save_load.saveAsClicked.connect(self._save_config_as)
        self._auto_preview_refresh_timer.timeout.connect(self._update_preview_async)
    
    def _start_auto_preview_refresh(self) -> None:
        self._auto_preview_refresh_timer.start()

    def _stop_auto_preview_refresh(self) -> None:
        self._auto_preview_refresh_timer.stop()

    def _on_user_change(self, *_args) -> None:
        if self._ui_locked:
            return
        self._apply_and_display()

    def _user_centers_from_slm(self) -> tuple[list[int], list[int]]:
        mm = self.slm.ModMuxMask
        modelab = mm.ModelabCompatibility
        offset = mm.offset_center
        lcos_size = mm.LCOS_size

        center_h = display_center_to_user(mm.Hcenter, lcos_size, offset, modelab, is_v=False)
        center_v = display_center_to_user(mm.Vcenter, lcos_size, offset, modelab, is_v=True)
        return list(center_h), list(center_v)

    def refresh_gui_state(self) -> None:
        """Pull SLM state into controls and preview. Does not call setmask()."""
        mm = self.slm.ModMuxMask
        h_on, v_on = masters_from_pol(mm.pol)

        center_h, center_v = self._user_centers_from_slm()

        self._panel_h.apply_state(
            master=h_on,
            pattern_enabled=mm.H.pattern_enabled,
            zernikes_enabled=mm.H.zernikes_enabled,
            att_enabled=mm.H.att_enabled,
            att_weight=mm.H.att_weight,
            center=tuple(center_h),
        )
        self._panel_v.apply_state(
            master=v_on,
            pattern_enabled=mm.V.pattern_enabled,
            zernikes_enabled=mm.V.zernikes_enabled,
            att_enabled=mm.V.att_enabled,
            att_weight=mm.V.att_weight,
            center=tuple(center_v),
        )
        self._channels.apply_channel(self.slm.ch)
        self._preview.set_channel(self.slm.ch)
        self._sync_config_buttons()
        self._update_preview()

    def _sync_channel(self, channel: int) -> None:
        """Switch HDMI channel on SLM and preview (e.g. from channel panel or Meadowlark SDK)."""
        if self._ui_locked:
            return

        channel = int(channel)
        self.slm.set_channel(channel)
        self._channels.apply_channel(channel)
        self._preview.set_channel(channel)

        mm = self.slm.ModMuxMask
        if mm.pol is not None:
            self.slm.setmask()

        self._update_preview()

    #! In theory you use the object slm externaly and call refresh gui state instead of this function which call setmask
    def _apply_and_display(self) -> None:
        """Push control state to ModMuxMask, update SLM, refresh preview. Internal use."""
        if self._ui_locked:
            return

        mm = self.slm.ModMuxMask
        h_state = self._panel_h.read_state()
        v_state = self._panel_v.read_state()
        center_h = h_state["center"]
        center_v = v_state["center"]

        mm.H.pattern_enabled = h_state["pattern_enabled"]
        mm.H.zernikes_enabled = h_state["zernikes_enabled"]
        mm.H.att_enabled = h_state["att_enabled"]
        mm.H.att_weight = h_state["att_weight"]

        mm.V.pattern_enabled = v_state["pattern_enabled"]
        mm.V.zernikes_enabled = v_state["zernikes_enabled"]
        mm.V.att_enabled = v_state["att_enabled"]
        mm.V.att_weight = v_state["att_weight"]

        self.slm.setCenters(center_h, center_v, display=False)

        pol = pol_from_masters(h_state["master"], v_state["master"])

        if pol is None:
            self.slm.LCOS_Clean()
        else:
            mm.pol = pol
            self.slm.setmask()

        self._update_preview()

    def _sync_config_buttons(self) -> None:
        """Enable Reload and Restore only when a file or a center backup exists."""
        if self._ui_locked:
            return
        self._save_load.set_path(self.slm.config_path)
        self._update_config_label()
        self._restore_btn.setEnabled(self.slm.ModMuxMask.has_center_backup())

    def _backup_centers(self) -> None:
        self.slm.backupCenters()
        self._sync_config_buttons()

    def _restore_centers(self) -> None:
        self.slm.restoreCenters()
        self.refresh_gui_state()

    def _config_dialog_start(self) -> str:
        return self.slm.config_path or str(modmux_config_default_path())

    def _browse_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load ModMux config",
            self._config_dialog_start(),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        self.slm.load(path)
        self.refresh_gui_state()

    def _load_config(self) -> None:
        if not self.slm.config_path:
            return
        self.slm.load(self.slm.config_path)
        self.refresh_gui_state()

    def _save_config(self) -> None:
        if self.slm.config_path:
            self.slm.save(self.slm.config_path)
            self.refresh_gui_state()
            return
        self._save_config_as()

    def _save_config_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save ModMux config",
            self._config_dialog_start(),
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path = f"{path}.json"
        self.slm.save(path)
        self.refresh_gui_state()

    def _hdmi_image(self) -> np.ndarray:
        ch = self.slm.ch
        return self.slm.screen_data[:, :, ch]

    def _update_preview(self) -> None:
        self._preview.set_hdmi_image(self._hdmi_image())
        refresh_freq = self.slm.refreshfreq
        self._update_info_label(f"Mask refreshed at {refresh_freq:.2f} Hz")

    def _update_preview_async(self) -> None:
        
        frame = self.slm.read_screen_buffer_async()
        self._preview.set_hdmi_image(frame)
        refresh_freq = self.slm.refreshfreq
        self._update_info_label(f"Mask refreshed at {refresh_freq:.2f} Hz - {UI_LOCKED_TEXT}")

    def _update_info_label(self, text: str) -> None:
        """Update the bottom status bar. Call after setmask() or from a timer."""
        self._info_label.setText(text)

    def _update_config_label(self) -> None:
        """Show the stored config path and the JSON saved_at timestamp."""
        path = self.slm.config_path
        if not path:
            self._config_label.setText("No config file")
            return
        saved_at = self.slm.config_saved_at
        if saved_at:
            self._config_label.setText(f"{path}  {saved_at}")
            return
        self._config_label.setText(str(path))

    def disable_user_interface(self, run_async = False) -> None:
        if run_async:
            QTimer.singleShot(0, self, self._disable_user_interface)
        else:
            self._disable_user_interface()

    def _disable_user_interface(self) -> None:
        self._ui_locked = True
        for widget in self._user_controls:
            widget.setEnabled(False)
        self._update_info_label(UI_LOCKED_TEXT)
        self._start_auto_preview_refresh()

    def enable_user_interface(self, run_async = False) -> None:
        if run_async:
            QTimer.singleShot(0, self, self._enable_user_interface)
        else:
            self._enable_user_interface()

    def _enable_user_interface(self) -> None:

        self._stop_auto_preview_refresh()
        self.refresh_gui_state() #resync all the controls based on the slm object
        for widget in self._user_controls:
            widget.setEnabled(True)

        self._panel_h._on_master_toggled(self._panel_h.isChecked())
        self._panel_v._on_master_toggled(self._panel_v.isChecked())

        self._ui_locked = False
        self._sync_config_buttons()
        self._stop_auto_preview_refresh()