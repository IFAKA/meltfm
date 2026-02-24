"""Personal AI Radio — entry point."""
import asyncio
import json
import os
import signal
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import print as rprint

from src.config import APP_VERSION, DEFAULT_DURATION, RADIOS_DIR
from src.manager import Radio, RadioManager, _slugify
from src.reactions import parse_reaction
from src.llm import generate_params, params_are_too_similar
from src.acestep import generate_track
from src.player import Player
from src.preflight import run_preflight
from src.errors import format_error

console = Console()
player = Player()
manager = RadioManager()


# ─── UI Helpers ───────────────────────────────────────────────────────────────

def print_header():
    console.print(
        f"\n  [bold cyan]♪  Personal Radio[/bold cyan]"
        f"  ·  v{APP_VERSION}"
        f"  ·  powered by ACE-Step + Ollama\n"
    )


def print_incoming(params: dict):
    console.print(f"\n  [bold yellow]✦  Building next track...[/bold yellow]")
    console.print(f"     [italic]\"{params.get('rationale', '')}\"[/italic]")
    tags = params.get("tags", "")
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")
    ts = params.get("time_signature", 4)
    inst = "instrumental" if params.get("instrumental") else "with vocals"
    console.print(f"     [dim]Tags:[/dim] {tags}")
    console.print(f"     [dim]{bpm} BPM · {key} · {ts}/4 · {inst}[/dim]")


def print_now_playing(params: dict, track_path: Optional[Path] = None):
    track_id = params.get("id", "???")
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")
    dur = DEFAULT_DURATION
    name = track_path.stem if track_path else f"track-{track_id}"
    console.print(
        f"\n  [bold green]♫  Now playing:[/bold green] {name}"
        f"  ·  {bpm} BPM  ·  {key}  ·  {dur}s"
    )
    console.print("     " + "─" * 52)


def print_status_line(params: Optional[dict], is_paused: bool, volume: int):
    """Persistent one-liner shown above every prompt so state is always visible."""
    if not params:
        return
    name = params.get("id", "?") + "  " + params.get("tags", "")[:30]
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")
    if is_paused:
        icon = "[yellow]⏸[/yellow]"
        state = "  [yellow dim][PAUSED][/yellow dim]"
    else:
        icon = "[green]♫[/green]"
        state = ""
    console.print(
        f"\n  {icon}  [dim]{name}  ·  {bpm} BPM  ·  {key}  ·  Vol: {volume}%{state}[/dim]"
    )


def print_history(radio: Radio):
    history = radio.get_history(10)
    if not history:
        console.print("  [dim]No tracks generated yet.[/dim]")
        return
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="dim", width=4)
    table.add_column("Tags", style="white")
    table.add_column("BPM", width=5)
    table.add_column("Key", width=10)
    table.add_column("Reaction", width=10)
    for t in history:
        reaction = t.get("reaction", "—")
        color = {"liked": "green", "disliked": "red", "skipped": "yellow"}.get(reaction, "dim")
        table.add_row(
            t.get("id", "?"),
            t.get("tags", "")[:45],
            str(t.get("bpm", "?")),
            t.get("key_scale", "?"),
            f"[{color}]{reaction}[/{color}]",
        )
    console.print(table)


def print_radios(radio_names: list[str], current: str):
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Radio", style="white")
    table.add_column("Tracks", width=7)
    table.add_column("Last played", width=16)
    table.add_column("", width=12)
    for name in radio_names:
        r = Radio(name)
        count = r.get_track_count()
        last = r.get_last_played_fmt()
        status = "[bold green]● active[/bold green]" if name == current else ""
        table.add_row(name, str(count), last, status)
    console.print(table)


def print_recipe(params: dict):
    console.print(Panel(
        json.dumps(params, indent=2),
        title="[bold]Track Recipe[/bold]",
        border_style="cyan",
        expand=False,
    ))


def friendly_redirect(text: str) -> bool:
    non_music = [
        "weather", "what time", "what's the time", "date", "news",
        "sports", "calculate", "translate", "google", "wikipedia",
        "stock", "currency", "tell me a joke",
    ]
    t = text.lower()
    return any(w in t for w in non_music)


