"""Module 3 — Reaction Parser (keyword matching, no LLM)"""
import re
from typing import Optional


def parse_reaction(text: str) -> dict:
    """
    Returns:
    {
        "signal":     "liked" | "disliked" | "skipped" | None,
        "direction":  "tweak" | "shift" | "reset" | None,
        "modifiers":  ["more bass", "no vocals", ...],
        "mood":       "focus" | "energy" | "chill" | ... | None,
        "command":    "save" | "what" | "history" | "quit" |
                      "switch_radio" | "create_radio" | "list_radios" |
                      "delete_radio" | "share" | "open_folder" | "help" | None,
        "radio_name": str | None,
        "raw":        original text,
    }
    """
    t = text.strip().lower()
    result: dict = {
        "signal": None,
        "direction": None,
        "modifiers": [],
        "mood": None,
        "command": None,
        "radio_name": None,
        "raw": text,
    }

    if not t:
        return result

    # ── Quit (checked first, high priority) ───────────────────────────────────
    if re.search(r"\bquit\b|\bexit\b|\bbye\b", t):
        result["command"] = "quit"
        return result

    # ── Radio management (checked before general commands) ────────────────────

    # list radios
    if re.search(r"(what radios|list radios|my radios|show radios|\bradios\b)", t):
        result["command"] = "list_radios"
        return result

    # switch to X / go to X / change to X
    switch_match = re.search(
        r"(?:switch to|change to|go to|use)\s+(?:my\s+)?(?:the\s+)?(.+?)(?:\s+radio)?$", t
    )
    if switch_match:
        result["command"] = "switch_radio"
        result["radio_name"] = _clean_radio_name(switch_match.group(1))
        return result

    # create / new radio named X
    create_match = re.search(
        r"(?:create|new|start|make)\s+(?:a\s+)?(?:radio\s+(?:called\s+|named\s+)?|new\s+radio\s+(?:called\s+|named\s+)?)(.+?)(?:\s+radio)?$",
        t,
    )
    if create_match:
        result["command"] = "create_radio"
        result["radio_name"] = _clean_radio_name(create_match.group(1))
        return result

    # delete / remove radio X — require "radio" keyword to avoid collision
    # with modifiers like "remove vocals" or "kill the beat"
    delete_match = re.search(
        r"(?:delete|remove|kill)\s+(?:the\s+)?(?:my\s+)?(.+?)\s+radio$", t
    ) or re.search(
        r"(?:delete|remove|kill)\s+(?:the\s+)?(?:my\s+)?radio\s+(.+?)$", t
    )
    if delete_match:
        result["command"] = "delete_radio"
        result["radio_name"] = _clean_radio_name(delete_match.group(1))
        return result

    # ── Commands ──────────────────────────────────────────────────────────────

    if re.search(r"\bsave\b|\bkeep\b|\bfavorite\b|\bfav\b", t):
        result["command"] = "save"
        result["signal"] = "liked"  # saving implies liking

    if re.search(r"what is this|what's this|\binfo\b|\brecipe\b|\bparams\b|\bdetails\b", t):
        result["command"] = "what"

    if re.search(r"\bhistory\b|\blast played\b|\brecent\b|\btracks\b|\bsongs\b", t):
        result["command"] = "history"

    if re.search(r"\bshare\b", t):
        result["command"] = "share"

    if re.search(r"open folder|open in finder|\bfinder\b", t):
        result["command"] = "open_folder"

    if re.search(r"^\s*help\s*$", t):
        result["command"] = "help"

    # ── Sleep timer ────────────────────────────────────────────────────────
    if re.search(r"cancel\s+sleep", t):
        result["command"] = "cancel_sleep"
        return result

    sleep_match = re.match(r"^\s*sleep\s+off\s*$", t)
    if sleep_match:
        result["command"] = "cancel_sleep"
        return result

    sleep_dur = re.match(r"^\s*sleep\s+(\d+)\s*(h|m|min|mins|hours?)?\s*$", t)
    if sleep_dur:
        amount = int(sleep_dur.group(1))
        unit = (sleep_dur.group(2) or "m").lower()
        if unit.startswith("h"):
            result["timer_minutes"] = amount * 60
        else:
            result["timer_minutes"] = amount
        result["command"] = "sleep_timer"
        return result

    if re.match(r"^\s*sleep\s*$", t):
        result["command"] = "sleep_status"
        return result

    # ── Signal ────────────────────────────────────────────────────────────────

    if re.search(
        r"\blove\b|\bperfect\b|\bamazing\b|\bincredible\b|\bfire\b|\byes\b"
        r"|❤️|🔥|💯|\bgreat\b|\bawesome\b|\bbanging\b|\bbanger\b",
        t,
    ):
        result["signal"] = "liked"
    elif re.search(r"\bhate\b|\bterrible\b|\bawful\b|\bnope\b|\bdislike\b|\bno+\b", t):
        result["signal"] = "disliked"
    elif re.search(r"\bskip\b|\bnext\b|\bpass\b|\bnot this\b", t):
        result["signal"] = "skipped"
    elif re.search(r"\bgood\b|\blike\b|\bnice\b|\bcool\b|\bsolid\b|\bokay\b|\bok\b|\bfresh\b", t):
        result["signal"] = "liked"

    # ── Direction ─────────────────────────────────────────────────────────────

    if re.search(
        r"something (?:completely )?different|change it up|\breset\b|surprise me|totally different",
        t,
    ):
        result["direction"] = "reset"
    elif re.search(r"more like this|similar|\bkeep it\b|\bstay\b|same vibe", t):
        result["direction"] = "tweak"
    elif result["signal"] or result["modifiers"]:
        result["direction"] = "tweak"

    # ── Modifiers — capture "more/less/add/remove/no X" ──────────────────────

    modifier_patterns = [
        r"\bmore\s+([\w ]{2,25}?)(?=\s*(?:and|,|$))",
        r"\bless\s+([\w ]{2,25}?)(?=\s*(?:and|,|$))",
        r"\badd\s+([\w ]{2,25}?)(?=\s*(?:and|,|$))",
        r"\bremove\s+([\w ]{2,25}?)(?=\s*(?:and|,|$))",
        r"\bno\s+([\w ]{2,25}?)(?=\s*(?:and|,|$))",
        r"\b(faster|slower|louder|quieter|harder|softer|heavier|lighter|darker|brighter|rawer|smoother)\b",
    ]
    seen: set = set()
    for pat in modifier_patterns:
        for m in re.finditer(pat, t):
            mod = m.group(1).strip()
            if mod and len(mod) < 40 and mod not in seen:
                seen.add(mod)
                result["modifiers"].append(mod)

    # ── Mood ──────────────────────────────────────────────────────────────────

    mood_map = {
        "focus":  r"\bfocus\b|\bwork\b|\bconcentrate\b|\bstudy\b",
        "energy": r"\benergy\b|\bpump\b|\bworkout\b|\bhype\b|\bfull energy\b",
        "chill":  r"\bchill\b|\brelax\b|\bsoothe\b|\beasy\b|\bmellow\b",
        "sad":    r"\bsad\b|\bmelancholy\b|\bdepressing\b|\bheavy\b|\bemotion\b",
        "happy":  r"\bhappy\b|\bjoyful\b|\buplifting\b|\bupbeat\b",
        "sleep":  r"\bsleep\b|\bdream\b|\bnight\b",
        "party":  r"\bparty\b|\bdance\b|\bclub\b|\brave\b",
    }
    for mood, pat in mood_map.items():
        if re.search(pat, t):
            result["mood"] = mood
            break

    return result


def _clean_radio_name(raw: str) -> str:
    """Normalize a radio name to a filesystem-safe slug."""
    name = raw.strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "-", name)
    return name.strip("-")
