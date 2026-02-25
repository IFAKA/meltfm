"""Personal AI Radio — entry point."""
import asyncio
import difflib
import json
import os
import select as _sel
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty
from datetime import datetime
from io import StringIO
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
from src.player import Player, get_audio_duration
from src.preflight import run_preflight
from src.errors import format_error

console = Console()
player = Player()
manager = RadioManager()

METRICS_LOG = RADIOS_DIR / "metrics.jsonl"


def append_metric(entry: dict):
    """Append a single JSON line to metrics.jsonl for pipeline analysis."""
    try:
        RADIOS_DIR.mkdir(parents=True, exist_ok=True)
        with open(METRICS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


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


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def print_status_line(params: Optional[dict], is_paused: bool, volume: int):
    """Persistent one-liner shown above every prompt so state is always visible."""
    if not params:
        return
    name = params.get("id", "?") + "  " + params.get("tags", "")[:30]
    bpm = params.get("bpm", "?")
    key = params.get("key_scale", "?")

    # Progress
    elapsed = player.elapsed
    dur = player.duration
    if dur and dur > 0:
        bar_len = 20
        filled = min(bar_len, int(elapsed / dur * bar_len))
        bar_filled = "[green]" + "━" * filled + "[/green]"
        bar_empty = "[dim]" + "·" * (bar_len - filled) + "[/dim]"
        progress = f"  {_fmt_time(elapsed)}/{_fmt_time(dur)} {bar_filled}{bar_empty}"
    else:
        progress = ""

    if is_paused:
        icon = "[yellow]⏸[/yellow]"
        state = ""
    else:
        icon = "[green]♫[/green]"
        state = ""
    console.print(
        f"\n  {icon}{progress}  [dim]{name}  ·  {bpm} BPM  ·  {key}  ·  Vol: {volume}%{state}[/dim]"
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


def _render_history_table(history: list, selected: int) -> tuple[str, int]:
    """Render history table with selected row highlighted; return (ansi_str, line_count)."""
    width = shutil.get_terminal_size((80, 24)).columns
    buf = StringIO()
    c = Console(file=buf, width=width, highlight=False)
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="dim", width=4)
    table.add_column("Tags", style="white")
    table.add_column("BPM", width=5)
    table.add_column("Key", width=10)
    table.add_column("Reaction", width=10)
    for i, t in enumerate(history):
        reaction = t.get("reaction", "—")
        color = {"liked": "green", "disliked": "red", "skipped": "yellow"}.get(reaction, "dim")
        row_style = "reverse" if i == selected else ""
        table.add_row(
            t.get("id", "?"),
            t.get("tags", "")[:45],
            str(t.get("bpm", "?")),
            t.get("key_scale", "?"),
            f"[{color}]{reaction}[/{color}]",
            style=row_style,
        )
    c.print(table)
    c.print("  [dim]j/k  ↑/↓  ·  Enter load as direction  ·  q/Esc cancel[/dim]")
    rendered = buf.getvalue()
    line_count = rendered.count("\n")
    return rendered, line_count


def _render_radios_table(radio_names: list[str], current: str, selected: int) -> tuple[str, int]:
    """Render radios table with selected row highlighted; return (ansi_str, line_count)."""
    width = shutil.get_terminal_size((80, 24)).columns
    buf = StringIO()
    c = Console(file=buf, width=width, highlight=False)
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Radio", style="white")
    table.add_column("Tracks", width=7)
    table.add_column("Last played", width=16)
    table.add_column("", width=12)
    for i, name in enumerate(radio_names):
        r = Radio(name)
        count = r.get_track_count()
        last = r.get_last_played_fmt()
        status = "[bold green]● active[/bold green]" if name == current else ""
        row_style = "reverse" if i == selected else ""
        table.add_row(name, str(count), last, status, style=row_style)
    c.print(table)
    c.print("  [dim]j/k  ↑/↓  ·  Enter switch  ·  q/Esc cancel[/dim]")
    rendered = buf.getvalue()
    line_count = rendered.count("\n")
    return rendered, line_count


async def navigate_history(radio: Radio) -> Optional[str]:
    """Interactive j/k navigator for track history. Returns selected tags or None."""
    history = radio.get_history(10)
    if not history:
        console.print("  [dim]No tracks generated yet.[/dim]")
        return None

    idx = 0
    loop = asyncio.get_event_loop()
    rendered, lines = _render_history_table(history, idx)
    sys.stdout.write(rendered)
    sys.stdout.flush()

    while True:
        key = await loop.run_in_executor(None, _read_nav_key)
        if key in ("down", "j"):
            idx = min(idx + 1, len(history) - 1)
        elif key in ("up", "k"):
            idx = max(idx - 1, 0)
        elif key in ("\r", "\n"):
            sys.stdout.write(f"\033[{lines}A\033[J")
            sys.stdout.flush()
            return history[idx].get("tags", "")
        elif key in ("esc", "q"):
            sys.stdout.write(f"\033[{lines}A\033[J")
            sys.stdout.flush()
            return None
        elif key == "\x03":
            sys.stdout.write(f"\033[{lines}A\033[J")
            sys.stdout.flush()
            raise KeyboardInterrupt
        elif key == "ignore":
            continue
        new_rendered, lines = _render_history_table(history, idx)
        sys.stdout.write(f"\033[{lines}A\033[J")
        sys.stdout.write(new_rendered)
        sys.stdout.flush()


async def navigate_radios(radio_names: list[str], current: str) -> Optional[str]:
    """Interactive j/k navigator for radio list. Returns selected name or None."""
    if not radio_names:
        console.print("  [dim]No radios found.[/dim]")
        return None

    idx = 0
    # Start cursor on the current radio
    if current in radio_names:
        idx = radio_names.index(current)

    loop = asyncio.get_event_loop()
    rendered, lines = _render_radios_table(radio_names, current, idx)
    sys.stdout.write(rendered)
    sys.stdout.flush()

    while True:
        key = await loop.run_in_executor(None, _read_nav_key)
        if key in ("down", "j"):
            idx = min(idx + 1, len(radio_names) - 1)
        elif key in ("up", "k"):
            idx = max(idx - 1, 0)
        elif key in ("\r", "\n"):
            sys.stdout.write(f"\033[{lines}A\033[J")
            sys.stdout.flush()
            return radio_names[idx]
        elif key in ("esc", "q"):
            sys.stdout.write(f"\033[{lines}A\033[J")
            sys.stdout.flush()
            return None
        elif key == "\x03":
            sys.stdout.write(f"\033[{lines}A\033[J")
            sys.stdout.flush()
            raise KeyboardInterrupt
        elif key == "ignore":
            continue
        new_rendered, lines = _render_radios_table(radio_names, current, idx)
        sys.stdout.write(f"\033[{lines}A\033[J")
        sys.stdout.write(new_rendered)
        sys.stdout.flush()


def print_recipe(params: dict):
    console.print(Panel(
        json.dumps(params, indent=2),
        title="[bold]Track Recipe[/bold]",
        border_style="cyan",
        expand=False,
    ))


def _show_reaction_feedback(reaction: dict):
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
        }
        parts.append(cmd_labels.get(command, f"[dim]{command}[/dim]"))

    if not parts:
        # Free-text feedback with no recognized pattern — still acknowledge
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


