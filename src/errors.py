"""Module 7 — AI-Pasteable Error Block"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import ERRORS_LOG, OUTPUT_DIR


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
 Fix ask:  The music-generator radio crashed at "{stage}".
           Reproduce with: uv run python radio.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

    _append_to_log(block)
    return block


def _append_to_log(block: str):
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERRORS_LOG, "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}]\n{block}\n")
    except OSError:
        pass  # Don't crash the error handler
