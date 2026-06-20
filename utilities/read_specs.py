import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
slm_specs_path = _REPO_ROOT / "config" / "slm_specs.json"

def load_slm_specs(config_path: Path | None = None) -> dict[str, Any]:
    """Load SLM specs from config/slm_specs.json and return as a dict."""
    if config_path is None:
        config_path = slm_specs_path
    with config_path.open(encoding="utf-8") as f:
        return json.load(f)


if __name__ == '__main__':
    print(load_slm_specs())