"""Interactive j/k navigators for history and radio lists."""
import asyncio
import shutil
import sys
from io import StringIO
from typing import Optional

from rich.console import Console
from rich.table import Table

from .manager import Radio
from .input import _read_nav_key


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
        from .ui import console
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
        from .ui import console
        console.print("  [dim]No radios found.[/dim]")
        return None

    idx = 0
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
