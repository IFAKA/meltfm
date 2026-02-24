"""Module 7b — Startup Preflight Check"""
import sys

import httpx
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from .config import OLLAMA_HOST, OLLAMA_MODEL, ACESTEP_HOST, APP_VERSION

console = Console()


async def run_preflight() -> bool:
    """
    Run all startup checks. Print results. Return True only if ALL pass.
    """
    console.print(f"\n  [bold]♪  Personal Radio v{APP_VERSION}[/bold] — preflight check\n")

    checks = [
        ("Python deps", _check_python_deps),
        ("Ollama daemon", _check_ollama_daemon),
        ("LLM model", _check_ollama_model),
        ("ACE-Step server", _check_acestep),
    ]

    results = []
    for i, (label, fn) in enumerate(checks, 1):
        ok, msg, fix = await fn()
        results.append((ok, label, msg, fix))
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        dot_count = 30 - len(label)
        dots = "." * max(dot_count, 3)
        status = f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]"
        console.print(f"  [{i}/{len(checks)}] {label} {dots} {icon} {status}")

    # Print fix instructions for any failures
    failures = [(label, fix) for ok, label, _, fix in results if not ok and fix]
    if failures:
        console.print("")
        for label, fix in failures:
            console.print(f"  [yellow]Fix for {label}:[/yellow]")
            for line in fix.strip().splitlines():
                console.print(f"    {line}")
            console.print("")
        console.print("  Then re-run: [bold]uv run python radio.py[/bold]\n")
        return False

    console.print("")
    return True


async def _check_python_deps() -> tuple[bool, str, str]:
    missing = []
    versions = []
    try:
        import httpx as hx
        versions.append(f"httpx {hx.__version__}")
    except ImportError:
        missing.append("httpx")

    try:
        import rich
        versions.append(f"rich {rich.__version__}")
    except ImportError:
        missing.append("rich")

    try:
        import dotenv
        versions.append("python-dotenv")
    except ImportError:
        missing.append("python-dotenv")

    if missing:
        return False, f"missing: {', '.join(missing)}", "Run: uv sync"
    return True, ", ".join(versions), ""


async def _check_ollama_daemon() -> tuple[bool, str, str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                return True, f"running at {OLLAMA_HOST.replace('http://', '')}", ""
    except Exception:
        pass
    fix = (
        "Ollama is not running. Start it with:\n"
        "  ollama serve\n"
        "Or if installed via Homebrew:\n"
        "  brew services start ollama"
    )
    return False, "not responding", fix


async def _check_ollama_model() -> tuple[bool, str, str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                # Check for exact or prefix match (e.g. "llama3.2:3b" matches "llama3.2:3b")
                if any(m == OLLAMA_MODEL or m.startswith(OLLAMA_MODEL.split(":")[0]) for m in models):
                    return True, f"{OLLAMA_MODEL} available", ""
                return False, f"{OLLAMA_MODEL} not found", f"Pull it: ollama pull {OLLAMA_MODEL}"
    except Exception:
        pass
    return False, "can't check (Ollama not running)", ""


async def _check_acestep() -> tuple[bool, str, str]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ACESTEP_HOST}/health")
            if r.status_code == 200:
                return True, f"running at {ACESTEP_HOST.replace('http://', '')}", ""
    except Exception:
        pass

    fix = (
        "ACE-Step is not running. Start it with:\n"
        "  cd ~/ACE-Step && ./start_api_server_macos.sh\n\n"
        "Wait for: API will be available at: http://127.0.0.1:8001\n"
        "(First run downloads model weights — ~20-40 GB)"
    )
    return False, "not responding at localhost:8001", fix
