"""Structured error logging — JSON to errors.log, no terminal formatting."""
import json
import logging
import sys
from datetime import datetime
from typing import Optional

from .config import ERRORS_LOG, OUTPUT_DIR, DEV_MODE

logger = logging.getLogger(__name__)

_FRIENDLY_MESSAGES = {
    "track_generation": "Track generation failed — retrying...",
    "llm_generate": "Couldn't generate params — retrying...",
    "disk_check": "Running low on disk space.",
    "preflight": "Startup check failed.",
}


def format_error(
    stage: str,
    user_msg: str = "",
    params: Optional[dict] = None,
    raw: str = "",
) -> str:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "stage": stage,
        "input": user_msg,
        "params": params,
        "error": raw,
        "python": sys.version.split()[0],
    }

    _append_to_log(entry)
    logger.error("Error at %s: %s", stage, raw)

    if DEV_MODE:
        return json.dumps(entry, indent=2)
    return _FRIENDLY_MESSAGES.get(stage, f"Something went wrong ({stage}).")


def _append_to_log(entry: dict):
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERRORS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
