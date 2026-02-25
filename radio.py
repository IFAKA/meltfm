"""Personal AI Radio — entry point."""
import asyncio
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich import print as rprint

from src.config import DEFAULT_DURATION, RADIOS_DIR
from src.manager import Radio, RadioManager, _slugify
from src.reactions import parse_reaction
from src.llm import generate_params, params_are_too_similar
from src.acestep import generate_track
from src.player import Player, get_audio_duration
from src.preflight import run_preflight
from src.errors import format_error
from src.ui import (
    print_header,
    print_startup,
    print_incoming,
    print_now_playing,
    print_status_line,
    print_recipe,
    print_help,
    show_reaction_feedback,
    friendly_redirect,
    show_generation_progress,
    fmt_countdown,
    console,
)
from src.input import get_user_input, _read_one_char
from src.navigation import navigate_history
from src.commands import (
    handle_radio_command,
    check_disk,
    update_recipe,
    append_metric,
)

player = Player()
manager = RadioManager()

def _show_help():
    print_help()


async def main():
    print_header()

    ok = await run_preflight()
    if not ok:
        sys.exit(1)

    radio = manager.current_radio()

    # First run: ask for sound preference
    if radio.is_first_run():
        console.print(f"  [bold]What's your sound?[/bold] (e.g., lo-fi beats for studying, dark ambient, upbeat jazz)")
        first_input = await get_user_input()
        if first_input:
            radio.add_note(first_input)
            radio.set_direction(first_input)
        last_reaction = first_input or ""
    else:
        print_startup(radio)
        last_reaction = ""

    _show_help()

    last_params: Optional[dict] = None
    queued_track: Optional[Path] = None
    queued_params: Optional[dict] = None
    recent_params: list[dict] = []
    interrupt_when_ready = False
    sleep_deadline: float | None = None

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:

        # ── Check sleep timer ──────────────────────────────────────────
        if sleep_deadline is not None and time.monotonic() >= sleep_deadline:
            console.print("\n  [yellow]⏾  Sleep timer expired — stopping after this track.[/yellow]")
            sleep_deadline = None
            break

        # ── Wait while paused ─────────────────────────────────────────────
        if player.is_paused():
            sys.stdout.write("  ⏸ paused — Space to resume\r")
            sys.stdout.flush()
            loop = asyncio.get_event_loop()
            while player.is_paused():
                ch = await loop.run_in_executor(None, _read_one_char)
                if ch in ("\x10", " "):
                    player.toggle_pause()
                elif ch == "\x03":
                    raise KeyboardInterrupt
            sys.stdout.write("\r  ▶ resumed                       \n")
            sys.stdout.flush()

        if not check_disk(radio):
            break

        # ── 1. Detect if LLM is stuck ────────────────────────────────────
        inject_vary = ""
        if last_params and params_are_too_similar(last_params, recent_params):
            inject_vary = " — vary significantly, change key, BPM range, and genre"

        # ── 2. Generate params (LLM) ─────────────────────────────────────
        try:
            with console.status("  [yellow]✦  Thinking...[/yellow]", spinner="dots"):
                params = await generate_params(
                    user_message=(last_reaction or "") + inject_vary,
                    taste_context=radio.to_llm_context(),
                    last_params=last_params,
                    recent_params=recent_params,
                )
        except Exception as e:
            console.print(f"\n[red]{format_error('llm_generate', last_reaction, last_params, str(e))}[/red]")
            await asyncio.sleep(2)
            continue

        track_id = radio.next_track_id()
        params["id"] = track_id
        params["radio"] = radio.name
        params["generated_at"] = datetime.now().isoformat()
        params["prompt"] = last_reaction[:120] if last_reaction else params.get("tags", "")

        print_incoming(params)

        # ── 3. Start ACE-Step generation in background ────────────────────
        slug = _slugify(params.get("tags", "track"))[:40]
        next_path = radio.tracks_dir / f"{track_id}-{slug}.mp3"
        gen_task = asyncio.create_task(generate_track(params, next_path))
        gen_start = time.monotonic()

        # ── 4. Play queued track if ready ─────────────────────────────────
        if queued_track and queued_track.exists():
            if not (player.is_playing() and player.current_track == queued_track):
                dur = get_audio_duration(queued_track)
                player.play(queued_track, duration=dur)
                print_now_playing(queued_params or {}, queued_track)

        # ── 5. Input strategy ─────────────────────────────────────────────
        user_input = ""
        first_play = False
        reaction = None

        if not (player.is_playing() or player.is_paused()) and not queued_track:
            console.print("  [dim]First track takes a moment to generate...[/dim]")

        if player.is_playing() or player.is_paused():
            # ── Inner input loop ──────────────────────────────────────
            while True:
                async def _auto_advance():
                    nonlocal interrupt_when_ready
                    if interrupt_when_ready and not gen_task.done():
                        done_waiter = asyncio.create_task(player.wait_done_async())
                        gen_waiter = asyncio.create_task(asyncio.shield(gen_task))
                        done_set, pending = await asyncio.wait(
                            [done_waiter, gen_waiter],
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for p in pending:
                            p.cancel()
                        if gen_waiter in done_set:
                            try:
                                ok, _ = gen_task.result()
                            except Exception:
                                return
                            if ok and next_path.exists():
                                interrupt_when_ready = False
                                player.stop()
                                dur = get_audio_duration(next_path)
                                player.play(next_path, duration=dur)
                                return

                    while True:
                        await player.wait_done_async()
                        if player.is_paused():
                            await asyncio.sleep(0.3)
                            continue
                        if gen_task.done():
                            try:
                                ok, _ = gen_task.result()
                            except Exception:
                                break
                            if ok and next_path.exists():
                                dur = get_audio_duration(next_path)
                                player.play(next_path, duration=dur)
                                continue
                        if queued_track and queued_track.exists():
                            player.replay()

                advance_watcher = asyncio.create_task(_auto_advance())
                print_status_line(queued_params, player, player.is_paused(), player._volume, sleep_deadline=sleep_deadline)
                user_input = await get_user_input(
                    player=player,
                    gen_task=gen_task,
                    gen_start=gen_start,
                    status_params=queued_params,
                    sleep_deadline=sleep_deadline,
                )
                advance_watcher.cancel()

                if not user_input:
                    if player.is_playing():
                        break
                    console.print("  [dim]Tell me how you're feeling or what to change...[/dim]")
                    continue

                if friendly_redirect(user_input):
                    console.print("  [dim]I only speak music — try 'more bass' or 'something darker' :)[/dim]")
                    continue

                reaction = parse_reaction(user_input)
                show_reaction_feedback(reaction)

                # ── Info commands — handle and re-prompt ──────────────
                if reaction["command"] == "help":
                    _show_help()
                    continue

                if reaction["command"] == "save":
                    if queued_track and queued_track.exists():
                        dest = radio.mark_favorite(queued_track)
                        console.print(f"  [green]✓ Saved to favorites:[/green] {dest.name}")
                        jpath = queued_track.with_suffix(".json")
                        if jpath.exists():
                            update_recipe(jpath, {"reaction": "liked", "favorited": True})
                        if queued_params:
                            radio.add_reaction(queued_params, "liked")
                    else:
                        console.print("  [dim]No track to save yet.[/dim]")
                    continue

                if reaction["command"] == "what":
                    if queued_params:
                        print_recipe(queued_params)
                    else:
                        console.print("  [dim]No track info yet.[/dim]")
                    continue

                if reaction["command"] == "history":
                    selected_tags = await navigate_history(radio)
                    if selected_tags:
                        console.print(f"  [dim]Direction →[/dim] {selected_tags[:60]}")
                        last_reaction = selected_tags
                        break
                    continue

                if reaction["command"] == "share":
                    if queued_params and queued_track:
                        print_recipe(queued_params)
                        json_path = queued_track.with_suffix(".json")
                        if json_path.exists():
                            console.print(f"  [dim]Recipe file:[/dim] {json_path}")
                    else:
                        console.print("  [dim]Nothing to share yet.[/dim]")
                    continue

                if reaction["command"] == "open_folder":
                    subprocess.run(["open", str(radio.tracks_dir)], check=False)
                    continue

                if reaction["command"] == "sleep_timer":
                    mins = reaction.get("timer_minutes", 30)
                    sleep_deadline = time.monotonic() + mins * 60
                    console.print(f"  [yellow]⏾  Sleep timer set — stopping in {mins} min[/yellow]")
                    continue

                if reaction["command"] == "cancel_sleep":
                    if sleep_deadline is not None:
                        sleep_deadline = None
                        console.print("  [yellow]⏾  Sleep timer cancelled[/yellow]")
                    else:
                        console.print("  [dim]No sleep timer active.[/dim]")
                    continue

                if reaction["command"] == "sleep_status":
                    if sleep_deadline is not None:
                        console.print(f"  [yellow]⏾  Sleep in {fmt_countdown(sleep_deadline)}[/yellow]")
                    else:
                        console.print("  [dim]No sleep timer active. Try: sleep 30[/dim]")
                    continue

                break  # quit, radio cmd, or musical reaction → proceed

            # If generation still running after input — show progress (with looping)
            if not gen_task.done():
                success, err = await show_generation_progress(
                    gen_task, "  ◈  Finishing track", loop_player=player, gen_params=params,
                )
            else:
                try:
                    success, err = gen_task.result()
                except Exception as e:
                    success, err = False, str(e)
        else:
            # Nothing playing — show progress bar until gen done, then play + prompt
            success, err = await show_generation_progress(gen_task, loop_player=player, gen_params=params)

            if success:
                dur = get_audio_duration(next_path)
                player.play(next_path, duration=dur)
                print_now_playing(params, next_path)
                first_play = True

        # ── 6. Handle generation failure ──────────────────────────────────
        if not success:
            console.print(f"\n[red]{format_error('track_generation', user_input, params, err)}[/red]")
            console.print("  [yellow]Retrying...[/yellow]")
            success2, err2 = await generate_track(params, next_path)
            if not success2:
                console.print(f"  [red]Retry failed: {err2}[/red]")
                last_reaction = user_input
                last_params = params
                continue

        # ── 7. Build recipe ───────────────────────────────────────────────
        gen_elapsed = time.monotonic() - gen_start
        audio_dur = get_audio_duration(next_path) if next_path.exists() else None
        file_size = next_path.stat().st_size if next_path.exists() else None

        recipe = {
            **params,
            "reaction": "neutral",
            "generation_time_s": round(gen_elapsed, 2),
            "audio_duration_s": round(audio_dur, 2) if audio_dur else None,
            "file_size_bytes": file_size,
            "realtime_ratio": round(audio_dur / gen_elapsed, 2) if audio_dur and gen_elapsed > 0 else None,
        }

        def _commit_track():
            """Write recipe, increment count, log metrics for a kept track."""
            next_path.with_suffix(".json").write_text(json.dumps(recipe, indent=2))
            radio.increment_count()
            append_metric({
                "track_id": track_id,
                "radio": radio.name,
                "timestamp": datetime.now().isoformat(),
                "generation_time_s": recipe["generation_time_s"],
                "audio_duration_s": recipe["audio_duration_s"],
                "file_size_bytes": file_size,
                "realtime_ratio": recipe["realtime_ratio"],
                "tags": params.get("tags", ""),
                "bpm": params.get("bpm"),
                "instrumental": params.get("instrumental"),
            })

        # ── First-play shortcut ───────────────────────────────────────────
        if first_play:
            _commit_track()
            queued_track = next_path
            queued_params = params
            last_params = params
            recent_params = (recent_params + [params])[-5:]
            continue

        # ── 8. Handle empty input ─────────────────────────────────────────
        if not user_input:
            if player.is_playing():
                _commit_track()
                queued_track = next_path
                queued_params = params
                last_params = params
                recent_params = (recent_params + [params])[-5:]
                continue
            else:
                console.print("  [dim]Tell me how you're feeling or what to change...[/dim]")
                user_input = await get_user_input(player=player)

        # ── 9. Parse reaction ─────────────────────────────────────────────
        if reaction is None:
            reaction = parse_reaction(user_input)
            show_reaction_feedback(reaction)

        # ── 10. Handle commands ───────────────────────────────────────────
        if reaction["command"] == "quit":
            console.print("\n  [bold]Saving taste profile...[/bold] [green]Done.[/green]")
            player.stop()
            break

        if reaction["command"] == "sleep_timer":
            mins = reaction.get("timer_minutes", 30)
            sleep_deadline = time.monotonic() + mins * 60
            console.print(f"  [yellow]⏾  Sleep timer set — stopping in {mins} min[/yellow]")
            continue

        if reaction["command"] == "cancel_sleep":
            if sleep_deadline is not None:
                sleep_deadline = None
                console.print("  [yellow]⏾  Sleep timer cancelled[/yellow]")
            else:
                console.print("  [dim]No sleep timer active.[/dim]")
            continue

        if reaction["command"] == "sleep_status":
            if sleep_deadline is not None:
                console.print(f"  [yellow]⏾  Sleep in {fmt_countdown(sleep_deadline)}[/yellow]")
            else:
                console.print("  [dim]No sleep timer active. Try: sleep 30[/dim]")
            continue

        if reaction["command"] in ("switch_radio", "create_radio", "delete_radio", "list_radios"):
            new_radio = await handle_radio_command(reaction, radio, manager)
            if new_radio:
                radio = new_radio
                last_params = None
                recent_params = []
                last_reaction = ""
                queued_track = None
                queued_params = None
            continue

        if reaction["command"] == "history":
            if not gen_task.done():
                gen_task.cancel()
                try:
                    await gen_task
                except (asyncio.CancelledError, Exception):
                    pass
            if next_path.exists():
                next_path.unlink()
            last_params = queued_params or last_params
            recent_params = (recent_params + [queued_params or params])[-5:]
            continue

        if reaction["signal"] == "skipped":
            player.stop()
            console.print("  [yellow]Skipped.[/yellow]")

        # ── 11. Update taste profile ──────────────────────────────────────
        if reaction["signal"] and queued_params:
            radio.add_reaction(queued_params, reaction["signal"])
            if queued_track:
                jpath = queued_track.with_suffix(".json")
                if jpath.exists():
                    update_recipe(jpath, {"reaction": reaction["signal"]})

        if reaction["modifiers"]:
            for mod in reaction["modifiers"]:
                radio.add_note(mod)

        if reaction["mood"]:
            radio.set_direction(f"mood: {reaction['mood']}")

        if reaction["direction"] == "reset":
            radio.set_direction("reset — bold departure from recent tracks")

        # ── 12. Queue or discard pre-generated track ──────────────────────
        wants_change = bool(
            reaction["modifiers"] or
            reaction["mood"] or
            reaction["direction"] == "reset" or
            (not reaction["command"] and not reaction["signal"] and user_input)
        )

        if wants_change:
            if not gen_task.done():
                gen_task.cancel()
                try:
                    await gen_task
                except (asyncio.CancelledError, Exception):
                    pass
            if next_path.exists():
                next_path.unlink()
            console.print("  [dim]↻ Got it — regenerating with your changes...[/dim]")
            interrupt_when_ready = True
            last_reaction = user_input
            last_params = queued_params or last_params
            recent_params = (recent_params + [queued_params or params])[-5:]
        else:
            interrupt_when_ready = False
            _commit_track()
            queued_track = next_path
            queued_params = params
            has_music = bool(reaction["signal"] or reaction["modifiers"] or reaction["mood"] or reaction["direction"])
            if has_music:
                if reaction["signal"] and not reaction["modifiers"] and not reaction["mood"] and reaction["direction"] != "reset":
                    _signal_hints = {
                        "liked":    "Continue in a similar direction, evolve subtly.",
                        "disliked": "Shift direction noticeably — change genre or energy.",
                        "skipped":  "Try something quite different.",
                    }
                    last_reaction = _signal_hints.get(reaction["signal"], user_input)
                else:
                    last_reaction = user_input
            last_params = params
            recent_params = (recent_params + [params])[-5:]

    # Cleanup
    player.stop()
    console.print("\n  [bold cyan]♪[/bold cyan]  See you next time.\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        player.stop()
        rprint("\n\n  [bold]Saved your taste profile.[/bold] Goodbye.\n")
        sys.exit(0)
