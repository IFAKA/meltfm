"""Core radio engine — pure async loop, no I/O.

Receives commands via methods, broadcasts state via RadioState.
"""
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DEFAULT_DURATION, RADIOS_DIR
from .manager import Radio, RadioManager, _slugify
from .reactions import parse_reaction
from .llm import generate_params, params_are_too_similar
from .acestep import generate_track
from .player import Player, get_audio_duration
from .errors import format_error
from .utils import friendly_redirect
from .commands import check_disk, update_recipe, append_metric
from .acestep import check_server as acestep_check_server, ensure_model as acestep_ensure_model
from .alignment import align_lyrics

logger = logging.getLogger(__name__)


class RadioEngine:
    def __init__(self, state):
        """state: RadioState instance for broadcasting to WebSocket clients."""
        self.state = state
        self.player = Player()
        self.manager = RadioManager()
        self.radio: Optional[Radio] = None

        self._running = False
        self._last_params: Optional[dict] = None
        self._queued_track: Optional[Path] = None
        self._queued_params: Optional[dict] = None
        self._recent_params: list[dict] = []
        self._last_reaction: str = ""
        self._gen_task: Optional[asyncio.Task] = None
        self._next_path: Optional[Path] = None
        self._interrupt_when_ready = False
        self._sleep_deadline: float | None = None

        # Pending reactions accumulated between generations
        self._pending_modifiers: list[str] = []
        self._pending_reaction: Optional[dict] = None
        self._reaction_event = asyncio.Event()

        # Browser fires track_ended when audio loops — drives auto-advance
        self._track_ended_event: asyncio.Event = asyncio.Event()

        # Track tick task
        self._tick_task: Optional[asyncio.Task] = None
        self._model_ensured = False

    # ── Public API (called from WebSocket handlers) ──────────────────────────

    async def submit_reaction(self, text: str):
        """Process a natural language reaction from the UI."""
        if friendly_redirect(text):
            await self.state.broadcast("toast", {"message": "I only speak music — try 'more bass' or 'something darker'"})
            return

        reaction = parse_reaction(text)
        await self.state.broadcast("reaction_feedback", reaction)

        # Accumulate modifiers
        if reaction.get("modifiers"):
            self._pending_modifiers.extend(reaction["modifiers"])

        self._pending_reaction = reaction
        self._last_reaction = text
        self._reaction_event.set()

        # Handle queue invalidation based on reaction type
        wants_change = bool(
            reaction.get("modifiers")
            or reaction.get("mood")
            or reaction.get("direction") == "reset"
            or reaction.get("signal") in ("disliked", "skipped")
            or (not reaction.get("command") and not reaction.get("signal") and text)
        )

        if wants_change:
            await self._discard_and_regenerate(reaction, text)

    async def pause(self):
        if self.player.is_playing():
            self.player.pause()
            await self._broadcast_playback_state()

    async def resume(self):
        if self.player.is_paused():
            self.player.resume()
            await self._broadcast_playback_state()

    async def toggle_pause(self):
        if self.player.is_paused():
            await self.resume()
        elif self.player.is_playing():
            await self.pause()

    async def skip(self):
        """Skip to the next track — never regenerates, always advances.

        Ready: play immediately.
        Still generating: stop current, play as soon as generation finishes.
        """
        await self.state.broadcast("reaction_feedback", {"signal": "skipped"})

        # Record current track as skipped
        if self._queued_params:
            self.radio.add_reaction(self._queued_params, "skipped")
            if self._queued_track:
                jpath = self._queued_track.with_suffix(".json")
                if jpath.exists():
                    update_recipe(jpath, {"reaction": "skipped"})

        self.player.stop()
        await self._broadcast_playback_state()

        if self._gen_task and self._gen_task.done() and self._next_path and self._next_path.exists():
            # Next track ready — trigger _auto_advance to play it now
            self._track_ended_event.set()
        elif self._gen_task and not self._gen_task.done():
            # Still generating — play as soon as it finishes (reuse dislike interrupt path)
            self._interrupt_when_ready = True

    async def save(self):
        """Save current track to favorites."""
        if self._queued_track and self._queued_track.exists():
            dest = self.radio.mark_favorite(self._queued_track)
            jpath = self._queued_track.with_suffix(".json")
            if jpath.exists():
                update_recipe(jpath, {"reaction": "liked", "favorited": True})
            if self._queued_params:
                self.radio.add_reaction(self._queued_params, "liked")
            await self.state.broadcast("toast", {"message": f"Saved to favorites: {dest.name}"})
        else:
            await self.state.broadcast("toast", {"message": "No track to save yet."})

    async def like(self):
        """Like the current track — keeps queue, records taste."""
        if self._queued_params:
            self.radio.add_reaction(self._queued_params, "liked")
            if self._queued_track:
                jpath = self._queued_track.with_suffix(".json")
                if jpath.exists():
                    update_recipe(jpath, {"reaction": "liked"})
            await self.state.broadcast("reaction_feedback", {"signal": "liked"})

    async def dislike(self):
        """Dislike — discard queue, regenerate with shift."""
        if self._queued_params:
            self.radio.add_reaction(self._queued_params, "disliked")
            if self._queued_track:
                jpath = self._queued_track.with_suffix(".json")
                if jpath.exists():
                    update_recipe(jpath, {"reaction": "disliked"})
        reaction = {"signal": "disliked", "modifiers": [], "mood": None,
                    "direction": None, "command": None, "raw": "dislike"}
        self._last_reaction = "Shift direction noticeably — change genre or energy."
        await self._discard_and_regenerate(reaction, "dislike")

    async def set_volume(self, level: int):
        self.player.set_volume(level)
        await self._broadcast_playback_state()

    async def seek(self, delta: float):
        self.player.seek(delta)
        await self._broadcast_playback_state()

    async def track_ended(self):
        """Browser audio ended (first play or loop). Sync server timer and signal advance."""
        self.player.replay()
        self._track_ended_event.set()

    async def switch_radio(self, name: str) -> bool:
        """Switch to a different radio. Returns True if switched."""
        existing = self.manager.list_radios()
        new_radio = self.manager.switch_to(name)

        # Cancel any in-flight generation
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            try:
                await self._gen_task
            except (asyncio.CancelledError, Exception):
                pass

        self.player.stop()
        self.radio = new_radio
        self._last_params = None
        self._recent_params = []
        self._last_reaction = ""
        self._queued_track = None
        self._queued_params = None
        self._interrupt_when_ready = False
        self._track_ended_event.clear()

        await self.state.broadcast("radio_switched", {
            "name": new_radio.name,
            "is_new": new_radio.is_first_run(),
        })
        await self._broadcast_playback_state()

        # Kick the main loop
        self._reaction_event.set()
        return True

    async def create_radio(self, name: str, vibe: str = "") -> bool:
        """Create a new radio and switch to it."""
        await self.switch_radio(name)
        if vibe:
            self.radio.add_note(vibe)
            self.radio.set_direction(vibe)
            self._last_reaction = vibe
        return True

    async def delete_radio(self, name: str) -> bool:
        """Delete a radio station."""
        if name == self.radio.name:
            self.manager.delete(name)
            await self.switch_radio("default")
        else:
            self.manager.delete(name)
        await self.state.broadcast("toast", {"message": f"Deleted radio '{name}'"})
        return True

    async def clean_radio(self):
        """Reset all user data for the current radio (taste + tracks + favorites)."""
        if self.radio:
            self.player.stop()
            self.radio.full_reset()
            self._queued_track = None
            self._queued_params = None
            self._last_params = None
            self._recent_params = []
            self._last_reaction = ""
            self._pending_modifiers.clear()
            self._pending_reaction = None
            await self.state.broadcast("first_run", {"radio": self.radio.name})
            self._reaction_event.clear()
            self._track_ended_event.clear()

    async def set_first_vibe(self, text: str):
        """Set initial direction for a new radio (first-run flow)."""
        if text:
            self.radio.add_note(text)
            self.radio.set_direction(text)
            self._last_reaction = text
            self._reaction_event.set()

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        self.player.stop()
        self._reaction_event.set()
        self._track_ended_event.set()
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            try:
                await self._gen_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
            try:
                await self._tick_task
            except (asyncio.CancelledError, Exception):
                pass

    # ── Main loop ────────────────────────────────────────────────────────────

    async def run(self):
        """Main radio loop — never stops unless self._running is set to False."""
        self._running = True
        self.radio = self.manager.current_radio()

        await self.state.set_radio(self.radio.name)
        await self._broadcast_playback_state()

        # Start tick broadcaster
        self._tick_task = asyncio.create_task(self._tick_loop())

        # Check if this is a first run
        if self.radio.is_first_run():
            await self.state.broadcast("first_run", {"radio": self.radio.name})

        while self._running:
            try:
                await self._generate_and_play_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Engine cycle error")
                await self.state.broadcast("error", {"message": str(e)})
                await asyncio.sleep(5)

    async def _generate_and_play_cycle(self):
        """One full cycle: generate params → generate track → play → wait."""

        # ── Check sleep timer ────────────────────────────────────────────
        if self._sleep_deadline is not None and time.monotonic() >= self._sleep_deadline:
            self._sleep_deadline = None
            self.player.stop()
            await self.state.broadcast("sleep_expired", {})
            await self._broadcast_playback_state()
            # Wait for user action
            self._reaction_event.clear()
            await self._reaction_event.wait()
            return

        # ── Disk check ───────────────────────────────────────────────────
        if not check_disk(self.radio):
            await self.state.broadcast("disk_full", {
                "free_mb": self.radio.disk_free_mb(),
            })
            if self.player.is_playing() or self.player.is_paused():
                # Keep playing, wait for user
                self._reaction_event.clear()
                await self._reaction_event.wait()
                return
            # Nothing playing and disk full — wait
            self._reaction_event.clear()
            await self._reaction_event.wait()
            return

        # ── Wait for first-run vibe if needed ────────────────────────────
        if self.radio.is_first_run() and not self._last_reaction:
            self._reaction_event.clear()
            await self._reaction_event.wait()
            if not self._running:
                return

        # ── Check ACE-Step is up before burning LLM tokens ───────────────
        if not await acestep_check_server():
            self._model_ensured = False  # reset so we re-activate after restart
            await self.state.broadcast("waiting", {"message": "ACE-Step starting up…"})
            await asyncio.sleep(15)
            return
        if not self._model_ensured:
            self._model_ensured = await acestep_ensure_model()


        # ── Play queued track now if it's not already playing (avoids silence gap) ──
        if self._queued_track and self._queued_track.exists():
            if not (self.player.is_playing() and self.player.current_track == self._queued_track):
                dur = get_audio_duration(self._queued_track)
                self.player.play(self._queued_track, duration=dur)
                await self.state.broadcast("now_playing", self._build_now_playing(self._queued_params, self._queued_track))
                await self._broadcast_playback_state()

        # ── Detect stuck LLM ────────────────────────────────────────────
        inject_vary = ""
        if self._last_params and params_are_too_similar(self._last_params, self._recent_params):
            inject_vary = " — vary significantly, change key, BPM range, and genre"

        # ── Generate params (LLM) ───────────────────────────────────────
        llm_message = (self._last_reaction or "") + inject_vary
        if self._pending_modifiers:
            llm_message += f" [modifiers: {', '.join(self._pending_modifiers)}]"

        if self._last_reaction:
            enrichment = parse_reaction(self._last_reaction)
            parts = []
            if enrichment.get("modifiers"):
                parts.append(f"modifiers: {', '.join(enrichment['modifiers'])}")
            if enrichment.get("mood"):
                parts.append(f"mood: {enrichment['mood']}")
            if parts:
                llm_message += f" [{'; '.join(parts)}]"

        # Loop current track during LLM call
        llm_looper = None
        if self.player.is_playing():
            llm_looper = asyncio.create_task(self._loop_current())

        await self.state.broadcast("thinking", {})

        try:
            params = await generate_params(
                user_message=llm_message,
                taste_context=self.radio.to_llm_context(),
                last_params=self._last_params,
                recent_params=self._recent_params,
            )
        except Exception as e:
            logger.error("LLM generation failed: %s", e)
            format_error("llm_generate", self._last_reaction, self._last_params, str(e))
            await self.state.broadcast("error", {"message": "LLM failed, retrying..."})
            await asyncio.sleep(2)
            return
        finally:
            if llm_looper and not llm_looper.done():
                llm_looper.cancel()

        # If a reaction fired while LLM was running, restart with updated direction
        if self._reaction_event.is_set():
            self._reaction_event.clear()
            return

        # Clear accumulated modifiers
        self._pending_modifiers.clear()

        track_id = self.radio.next_track_id()
        params["id"] = track_id
        params["radio"] = self.radio.name
        params["generated_at"] = datetime.now().isoformat()
        params["prompt"] = self._last_reaction[:120] if self._last_reaction else params.get("tags", "")

        warnings = params.pop("_warnings", [])

        await self.state.broadcast("generation_start", {
            "params": {k: v for k, v in params.items() if k in (
                "tags", "bpm", "key_scale", "time_signature", "instrumental", "rationale", "id"
            )},
            "warnings": warnings,
        })

        # ── Start ACE-Step generation ───────────────────────────────────
        slug = _slugify(params.get("tags", "track"))[:40]
        next_path = self.radio.tracks_dir / f"{track_id}-{slug}.mp3"
        self._next_path = next_path
        self._gen_task = asyncio.create_task(generate_track(params, next_path))
        gen_start = time.monotonic()

        # ── Wait for generation while track plays ───────────────────────
        if self.player.is_playing() or self.player.is_paused():
            await self._wait_with_playback(params, next_path, gen_start)
        else:
            # Nothing playing — wait for generation to finish
            await self._wait_for_generation(params, next_path, gen_start)

    async def _wait_for_generation(self, params, next_path, gen_start):
        """Wait for generation with no music playing (first track or after failure)."""
        # Loop current if available
        looper = None
        if self.player.current_track:
            looper = asyncio.create_task(self._loop_current())

        try:
            while not self._gen_task.done():
                await asyncio.sleep(0.5)
                elapsed = time.monotonic() - gen_start
                await self.state.broadcast("generation_progress", {
                    "elapsed": round(elapsed, 1),
                })
        finally:
            if looper and not looper.done():
                looper.cancel()

        success, err = await self._get_gen_result()
        if not success:
            if err == "cancelled":
                return  # cancelled by user reaction — main loop will restart
            await self._handle_gen_failure(params, next_path, err, gen_start)
            return

        # Play the freshly generated track
        dur = get_audio_duration(next_path)
        self.player.play(next_path, duration=dur)
        self._commit_track(params, next_path, gen_start)
        self._queued_track = next_path
        self._queued_params = params
        self._last_params = params
        self._recent_params = (self._recent_params + [params])[-5:]

        await self.state.broadcast("now_playing", self._build_now_playing(params, next_path))
        await self.state.broadcast("generation_done", {})
        await self._broadcast_playback_state()
        asyncio.create_task(self._align_and_broadcast(params, next_path))
        # Return immediately — main loop starts generating next track while this one plays

    async def _wait_with_playback(self, params, next_path, gen_start):
        """Wait for generation while a track is playing. Handle auto-advance.

        Auto-advance rules:
        - First play of current track: wait for browser to signal track_ended, THEN advance.
        - Looping (track ended but next not ready): keep looping, advance at next track_ended.
        - Dislike interrupt: switch immediately when next is ready, mid-play.
        """
        auto_advanced = False
        reaction_broke = False

        async def _auto_advance():
            nonlocal auto_advanced
            while True:
                # Clear before waiting so we don't act on a stale signal
                self._track_ended_event.clear()

                # Wait for browser track_ended OR dislike interrupt
                while not self._track_ended_event.is_set():
                    if self._gen_task.done() and self._interrupt_when_ready:
                        break
                    if not self._running:
                        return
                    await asyncio.sleep(0.2)

                # Dislike: interrupt current track immediately when next is ready
                if self._gen_task.done() and self._interrupt_when_ready:
                    self._interrupt_when_ready = False
                    success, _ = await self._get_gen_result()
                    if success and next_path.exists():
                        dur = get_audio_duration(next_path)
                        self.player.play(next_path, duration=dur)
                        self._queued_track = next_path
                        self._queued_params = params
                        auto_advanced = True
                        await self.state.broadcast("now_playing", self._build_now_playing(params, next_path))
                        await self._broadcast_playback_state()
                        continue
                    return

                # track_ended fired — clear it and decide: advance or loop
                self._track_ended_event.clear()

                if self._gen_task.done():
                    # Next track ready — auto-advance
                    success, _ = await self._get_gen_result()
                    if success and next_path.exists():
                        dur = get_audio_duration(next_path)
                        self.player.play(next_path, duration=dur)
                        self._queued_track = next_path
                        self._queued_params = params
                        auto_advanced = True
                        await self.state.broadcast("now_playing", self._build_now_playing(params, next_path))
                        await self._broadcast_playback_state()
                        continue
                    return

                # Next not ready — browser already looped (audio.ts loops on ended),
                # server timer was reset by track_ended() calling player.replay().
                # Just wait for the next track_ended signal.

        advance_task = asyncio.create_task(_auto_advance())

        # Monitor generation progress
        progress_task = asyncio.create_task(self._broadcast_gen_progress(gen_start))

        self._reaction_event.clear()

        while self._running:
            waiters = [asyncio.create_task(self._reaction_event.wait())]
            if not self._gen_task.done():
                waiters.append(asyncio.shield(self._gen_task))

            done, pending = await asyncio.wait(waiters, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()

            if self._reaction_event.is_set():
                self._reaction_event.clear()
                reaction_broke = True
                break

            if auto_advanced:
                break

            # Fallback: gen done and player stopped (e.g. browser disconnected)
            if self._gen_task.done() and not self.player.is_playing() and not self.player.is_paused():
                break

        advance_task.cancel()
        progress_task.cancel()

        if not self._gen_task.done() or reaction_broke:
            return

        success, err = await self._get_gen_result()
        if not success:
            if err == "cancelled":
                return
            await self._handle_gen_failure(params, next_path, err, gen_start)
            return

        self._commit_track(params, next_path, gen_start)
        asyncio.create_task(self._align_and_broadcast(params, next_path))

        if not auto_advanced:
            self._queued_track = next_path
            self._queued_params = params

        self._last_params = params
        self._recent_params = (self._recent_params + [params])[-5:]

    async def _wait_for_track_end(self):
        """Wait for the current track to end naturally or for user to react."""
        self._reaction_event.clear()
        while self._running:
            if not self.player.is_playing() and not self.player.is_paused():
                break
            if self._reaction_event.is_set():
                self._reaction_event.clear()
                break
            await asyncio.sleep(0.3)

    async def _discard_and_regenerate(self, reaction: dict, user_input: str):
        """Cancel in-flight generation, record taste, and signal main loop."""
        # Record taste on the track user was hearing
        if reaction.get("signal") and self._queued_params:
            self.radio.add_reaction(self._queued_params, reaction["signal"])
            if self._queued_track:
                jpath = self._queued_track.with_suffix(".json")
                if jpath.exists():
                    update_recipe(jpath, {"reaction": reaction["signal"]})

        if reaction.get("modifiers"):
            for mod in reaction["modifiers"]:
                self.radio.add_note(mod)
        if reaction.get("mood"):
            self.radio.set_direction(f"mood: {reaction['mood']}")
        if reaction.get("direction") == "reset":
            self.radio.set_direction("reset — bold departure from recent tracks")

        # Cancel in-flight generation
        if self._gen_task and not self._gen_task.done():
            self._gen_task.cancel()
            try:
                await self._gen_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._next_path and self._next_path.exists():
            try:
                self._next_path.unlink()
            except OSError:
                pass

        if reaction.get("signal") == "skipped":
            self.player.stop()
            await self._broadcast_playback_state()
        elif reaction.get("signal") == "disliked":
            self._interrupt_when_ready = True
            self._last_reaction = "Shift direction noticeably — change genre or energy. " + user_input
            self._queued_track = None
            self._queued_params = None

        # Update tracking
        self._last_params = self._queued_params or self._last_params
        self._recent_params = (self._recent_params + [self._queued_params or {}])[-5:]

        await self.state.broadcast("regenerating", {"reason": user_input})
        self._reaction_event.set()

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _loop_current(self):
        """Keep replaying the current track to avoid silence."""
        while True:
            await self.player.wait_done_async()
            if self.player.is_playing() or self.player.is_paused():
                continue
            if self.player.current_track:
                self.player.replay()
            else:
                break

    async def _get_gen_result(self) -> tuple[bool, str]:
        try:
            return self._gen_task.result()
        except asyncio.CancelledError:
            return False, "cancelled"
        except Exception as e:
            return False, str(e)

    async def _handle_gen_failure(self, params, next_path, err, gen_start):
        """Handle generation failure with retry."""
        logger.error("Generation failed: %s", err)
        format_error("track_generation", "", params, err)
        await self.state.broadcast("error", {"message": f"Generation failed: {err}"})

        # Retry once
        try:
            success2, err2 = await generate_track(params, next_path)
        except Exception as e:
            success2, err2 = False, str(e)

        if not success2:
            await self.state.broadcast("error", {"message": f"Retry failed: {err2}"})
            # Loop current track if available
            if self.player.current_track:
                self.player.replay()
                await self._broadcast_playback_state()
            # Back off before next cycle so we don't hammer ACE-Step while it's down
            await asyncio.sleep(15)
            return

        # Retry succeeded
        dur = get_audio_duration(next_path)
        self.player.play(next_path, duration=dur)
        self._commit_track(params, next_path, gen_start)
        asyncio.create_task(self._align_and_broadcast(params, next_path))
        self._queued_track = next_path
        self._queued_params = params
        self._last_params = params
        self._recent_params = (self._recent_params + [params])[-5:]
        await self.state.broadcast("now_playing", self._build_now_playing(params, next_path))
        await self._broadcast_playback_state()

    def _commit_track(self, params, next_path, gen_start):
        """Write recipe, increment count, log metrics."""
        gen_elapsed = time.monotonic() - gen_start
        audio_dur = get_audio_duration(next_path) if next_path.exists() else None
        try:
            file_size = next_path.stat().st_size if next_path.exists() else None
        except OSError:
            file_size = None

        recipe = {
            **params,
            "reaction": "neutral",
            "generation_time_s": round(gen_elapsed, 2),
            "audio_duration_s": round(audio_dur, 2) if audio_dur else None,
            "file_size_bytes": file_size,
            "realtime_ratio": round(audio_dur / gen_elapsed, 2) if audio_dur and gen_elapsed > 0 else None,
        }

        try:
            next_path.with_suffix(".json").write_text(json.dumps(recipe, indent=2))
        except OSError:
            pass

        self.radio.increment_count()
        append_metric({
            "track_id": params.get("id"),
            "radio": self.radio.name,
            "timestamp": datetime.now().isoformat(),
            "generation_time_s": recipe["generation_time_s"],
            "audio_duration_s": recipe["audio_duration_s"],
            "file_size_bytes": file_size,
            "realtime_ratio": recipe["realtime_ratio"],
            "tags": params.get("tags", ""),
            "bpm": params.get("bpm"),
            "instrumental": params.get("instrumental"),
        })

    async def _align_and_broadcast(self, params: dict, track_path: Path):
        """Background task: transcribe audio then broadcast lyrics_sync.

        Fires after _commit_track. Never blocks playback.
        Always broadcasts for vocal tracks — null timestamps signals failure
        so the frontend knows to hide the lyrics button rather than spin forever.
        Skips entirely for instrumental tracks (no lyrics button shown).
        """
        track_id = params.get("id")
        is_instrumental = params.get("instrumental", True)
        lyrics = params.get("lyrics", "") or ""

        if is_instrumental or not lyrics or lyrics == "[inst]":
            return  # instrumental — frontend never shows lyrics button

        vocal_language = params.get("vocal_language", "en") or "en"

        try:
            timestamps = await align_lyrics(track_path, lyrics, vocal_language)
        except Exception as e:
            logger.error("_align_and_broadcast error for %s: %s", track_id, e)
            timestamps = []

        # Always broadcast for vocal tracks so the frontend can stop the spinner.
        # timestamps=None means failed/unavailable → button hidden.
        if self._queued_params and self._queued_params.get("id") == track_id:
            await self.state.broadcast("lyrics_sync", {
                "track_id": track_id,
                "timestamps": timestamps if timestamps else None,
            })

    def _build_now_playing(self, params: dict, track_path: Path) -> dict:
        """Build now-playing payload for WebSocket broadcast."""
        raw_lyrics = params.get("lyrics", "") or ""
        is_instrumental = params.get("instrumental", False)
        lyrics = raw_lyrics if not is_instrumental and raw_lyrics not in ("", "[inst]") else ""
        return {
            "id": params.get("id"),
            "tags": params.get("tags", ""),
            "bpm": params.get("bpm"),
            "key_scale": params.get("key_scale"),
            "time_signature": params.get("time_signature"),
            "instrumental": is_instrumental,
            "rationale": params.get("rationale", ""),
            "radio": params.get("radio", ""),
            "audio_url": f"/audio/{self.radio.name}/{track_path.name}",
            "duration": self.player.duration,
            "lyrics": lyrics,
        }

    async def _broadcast_playback_state(self):
        """Push current player state to all clients."""
        await self.state.broadcast("playback_state", {
            "playing": self.player.is_playing() and not self.player.is_paused(),
            "paused": self.player.is_paused(),
            "elapsed": round(self.player.elapsed, 1),
            "duration": self.player.duration,
            "volume": self.player._volume,
            "has_track": self.player.current_track is not None,
        })

    async def _broadcast_gen_progress(self, gen_start):
        """Periodically broadcast generation progress."""
        while not self._gen_task.done():
            elapsed = time.monotonic() - gen_start
            await self.state.broadcast("generation_progress", {
                "elapsed": round(elapsed, 1),
            })
            await asyncio.sleep(1)
        await self.state.broadcast("generation_done", {})

    async def _tick_loop(self):
        """Send elapsed/duration tick to clients every second."""
        while self._running:
            await asyncio.sleep(1)
            if self.player.is_playing():
                await self.state.broadcast("tick", {
                    "elapsed": round(self.player.elapsed, 1),
                    "duration": self.player.duration,
                })

    def get_snapshot(self) -> dict:
        """Full state snapshot for initial WebSocket sync."""
        now_playing = None
        if self._queued_params and self._queued_track:
            now_playing = self._build_now_playing(self._queued_params, self._queued_track)

        return {
            "radio_name": self.radio.name if self.radio else "default",
            "now_playing": now_playing,
            "playback": {
                "playing": self.player.is_playing() and not self.player.is_paused(),
                "paused": self.player.is_paused(),
                "elapsed": round(self.player.elapsed, 1),
                "duration": self.player.duration,
                "volume": self.player._volume,
                "has_track": self.player.current_track is not None,
            },
            "is_first_run": self.radio.is_first_run() if self.radio else True,
            "generating": self._gen_task is not None and not self._gen_task.done(),
        }
