"""Channel-tinted preview colors for SLM phase maps."""

import math

import numpy as np

PI = math.pi


def channel_colormap_lut(channel: int, n: int = 256) -> np.ndarray:
    """Return an (n, 4) uint8 LUT for pyqtgraph ImageItem."""
    t = np.linspace(0.0, 1.0, n, dtype=np.float64)
    lut = np.zeros((n, 4), dtype=np.uint8)
    lut[:, 3] = 255
    ch = int(channel) if channel in (0, 1, 2) else 0
    lut[:, ch] = (t * 255).astype(np.uint8)
    return lut


def apply_channel_colormap(image_item, channel: int) -> None:
    """Apply a single-hue LUT to a pyqtgraph ImageItem."""
    image_item.setLookupTable(channel_colormap_lut(channel))


def phase_to_rgb(phase: np.ndarray, channel: int) -> np.ndarray:
    """Map phase (-pi..pi) to an RGB888 image tinted to the SLM channel."""
    level = np.clip((phase + PI) / (2.0 * PI), 0.0, 1.0)
    gray = (level * 255.0).astype(np.uint8)
    h, w = gray.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    ch = int(channel) if channel in (0, 1, 2) else 0
    rgb[:, :, ch] = gray
    return np.ascontiguousarray(rgb)
