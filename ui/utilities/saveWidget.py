"""File buttons for a parent that owns the actual save and load calls."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class SaveLoad(QGroupBox):
    """Browse, Reload, Save, and Save As. The parent connects the signals."""

    browseClicked = Signal()
    reloadClicked = Signal()
    saveClicked = Signal()
    saveAsClicked = Signal()

    def __init__(self, orientation: str = "horizontal", parent=None):
        super().__init__("Config", parent)
        if orientation not in ("horizontal", "vertical"):
            raise ValueError("orientation must be 'horizontal' or 'vertical'")

        self.path: str | None = None
        self._browse = QPushButton("Browse")
        self._reload = QPushButton("Reload")
        self._save = QPushButton("Save")
        self._save_as = QPushButton("Save As")

        buttons = QHBoxLayout(self) if orientation == "horizontal" else QVBoxLayout(self)
        for button in (self._browse, self._reload, self._save, self._save_as):
            buttons.addWidget(button)

        self._browse.clicked.connect(self.browseClicked)
        self._reload.clicked.connect(self.reloadClicked)
        self._save.clicked.connect(self.saveClicked)
        self._save_as.clicked.connect(self.saveAsClicked)
        self._reload.setEnabled(False)

    def user_controls(self) -> list[QWidget]:
        return [self, self._browse, self._reload, self._save, self._save_as]

    def set_path(self, path: str | None) -> None:
        """Store the current file and enable Reload only when one is set."""
        self.path = str(path) if path else None
        self._reload.setEnabled(self.path is not None)
