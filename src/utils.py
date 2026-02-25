"""Utility helpers salvaged from the old TUI."""
import time


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def fmt_countdown(deadline: float) -> str:
    """Format remaining time until deadline as mm:ss or h:mm:ss."""
    remaining = max(0, deadline - time.monotonic())
    total_s = int(remaining)
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def friendly_redirect(text: str) -> bool:
    non_music = [
        "weather", "what time", "what's the time", "date", "news",
        "sports", "calculate", "translate", "google", "wikipedia",
        "stock", "currency", "tell me a joke",
    ]
    t = text.lower()
    return any(w in t for w in non_music)
