"""Module 2 — Radio Manager + Taste Profile"""
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import (
    RADIOS_DIR,
    MAX_LIKED_HISTORY,
    MAX_DISLIKED_HISTORY,
    MAX_SKIPPED_HISTORY,
)

_CURRENT_FILE = RADIOS_DIR / ".current"

_EMPTY_TASTE = {
    "liked": [],
    "disliked": [],
    "skipped": [],
    "explicit_notes": [],
    "session_direction": None,
    "generation_count": 0,
}


class Radio:
    def __init__(self, name: str):
        self.name = name
        self.path = RADIOS_DIR / name
        self.tracks_dir = self.path / "tracks"
        self.favorites_dir = self.path / "favorites"
        self._taste_path = self.path / "taste.json"
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.tracks_dir.mkdir(parents=True, exist_ok=True)
        self.favorites_dir.mkdir(parents=True, exist_ok=True)

    # ── Taste profile ──────────────────────────────────────────────────────────

    def load_taste(self) -> dict:
        if not self._taste_path.exists():
            return dict(_EMPTY_TASTE)
        try:
            return json.loads(self._taste_path.read_text())
        except (json.JSONDecodeError, OSError):
            return dict(_EMPTY_TASTE)

    def save_taste(self, profile: dict):
        """Atomic write — write to tmp then replace."""
        tmp = self._taste_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile, indent=2))
        tmp.replace(self._taste_path)

    def is_first_run(self) -> bool:
        return not self._taste_path.exists()

    def reset_taste(self):
        """Wipe taste profile completely — fresh start."""
        self.save_taste(dict(_EMPTY_TASTE))

    def full_reset(self):
        """Wipe taste profile + all tracks + favorites."""
        self.reset_taste()
        shutil.rmtree(self.tracks_dir, ignore_errors=True)
        shutil.rmtree(self.favorites_dir, ignore_errors=True)
        self._ensure_dirs()

    def add_reaction(self, params: dict, signal: Optional[str]):
        """signal: 'liked' | 'disliked' | 'skipped' | None (neutral)"""
        if signal is None:
            return
        taste = self.load_taste()
        entry = {
            "tags": params.get("tags", ""),
            "bpm": params.get("bpm"),
            "key_scale": params.get("key_scale", ""),
            "time_signature": params.get("time_signature"),
            "instrumental": params.get("instrumental"),
            "rationale": params.get("rationale", ""),
            "reacted_at": datetime.now().isoformat(),
        }
        if signal == "liked":
            taste["liked"].append(entry)
            taste["liked"] = taste["liked"][-MAX_LIKED_HISTORY:]
        elif signal == "disliked":
            taste["disliked"].append(entry)
            taste["disliked"] = taste["disliked"][-MAX_DISLIKED_HISTORY:]
        elif signal == "skipped":
            taste["skipped"].append(entry)
            taste["skipped"] = taste["skipped"][-MAX_SKIPPED_HISTORY:]

        self.save_taste(taste)

    def add_note(self, note: str):
        taste = self.load_taste()
        if note not in taste["explicit_notes"]:
            taste["explicit_notes"].append(note)
        self.save_taste(taste)

    def set_direction(self, direction: str):
        taste = self.load_taste()
        taste["session_direction"] = direction
        self.save_taste(taste)

    def increment_count(self):
        taste = self.load_taste()
        taste["generation_count"] = taste.get("generation_count", 0) + 1
        self.save_taste(taste)

    def to_llm_context(self) -> str:
        taste = self.load_taste()
        lines = [f"Radio: {self.name}"]

        if taste["explicit_notes"]:
            lines.append("User preferences:")
            for note in taste["explicit_notes"]:
                lines.append(f"  - {note}")

        if taste["liked"]:
            lines.append(f"Liked tracks (last {len(taste['liked'])}):")
            for t in taste["liked"][-5:]:
                lines.append(f"  - {t['tags']} | {t['bpm']} BPM | {t['key_scale']}")

        if taste["disliked"]:
            lines.append("Disliked tracks (avoid these patterns):")
            for t in taste["disliked"][-3:]:
                lines.append(f"  - {t['tags']}")

        if taste["session_direction"]:
            lines.append(f"Current direction: {taste['session_direction']}")

        gen_count = taste.get("generation_count", 0)
        lines.append(f"Tracks generated so far: {gen_count}")

        return "\n".join(lines)

    # ── Track management ───────────────────────────────────────────────────────

    def next_track_id(self) -> str:
        taste = self.load_taste()
        n = taste.get("generation_count", 0) + 1
        return f"{n:03d}"

    def save_track(self, audio_bytes: bytes, params: dict) -> tuple[Path, Path]:
        """Save .mp3 and .json recipe. Caller is responsible for increment_count().
        Returns (mp3_path, json_path)."""
        track_id = params.get("id", self.next_track_id())
        slug = _slugify(params.get("tags", "track"))[:40]
        base = f"{track_id}-{slug}"

        mp3_path = self.tracks_dir / f"{base}.mp3"
        json_path = self.tracks_dir / f"{base}.json"

        mp3_path.write_bytes(audio_bytes)
        json_path.write_text(json.dumps(params, indent=2))

        return mp3_path, json_path

    def mark_favorite(self, mp3_path: Path):
        """Copy track + recipe to favorites/."""
        dest_mp3 = self.favorites_dir / mp3_path.name
        dest_json = self.favorites_dir / mp3_path.with_suffix(".json").name

        src_json = mp3_path.with_suffix(".json")

        shutil.copy2(mp3_path, dest_mp3)
        if src_json.exists():
            shutil.copy2(src_json, dest_json)

        return dest_mp3

    def get_tracks(self, filter_by: str = "all") -> list[Path]:
        """filter_by: 'all' | 'favorites'"""
        if filter_by == "favorites":
            return sorted(self.favorites_dir.glob("*.mp3"))
        return sorted(self.tracks_dir.glob("*.mp3"))

    def get_track_count(self) -> int:
        return len(list(self.tracks_dir.glob("*.mp3")))

    def get_last_played_fmt(self) -> str:
        """Return human-readable 'last played' string, e.g. '2h ago' or 'never'."""
        tracks = sorted(self.tracks_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        if not tracks:
            return "never"
        mtime = tracks[-1].stat().st_mtime
        delta = time.time() - mtime
        if delta < 60:
            return "just now"
        elif delta < 3600:
            return f"{int(delta // 60)}m ago"
        elif delta < 86400:
            return f"{int(delta // 3600)}h ago"
        elif delta < 86400 * 7:
            return f"{int(delta // 86400)}d ago"
        else:
            return datetime.fromtimestamp(mtime).strftime("%b %d")

    def get_history(self, limit: int = 10) -> list[dict]:
        """Return last N tracks with their recipe data."""
        mp3s = sorted(self.tracks_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
        result = []
        for mp3 in mp3s[-limit:]:
            recipe_path = mp3.with_suffix(".json")
            if recipe_path.exists():
                try:
                    recipe = json.loads(recipe_path.read_text())
                    recipe["_mp3"] = str(mp3)
                    result.append(recipe)
                except json.JSONDecodeError:
                    pass
        return list(reversed(result))

    def disk_free_mb(self) -> float:
        stat = shutil.disk_usage(self.tracks_dir)
        return stat.free / (1024 * 1024)


class RadioManager:
    def __init__(self):
        RADIOS_DIR.mkdir(parents=True, exist_ok=True)

    def list_radios(self) -> list[str]:
        return sorted(
            d.name for d in RADIOS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def get_radio(self, name: str) -> Radio:
        return Radio(name)

    def current_radio(self) -> Radio:
        if _CURRENT_FILE.exists():
            name = _CURRENT_FILE.read_text().strip()
            if name and (RADIOS_DIR / name).is_dir():
                return Radio(name)
        # Default to "default"
        radio = Radio("default")
        self._set_current(radio.name)
        return radio

    def switch_to(self, name: str) -> Radio:
        radio = Radio(name)  # creates dirs if new
        self._set_current(name)
        return radio

    def delete(self, name: str):
        path = RADIOS_DIR / name
        if path.exists():
            shutil.rmtree(path)
        # If deleted was current, reset to default
        if _CURRENT_FILE.exists() and _CURRENT_FILE.read_text().strip() == name:
            _CURRENT_FILE.write_text("default")

    def _set_current(self, name: str):
        _CURRENT_FILE.write_text(name)


def _slugify(text: str) -> str:
    """Convert tags string to a filename-safe slug."""
    import re
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s,]+", "-", slug)
    slug = slug.strip("-")
    return slug
