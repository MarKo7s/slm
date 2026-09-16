#!/usr/bin/env python3
"""Grab a live Fake/sim GUI screenshot for README (docs/images/gui.png).

Uses a real ModMuxWidget on an in-memory LCOS (no SLM monitor, no SDK).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# This script lives in `scripts/`; repo root is its parent directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DEFAULT = REPO_ROOT / "docs" / "images" / "gui.png"

_SIM_WIDTH = 1920
_SIM_HEIGHT = 1152
_MASK = 960


def _fake_fullscreen_init(self, screen=0, parent=None):
    """In-memory HDMI buffer; do not map a real monitor."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QWidget

    QWidget.__init__(self, parent)
    self.qimg = QImage(_SIM_WIDTH, _SIM_HEIGHT, QImage.Format_RGB888)
    self.qimg.fill(0)
    self.data = self.getBuffer()
    self.rect = QRect(0, 0, _SIM_WIDTH, _SIM_HEIGHT)


def _sim_phase_tiles():
    import numpy as np

    yy, xx = np.mgrid[0:_MASK, 0:_MASK].astype(np.float64)
    xn = xx / (_MASK - 1) * 2.0 - 1.0
    yn = yy / (_MASK - 1) * 2.0 - 1.0
    h_pattern = np.pi * xn
    v_pattern = np.pi * (xn**2 + yn**2 - 0.5)
    return h_pattern, v_pattern


def build_window():
    """Return (window, teardown) where teardown() stops/closes device + window."""
    from slm.hdmi.fullscreenqt import FullscreenWindow
    from slm.pyLCOS import LCOS
    from slm.ui.ModMux import ModMuxWidget

    original_init = FullscreenWindow.__init__
    original_update = FullscreenWindow.update
    FullscreenWindow.__init__ = _fake_fullscreen_init
    FullscreenWindow.update = lambda self: None

    slm = LCOS(screen=0, mask_size=(_MASK, _MASK), MODELAB_COMPATIBILITY=True)
    slm.alias = "meadowlark"
    h_pattern, v_pattern = _sim_phase_tiles()
    slm.ModMuxMask.H.pattern = h_pattern
    slm.ModMuxMask.V.pattern = v_pattern
    slm.setmask()

    gui = ModMuxWidget(slm)
    gui.show()

    def teardown() -> None:
        gui.close()
        slm.close()
        FullscreenWindow.__init__ = original_init
        FullscreenWindow.update = original_update

    return gui, teardown


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture GUI screenshot for README.")
    parser.add_argument("-o", "--output", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--wait-ms", type=int, default=4000)
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="Use QT_QPA_PLATFORM=offscreen (may blank pyqtgraph on Windows).",
    )
    args = parser.parse_args()

    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    import pyqtgraph as pg
    from PySide6.QtWidgets import QApplication

    pg.setConfigOptions(useOpenGL=False, antialias=True)

    app = QApplication.instance() or QApplication(sys.argv)
    window, teardown = build_window()
    window.resize(1100, 720)
    window.show()
    window.raise_()
    window.activateWindow()

    deadline = time.perf_counter() + max(args.wait_ms, 200) / 1000.0
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pix = window.grab()
    if pix.isNull() or pix.width() < 10:
        teardown()
        raise SystemExit("grab() returned an empty pixmap")
    if not pix.save(str(args.output), "PNG"):
        teardown()
        raise SystemExit(f"Failed to write {args.output}")

    teardown()
    print(f"Wrote {args.output}")
    app.quit()


if __name__ == "__main__":
    main()
