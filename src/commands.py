"""Command handlers — radio management, disk checks, metrics, recipe updates."""
import difflib
import json
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

from .config import RADIOS_DIR
from .manager import Radio, RadioManager
from .input import get_user_input
from .navigation import navigate_history, navigate_radios
from .errors import format_error

console = Console()

METRICS_LOG = RADIOS_DIR / "metrics.jsonl"


def append_metric(entry: dict):
    """Append a single JSON line to metrics.jsonl for pipeline analysis."""
    try:
        RADIOS_DIR.mkdir(parents=True, exist_ok=True)
        with open(METRICS_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


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


def update_recipe(json_path: Path, updates: dict):
    """Merge updates into an existing recipe JSON file."""
    try:
        recipe = json.loads(json_path.read_text())
        recipe.update(updates)
        json_path.write_text(json.dumps(recipe, indent=2))
    except Exception:
        pass


async def handle_radio_command(
    reaction: dict,
    current_radio: Radio,
    manager: RadioManager,
) -> Optional[Radio]:
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
            confirm = await get_user_input(prompt_suffix="(yes/no) ")
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
