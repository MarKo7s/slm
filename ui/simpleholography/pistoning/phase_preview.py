"""LCOS phase preview widgets (Qt Graphics View and pyqtgraph backends)."""

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .colormaps import apply_channel_colormap, level_to_rgb, phase_to_rgb

PI = math.pi
HIT_TOLERANCE_PX = 8
MAX_ZOOM_FACTOR = 32.0

# Switch preview backend: "qt" (default) or "pyqtgraph"
PREVIEW_BACKEND = "pyqtgraph"


def _clamp_cuts(cut_x: int, cut_y: int, width: int, height: int) -> tuple[int, int]:
    return (
        int(np.clip(cut_x, 1, width - 1)),
        int(np.clip(cut_y, 1, height - 1)),
    )


def _qt_cut_pens() -> tuple[QPen, QPen]:
    """Vertical cut: yellow; horizontal cut: cyan. Both solid at 50% alpha."""
    v_pen = QPen(QColor(255, 255, 0, 128), 0)
    v_pen.setCosmetic(True)
    v_pen.setStyle(Qt.PenStyle.SolidLine)
    h_pen = QPen(QColor(0, 220, 255, 128), 0)
    h_pen.setCosmetic(True)
    h_pen.setStyle(Qt.PenStyle.SolidLine)
    return v_pen, h_pen


def _pg_cut_pens() -> tuple[pg.QtGui.QPen, pg.QtGui.QPen]:
    """Vertical cut: yellow; horizontal cut: cyan. Both solid at 50% alpha."""
    return (
        pg.mkPen((255, 255, 0, 128), width=1),
        pg.mkPen((0, 220, 255, 128), width=1),
    )


class PhasePreviewQt(QGraphicsView):
    """LCOS phase preview with draggable cut lines (native PySide6)."""

    cutsChanged = Signal()

    def __init__(self, width: int, height: int, channel: int, parent=None):
        super().__init__(parent)
        self.lcos_width = width
        self.lcos_height = height
        self.channel = channel
        self.cut_x = width // 2
        self.cut_y = height // 2
        self.enable_v_cut = True
        self.enable_h_cut = True
        self._drag_axis: str | None = None
        self._min_scale = 1.0

        self.setScene(QGraphicsScene(0, 0, width, height, self))
        self.setSceneRect(0, 0, width, height)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setZValue(0)
        self.scene().addItem(self._pixmap_item)

        v_pen, h_pen = _qt_cut_pens()

        self._v_line = QGraphicsLineItem()
        self._v_line.setPen(v_pen)
        self._v_line.setZValue(1)
        self.scene().addItem(self._v_line)

        self._h_line = QGraphicsLineItem()
        self._h_line.setPen(h_pen)
        self._h_line.setZValue(1)
        self.scene().addItem(self._h_line)

        self._sync_cut_lines()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_to_view()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if abs(self.transform().m11() - self._min_scale) < 1e-6:
            self._fit_to_view()

    def _fit_to_view(self) -> None:
        self.resetTransform()
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._min_scale = self.transform().m11()

    def update_cuts(self, cut_x: int, cut_y: int, enable_v: bool, enable_h: bool) -> None:
        self.cut_x, self.cut_y = _clamp_cuts(cut_x, cut_y, self.lcos_width, self.lcos_height)
        self.enable_v_cut = enable_v
        self.enable_h_cut = enable_h
        self._sync_cut_lines()

    def _sync_cut_lines(self) -> None:
        self._v_line.setVisible(self.enable_v_cut)
        self._h_line.setVisible(self.enable_h_cut)
        self._v_line.setLine(self.cut_x, 0, self.cut_x, self.lcos_height)
        self._h_line.setLine(0, self.cut_y, self.lcos_width, self.cut_y)

    def set_phase(self, phase: np.ndarray) -> None:
        rgb = phase_to_rgb(phase, self.channel)
        h, w, _ = rgb.shape
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self._pixmap_item.setPixmap(QPixmap.fromImage(image.copy()))

    def set_level(self, level: np.ndarray) -> None:
        rgb = level_to_rgb(level, self.channel)
        h, w, _ = rgb.shape
        image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self._pixmap_item.setPixmap(QPixmap.fromImage(image.copy()))

    def _scene_tolerance(self) -> float:
        scale = self.transform().m11()
        if scale <= 0:
            return HIT_TOLERANCE_PX
        return HIT_TOLERANCE_PX / scale

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = self.mapToScene(event.position().toPoint())
        tol = self._scene_tolerance()
        self._drag_axis = None

        if self.enable_v_cut and abs(pos.x() - self.cut_x) <= tol:
            self._drag_axis = "v"
        elif self.enable_h_cut and abs(pos.y() - self.cut_y) <= tol:
            self._drag_axis = "h"

        if self._drag_axis is None:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_axis is None:
            super().mouseMoveEvent(event)
            return

        pos = self.mapToScene(event.position().toPoint())
        if self._drag_axis == "v":
            self.cut_x = int(round(pos.x()))
        else:
            self.cut_y = int(round(pos.y()))
        self.cut_x, self.cut_y = _clamp_cuts(self.cut_x, self.cut_y, self.lcos_width, self.lcos_height)
        self._sync_cut_lines()
        self.cutsChanged.emit()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_axis = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return

        factor = 1.15 if delta > 0 else 1 / 1.15
        current_scale = self.transform().m11()
        target_scale = current_scale * factor

        if target_scale < self._min_scale:
            self._fit_to_view()
            return
        if target_scale > self._min_scale * MAX_ZOOM_FACTOR:
            return

        self.scale(factor, factor)


