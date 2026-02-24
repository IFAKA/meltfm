"""Module 6 — Audio Playback via afplay"""
import os
import signal
import subprocess
from pathlib import Path
from typing import Optional


class Player:
    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._current: Optional[Path] = None
        self._paused: bool = False
        self._volume: int = self._get_system_volume()

    # ── Playback ───────────────────────────────────────────────────────────────

    def play(self, path: Path):
        """Start afplay for the given file. Stops any current playback first."""
        self.stop()
        self._proc = subprocess.Popen(
            ["afplay", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._current = path
        self._paused = False

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
        self._proc = None
        self._current = None
        self._paused = False

    def pause(self):
        """Suspend afplay in place (SIGSTOP). Position is preserved."""
        if self._proc and self._proc.poll() is None and not self._paused:
            try:
                os.kill(self._proc.pid, signal.SIGSTOP)
                self._paused = True
            except ProcessLookupError:
                pass

    def resume(self):
        """Resume a paused track exactly where it left off (SIGCONT)."""
        if self._proc and self._paused:
            try:
                os.kill(self._proc.pid, signal.SIGCONT)
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
