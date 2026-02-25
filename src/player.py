"""Module 6 — Virtual Playback Tracker (browser plays the audio via PWA)"""
import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import Optional


def get_audio_duration(path: Path) -> float | None:
    """Get audio duration in seconds. Tries ffprobe first (accurate), falls back to afinfo."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, Exception):
        pass

    try:
        result = subprocess.run(
            ["afinfo", str(path)],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r"estimated duration:\s+([\d.]+)\s+sec", result.stdout)
        return float(match.group(1)) if match else None
    except Exception:
        return None


class Player:
    """Tracks playback state with asyncio timers. Audio is played by the browser."""

    def __init__(self):
        self._current: Optional[Path] = None
        self._source: Optional[Path] = None
        self._paused: bool = False
        self._volume: int = 80
        self._play_start: float = 0.0
        self._duration: Optional[float] = None
        self._paused_at: float = 0.0
        self._total_paused: float = 0.0
        self._seek_offset: float = 0.0
        self._done_event: asyncio.Event = asyncio.Event()
        self._watcher_task: Optional[asyncio.Task] = None

    # ── Playback ───────────────────────────────────────────────────────────────

    def play(self, path: Path, duration: Optional[float] = None):
        """Start virtual playback tracking. Browser plays the actual audio."""
        self.stop()
        self._done_event = asyncio.Event()
        self._current = path
        self._source = path
        self._paused = False
        self._play_start = time.monotonic()
        self._duration = duration
        self._paused_at = 0.0
        self._total_paused = 0.0
        self._seek_offset = 0.0
        self._start_watcher(duration)

    def stop(self):
        """Stop virtual playback."""
        self._cancel_watcher()
        self._done_event.set()
        self._current = None
        self._source = None
        self._paused = False
        self._play_start = 0.0
        self._duration = None
        self._paused_at = 0.0
        self._total_paused = 0.0
        self._seek_offset = 0.0

    def pause(self):
        """Pause virtual playback."""
        if self._current and not self._paused:
            self._paused = True
            self._paused_at = time.monotonic()
            self._cancel_watcher()

    def resume(self):
        """Resume virtual playback from paused position."""
        if self._current and self._paused:
            if self._paused_at > 0:
                self._total_paused += time.monotonic() - self._paused_at
                self._paused_at = 0.0
            self._paused = False
            if self._duration is not None:
                remaining = self._duration - self.elapsed
                if remaining > 0:
                    self._start_watcher(remaining)

    def toggle_pause(self):
        if self._paused:
            self.resume()
        else:
            self.pause()

    def is_playing(self) -> bool:
        if self._current is None or self._paused:
            return False
        # Watcher done means the timer fired — track ended naturally
        if self._watcher_task is None or self._watcher_task.done():
            return False
        return True

    def is_paused(self) -> bool:
        return self._paused and self._current is not None

    def wait_done(self):
        """Sync wait — no-op in async context."""
        pass

    async def wait_done_async(self):
        """Async wait — returns when the virtual track timer expires or stop() is called."""
        await self._done_event.wait()

    def replay(self):
        """Restart the current track from the beginning."""
        path = self._source or self._current
        if path and path.exists():
            saved_dur = self._duration
            self.play(path, duration=saved_dur)

    def seek(self, delta: float) -> float:
        """Update seek position. Browser performs the actual seek."""
        new_pos = max(0.0, self.elapsed + delta)
        if self._duration is not None:
            new_pos = min(new_pos, self._duration - 0.5)

        self._cancel_watcher()
        self._done_event = asyncio.Event()
        self._seek_offset = new_pos
        self._play_start = time.monotonic()
        self._paused_at = 0.0
        self._total_paused = 0.0

        if not self._paused and self._duration is not None:
            remaining = self._duration - new_pos
            if remaining > 0:
                self._start_watcher(remaining)

        return new_pos

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _start_watcher(self, duration: Optional[float]):
        """Start asyncio task that sets done_event after duration seconds."""
        done_ev = self._done_event
        sleep_for = duration if (duration and duration > 0) else 7200.0

        async def _watch():
            await asyncio.sleep(sleep_for)
            done_ev.set()

        self._watcher_task = asyncio.create_task(_watch())

    def _cancel_watcher(self):
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
        self._watcher_task = None

    @property
    def elapsed(self) -> float:
        """Seconds elapsed in current playback, accounting for pauses and seeks."""
        if self._play_start == 0:
            return 0.0
        if self._paused and self._paused_at > 0:
            raw = self._paused_at - self._play_start - self._total_paused
        else:
            raw = time.monotonic() - self._play_start - self._total_paused
        return self._seek_offset + raw

    @property
    def duration(self) -> Optional[float]:
        return self._duration

    @property
    def current_track(self) -> Optional[Path]:
        return self._source or self._current

    # ── Volume ─────────────────────────────────────────────────────────────────

    def volume_up(self, step: int = 10) -> int:
        self._volume = min(100, self._volume + step)
        return self._volume

    def volume_down(self, step: int = 10) -> int:
        self._volume = max(0, self._volume - step)
        return self._volume

    def set_volume(self, level: int) -> int:
        self._volume = max(0, min(100, level))
        return self._volume

    def _apply_volume(self):
        """No-op — volume is handled by the browser."""
        pass
