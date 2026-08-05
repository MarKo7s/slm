# pyLCOS — MODMUX dual-polarization LCOS driver

`pyLCOS` drives a dual-polarization LCOS SLM in **MODMUX** mode: independent H and V hologram tiles (typically 960×960) are composed with zernike correction, holographic patterns, and optional attenuation, placed on the full LCOS frame, aperture-filtered, converted to 8-bit drive levels, and displayed on the SLM monitor.

Mask state, centers, and apertures live in `ModMuxMask` (`maksSpecs.py`). The `LCOS` class handles display, composition, and the update pipeline.

Python package name: **`slm`** (GitHub: [MarKo7s/slm](https://github.com/MarKo7s/slm)).

---

## Installation

### From GitHub (tagged release)

```bash
pip install "slm[notebooks] @ git+https://github.com/MarKo7s/slm.git@v0.1.0"
```

Core only (no Jupyter / pyqtgraph extras):

```bash
pip install "slm @ git+https://github.com/MarKo7s/slm.git@v0.1.0"
```

### Local development (editable install)

```bash
git clone git@github.com:MarKo7s/slm.git
cd slm
pip install -e ".[notebooks]"
```

### Conda environment

```bash
conda create -n slm python=3.11 -y
conda activate slm
pip install -e ".[notebooks]"
```

`requirements.txt` remains available for legacy workflows; prefer `pip install -e ".[notebooks]"`.

---

## Quick start

`LCOS` subclasses a Qt fullscreen window. You **must run a Qt event loop** (`QApplication.exec()`) for the display to update.

```python
import sys
from PySide6.QtWidgets import QApplication
from slm import LCOS

app = QApplication(sys.argv)

slm = LCOS(screen=1, mask_size=(960, 960))

# ... change patterns, call slm.setmask(), etc.

app.exec()
```

Or import the driver module explicitly:

```python
from slm.pyLCOS import LCOS
from slm.ui.simpleholography.pistoning import PistoningWidget
from slm.ui.ModMux import ModMuxWidget
```

### Screen selection

| `screen` argument | Behavior |
|-------------------|----------|
| `int` (e.g. `1`) | Monitor index passed to Qt |
| `str` (e.g. `'meadowlark'`) | Look up resolution in `config/slm_specs.json`, match connected display |

```python
slm = LCOS(screen='meadowlark')
```

---

## Initialization

```python
LCOS(
    screen=1,
    channel=0,                    # RGB channel: 0=red, 1=green, 2=blue
    pixel_size=9.2e-6,            # SLM pixel pitch [m]
    aperture_diameter=7.5e-3,     # Circular aperture diameter [m]
    mask_size=(960, 960),         # H/V tile size [pixels]
    MODELAB_COMPATIBILITY=True,   # Apply Modelab center transforms
    **kwargs,
)
```

On construction, `LCOS` creates `self.ModMuxMask`, applies optional kwargs, allocates buffers, and calls `setmask()` once to display.

### Optional kwargs

| Kwarg | Type | Description |
|-------|------|-------------|
| `zernikeH` | array | H zernike phase tile, radians (−π…π) |
| `zernikeV` | array | V zernike phase tile |
| `patternH` | array | H hologram pattern, radians |
| `patternV` | array | V hologram pattern |
| `HmaskCenter` | `[x, y]` | H tile center in **user/Modelab** coordinates |
| `VmaskCenter` | `[x, y]` | V tile center in user/Modelab coordinates |
| `polEnabled` | `'H'`, `'V'`, `'HV'` | Which polarization(s) to display (default `'HV'`) |
| `zernikesEnabled` | `0` or `1` | Applied to **both** H and V at init |
| `patternEnabled` | `0` or `1` | Applied to **both** H and V at init |

Example with zernikes from complex fields:

```python
import numpy as np

slm = LCOS(
    screen=1,
    mask_size=(960, 960),
    zernikeH=np.angle(field_h),
    zernikeV=np.angle(field_v),
)
```

Both `HmaskCenter` and `VmaskCenter` must be provided together to override defaults at init.

---

## Mask state: `ModMuxMask`

All hologram content and MODMUX settings are on `slm.ModMuxMask`:

```python
mm = slm.ModMuxMask

# Per-polarization content (960×960 phase arrays, radians)
mm.H.zernike
mm.H.pattern
mm.V.zernike
mm.V.pattern

# Per-polarization enable flags (can differ between H and V)
mm.H.zernikes_enabled   # bool
mm.H.pattern_enabled
mm.V.zernikes_enabled
mm.V.pattern_enabled

# Attenuation (checkerboard-based)
mm.H.att_enabled        # bool
mm.H.att_weight         # dB
mm.V.att_enabled
mm.V.att_weight

# Display polarization selection
mm.pol                  # 'H', 'V', or 'HV'

# Centers and apertures — read-only from outside; see "Updating masks vs centers" below
mm.Hcenter              # display coords (after Modelab correction)
mm.Vcenter
mm.ap_H, mm.ap_V, mm.ap
```

---

## Updating masks vs centers

**Important:** tile content and tile placement follow different update paths.

| What you change | How to update | Then |
|-----------------|---------------|------|
| Pattern, zernike, flags, pol, attenuation | Edit `slm.ModMuxMask.H.*` / `.V.*` / `.pol` directly | `slm.setmask()` |
| **Centers** | **`slm.setCenters(centerH, centerV, ...)` only** | see below |

**Do not** assign centers yourself on `ModMuxMask` (e.g. do not set `mm.Hcenter` or call `mm.set_centers()` from application code). Always use `slm.setCenters()` so Modelab correction, apertures, and LCOS buffer cleanup run correctly.

### Change content only (patterns, zernikes, flags, …)

```python
slm.ModMuxMask.H.pattern = new_h_pattern
slm.ModMuxMask.V.pattern = new_v_pattern
slm.ModMuxMask.H.pattern_enabled = True
slm.ModMuxMask.pol = 'HV'
slm.setmask()
```

### Change centers **and** content together

Update centers first without displaying, then rebuild and display everything:

```python
slm.setCenters(centerH, centerV, display=False)
slm.ModMuxMask.H.pattern = new_h_pattern
slm.ModMuxMask.V.pattern = new_v_pattern
slm.setmask()
```

### Move masks on the SLM only (same Hmask/Vmask, new position)

Use `display=True` (default). This recalculates apertures, clears placement buffers, and redisplays **without** re-running `_addMasks()` — faster when only position changed:

```python
slm.setCenters(centerH, centerV)              # display=True by default
# equivalent to:
slm.setCenters(centerH, centerV, display=True)
```

Use this when you only want to shift the existing composed tiles on the LCOS frame.

---

## Main methods

### `setmask(Hpattern=0, Vpattern=0, pol=None)`

Rebuild H/V composed masks and push to the SLM. Call this after changing `ModMuxMask` **content** (patterns, zernikes, flags, pol, attenuation). For center changes, use `setCenters()` first.

```python
# Refresh current ModMuxMask state
slm.setmask()

# Update patterns and polarization in one call
slm.setmask(Hpattern=mode_h, Vpattern=mode_v, pol='HV')

# Check last update rate [Hz]
print(slm.refreshfreq)
```

- Pass `Hpattern=0` / `Vpattern=0` to leave that pattern unchanged.
- Phase on each tile should be in **radians**, roughly −π…π.

### `setCenters(centerH, centerV, display=True)`

**Required for any center change.** Accepts user/Modelab coordinates, applies corrections, recalculates apertures, and clears LCOS placement buffers.

| `display` | Behavior |
|-----------|----------|
| `True` (default) | Reposition on SLM using current `Hmask`/`Vmask` — no `_addMasks()` |
| `False` | Update centers/apertures only — call `setmask()` next to rebuild and display |

```python
# Move tiles only (fast)
slm.setCenters([480, 540], [1440, 540])

# New centers + new patterns
slm.setCenters(h, v, display=False)
slm.ModMuxMask.H.pattern = mode_h
slm.setmask()
```

Display coordinates after correction (read-only): `slm.ModMuxMask.Hcenter`, `slm.ModMuxMask.Vcenter`.

### `resetAttenuation()`

Disable attenuation on both polarizations. Call `setmask()` afterwards to refresh the display.

```python
slm.resetAttenuation()
slm.setmask()
```

### `LCOS_Display(arr_data, ch=None)`

Write a full-frame uint8 array directly to the SLM buffer (bypasses MODMUX pipeline).

```python
level = LCOS.phaseTolevel(phase_array)  # full LCOS size, radians → 0–255
slm.LCOS_Display(level)
```

### `LCOS_Clean(ch=None)`

Clear the screen. `ch=None` clears all channels.

```python
slm.LCOS_Clean()
```

---

## Processing pipeline

Each `setmask()` runs:

```
ModMuxMask H/V tiles
        ↓  _addMasks()
   Hmask, Vmask  (960×960 composed phase)
        ↓  _masksToLCOS()
   LCOS_array    (full frame, float phase)
        ↓  phaseTolevel()
   DisplayedLevelMask  (full frame, uint8 0–255)
        ↓  LCOS_Display()
   SLM monitor
```

Intermediate buffers on `LCOS`:

| Attribute | Size | Description |
|-----------|------|-------------|
| `Hmask`, `Vmask` | tile | Composed H/V phase before placement |
| `LCOS_array` | full LCOS | Combined phase on display |
| `DisplayedPhaseMask` | full LCOS | Copy of `LCOS_array` |
| `apertureApplied` | full LCOS | Aperture mask used in level conversion |
| `DisplayedLevelMask` | full LCOS | Final 0–255 drive levels |

---

## Typical workflows

### Holography with zernikes + modes

```python
slm.ModMuxMask.H.pattern = modes_h[0]
slm.ModMuxMask.V.pattern = modes_v[0]
slm.ModMuxMask.pol = 'HV'
slm.setmask()
```

### Single-pol display

```python
slm.setmask(pol='H')
```

### Loop over mode pairs

```python
for i in range(n_modes):
    slm.ModMuxMask.H.pattern = modes_h[i]
    slm.ModMuxMask.V.pattern = modes_v[n_modes - 1 - i]
    slm.setmask(pol='HV')
```

### Disable zernikes on one pol only

```python
slm.ModMuxMask.H.zernikes_enabled = True
slm.ModMuxMask.V.zernikes_enabled = False
slm.setmask()
```

---

## Phase and units

- **Tile phases** (`zernike`, `pattern`): radians, −π…π
- **Attenuation weight**: dB (`att_weight`); converted internally via `CalcAttPhase`
- **Centers**: `[x, y]` in SLM pixel coordinates; with `MODELAB_COMPATIBILITY=True`, pass Modelab coordinates and the driver applies the Y-flip and V x-offset
- **Levels**: `phaseTolevel` maps −π…π → 0…255 (`level ≈ 255·(φ+π)/(2π)`; level 0 → −π, ~128 → 0, 255 → π). Preview hover uses the inverse.

---

## Migration from old API

If you have code using `mask_specs`, update as follows:

| Old | New |
|-----|-----|
| `slm.mask_specs['H']['pattern']` | `slm.ModMuxMask.H.pattern` |
| `slm.mask_specs['H']['zernike']` | `slm.ModMuxMask.H.zernike` |
| `slm.mask_specs['H']['att_enabled']` | `slm.ModMuxMask.H.att_enabled` |
| `slm.mask_specs['H']['attWeight']` | `slm.ModMuxMask.H.att_weight` |
| `slm.mask_specs['H']['centers']` | `slm.setCenters(h, v)` — **always**; never assign centers on `ModMuxMask` directly |
| `slm.polEnabled` | `slm.ModMuxMask.pol` |
| `slm.zernikesEnabled` | `slm.ModMuxMask.H.zernikes_enabled` / `.V.zernikes_enabled` |
| `slm.patternEnabled` | `slm.ModMuxMask.H.pattern_enabled` / `.V.pattern_enabled` |
| `slm.Hcenter`, `slm.Vcenter` | `slm.ModMuxMask.Hcenter`, `.Vcenter` (read-only; set via `setCenters`) |
| `slm._defineCenters()`, `slm._calcApertures()` | `slm.setCenters(h, v)` |

---

## Examples

See `tests/pyLCOS_example.ipynb` for interactive demos (screen setup, phase sweeps, MODMUX patterns). Some notebook cells may still reference the old `mask_specs` API — use the migration table above when updating them.

---

## ModMux widget (`ui/ModMux`)

Embeddable Qt control panel for MODMUX routing, enable flags, attenuation, and mask centers. It takes an **already-constructed** `LCOS` instance (same pattern as `ui/simpleholography/pistoning`).

**The widget does not load patterns or zernikes** — the parent application or notebook owns mask content (`mm.H.pattern`, `mm.V.zernike`, etc.).

### Quick start

```python
from ui.ModMux import ModMuxWidget

slm = LCOS(screen=1, mask_size=(960, 960))
slm.ModMuxMask.H.pattern = mode_h
slm.setmask()

modmux_gui = ModMuxWidget(slm)
modmux_gui.show()
```

Requires a running Qt event loop (`QApplication.exec()`).

### Controls

| UI section | Maps to |
|------------|---------|
| **Mask H / Mask V** (checkable group) | Master on/off → `mm.pol` (`H`, `V`, `HV`; both off → `LCOS_Clean()`) |
| Pattern / Zernike | `mm.H/V.pattern_enabled`, `zernikes_enabled` |
| **Attenuation** (checkable group + dB spin) | `mm.H/V.att_enabled`, `att_weight` |
| **Center** (x, y in px) | Per-mask center → `slm.setCenters([h_x, h_y], [v_x, v_y])` |

### Sync API

Two directions — do not call both for the same update.

| Method | Direction | When to use |
|--------|-----------|-------------|
| `refresh_gui_state()` | SLM → GUI | After external `setmask()`, loading patterns, or at end of a blocked routine |
| `_apply_and_display()` | GUI → SLM | **Internal only** — runs automatically when the user changes a control |

| Helper | Purpose |
|--------|---------|
| `_update_preview()` | Refresh LCOS Panel Viewer from `screen_data` (HDMI buffer) only |
| Hover on preview | Shows pixel `level` (0–255) and `phase` (−π…π) via inverse of `phaseTolevel` |
| `_update_info_label(text)` | Set bottom status bar (e.g. mask generation timing) |
| `_disable_user_interface()` / `_enable_user_interface()` | Lock controls during automated routines |

### Typical patterns

**After changing the SLM from code:**

```python
slm.setmask()
modmux_gui.refresh_gui_state()
modmux_gui._update_info_label(f"Mask gen: {slm.refreshfreq:.1f} Hz")
```

**Automated routine (preview follows HDMI, controls sync at end):**

```python
modmux_gui._disable_user_interface()
try:
    for step in routine:
        slm.setmask()
        modmux_gui._update_preview()
finally:
    modmux_gui.refresh_gui_state()
    modmux_gui._enable_user_interface()
```

### Files

| File | Role |
|------|------|
| `ui/ModMux/widget.py` | `ModMuxWidget` |
| `ui/ModMux/pol_mask_panel.py` | Per-pol mask controls (incl. center x/y px) |
| `ui/ModMux/centers_panel.py` | User ↔ display center coordinate helpers |
| `ui/ModMux/preview.py` | LCOS HDMI preview (pyqtgraph) |

---

## Related files

| File | Role |
|------|------|
| `pyLCOS.py` | `LCOS` driver — display, composition, pipeline |
| `maksSpecs.py` | `ModMuxMask`, `HologramMask`, `Aperture` |
| `hdmi/fullscreenqt.py` | Qt fullscreen display base class |
| `config/slm_specs.json` | Named SLM resolutions for auto-detection |
| `utilities/displays.py` | Monitor discovery |
| `ui/ModMux/` | `ModMuxWidget` — MODMUX control panel |
| `ui/simpleholography/pistoning/` | `PistoningWidget` — quadrant pistoning tool |

---

## Notes

- **Centers:** always use `slm.setCenters()`. Edit everything else on `slm.ModMuxMask`, then `setmask()`.
- `save()`, `restore()`, and `load()` on `LCOS` are not implemented yet.
- `setmask()` must be called after `resetAttenuation()` or direct `ModMuxMask` content edits to refresh the SLM.
- For low-level full-frame control without MODMUX, use `LCOS_Display` + `phaseTolevel` directly.

---

## Versioning

The package version is defined in **one place only**: `pyproject.toml` → `[project].version`.

Do **not** edit `__init__.py` on each release. `slm.__version__` is read from pip metadata after install (`importlib.metadata`).

```bash
pip show slm
python -c "import slm; print(slm.__version__)"
```

Use [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

## Releasing a new version

1. Add an entry for the new version at the top of `CHANGELOG.md`.
2. Bump `version` in `pyproject.toml`.
3. Commit all changes (including the changelog).
4. Run the release script from the repo root:

```bash
python scripts/release.py --from-changelog
```

The script reads the version from `pyproject.toml`, pushes `main`, creates annotated git tag `vX.Y.Z`, and pushes the tag. With `--from-changelog`, the tag message is taken from the matching `CHANGELOG.md` section.

Install a released tag:

```bash
pip install "slm[notebooks] @ git+https://github.com/MarKo7s/slm.git@vX.Y.Z"
```

Dry run:

```bash
python scripts/release.py --from-changelog --dry-run
```

Optional GitHub Release:

```bash
gh release create vX.Y.Z --title "slm X.Y.Z" --notes-file CHANGELOG.md
```

**Requirements before release:** clean working tree; tag `vX.Y.Z` must not already exist on GitHub.
