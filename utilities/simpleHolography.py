"""Simple hologram generators for SLM widgets."""

import numpy as np

REGION_ALL = "all"
REGION_LEFT = "left"
REGION_RIGHT = "right"
REGION_TOP = "top"
REGION_BOTTOM = "bottom"
REGION_TL = "tl"
REGION_TR = "tr"
REGION_BL = "bl"
REGION_BR = "br"
REGION_INNER = "inner"
REGION_OUTER = "outer"


def region_keys(
    enable_v_cut: bool,
    enable_h_cut: bool,
    enable_circular: bool = False,
) -> list[str]:
    """Return active region identifiers for the given cut configuration."""
    if enable_circular:
        return [REGION_INNER, REGION_OUTER]
    if not enable_v_cut and not enable_h_cut:
        return [REGION_ALL]
    if enable_v_cut and not enable_h_cut:
        return [REGION_LEFT, REGION_RIGHT]
    if not enable_v_cut and enable_h_cut:
        return [REGION_TOP, REGION_BOTTOM]
    return [REGION_TL, REGION_TR, REGION_BL, REGION_BR]


def _clamp_cut(value: int, limit: int) -> int:
    return int(np.clip(value, 1, limit - 1))


def pistoning_phase_mask(
    shape: tuple[int, int],
    cut_x: int,
    cut_y: int,
    enable_v_cut: bool,
    enable_h_cut: bool,
    phases: dict[str, float],
    *,
    enable_circular: bool = False,
    center_x: int = 0,
    center_y: int = 0,
    radius: int = 1,
) -> np.ndarray:
    """Build a uniform-value mask split by cuts or a circular piston.

    Args:
        shape: (height, width) LCOS array shape.
        cut_x: Vertical divider column index.
        cut_y: Horizontal divider row index.
        enable_v_cut: Split left/right at cut_x.
        enable_h_cut: Split top/bottom at cut_y.
        phases: Mapping from region key (see region_keys) to uniform value
            (phase in radians, or drive level 0…255).
        enable_circular: Fill a disk and leave the rest as the outer value.
            Ignores the linear cuts.
        center_x: Disk center column. Row 0 is the top of the panel.
        center_y: Disk center row.
        radius: Disk radius in pixels. A pixel is inside when
            ``(col - center_x)^2 + (row - center_y)^2 <= radius^2``.

    Returns:
        float64 array with shape ``shape``.
    """
    height, width = shape
    cut_x = _clamp_cut(cut_x, width)
    cut_y = _clamp_cut(cut_y, height)

    phase = np.zeros(shape, dtype=np.float64)
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]

    keys = region_keys(enable_v_cut, enable_h_cut, enable_circular)
    for key in keys:
        if key not in phases:
            raise KeyError(f"Missing phase for region '{key}'. Expected keys: {keys}")

    if enable_circular:
        phase[:] = phases[REGION_OUTER]
        inside = (cols - int(center_x)) ** 2 + (rows - int(center_y)) ** 2 <= int(radius) ** 2
        phase[inside] = phases[REGION_INNER]
        return phase

    if REGION_ALL in keys:
        phase[:] = phases[REGION_ALL]
        return phase

    if enable_v_cut and not enable_h_cut:
        phase[:, :cut_x] = phases[REGION_LEFT]
        phase[:, cut_x:] = phases[REGION_RIGHT]
        return phase

    if not enable_v_cut and enable_h_cut:
        phase[:cut_y, :] = phases[REGION_TOP]
        phase[cut_y:, :] = phases[REGION_BOTTOM]
        return phase

    top = rows < cut_y
    left = cols < cut_x
    phase[top & left] = phases[REGION_TL]
    phase[top & ~left] = phases[REGION_TR]
    phase[~top & left] = phases[REGION_BL]
    phase[~top & ~left] = phases[REGION_BR]
    return phase
