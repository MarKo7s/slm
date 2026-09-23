"""LCOS phase preview (pyqtgraph) — fit-to-window, no zoom-out below full frame."""

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QSizePolicy, QWidget

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

        # Collapse ImageView chrome: hidden histogram/buttons still leave a
        # vertical splitter + roiPlot strip that grows oddly on window resize.
        self.ui.roiBtn.hide()
        self.ui.menuBtn.hide()
        self.ui.histogram.hide()
        self.ui.roiPlot.hide()
        self.ui.roiPlot.setMinimumHeight(0)
        self.ui.splitter.setHandleWidth(0)
        self.ui.splitter.setSizes([1, 0])

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

        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(16)
        self._fit_timer.timeout.connect(self.fit_to_window)

        self.scene.sigMouseMoved.connect(self._on_mouse_moved)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_fit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Keep the ROI strip collapsed if ImageView re-applies splitter sizes.
        self.ui.splitter.setSizes([1, 0])
        self._schedule_fit()

    def leaveEvent(self, event) -> None:
        self.hoverChanged.emit("")
        super().leaveEvent(event)

    def _schedule_fit(self) -> None:
        self._fit_timer.start()

    def fit_to_window(self) -> None:
        self.view.setRange(
            xRange=(0, self.lcos_width),
            yRange=(0, self.lcos_height),
            padding=0,
        )

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


class LcosPreviewHost(QWidget):
    """Letterbox an LcosPreview so its widget matches the LCOS aspect ratio."""

    def __init__(self, preview: LcosPreview, parent=None):
        super().__init__(parent)
        self.preview = preview
        preview.setParent(self)
        preview.setMinimumSize(0, 0)
        preview.show()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.black)
        self.setPalette(palette)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._place_preview()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_preview()

    def _place_preview(self) -> None:
        avail_w = self.width()
        avail_h = self.height()
        if avail_w < 1 or avail_h < 1 or self.preview.lcos_height < 1:
            return
        self.preview.setMinimumSize(0, 0)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        aspect = self.preview.lcos_width / self.preview.lcos_height
        if avail_w / avail_h > aspect:
            height = avail_h
            width = max(1, int(round(height * aspect)))
        else:
            width = avail_w
            height = max(1, int(round(width / aspect)))
        x = (avail_w - width) // 2
        y = (avail_h - height) // 2
        self.preview.setGeometry(x, y, width, height)
        self.preview.fit_to_window()