# ─── Generation progress bar ──────────────────────────────────────────────────

async def show_generation_progress(
    gen_task: asyncio.Task,
    label: str = "  ◈  Generating",
    est_seconds: int = 60,
) -> tuple[bool, str]:
    """Show Rich Live progress bar until gen_task completes. Returns (success, error)."""
    start = time.monotonic()
    bar_len = 24

    with Live(console=console, refresh_per_second=8) as live:
        while not gen_task.done():
            elapsed = time.monotonic() - start
            filled = min(bar_len, int(elapsed / est_seconds * bar_len))
            bar = "[green]" + "━" * filled + "[/green][dim]" + "·" * (bar_len - filled) + "[/dim]"
            live.update(Text.from_markup(f"{label}...  [{bar}]  {elapsed:.0f}s"))
            await asyncio.sleep(0.12)

        elapsed = time.monotonic() - start
        live.update(Text.from_markup(
            f"{label}  [green]✓[/green]  {elapsed:.0f}s"
        ))
        await asyncio.sleep(0.4)

    try:
        return gen_task.result()
    except asyncio.CancelledError:
        return False, "cancelled"
    except Exception as e:
        return False, str(e)


# ─── User input — raw char reader with keyboard shortcuts ─────────────────────
#
#  Shortcuts (only when buffer is empty, i.e. first keypress):
#    Space   → toggle pause/resume
#    +  / =  → volume up 10%
#    -       → volume down 10%
#
#  Everything else works as normal terminal input (type + Enter to submit).

