"""LCOS phase preview (pyqtgraph) — fit-to-window, no zoom-out below full frame."""

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Signal

from slm.ui.simpleholography.pistoning.colormaps import apply_channel_colormap, level_to_phase

PI = math.pi


class LcosPreview(pg.ImageView):
    """Full-frame LCOS HDMI image with hover readout of level and phase."""

    hoverChanged = Signal(str)

    def __init__(self, width: int, height: int, channel: int, parent=None):
        pg.setConfigOptions(useOpenGL=False, antialias=False)
        super().__init__(parent, levelMode="mono")

        self.lcos_width = width
        self.lcos_height = height
        self.channel = channel
        self._level_image: np.ndarray | None = None

        self.ui.roiBtn.hide()
        self.ui.menuBtn.hide()
        self.ui.histogram.hide()

        self.view.setAspectLocked(True)
        self.view.invertY(True)
        self.view.enableAutoRange(x=False, y=False)

        apply_channel_colormap(self.getImageItem(), channel)
        self.getImageItem().axisOrder = "row-major"

        self.view.setLimits(
            xMin=0,
            xMax=self.lcos_width,
            yMin=0,
            yMax=self.lcos_height,
            minXRange=4,
            minYRange=4,
            maxXRange=self.lcos_width,
            maxYRange=self.lcos_height,
        )

        self.scene.sigMouseMoved.connect(self._on_mouse_moved)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_to_window)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_to_window)

    def leaveEvent(self, event) -> None:
        self.hoverChanged.emit("")
        super().leaveEvent(event)

    def fit_to_window(self) -> None:
        self.view.autoRange(padding=0)

    def set_hdmi_image(self, image: np.ndarray) -> None:
        """Show the uint8 frame on the SLM monitor (screen_data channel)."""
        self._level_image = np.asarray(image)
        self.setImage(
            self._level_image,
            autoRange=False,
            autoLevels=False,
            levels=(0, 255),
            autoHistogramRange=False,
        )

    def set_channel(self, channel: int) -> None:
        """Switch preview colormap to match HDMI channel."""
        channel = int(channel)
        if channel not in (0, 1, 2):
            raise ValueError("channel must be 0, 1, or 2")
        self.channel = channel
        apply_channel_colormap(self.getImageItem(), channel)

    def _on_mouse_moved(self, pos) -> None:
        if self._level_image is None:
            return
        if not self.view.sceneBoundingRect().contains(pos):
            self.hoverChanged.emit("")
            return

        point = self.view.mapSceneToView(pos)
        x = int(round(point.x()))
        y = int(round(point.y()))
        if x < 0 or y < 0 or x >= self.lcos_width or y >= self.lcos_height:
            self.hoverChanged.emit("")
            return

        level = int(self._level_image[y, x])
        phase = level_to_phase(level)
        text = (
            f"x={x}  y={y}  |  level={level}  |  "
            f"phase={phase:.4f} rad  ({math.degrees(phase):.2f}°)"
        )
        self.hoverChanged.emit(text)