class PhasePreviewPyqtgraph(pg.ImageView):
    """LCOS phase preview using pyqtgraph ImageView (row-major, monitor-aligned)."""

    cutsChanged = Signal()

    def __init__(self, width: int, height: int, channel: int, parent=None):
        pg.setConfigOptions(useOpenGL=False, antialias=False)
        super().__init__(parent, levelMode="mono")
        self.lcos_width = width
        self.lcos_height = height
        self.channel = channel
        self.cut_x = width // 2
        self.cut_y = height // 2
        self.enable_v_cut = True
        self.enable_h_cut = True
        self._did_initial_fit = False

        self.ui.roiBtn.hide()
        self.ui.menuBtn.hide()
        self.ui.histogram.hide()

        self.view.setAspectLocked(True)
        # pyqtgraph ImageItem y-axis is opposite the LCOS/monitor row order; flip view vertically.
        self.view.invertY(True)
        self.view.enableAutoRange(x=False, y=False)

        apply_channel_colormap(self.getImageItem(), channel)
        self.getImageItem().axisOrder = "row-major"

        v_pen, h_pen = _pg_cut_pens()
        self._v_line = pg.InfiniteLine(
            pos=self.cut_x,
            angle=90,
            movable=True,
            pen=v_pen,
        )
        self._h_line = pg.InfiniteLine(
            pos=self.cut_y,
            angle=0,
            movable=True,
            pen=h_pen,
        )
        self.view.addItem(self._v_line)
        self.view.addItem(self._h_line)

        self._v_line.sigPositionChanged.connect(self._on_v_line_moved)
        self._h_line.sigPositionChanged.connect(self._on_h_line_moved)
        self._sync_cut_lines()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.fit_to_window)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_to_window)

    def fit_to_window(self) -> None:
        """Fit full LCOS frame to the view; max range prevents zooming out past fit."""
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
        self.view.autoRange(padding=0)

    def update_cuts(self, cut_x: int, cut_y: int, enable_v: bool, enable_h: bool) -> None:
        self.cut_x, self.cut_y = _clamp_cuts(cut_x, cut_y, self.lcos_width, self.lcos_height)
        self.enable_v_cut = enable_v
        self.enable_h_cut = enable_h
        self._sync_cut_lines()

    def _sync_cut_lines(self) -> None:
        self._v_line.setVisible(self.enable_v_cut)
        self._v_line.setMovable(self.enable_v_cut)
        self._h_line.setVisible(self.enable_h_cut)
        self._h_line.setMovable(self.enable_h_cut)

        self._v_line.blockSignals(True)
        self._h_line.blockSignals(True)
        self._v_line.setValue(self.cut_x)
        self._h_line.setValue(self.cut_y)
        self._v_line.blockSignals(False)
        self._h_line.blockSignals(False)

    def _on_v_line_moved(self) -> None:
        if not self.enable_v_cut:
            return
        self.cut_x = int(round(self._v_line.value()))
        self.cut_x, self.cut_y = _clamp_cuts(self.cut_x, self.cut_y, self.lcos_width, self.lcos_height)
        if int(round(self._v_line.value())) != self.cut_x:
            self._v_line.setValue(self.cut_x)
        self.cutsChanged.emit()

    def _on_h_line_moved(self) -> None:
        if not self.enable_h_cut:
            return
        self.cut_y = int(round(self._h_line.value()))
        self.cut_x, self.cut_y = _clamp_cuts(self.cut_x, self.cut_y, self.lcos_width, self.lcos_height)
        if int(round(self._h_line.value())) != self.cut_y:
            self._h_line.setValue(self.cut_y)
        self.cutsChanged.emit()

    def set_phase(self, phase: np.ndarray) -> None:
        # LCOS arrays are (row, col) = (Y, X); row-major matches the monitor buffer.
        self.setImage(
            phase,
            autoRange=False,
            autoLevels=False,
            levels=(-PI, PI),
            autoHistogramRange=False,
        )
        if not self._did_initial_fit:
            self._did_initial_fit = True
            QTimer.singleShot(0, self.fit_to_window)

    def set_level(self, level: np.ndarray) -> None:
        self.setImage(
            level.astype(np.float64),
            autoRange=False,
            autoLevels=False,
            levels=(0, 255),
            autoHistogramRange=False,
        )
        if not self._did_initial_fit:
            self._did_initial_fit = True
            QTimer.singleShot(0, self.fit_to_window)


_BACKENDS = {
    "qt": PhasePreviewQt,
    "pyqtgraph": PhasePreviewPyqtgraph,
}


def create_phase_preview(width: int, height: int, channel: int, parent=None, backend: str | None = None):
    """Build a preview widget for the selected backend."""
    name = (backend or PREVIEW_BACKEND).lower()
    try:
        cls = _BACKENDS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown preview backend {name!r}. Choose from: {list(_BACKENDS)}") from exc
    return cls(width, height, channel, parent)


PhasePreview = _BACKENDS[PREVIEW_BACKEND.lower()]

__all__ = [
    "PREVIEW_BACKEND",
    "PhasePreview",
    "PhasePreviewQt",
    "PhasePreviewPyqtgraph",
    "create_phase_preview",
]