def _read_one_char() -> str:
    """Read exactly one character from stdin without requiring Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def get_user_input(prompt_suffix: str = "") -> str:
    """Read input char by char with non-conflicting keyboard shortcuts.

    Shortcuts (work at any point, never conflict with typed text):
      Ctrl+P       → toggle pause / resume
      ↑ (Up arrow) → volume up 10%
      ↓ (Down arrow) → volume down 10%

    Everything else is standard terminal input. Space, +, -, =, letters —
    all go straight into the buffer as normal characters.
    """
    if prompt_suffix:
        console.print(f"  [dim]{prompt_suffix}[/dim]")

    sys.stdout.write("  ❯ ")
    sys.stdout.flush()

    loop = asyncio.get_event_loop()
    buffer = ""

    while True:
        ch = await loop.run_in_executor(None, _read_one_char)

        # ── Ctrl+P → pause / resume ───────────────────────────────────────────
        if ch == "\x10":
            if player.is_playing() or player.is_paused():
                player.toggle_pause()
                if player.is_paused():
                    sys.stdout.write(f"\r  [⏸ paused — Ctrl+P to resume]                \n  ❯ {buffer}")
                else:
                    sys.stdout.write(f"\r  [▶ resumed]                                   \n  ❯ {buffer}")
                sys.stdout.flush()
            continue

        # ── Escape sequences (arrows, function keys, etc.) ────────────────────
        if ch == "\x1b":
            # Read the full CSI sequence: ESC [ <char>
            # We non-blockingly consume it so it never leaks into the buffer.
            next1 = await loop.run_in_executor(None, _read_one_char)
            if next1 == "[":
                next2 = await loop.run_in_executor(None, _read_one_char)
                if next2 == "A":       # Up arrow → volume up
                    vol = player.volume_up()
                    sys.stdout.write(f"\r  Volume: {vol}%                        \n  ❯ {buffer}")
                    sys.stdout.flush()
                elif next2 == "B":     # Down arrow → volume down
                    vol = player.volume_down()
                    sys.stdout.write(f"\r  Volume: {vol}%                        \n  ❯ {buffer}")
                    sys.stdout.flush()
                # Left/Right/other CSI sequences: silently ignored
            # Bare ESC or other sequences: silently ignored
            continue

        # ── Standard terminal input ───────────────────────────────────────────
        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return buffer.strip()

        if ch == "\x7f":  # Backspace
            if buffer:
                buffer = buffer[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue

        if ch == "\x03":  # Ctrl+C
            sys.stdout.write("\n")
            sys.stdout.flush()
            raise KeyboardInterrupt

        if ch == "\x04":  # Ctrl+D / EOF
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "quit"

        if ch >= " ":  # All printable characters — always literal
            buffer += ch
            sys.stdout.write(ch)
            sys.stdout.flush()


# ─── Radio management helpers ─────────────────────────────────────────────────

async def handle_radio_command(reaction: dict, current_radio: Radio) -> Optional[Radio]:
    cmd = reaction.get("command")
    name = reaction.get("radio_name", "")

    if cmd == "list_radios":
        radios = manager.list_radios()
        print_radios(radios, current_radio.name)
        return None

    if cmd == "switch_radio":
        if not name:
            console.print("  [yellow]Which radio? Try: switch to chill[/yellow]")
            return None
        new_radio = manager.switch_to(name)
        is_new = new_radio.is_first_run()
        if is_new:
            console.print(f"\n  [cyan]Radio '[bold]{name}[/bold]' doesn't exist — creating it.[/cyan]")
            vibe = await get_user_input()
            if vibe:
                new_radio.add_note(vibe)
                new_radio.set_direction(vibe)
        else:
            taste = new_radio.load_taste()
            count = taste.get("generation_count", 0)
            console.print(f"\n  [green]Switched to [bold]{name}[/bold] ({count} tracks generated)[/green]")
        return new_radio

    if cmd == "create_radio":
        if not name:
            console.print("  [yellow]What should the new radio be called?[/yellow]")
            return None
        new_radio = manager.switch_to(name)
        console.print(f"\n  [cyan]Created radio '[bold]{name}[/bold]'.[/cyan]")
        console.print("  What's the vibe?")
        vibe = await get_user_input()
        if vibe:
            new_radio.add_note(vibe)
            new_radio.set_direction(vibe)
        return new_radio

    if cmd == "delete_radio":
        if not name:
            console.print("  [yellow]Which radio to delete?[/yellow]")
            return None
        target = Radio(name)
        liked = len(target.load_taste().get("liked", []))
        if liked > 0:
            console.print(f"  [yellow]Radio '{name}' has {liked} liked tracks. Delete anyway?[/yellow]")
            confirm = await get_user_input("(yes/no) ")
            if confirm.strip().lower() not in ("yes", "y"):
                console.print("  Cancelled.")
                return None
        manager.delete(name)
        console.print(f"  [red]Deleted radio '{name}'.[/red]")
        if current_radio.name == name:
            new_radio = manager.switch_to("default")
            console.print("  [cyan]Switched to default radio.[/cyan]")
            return new_radio
        return None

    return None


# ─── Disk check ───────────────────────────────────────────────────────────────

def check_disk(radio: Radio) -> bool:
    free_mb = radio.disk_free_mb()
    if free_mb < 50:
        msg = format_error(
            stage="disk_check",
            raw=f"Only {free_mb:.0f}MB free. Need at least 50MB.",
        )
        console.print(f"[red]{msg}[/red]")
        console.print(
            f"  Free up space — run: [bold]ls -lh {radio.tracks_dir}[/bold]"
        )
        return False
    return True


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print_header()

    # Preflight — exits if any check fails
    ok = await run_preflight()
    if not ok:
        sys.exit(1)

    # Load active radio
    radio = manager.current_radio()

    # First run: ask for sound preference
    if radio.is_first_run():
        console.print(f"  [bold]What's your sound?[/bold] Tell me anything to get started:")
        first_input = await get_user_input()
        if first_input:
            radio.add_note(first_input)
            radio.set_direction(first_input)
        last_reaction = first_input or ""
    else:
        taste = radio.load_taste()
        count = taste.get("generation_count", 0)
        console.print(
            f"\n  [bold green]Welcome back.[/bold green]"
            f" You've generated [bold]{count}[/bold] tracks on [bold]{radio.name}[/bold]."
        )
        # Show last track so there's continuity on resume
        history = radio.get_history(1)
        if history:
            last = history[0]
            tags = last.get("tags", "")[:40]
            reaction = last.get("reaction", "neutral")
            last_played = radio.get_last_played_fmt()
            color = {"liked": "green", "disliked": "red", "skipped": "yellow"}.get(reaction, "dim")
            console.print(
                f"  [dim]Last:[/dim] {last.get('id','?')}-{tags}"
                f"  ·  [{color}]{reaction}[/{color}]"
                f"  ·  [dim]{last_played}[/dim]"
            )
        last_reaction = ""

    console.print(
        "\n  [dim]Try: love it · skip · more bass · something different"
        " · save this · what is this · history · switch to <name> · quit[/dim]"
    )
    console.print(
        "  [dim]Shortcuts: Ctrl+P = pause/resume · ↑↓ arrows = volume[/dim]\n"
    )

    last_params: Optional[dict] = None
    queued_track: Optional[Path] = None
    queued_params: Optional[dict] = None
    recent_params: list[dict] = []

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:

        # ── Wait while paused — don't start N+2 generation until resumed ─────
        while player.is_paused():
            await asyncio.sleep(0.3)

        # Disk space guard
        if not check_disk(radio):
            break

        # ── 1. Detect if LLM is stuck and needs a nudge ──────────────────────
        inject_vary = ""
        if last_params and params_are_too_similar(last_params, recent_params):
            inject_vary = " — vary significantly, change key, BPM range, and genre"

        # ── 2. Generate params (LLM, fast) ───────────────────────────────────
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

        # Stamp params with metadata
        track_id = radio.next_track_id()
        params["id"] = track_id
        params["radio"] = radio.name
        params["generated_at"] = datetime.now().isoformat()
        params["prompt"] = last_reaction[:120] if last_reaction else params.get("tags", "")

        print_incoming(params)

        # ── 3. Start ACE-Step generation in background ───────────────────────
        slug = _slugify(params.get("tags", "track"))[:40]
        next_path = radio.tracks_dir / f"{track_id}-{slug}.mp3"
        gen_task = asyncio.create_task(generate_track(params, next_path))

        # ── 4. Play queued track if ready ────────────────────────────────────
        if queued_track and queued_track.exists():
            player.play(queued_track)
            print_now_playing(queued_params or {}, queued_track)

        # ── 5. Input strategy depends on whether something is playing ────────
        #
        # Playing: show prompt immediately — generation runs silently in bg.
        #   After user submits, if gen not done → show progress bar.
        #
        # Not playing (first track or gap): show progress bar until done,
        #   then show prompt.
        #
        user_input = ""

        if player.is_playing() or player.is_paused():
            # Track is playing or paused — show status line then accept input
            print_status_line(queued_params, player.is_paused(), player._volume)
            if not gen_task.done():
                gen_hint = "◈ generating next..."
            else:
                gen_hint = ""
            user_input = await get_user_input(gen_hint)

            # If track ended (not just paused) while user was typing, note it
            if not player.is_playing() and not player.is_paused() and not user_input:
                console.print("  [dim]Track ended.[/dim]")

            # If generation still running after input — show progress
            if not gen_task.done():
                success, err = await show_generation_progress(gen_task, "  ◈  Finishing track")
            else:
                try:
                    success, err = gen_task.result()
                except Exception as e:
                    success, err = False, str(e)
        else:
            # Nothing playing — show progress bar until gen done, then prompt
            success, err = await show_generation_progress(gen_task)

            # After generation, prompt for input
            if success:
                # Will start playing at top of next loop; ask for input now
                print_status_line(params, False, player._volume)
                user_input = await get_user_input()
            else:
                # Generation failed — just continue to error handling below
                pass

        # ── 6. Handle generation failure ─────────────────────────────────────
        if not success:
            console.print(f"\n[red]{format_error('track_generation', user_input, params, err)}[/red]")
            # Retry once
            console.print("  [yellow]Retrying...[/yellow]")
            success2, err2 = await generate_track(params, next_path)
            if not success2:
                console.print(f"  [red]Retry failed: {err2}[/red]")
                last_reaction = user_input
                last_params = params
                continue

        # ── 7. Save recipe + update count ────────────────────────────────────
        recipe = {
            **params,
            "reaction": "neutral",  # updated later when user reacts
        }
        next_path.with_suffix(".json").write_text(json.dumps(recipe, indent=2))
        radio.increment_count()

        # ── 8. Handle empty input ─────────────────────────────────────────────
        if not user_input:
            if player.is_playing():
                # User hit enter with nothing — keep playing, loop
                queued_track = next_path
                queued_params = params
                last_reaction = ""
                last_params = params
                recent_params = (recent_params + [params])[-5:]
                continue
            else:
                # Not playing and no input — re-prompt without regenerating
                console.print("  [dim]Tell me how you're feeling or what to change...[/dim]")
                user_input = await get_user_input()

        # Friendly redirect for non-music chatter
        if friendly_redirect(user_input):
            console.print("  [dim]I only speak music — try 'more bass' or 'something darker' :)[/dim]")
            queued_track = next_path
            queued_params = params
            last_reaction = ""
            last_params = params
            recent_params = (recent_params + [params])[-5:]
            continue

        # ── 9. Parse reaction ─────────────────────────────────────────────────
        reaction = parse_reaction(user_input)

        # ── 10. Handle commands ───────────────────────────────────────────────

        if reaction["command"] == "quit":
            console.print("\n  [bold]Saving taste profile...[/bold] [green]Done.[/green]")
            player.stop()
            break

        # Radio management commands
        if reaction["command"] in ("switch_radio", "create_radio", "delete_radio", "list_radios"):
            new_radio = await handle_radio_command(reaction, radio)
            if new_radio:
                radio = new_radio
                last_params = None
                recent_params = []
                last_reaction = ""
                queued_track = None
                queued_params = None
                # Note: next_path/gen already done — it's queued for new radio
            continue

        if reaction["command"] == "save":
            if queued_track and queued_track.exists():
                dest = radio.mark_favorite(queued_track)
                console.print(f"  [green]✓ Saved to favorites:[/green] {dest.name}")
                # Mark recipe as favorite
                jpath = queued_track.with_suffix(".json")
                if jpath.exists():
                    _update_recipe(jpath, {"reaction": "liked", "favorited": True})
            else:
                console.print("  [dim]No track to save yet.[/dim]")

        if reaction["command"] == "what":
            if queued_params:
                print_recipe(queued_params)
            else:
                console.print("  [dim]No track info yet.[/dim]")

        if reaction["command"] == "history":
            print_history(radio)

        if reaction["command"] == "share":
            if queued_params and queued_track:
                print_recipe(queued_params)
                json_path = queued_track.with_suffix(".json")
                if json_path.exists():
                    console.print(f"  [dim]Recipe file:[/dim] {json_path}")
            else:
                console.print("  [dim]Nothing to share yet.[/dim]")

        if reaction["command"] == "open_folder":
            subprocess.run(["open", str(radio.tracks_dir)], check=False)

        if reaction["signal"] == "skipped":
            player.stop()
            console.print("  [yellow]Skipped.[/yellow]")

        # ── 11. Update taste profile ──────────────────────────────────────────
        if reaction["signal"] and queued_params:
            radio.add_reaction(queued_params, reaction["signal"])
            # Update reaction in queued track's recipe
            if queued_track:
                jpath = queued_track.with_suffix(".json")
                if jpath.exists():
                    _update_recipe(jpath, {"reaction": reaction["signal"]})

        if reaction["modifiers"]:
            for mod in reaction["modifiers"]:
                radio.add_note(mod)

        if reaction["mood"]:
            radio.set_direction(f"mood: {reaction['mood']}")

        if reaction["direction"] == "reset":
            radio.set_direction("reset — bold departure from recent tracks")

        # ── 12. Queue new track ───────────────────────────────────────────────
        queued_track = next_path
        queued_params = params
        last_reaction = user_input
        last_params = params
        recent_params = (recent_params + [params])[-5:]

    # Cleanup
    player.stop()
    console.print("\n  [bold cyan]♪[/bold cyan]  See you next time.\n")


def _update_recipe(json_path: Path, updates: dict):
    """Merge updates into an existing recipe JSON file."""
    try:
        recipe = json.loads(json_path.read_text())
        recipe.update(updates)
        json_path.write_text(json.dumps(recipe, indent=2))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        player.stop()
        rprint("\n\n  [bold]Saved your taste profile.[/bold] Goodbye.\n")
        sys.exit(0)
