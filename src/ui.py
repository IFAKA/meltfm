"""UI display helpers — print functions, progress bars, reaction feedback."""
import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.columns import Columns

from .config import APP_VERSION, DEFAULT_DURATION
from .manager import Radio

console = Console()


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


def print_header():
    console.print(
        f"\n  [bold cyan]♪  Personal Radio[/bold cyan]"
        f"  [dim]v{APP_VERSION}[/dim]"
    )


def print_startup(radio: Radio):
    """Show polished startup panel with radio info."""
    taste = radio.load_taste()
    count = taste.get("generation_count", 0)
    fav_count = len(list(radio.favorites_dir.glob("*.mp3")))
    notes = taste.get("explicit_notes", [])

    lines: list[str] = []
    lines.append(f"  [bold]{count}[/bold] tracks · [bold]{fav_count}[/bold] favorites")

    history = radio.get_history(1)
    if history:
        last = history[0]
        tags = last.get("tags", "")[:40]
        reaction = last.get("reaction", "neutral")
        icon = {"liked": "[green]♥[/green]", "disliked": "[red]✗[/red]", "skipped": "[yellow]»[/yellow]"}.get(reaction, "[dim]·[/dim]")
        last_played = radio.get_last_played_fmt()
        lines.append(f"  Last: {tags}  {icon}  [dim]{last_played}[/dim]")

    if notes:
        mood = notes[-1][:50]
        lines.append(f"  Vibe: [italic]{mood}[/italic]")

    body = "\n".join(lines)
    console.print(Panel(
        body,
        title=f"[bold cyan]♪[/bold cyan] {radio.name}",
        border_style="cyan",
        expand=False,
        padding=(0, 1),
    ))


def print_incoming(params: dict):
    """Show what's being built — compact preview of next track."""
    tags = params.get("tags", "")
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")
    ts = params.get("time_signature", 4)
    inst = "instrumental" if params.get("instrumental") else "vocal"
    rationale = params.get("rationale", "")

    lines = [f"  [dim]{tags}[/dim]"]
    lines.append(f"  [dim]{bpm} BPM · {key} · {ts}/4 · {inst}[/dim]")
    if rationale:
        lines.append(f'  [italic dim]"{rationale}"[/italic dim]')

    console.print(Panel(
        "\n".join(lines),
        title="[bold yellow]✦[/bold yellow] Building next track",
        border_style="yellow",
        expand=False,
        padding=(0, 1),
    ))


def print_now_playing(params: dict, track_path: Optional[Path] = None):
    """Panel-based now-playing display with tags, metadata, and rationale."""
    tags = params.get("tags", "")
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")
    ts = params.get("time_signature", 4)
    inst = "instrumental" if params.get("instrumental") else params.get("vocal_language", "vocal")
    rationale = params.get("rationale", "")

    # Split tags into genre/mood line and instruments line for readability
    tag_list = [t.strip() for t in tags.split(",")]
    line1 = ", ".join(tag_list)

    lines = [f"  [bold]{line1}[/bold]"]
    lines.append(f"  {bpm} BPM · {key} · {ts}/4 · {inst}")
    if rationale:
        lines.append(f'  [italic]"{rationale}"[/italic]')

    console.print(Panel(
        "\n".join(lines),
        title="[bold green]♫[/bold green] Now playing",
        border_style="green",
        expand=False,
        padding=(0, 1),
    ))


