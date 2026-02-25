"""Module 6 — Audio Playback via afplay"""
import asyncio
import os
import re
import signal
import subprocess
import tempfile
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
        self._source: Optional[Path] = None
        self._paused: bool = False
        self._volume: int = self._get_system_volume()
        self._play_start: float = 0.0
        self._duration: Optional[float] = None
        self._paused_at: float = 0.0
        self._total_paused: float = 0.0
        self._seek_offset: float = 0.0
        self._temp_file: Optional[Path] = None
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
        self._source = path
        self._paused = False
        self._play_start = time.monotonic()
        self._duration = duration
        self._paused_at = 0.0
        self._total_paused = 0.0
        self._seek_offset = 0.0
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
        self._source = None
        self._paused = False
        self._play_start = 0.0
        self._duration = None
        self._paused_at = 0.0
        self._total_paused = 0.0
        self._seek_offset = 0.0
        self._cleanup_temp()

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
        path = self._source or self._current
        if path and path.exists():
            saved_dur = self._duration
            self.play(path, duration=saved_dur)

    def seek(self, delta: float) -> float:
        """Seek forward/backward by delta seconds. Returns new position.

        Uses ffmpeg to create a trimmed temp file from the target position,
        since afplay has no native seek support.
        """
        source = self._source
        if not source or not source.exists():
            return 0.0

        new_pos = max(0.0, self.elapsed + delta)
        if self._duration:
            new_pos = min(new_pos, self._duration - 0.5)
        if new_pos < 0:
            new_pos = 0.0

        self._cleanup_temp()

        tmp = Path(tempfile.mktemp(suffix=".wav"))
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error",
                 "-ss", str(new_pos), "-i", str(source),
                 "-f", "wav", str(tmp)],
                capture_output=True, timeout=15,
            )
            if not tmp.exists() or tmp.stat().st_size < 100:
                tmp.unlink(missing_ok=True)
                return self.elapsed
        except Exception:
            tmp.unlink(missing_ok=True)
            return self.elapsed

        self._temp_file = tmp
        saved_duration = self._duration
        was_paused = self._paused

        # Kill current afplay without full stop() (preserve _source)
        if self._proc and self._proc.poll() is None:
            if self._paused:
                try:
                    os.kill(self._proc.pid, signal.SIGCONT)
                except ProcessLookupError:
                    pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()

        # Start playing from temp file
        self._proc = subprocess.Popen(
            ["afplay", str(tmp)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._done_event = asyncio.Event()
        self._current = tmp
        self._source = source
        self._duration = saved_duration
        self._paused = False
        self._play_start = time.monotonic()
        self._paused_at = 0.0
        self._total_paused = 0.0
        self._seek_offset = new_pos

        # Watcher for new process
        proc = self._proc
        done_ev = self._done_event

        async def _watch():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, proc.wait)
            done_ev.set()

        self._watcher_task = asyncio.create_task(_watch())

        # If was paused, pause again at new position
        if was_paused:
            time.sleep(0.05)
            self.pause()

        return new_pos

    def _cleanup_temp(self):
        """Remove any temporary seek file."""
        if self._temp_file:
            try:
                self._temp_file.unlink(missing_ok=True)
            except OSError:
                pass
            self._temp_file = None

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
