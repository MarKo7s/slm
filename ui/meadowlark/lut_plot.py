"""Small 1D LUT preview plot."""

import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget


class LutPlot(QWidget):
    """Plot Meadowlark LUT: input graylevel vs drive level."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plot = pg.PlotWidget()
        self._plot.setLabel("bottom", "input graylevel")
        self._plot.setLabel("left", "drive level")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._curve = self._plot.plot([], [], pen=pg.mkPen(width=2))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)
        self.setMinimumHeight(140)

    def set_lut(self, inputs, outputs) -> None:
        self._curve.setData(inputs, outputs)
