"""Startup health checks — used by /api/health and engine startup."""
import asyncio
import logging
import subprocess
import os
from pathlib import Path

import httpx

from .config import OLLAMA_HOST, OLLAMA_MODEL, ACESTEP_HOST

logger = logging.getLogger(__name__)


async def check_ollama() -> dict:
    """Check if Ollama is running and has the required model."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                has_model = any(
                    m == OLLAMA_MODEL or m.startswith(OLLAMA_MODEL.split(":")[0])
                    for m in models
                )
                return {
                    "ok": True,
                    "model": OLLAMA_MODEL,
                    "model_available": has_model,
                }
    except Exception as e:
        pass
    return {"ok": False, "error": "Ollama not responding"}


async def check_acestep() -> dict:
    """Check if ACE-Step server is running."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ACESTEP_HOST}/health")
            if r.status_code == 200:
                return {"ok": True}
    except Exception:
        pass
    return {"ok": False, "error": "ACE-Step not responding"}


async def try_start_acestep() -> bool:
    """Attempt to auto-start ACE-Step. Returns True if it starts successfully."""
    acestep_dir = Path.home() / "ACE-Step"
    if not acestep_dir.exists():
        return False

    # Find uv
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
        return False

    logger.info("Auto-starting ACE-Step...")
    env = os.environ.copy()
    env["ACESTEP_LM_BACKEND"] = "mlx"
    env["ACESTEP_INIT_LLM"] = "true"
    env["TOKENIZERS_PARALLELISM"] = "false"
    subprocess.Popen(
        [uv_path, "run", "acestep-api", "--host", "127.0.0.1", "--port", "8001",
         "--lm-model-path", "acestep-5Hz-lm-4B"],
        cwd=str(acestep_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait up to 180s
    for elapsed in range(180):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"{ACESTEP_HOST}/health")
                if r.status_code == 200:
                    logger.info("ACE-Step auto-started after %ds", elapsed)
                    return True
        except Exception:
            pass

    return False


async def run_preflight() -> dict:
    """Run all startup checks. Returns dict of check results."""
    ollama = await check_ollama()
    acestep = await check_acestep()

    if not acestep["ok"]:
        started = await try_start_acestep()
        if started:
            acestep = {"ok": True, "auto_started": True}

    return {
        "ollama": ollama,
        "acestep": acestep,
        "all_ok": ollama["ok"] and acestep["ok"],
    }
