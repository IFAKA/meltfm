"""Module 6 — Audio Playback via afplay"""
import asyncio
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional


def get_audio_duration(path: Path) -> float | None:
    """Get audio duration in seconds using macOS afinfo. Returns None on failure."""
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
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._current: Optional[Path] = None
        self._paused: bool = False
        self._volume: int = self._get_system_volume()
        self._play_start: float = 0.0
        self._duration: Optional[float] = None
        self._paused_at: float = 0.0
        self._total_paused: float = 0.0
        self._done_event: asyncio.Event = asyncio.Event()
        self._watcher_task: Optional[asyncio.Task] = None

    # ── Playback ───────────────────────────────────────────────────────────────

    def play(self, path: Path, duration: Optional[float] = None):
        """Start afplay for the given file. Stops any current playback first."""
        self.stop()
        self._proc = subprocess.Popen(
            ["afplay", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._done_event = asyncio.Event()
        self._current = path
        self._paused = False
        self._play_start = time.monotonic()
        self._duration = duration
        self._paused_at = 0.0
        self._total_paused = 0.0
        # Reactive watcher — waits for afplay to exit, then sets the event
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
        proc = self._proc
        done_ev = self._done_event

        async def _watch():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, proc.wait)
            done_ev.set()

        self._watcher_task = asyncio.create_task(_watch())

    def stop(self):
        """Terminate playback and wait for process to clean up."""
        if self._proc and self._proc.poll() is None:
            if self._paused:
                # Must resume before terminate — SIGSTOP blocks SIGTERM
                try:
                    os.kill(self._proc.pid, signal.SIGCONT)
                except ProcessLookupError:
                    pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._done_event.set()
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
        self._proc = None
        self._current = None
        self._paused = False
        self._play_start = 0.0
        self._duration = None
        self._paused_at = 0.0
        self._total_paused = 0.0

    def pause(self):
        """Suspend afplay in place (SIGSTOP). Position is preserved."""
        if self._proc and self._proc.poll() is None and not self._paused:
            try:
                os.kill(self._proc.pid, signal.SIGSTOP)
                self._paused = True
                self._paused_at = time.monotonic()
            except ProcessLookupError:
                pass

    def resume(self):
        """Resume a paused track exactly where it left off (SIGCONT)."""
        if self._proc and self._paused:
            try:
                os.kill(self._proc.pid, signal.SIGCONT)
                if self._paused_at > 0:
                    self._total_paused += time.monotonic() - self._paused_at
                    self._paused_at = 0.0
                self._paused = False
            except ProcessLookupError:
                self._paused = False

    def toggle_pause(self):
        """Pause if playing, resume if paused."""
        if self._paused:
            self.resume()
        else:
            self.pause()

    def is_playing(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def is_paused(self) -> bool:
        return self._paused

    def wait_done(self):
        """Block until current track finishes naturally."""
        if self._proc:
            self._proc.wait()

    async def wait_done_async(self):
        """Async wait — returns immediately when the track ends (no polling)."""
        await self._done_event.wait()

    def replay(self):
        """Restart the current track from the beginning (gap-filler)."""
        if self._current and self._current.exists():
            saved_dur = self._duration
            self.play(self._current, duration=saved_dur)

    @property
    def elapsed(self) -> float:
        """Seconds elapsed in current playback, accounting for pauses."""
        if self._play_start == 0:
            return 0.0
        if self._paused and self._paused_at > 0:
            return self._paused_at - self._play_start - self._total_paused
        return time.monotonic() - self._play_start - self._total_paused

    @property
    def duration(self) -> Optional[float]:
        return self._duration

    @property
    def current_track(self) -> Optional[Path]:
        return self._current

    # ── Volume ─────────────────────────────────────────────────────────────────

    def volume_up(self, step: int = 10) -> int:
        self._volume = min(100, self._volume + step)
        self._set_system_volume(self._volume)
        return self._volume

    def volume_down(self, step: int = 10) -> int:
        self._volume = max(0, self._volume - step)
        self._set_system_volume(self._volume)
        return self._volume

    def set_volume(self, level: int) -> int:
        self._volume = max(0, min(100, level))
        self._set_system_volume(self._volume)
        return self._volume

    @staticmethod
    def _get_system_volume() -> int:
        try:
            result = subprocess.run(
                ["osascript", "-e", "output volume of (get volume settings)"],
                capture_output=True, text=True, timeout=2,
            )
            return int(result.stdout.strip())
        except Exception:
            return 50

    @staticmethod
    def _set_system_volume(level: int):
        try:
            subprocess.run(
                ["osascript", "-e", f"set volume output volume {level}"],
                check=False, timeout=2,
            )
        except Exception:
            pass
