"""HDMI channel selection (R / G / B) for ModMux."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QWidget

_CHANNEL_LABELS = ("R", "G", "B")


class ChannelPanel(QGroupBox):
    """Mutually exclusive R / G / B checkboxes."""

    channelChanged = Signal(int)

    def __init__(self, initial_channel: int = 0, parent=None):
        super().__init__("Channels", parent)
        self._boxes = [QCheckBox(label) for label in _CHANNEL_LABELS]

        row = QHBoxLayout(self)
        for box in self._boxes:
            row.addWidget(box)

        for index, box in enumerate(self._boxes):
            box.toggled.connect(lambda checked, i=index: self._on_toggled(i, checked))

        self.apply_channel(initial_channel)

    def user_controls(self) -> list[QWidget]:
        return [self, *self._boxes]

    def current_channel(self) -> int:
        for index, box in enumerate(self._boxes):
            if box.isChecked():
                return index
        return 0

    def apply_channel(self, channel: int) -> None:
        channel = int(channel)
        if channel not in (0, 1, 2):
            raise ValueError("channel must be 0, 1, or 2")
        for widget in self.user_controls():
            widget.blockSignals(True)
        for index, box in enumerate(self._boxes):
            box.setChecked(index == channel)
        for widget in self.user_controls():
            widget.blockSignals(False)

    def _on_toggled(self, index: int, checked: bool) -> None:
        if not checked:
            if not any(box.isChecked() for box in self._boxes):
                self.apply_channel(index)
            return
        self.apply_channel(index)
        self.channelChanged.emit(index)
