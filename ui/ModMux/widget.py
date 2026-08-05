"""ModMux control widget — routing and composition flags for an existing LCOS instance."""

import numpy as np
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .centers_panel import display_center_to_user
from .channel_panel import ChannelPanel
from .extra_functionalities import create_extra_widgets
from .pol_mask_panel import PolMaskPanel
from .preview import LcosPreview


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
        self._channels = ChannelPanel(self.slm.ch)
        self._user_controls = self._panel_h.user_controls() + self._panel_v.user_controls()
        self._extra_functionality = create_extra_widgets(self.slm.alias, parent = self) #Pass self so we can connect signals

        self._preview = LcosPreview(self.width, self.height, self.slm.ch)

        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)

        self._build_ui()
        self._connect_signals()
        self.refresh_gui_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        body = QHBoxLayout()
        controls = QVBoxLayout()
        controls.addWidget(self._panel_h)
        controls.addWidget(self._panel_v)
        controls.addWidget(self._channels)
        controls.addStretch(1)
        for widget in self._extra_functionality:
            controls.addWidget(widget)

        preview_box = QGroupBox("LCOS Panel Viewer")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(4, 8, 4, 4)
        preview_layout.addWidget(self._preview)

        self._hover_label = QLabel("")
        self._hover_label.setWordWrap(True)
        preview_layout.addWidget(self._hover_label)
        self._preview.hoverChanged.connect(self._hover_label.setText)

        body.addLayout(controls, stretch=0)
        body.addWidget(preview_box, stretch=1)
        root.addLayout(body, stretch=1)
        root.addWidget(self._info_label)

    def _connect_signals(self) -> None:
        for widget in self._user_controls:
            if hasattr(widget, "toggled"):
                widget.toggled.connect(self._on_user_change)
            elif hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._on_user_change)
        self._channels.channelChanged.connect(self._sync_channel)

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

    def _hdmi_image(self) -> np.ndarray:
        ch = self.slm.ch
        return self.slm.screen_data[:, :, ch]

    def _update_preview(self) -> None:
        self._preview.set_hdmi_image(self._hdmi_image())

    def _update_info_label(self, text: str) -> None:
        """Update the bottom status bar. Call after setmask() or from a timer."""
        self._info_label.setText(text)

    def _disable_user_interface(self) -> None:
        self._ui_locked = True
        for widget in self._user_controls:
            widget.setEnabled(False)

    def _enable_user_interface(self) -> None:
        for widget in self._user_controls:
            widget.setEnabled(True)
        self._panel_h._on_master_toggled(self._panel_h.isChecked())
        self._panel_v._on_master_toggled(self._panel_v.isChecked())
        self._ui_locked = False