# ─── Generation progress bar ──────────────────────────────────────────────────

async def show_generation_progress(
    gen_task: asyncio.Task,
    label: str = "  ◈  Generating",
    est_seconds: int = 60,
    loop_player: Optional[Player] = None,
) -> tuple[bool, str]:
    """Show Rich Live progress bar until gen_task completes. Returns (success, error).

    If loop_player is provided and has a current track, it will replay that
    track whenever it ends — filling the silence gap while waiting.
    """
    start = time.monotonic()
    bar_len = 24
    looping = loop_player is not None and loop_player.current_track is not None

    with Live(console=console, refresh_per_second=8) as live:
        while not gen_task.done():
            # Loop current track if it ended while we wait
            if looping and not loop_player.is_playing() and not loop_player.is_paused():
                loop_player.replay()

            elapsed = time.monotonic() - start
            filled = min(bar_len, int(elapsed / est_seconds * bar_len))
            bar = "[green]" + "━" * filled + "[/green][dim]" + "·" * (bar_len - filled) + "[/dim]"
            loop_tag = "  [dim]♪ looping[/dim]" if looping else ""
            live.update(Text.from_markup(f"{label}...  [{bar}]  {elapsed:.0f}s{loop_tag}"))
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


def _read_nav_key() -> str:
    """Read one logical keypress in raw mode; return a normalised action string."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            readable, _, _ = _sel.select([sys.stdin], [], [], 0.05)
            if readable:
                nxt = sys.stdin.read(1)
                if nxt == "[":
                    readable2, _, _ = _sel.select([sys.stdin], [], [], 0.05)
                    if readable2:
                        n2 = sys.stdin.read(1)
                        if n2 == "A":
                            return "up"
                        if n2 == "B":
                            return "down"
                return "ignore"
            return "esc"   # bare Escape
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def get_user_input(
    prompt_suffix: str = "",
    gen_task: Optional[asyncio.Task] = None,
    gen_start: Optional[float] = None,
    status_params: Optional[dict] = None,
) -> str:
    """Read input with cursor navigation, live generation progress, and in-place updates.

    Supports full cursor movement (←/→), insert at cursor, and backspace at cursor.

    Shortcuts:
      Space (empty buffer) or Ctrl+P → toggle pause / resume
      ↑ / ↓ arrows                   → volume up / down
      ← / → arrows                   → move cursor within input
    """
    SPINNERS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    loop = asyncio.get_event_loop()
    buf = [""]  # text buffer (mutable so closures can read/write it)
    pos = [0]   # cursor position within buf[0]
    has_hint = gen_task is not None
    _gen_start = gen_start or time.monotonic()

    if prompt_suffix and not has_hint:
        console.print(f"  [dim]{prompt_suffix}[/dim]")

    if has_hint:
        if gen_task.done():
            sys.stdout.write("  ✓ ready\n")
        else:
            sys.stdout.write(f"  {SPINNERS[0]} generating...  0s\n")
        sys.stdout.flush()

    sys.stdout.write("  ❯ ")
    sys.stdout.flush()

    stop_ev = asyncio.Event()

    def _reposition():
        """After writing full buffer to stdout, move cursor back to pos."""
        behind = len(buf[0]) - pos[0]
        if behind > 0:
            sys.stdout.write(f"\033[{behind}D")

    def _draw_hint(text: str):
        """Overwrite hint line (1 above prompt) without disrupting input."""
        sys.stdout.write(f"\033[1A\r  {text}\033[K\033[1B\r  ❯ {buf[0]}")
        _reposition()
        sys.stdout.flush()

    def _draw_status(volume: int):
        """Rewrite the ♫ status line in-place with updated volume/pause/progress."""
        if not status_params:
            return
        p = status_params
        name = p.get("id", "?") + "  " + p.get("tags", "")[:30]
        bpm = p.get("bpm", "?")
        key = p.get("key_scale", "?")
        is_p = player.is_paused()
        icon_col = "\033[33m" if is_p else "\033[32m"
        icon = "⏸" if is_p else "♫"
        pause_str = ""

        el = player.elapsed
        dur = player.duration
        if dur and dur > 0:
            bar_len = 20
            filled = min(bar_len, int(el / dur * bar_len))
            bar = f"\033[32m{'━' * filled}\033[2m{'·' * (bar_len - filled)}\033[0m"
            progress = f"  {_fmt_time(el)}/{_fmt_time(dur)} {bar}"
        else:
            progress = ""

        line = (
            f"  {icon_col}{icon}\033[0m{progress}  \033[2m{name}"
            f"  ·  {bpm} BPM  ·  {key}  ·  Vol: {volume}%{pause_str}\033[0m"
        )
        n = 2 if has_hint else 1
        sys.stdout.write(f"\033[{n}A\r{line}\033[K\033[{n}B\r  ❯ {buf[0]}")
        _reposition()
        sys.stdout.flush()

    def _delete_word_back():
        """Ctrl+W / Option+Backspace — delete one word before the cursor."""
        if pos[0] == 0:
            return
        p = pos[0]
        while p > 0 and buf[0][p - 1] == " ":   # skip trailing spaces
            p -= 1
        while p > 0 and buf[0][p - 1] != " ":   # skip word chars
            p -= 1
        removed = pos[0] - p
        buf[0] = buf[0][:p] + buf[0][pos[0]:]
        pos[0] = p
        tail = buf[0][p:]
        sys.stdout.write(f"\033[{removed}D{tail}{' ' * removed}\033[{len(tail) + removed}D")
        sys.stdout.flush()

    def _kill_to_start():
        """Ctrl+U / Cmd+Backspace — delete everything before the cursor."""
        if pos[0] == 0:
            return
        buf[0] = buf[0][pos[0]:]
        pos[0] = 0
        sys.stdout.write(f"\r  ❯ {buf[0]}\033[K")
        sys.stdout.flush()

    def _go_home():
        """Ctrl+A — move cursor to start of line."""
        if pos[0] > 0:
            sys.stdout.write(f"\033[{pos[0]}D")
            sys.stdout.flush()
            pos[0] = 0

    def _go_end():
        """Ctrl+E — move cursor to end of line."""
        behind = len(buf[0]) - pos[0]
        if behind > 0:
            sys.stdout.write(f"\033[{behind}C")
            sys.stdout.flush()
            pos[0] = len(buf[0])

    async def _spinner():
        i = 0
        while not stop_ev.is_set():
            await asyncio.sleep(0.25)
            if stop_ev.is_set():
                break
            elapsed = time.monotonic() - _gen_start
            if gen_task.done():
                _draw_hint(f"✓ ready  {elapsed:.0f}s")
                break
            _draw_hint(f"{SPINNERS[i % len(SPINNERS)]} generating...  {elapsed:.0f}s")
            i += 1

    async def _progress_tick():
        """Periodically redraw the status line with updated playback progress."""
        while not stop_ev.is_set():
            await asyncio.sleep(1)
            if stop_ev.is_set():
                break
            if status_params and (player.is_playing() or player.is_paused()):
                _draw_status(player._volume)

    spinner_t: Optional[asyncio.Task] = None
    if has_hint and not gen_task.done():
        spinner_t = asyncio.create_task(_spinner())

    progress_t: Optional[asyncio.Task] = None
    if status_params and (player.is_playing() or player.is_paused()):
        progress_t = asyncio.create_task(_progress_tick())

    try:
        while True:
            ch = await loop.run_in_executor(None, _read_one_char)

            # ── Space (empty buffer) or Ctrl+P → pause / resume ──────────────
            if ch == "\x10" or (ch == " " and not buf[0]):
                if player.is_playing() or player.is_paused():
                    player.toggle_pause()
                    if status_params:
                        _draw_status(player._volume)
                    elif has_hint:
                        label = "⏸ paused — Space to resume" if player.is_paused() else "▶ resumed"
                        _draw_hint(label)
                    else:
                        label = "⏸ paused" if player.is_paused() else "▶ resumed"
                        sys.stdout.write(f"\r  {label}  ❯ {buf[0]}\033[K")
                        _reposition()
                        sys.stdout.flush()
                continue

            # ── Escape sequences ──────────────────────────────────────────────
            if ch == "\x1b":
                next1 = await loop.run_in_executor(None, _read_one_char)
                if next1 == "[":
                    next2 = await loop.run_in_executor(None, _read_one_char)
                    if next2 == "A":           # ↑ volume up
                        vol = player.volume_up()
                        if status_params:
                            _draw_status(vol)
                        elif has_hint:
                            _draw_hint(f"Vol: {vol}%")
                        else:
                            sys.stdout.write(f"\r  Vol: {vol}%  ❯ {buf[0]}\033[K")
                            _reposition()
                            sys.stdout.flush()
                    elif next2 == "B":         # ↓ volume down
                        vol = player.volume_down()
                        if status_params:
                            _draw_status(vol)
                        elif has_hint:
                            _draw_hint(f"Vol: {vol}%")
                        else:
                            sys.stdout.write(f"\r  Vol: {vol}%  ❯ {buf[0]}\033[K")
                            _reposition()
                            sys.stdout.flush()
                    elif next2 == "C":         # → cursor right
                        if pos[0] < len(buf[0]):
                            pos[0] += 1
                            sys.stdout.write("\033[1C")
                            sys.stdout.flush()
                    elif next2 == "D":         # ← cursor left
                        if pos[0] > 0:
                            pos[0] -= 1
                            sys.stdout.write("\033[1D")
                            sys.stdout.flush()
                elif next1 == "\x7f":          # Option+Backspace → delete word back
                    _delete_word_back()
                continue

            # ── Enter ─────────────────────────────────────────────────────────
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return buf[0].strip()

            # ── Backspace (delete char before cursor) ─────────────────────────
            if ch == "\x7f":
                if pos[0] > 0:
                    buf[0] = buf[0][:pos[0] - 1] + buf[0][pos[0]:]
                    pos[0] -= 1
                    tail = buf[0][pos[0]:]
                    # Move back 1, redraw tail + space to erase old last char, reposition
                    sys.stdout.write(f"\b{tail} \033[{len(tail) + 1}D")
                    sys.stdout.flush()
                continue

            # ── Ctrl+C ────────────────────────────────────────────────────────
            if ch == "\x03":
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise KeyboardInterrupt

            # ── Ctrl+D ────────────────────────────────────────────────────────
            if ch == "\x04":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "quit"

            # ── Ctrl+W / Option+Backspace → delete word before cursor ─────────
            if ch == "\x17":
                _delete_word_back()
                continue

            # ── Ctrl+U / Cmd+Backspace → delete to start of line ─────────────
            if ch == "\x15":
                _kill_to_start()
                continue

            # ── Ctrl+A → go to beginning ──────────────────────────────────────
            if ch == "\x01":
                _go_home()
                continue

            # ── Ctrl+E → go to end ────────────────────────────────────────────
            if ch == "\x05":
                _go_end()
                continue

            # ── Printable characters (insert at cursor position) ──────────────
            if ch >= " ":
                buf[0] = buf[0][:pos[0]] + ch + buf[0][pos[0]:]
                pos[0] += 1
                tail = buf[0][pos[0]:]
                sys.stdout.write(ch + tail)
                if tail:
                    sys.stdout.write(f"\033[{len(tail)}D")
                sys.stdout.flush()

    finally:
        stop_ev.set()
        if spinner_t and not spinner_t.done():
            spinner_t.cancel()
        if progress_t and not progress_t.done():
            progress_t.cancel()


# ─── Radio management helpers ─────────────────────────────────────────────────

async def handle_radio_command(reaction: dict, current_radio: Radio) -> Optional[Radio]:
    cmd = reaction.get("command")
    name = reaction.get("radio_name", "")

    if cmd == "list_radios":
        radios = manager.list_radios()
        selected = await navigate_radios(radios, current_radio.name)
        if selected and selected != current_radio.name:
            return manager.switch_to(selected)
        return None

    if cmd == "switch_radio":
        if not name:
            console.print("  [yellow]Which radio? Try: switch to chill[/yellow]")
            return None
        existing = manager.list_radios()
        if name not in existing:
            # Check for close matches before creating
            close = difflib.get_close_matches(name, existing, n=1, cutoff=0.6)
            if close:
                console.print(f"  [yellow]Did you mean '[bold]{close[0]}[/bold]'? (yes/no)[/yellow]")
                confirm = await get_user_input()
                if confirm.strip().lower() in ("yes", "y"):
                    name = close[0]
                else:
                    console.print(f"  [yellow]Create radio '[bold]{name}[/bold]'? (yes/no)[/yellow]")
                    confirm2 = await get_user_input()
                    if confirm2.strip().lower() not in ("yes", "y"):
                        console.print("  Cancelled.")
                        return None
            else:
                console.print(f"  [yellow]Radio '[bold]{name}[/bold]' doesn't exist. Create it? (yes/no)[/yellow]")
                confirm = await get_user_input()
                if confirm.strip().lower() not in ("yes", "y"):
                    console.print("  Cancelled.")
                    return None
        new_radio = manager.switch_to(name)
        is_new = new_radio.is_first_run()
        if is_new:
            console.print(f"\n  [cyan]Created radio '[bold]{name}[/bold]'.[/cyan]")
            console.print("  What's the vibe? (e.g., lo-fi beats for studying, dark ambient, upbeat jazz)")
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
        console.print("  What's the vibe? (e.g., lo-fi beats for studying, dark ambient, upbeat jazz)")
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
        console.print(f"  [bold]What's your sound?[/bold] (e.g., lo-fi beats for studying, dark ambient, upbeat jazz)")
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

    _HELP_TEXT = (
        "\n  [dim]Try: love it · skip · more bass · something different"
        " · save this · what is this · tracks · radios · switch to <name> · help · quit[/dim]"
        "\n  [dim]Shortcuts: Space = pause/resume · ↑↓ arrows = volume[/dim]\n"
    )
    console.print(_HELP_TEXT)

    last_params: Optional[dict] = None
    queued_track: Optional[Path] = None
    queued_params: Optional[dict] = None
    recent_params: list[dict] = []
    interrupt_when_ready = False

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:

        # ── Wait while paused — accept Space / Ctrl+P to resume ──────────
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
        gen_start = time.monotonic()

        # ── 4. Play queued track if ready (skip if already playing it) ──────
        if queued_track and queued_track.exists():
            if not (player.is_playing() and player.current_track == queued_track):
                dur = get_audio_duration(queued_track)
                player.play(queued_track, duration=dur)
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
        first_play = False
        reaction = None

        if not (player.is_playing() or player.is_paused()) and not queued_track:
            console.print("  [dim]First track takes a moment to generate...[/dim]")

        if player.is_playing() or player.is_paused():
            # ── Inner input loop ──────────────────────────────────────────
            # Info commands (help, save, what, history, share, open_folder)
            # re-prompt without restarting the generation pipeline.
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
                print_status_line(queued_params, player.is_paused(), player._volume)
                user_input = await get_user_input(
                    gen_task=gen_task,
                    gen_start=gen_start,
                    status_params=queued_params,
                )
                advance_watcher.cancel()

                # Empty input while playing — treat as neutral
                if not user_input:
                    if player.is_playing():
                        break
                    console.print("  [dim]Tell me how you're feeling or what to change...[/dim]")
                    continue

                # Non-music chatter — re-prompt
                if friendly_redirect(user_input):
                    console.print("  [dim]I only speak music — try 'more bass' or 'something darker' :)[/dim]")
                    continue

                reaction = parse_reaction(user_input)
                _show_reaction_feedback(reaction)

                # ── Info commands — handle and re-prompt ──────────────────
                if reaction["command"] == "help":
                    console.print(_HELP_TEXT)
                    continue

                if reaction["command"] == "save":
                    if queued_track and queued_track.exists():
                        dest = radio.mark_favorite(queued_track)
                        console.print(f"  [green]✓ Saved to favorites:[/green] {dest.name}")
                        jpath = queued_track.with_suffix(".json")
                        if jpath.exists():
                            _update_recipe(jpath, {"reaction": "liked", "favorited": True})
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
                        break  # user picked direction → regenerate
                    continue  # escaped → re-prompt

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

                break  # quit, radio cmd, or musical reaction → proceed

            # If generation still running after input — show progress (with looping)
            if not gen_task.done():
                success, err = await show_generation_progress(
                    gen_task, "  ◈  Finishing track", loop_player=player,
                )
            else:
                try:
                    success, err = gen_task.result()
                except Exception as e:
                    success, err = False, str(e)
        else:
            # Nothing playing — show progress bar until gen done, then play + prompt
            success, err = await show_generation_progress(gen_task, loop_player=player)

            if success:
                # Start playing — don't prompt yet; loop back so the next
                # iteration kicks off track 2 generation with a visible spinner.
                dur = get_audio_duration(next_path)
                player.play(next_path, duration=dur)
                print_now_playing(params, next_path)
                first_play = True
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

        # ── 7. Build recipe dict (writing deferred — only save if track is kept) ──
        gen_elapsed = time.monotonic() - gen_start
        audio_dur = get_audio_duration(next_path) if next_path.exists() else None
        file_size = next_path.stat().st_size if next_path.exists() else None

        recipe = {
            **params,
            "reaction": "neutral",  # updated later when user reacts
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

        # ── First-play shortcut: save recipe + loop back for track 2 generation
        if first_play:
            _commit_track()
            queued_track = next_path
            queued_params = params
            # Keep last_reaction so LLM continues evolving the same direction
            last_params = params
            recent_params = (recent_params + [params])[-5:]
            continue

        # ── 8. Handle empty input ─────────────────────────────────────────────
        if not user_input:
            if player.is_playing():
                # User hit enter with nothing — keep playing, loop
                _commit_track()
                queued_track = next_path
                queued_params = params
                # Keep last_reaction so LLM continues evolving the same direction
                last_params = params
                recent_params = (recent_params + [params])[-5:]
                continue
            else:
                # Not playing and no input — re-prompt without regenerating
                console.print("  [dim]Tell me how you're feeling or what to change...[/dim]")
                user_input = await get_user_input()

        # ── 9. Parse reaction (if not already parsed in inner input loop) ─────
        if reaction is None:
            reaction = parse_reaction(user_input)
            _show_reaction_feedback(reaction)

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
                # Discard the pre-generated track (wrong radio params)
            continue

        # History direction selected from inner loop — discard pre-gen, regenerate
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

        # ── 12. Queue new track — or discard and regenerate if user wants a change
        #
        # The pre-generated N+1 track was built from the PREVIOUS reaction, so it
        # doesn't reflect modifications typed during this iteration.  If the user
        # gave us actionable direction (modifiers, mood, reset, or any free text
        # that didn't resolve to a pure signal/command), throw N+1 away and let
        # the next iteration generate fresh with the right params.
        #
        # Pure sentiment ("love it", "save", "skip") carry no musical change,
        # so N+1 is still relevant — keep it.

        wants_change = bool(
            reaction["modifiers"] or
            reaction["mood"] or
            reaction["direction"] == "reset" or
            # Free-text that didn't resolve to any recognised signal or command
            (not reaction["command"] and not reaction["signal"] and user_input)
        )

        if wants_change:
            # Cancel in-flight generation to free up the ACE-Step server
            if not gen_task.done():
                gen_task.cancel()
                try:
                    await gen_task
                except (asyncio.CancelledError, Exception):
                    pass
            # Delete any partial/complete file written by the task
            if next_path.exists():
                next_path.unlink()
            # Don't save recipe or increment count for a discarded track
            console.print("  [dim]↻ Got it — regenerating with your changes...[/dim]")
            interrupt_when_ready = True
            last_reaction = user_input
            last_params = queued_params or last_params
            recent_params = (recent_params + [queued_params or params])[-5:]
        else:
            # No change — save recipe and queue the pre-generated track
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
