# Changelog

All notable changes to slm are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-09-16

### Added

- Meadowlark SDK/widget: store the session LUT into controller flash, last-loaded vs in-flash LUT status, and pre/post ramp-slope controls.
- Example notebook cell for the standalone Meadowlark SDK panel.
- Conda install guidance: Python + pip only, then install `slm` with pip so PySide6 is not mixed with conda Qt.
- README screenshot of the ModMux control panel.

### Fixed

- ModMux and pistoning previews collapsing the leftover ImageView ROI strip and fitting the full LCOS frame on resize.
- Packaged `slm.ui` imports in ModMux extra functionalities.

## [0.1.0] - 2026-08-05

### Added

- First packaged release of the MODMUX LCOS driver (`pyLCOS` / `ModMuxMask`).
- Qt widgets: ModMux control panel, Meadowlark settings, simple holography pistoning (phase and level modes).
- ModeLab pip/git-tag packaging (`pyproject.toml`, `CHANGELOG.md`, `scripts/release.py`).
