# Changelog

All notable changes to slm are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-09-23

### Added

- `LCOS.save()` / `LCOS.load()` persist caller H/V centers in a preamble JSON file. `LCOS` loads `config/modmux_config.json` when `path` is omitted.
- ModMux panel: Backup / Restore for the in-memory center pair, and Browse / Reload / Save / Save As for the center file.

### Changed

- `setCenters` clips each center to the panel after the Modelab correction (`x` in `0 … width-1`, `y` in `0 … height-1`).
- Placing an H or V tile crops the part that hangs off the LCOS frame instead of failing the slice assignment.

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
