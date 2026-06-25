"""Manufacturer-specific ModMux extras, selected by ``slm.alias``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QPushButton, QWidget

if TYPE_CHECKING:
    from ui.ModMux.widget import ModMuxWidget

#! ADD HERE THE WIDGETS
#! If meadowlark is the alias, this button will open the Meadowlark SDK panel; SDK channel changes sync into ModMux.
class MeadowlarkDriverButton(QPushButton):
    """Opens the Meadowlark SDK panel; SDK channel changes sync into ModMux."""

    def __init__(self, parent: ModMuxWidget):
        super().__init__("Open Meadowlark Driver", parent)
        self._modmux = parent
        self._gui = None
        self.clicked.connect(self._open)

    @property
    def gui(self):
        return self._gui

    def _open(self) -> None:
        from ui.meadowlark import MeadowlarkWidget

        if self._gui is None:
            self._gui = MeadowlarkWidget(self._modmux.slm)
            self._gui.channel_changed.connect(self._modmux._sync_channel)
            self._gui.destroyed.connect(self._on_gui_destroyed)
        self._gui.show()
        self._gui.raise_()
        self._gui.activateWindow()

    def _on_gui_destroyed(self, *_args) -> None:
        self._gui = None


#! LINK ALIAD TO WIDGET
# alias -> factory(parent) -> widget to pin at the bottom of the controls column
EXTRA_FUNCTIONALITIES = {
    "meadowlark":  MeadowlarkDriverButton,
}

#! Function run at the parent level
def create_extra_widgets(alias: str, parent: ModMuxWidget) -> list[QWidget]:
    factory = EXTRA_FUNCTIONALITIES.get(alias)
    if factory is None:
        return []
    return [factory(parent)]
