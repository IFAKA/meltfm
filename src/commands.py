"""Command handlers — disk checks, metrics, recipe updates."""
import json
import logging
from pathlib import Path

from .config import RADIOS_DIR
from .manager import Radio
from .errors import format_error

logger = logging.getLogger(__name__)

METRICS_LOG = RADIOS_DIR / "metrics.jsonl"


def append_metric(entry: dict):
    """Append a single JSON line to metrics.jsonl for pipeline analysis."""
    try:
        RADIOS_DIR.mkdir(parents=True, exist_ok=True)
        with open(METRICS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def check_disk(radio: Radio) -> bool:
    free_mb = radio.disk_free_mb()
    if free_mb < 50:
        format_error(
            stage="disk_check",
            raw=f"Only {free_mb:.0f}MB free. Need at least 50MB.",
        )
        logger.warning("Low disk: %.0fMB free", free_mb)
        return False
    return True


def update_recipe(json_path: Path, updates: dict):
    """Merge updates into an existing recipe JSON file."""
    try:
        recipe = json.loads(json_path.read_text())
        recipe.update(updates)
        json_path.write_text(json.dumps(recipe, indent=2))
    except Exception:
        pass
