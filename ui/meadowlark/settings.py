"""JSON persistence for Meadowlark widget settings."""

import json
from pathlib import Path

SLM_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = SLM_ROOT / "config" / "meadowlark_widget.json"
LUT_DIR = SLM_ROOT / "config" / "LUT Files" / "meadowlark"


def load_settings(path: Path = DEFAULT_SETTINGS_PATH) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_settings(data: dict, path: Path = DEFAULT_SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
