"""Module 7b — Startup Preflight Check"""
import asyncio
import subprocess
import sys
from pathlib import Path

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
        v = getattr(rich, "__version__", "ok")
        versions.append(f"rich {v}")
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
    # Already running?
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ACESTEP_HOST}/health")
            if r.status_code == 200:
                return True, f"running at {ACESTEP_HOST.replace('http://', '')}", ""
    except Exception:
        pass

    # Try to auto-start it
    acestep_dir = Path.home() / "ACE-Step"
    start_script = acestep_dir / "start_api_server_macos.sh"

    if not start_script.exists():
        return False, "not installed", (
            "ACE-Step not found. Run ./setup.sh to install it."
        )

    console.print("  [yellow]→[/yellow] ACE-Step not running — starting it... [dim](Ctrl+C to cancel)[/dim]")

    import tempfile, os
    log_file = Path(tempfile.gettempdir()) / "acestep_start.log"
    log_f = open(log_file, "w")

    # Find uv — search common locations + broad find as fallback
    uv_path = None
    for candidate in [
        Path.home() / ".local/bin/uv",
        Path.home() / ".cargo/bin/uv",
        Path("/opt/homebrew/bin/uv"),
        Path("/usr/local/bin/uv"),
    ]:
        if candidate.exists():
            uv_path = str(candidate)
            break
    if not uv_path:
        try:
            result = subprocess.run(
                ["find", str(Path.home()), "-name", "uv", "-type", "f", "-perm", "+111"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "__pycache__" not in line and line.strip():
                    uv_path = line.strip()
                    break
        except Exception:
            pass

    if not uv_path:
        log_f.close()
        return False, "uv not found", (
            "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh\n"
            "Then re-run: uv run python radio.py"
        )

    # Bypass the interactive start script — run acestep-api directly
    env = os.environ.copy()
    env["ACESTEP_LM_BACKEND"] = "mlx"
    env["TOKENIZERS_PARALLELISM"] = "false"
    subprocess.Popen(
        [uv_path, "run", "acestep-api", "--host", "127.0.0.1", "--port", "8001"],
        cwd=str(acestep_dir),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
    )

    # Wait up to 180s — covers cold start when models are already downloaded
    last_shown = ""
    for elapsed in range(180):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"{ACESTEP_HOST}/health")
                if r.status_code == 200:
                    log_f.close()
                    return True, f"auto-started at {ACESTEP_HOST.replace('http://', '')}", ""
        except Exception:
            pass

        # Show latest line from log
        try:
            lines = log_file.read_text().splitlines()
            last = next((l.strip() for l in reversed(lines) if l.strip()), "")
            if last and last != last_shown:
                last_shown = last
                console.print(f"  [dim]  [{elapsed}s] {last[:80]}[/dim]")
        except Exception:
            pass

    log_f.close()
    return False, "not ready after 3 min", (
        "First time running? You need to download the model weights first (~20-40 GB).\n"
        "Open a separate terminal and run:\n"
        "  cd ~/ACE-Step && ./start_api_server_macos.sh\n"
        "Wait for: 'API will be available at: http://127.0.0.1:8001' (takes 30-60 min)\n"
        "Then re-run: radio"
    )
