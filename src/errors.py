"""Module 7 — AI-Pasteable Error Block"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import ERRORS_LOG, OUTPUT_DIR, DEV_MODE

_FRIENDLY_MESSAGES = {
    "track_generation": "Oops, that track failed — trying again...",
    "llm_generate": "Couldn't come up with params — retrying...",
    "disk_check": "Running low on disk space.",
    "preflight": "Startup check failed — see above for details.",
}


def format_error(
    stage: str,
    user_msg: str = "",
    params: Optional[dict] = None,
    raw: str = "",
) -> str:
    params_str = json.dumps(params, indent=2) if params else "N/A"
    py_version = sys.version.replace("\n", " ")
    block = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ERROR  stage: {stage}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 System:   macOS · M4 Pro · Python {py_version}
 Stage:    {stage}
 Input:    "{user_msg}"
 Params:   {params_str}
 Error:    {raw}
 Fix ask:  The meltfm radio crashed at "{stage}".
           Reproduce with: uv run python radio.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    _append_to_log(block)

    if DEV_MODE:
        return block
    return _FRIENDLY_MESSAGES.get(stage, f"Something went wrong ({stage}). Check errors.log for details.")


def _append_to_log(block: str):
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERRORS_LOG, "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}]\n{block}\n")
    except OSError:
        pass  # Don't crash the error handler