def print_status_line(params: Optional[dict], player, is_paused: bool, volume: int, sleep_deadline: Optional[float] = None):
    """Persistent one-liner shown above every prompt so state is always visible."""
    if not params:
        return
    name = params.get("id", "?") + "  " + params.get("tags", "")[:30]
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")

    elapsed = player.elapsed
    dur = player.duration
    if dur and dur > 0:
        bar_len = 20
        filled = min(bar_len, int(elapsed / dur * bar_len))
        bar_filled = "[green]" + "━" * filled + "[/green]"
        bar_empty = "[dim]" + "·" * (bar_len - filled) + "[/dim]"
        progress = f"  {fmt_time(elapsed)}/{fmt_time(dur)} {bar_filled}{bar_empty}"
    else:
        progress = ""

    sleep_tag = ""
    if sleep_deadline is not None:
        sleep_tag = f"  ·  [yellow]⏾ Sleep {fmt_countdown(sleep_deadline)}[/yellow]"

    if is_paused:
        icon = "[yellow]⏸[/yellow]"
    else:
        icon = "[green]♫[/green]"
    console.print(
        f"\n  {icon}{progress}  [dim]{name}  ·  {bpm} BPM  ·  {key}  ·  Vol: {volume}%[/dim]{sleep_tag}"
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


def print_help():
    """Polished help screen with organized sections."""
    from rich.box import ROUNDED

    sections = [
        ("Reactions", "love it · nice · skip · nope · something different"),
        ("Modifiers", "more bass · less drums · add piano · faster · darker"),
        ("Commands", "save · info · tracks · radios · switch <name> · help · quit"),
        ("Sleep", "sleep 30 · sleep 1h · sleep off · sleep"),
        ("Shortcuts", "Space pause · ↑↓ volume · ←→ seek · Ctrl+D quit"),
    ]

    lines: list[str] = []
    for title, content in sections:
        lines.append(f"  [bold]{title}[/bold]  [dim]│[/dim]  {content}")

    console.print(Panel(
        "\n".join(lines),
        border_style="dim",
        expand=False,
        padding=(0, 1),
    ))


def show_reaction_feedback(reaction: dict):
    """Show a brief visual confirmation of what we understood from user input."""
    parts: list[str] = []

    signal = reaction.get("signal")
    if signal:
        icon = {"liked": "[green]♥ liked[/green]", "disliked": "[red]✗ disliked[/red]", "skipped": "[yellow]» skipped[/yellow]"}.get(signal, signal)
        parts.append(icon)

    mood = reaction.get("mood")
    if mood:
        parts.append(f"[magenta]☾ {mood}[/magenta]")

    modifiers = reaction.get("modifiers", [])
    if modifiers:
        parts.append("[cyan]✎ " + ", ".join(modifiers) + "[/cyan]")

    direction = reaction.get("direction")
    if direction == "reset":
        parts.append("[bold yellow]↻ fresh start[/bold yellow]")

    command = reaction.get("command")
    if command and command not in ("quit",):
        cmd_labels = {
            "save": "[green]★ saving[/green]",
            "what": "[blue]◈ showing info[/blue]",
            "history": "[blue]◈ showing history[/blue]",
            "share": "[blue]◈ sharing[/blue]",
            "open_folder": "[blue]◈ opening folder[/blue]",
            "switch_radio": "[cyan]⇄ switching radio[/cyan]",
            "create_radio": "[cyan]+ creating radio[/cyan]",
            "delete_radio": "[red]✗ deleting radio[/red]",
            "list_radios": "[blue]◈ listing radios[/blue]",
            "help": "[blue]◈ help[/blue]",
            "sleep_timer": "[yellow]⏾ sleep timer set[/yellow]",
            "cancel_sleep": "[yellow]⏾ sleep timer off[/yellow]",
            "sleep_status": "[yellow]⏾ sleep status[/yellow]",
        }
        parts.append(cmd_labels.get(command, f"[dim]{command}[/dim]"))

    if not parts:
        raw = reaction.get("raw", "").strip()
        if raw:
            parts.append(f"[dim]↳ using that for the next track[/dim]")

    if parts:
        console.print("  " + "  ".join(parts))


def friendly_redirect(text: str) -> bool:
    non_music = [
        "weather", "what time", "what's the time", "date", "news",
        "sports", "calculate", "translate", "google", "wikipedia",
        "stock", "currency", "tell me a joke",
    ]
    t = text.lower()
    return any(w in t for w in non_music)


async def show_generation_progress(
    gen_task: asyncio.Task,
    label: str = "  ◈  Generating",
    est_seconds: int = 60,
    loop_player=None,
    gen_params: Optional[dict] = None,
) -> tuple[bool, str]:
    """Show Rich Live progress bar until gen_task completes. Returns (success, error).

    If gen_params is provided, shows what's being generated.
    If loop_player is provided and has a current track, it will replay that
    track whenever it ends — filling the silence gap while waiting.
    """
    start = time.monotonic()
    bar_len = 24
    looping = loop_player is not None and loop_player.current_track is not None

    # Build context line from params
    context = ""
    if gen_params:
        tags = gen_params.get("tags", "")[:50]
        bpm = gen_params.get("bpm", "")
        key = gen_params.get("key_scale", "")
        context = f"\n     [dim]{tags} · {bpm} BPM · {key}[/dim]"

    with Live(console=console, refresh_per_second=8) as live:
        while not gen_task.done():
            if looping and not loop_player.is_playing() and not loop_player.is_paused():
                loop_player.replay()

            elapsed = time.monotonic() - start
            filled = min(bar_len, int(elapsed / est_seconds * bar_len))
            bar = "[green]" + "━" * filled + "[/green][dim]" + "·" * (bar_len - filled) + "[/dim]"
            loop_tag = "  [dim]♪ looping[/dim]" if looping else ""
            live.update(Text.from_markup(f"{label}...  {bar}  {elapsed:.0f}s{loop_tag}{context}"))
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
