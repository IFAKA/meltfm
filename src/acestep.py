"""Module 5 — ACE-Step Interface"""
import httpx

from .config import ACESTEP_HOST, ACESTEP_TIMEOUT, DEFAULT_DURATION, DEFAULT_INFER_STEPS


async def check_server(host: str = ACESTEP_HOST) -> bool:
    """GET /health — returns True if server is up."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{host}/health")
            return r.status_code == 200
    except Exception:
        return False


def _build_lyrics(params: dict) -> str:
    if params.get("instrumental", True):
        return ""
    theme = params.get("lyric_theme", "").strip()
    if not theme:
        return "[verse]\nla la la"   # fallback: same as before
    lines = [ln.strip() for ln in theme.replace(",", "\n").split("\n") if ln.strip()]
    return "[verse]\n" + "\n".join(lines[:4])


async def generate_track(params: dict, output_path) -> tuple[bool, str]:
    """
    POST /generate to ACE-Step.
    Saves audio bytes to output_path.
    Returns (success, error_message).
    """
    payload = {
        "audio_duration": DEFAULT_DURATION,
        "infer_steps": DEFAULT_INFER_STEPS,
        "prompt": params.get("tags", ""),
        "lyrics": _build_lyrics(params),
        "guidance_scale_text": 0.0 if params.get("instrumental", True) else 4.0,
        "guidance_scale_lyric": 0.0 if params.get("instrumental", True) else 2.0,
        "seed": params.get("seed", -1),
        "scheduler_type": "euler",
        "cfg_type": "cfg",
        "omega_scale": 10.0,
        "actual_seeds": [params.get("seed", -1)],
    }

    # Add BPM and key hints to tags if present
    bpm = params.get("bpm")
    key = params.get("key_scale")
    if bpm:
        payload["prompt"] += f", {bpm} bpm"
    if key:
        payload["prompt"] += f", {key.lower()}"

    try:
        async with httpx.AsyncClient(timeout=ACESTEP_TIMEOUT) as client:
            r = await client.post(f"{ACESTEP_HOST}/generate", json=payload)
            if r.status_code != 200:
                return False, f"ACE-Step HTTP {r.status_code}: {r.text[:200]}"
            output_path = output_path  # ensure it's a Path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(r.content)
            return True, ""
    except httpx.TimeoutException:
        return False, f"ACE-Step generation timed out after {ACESTEP_TIMEOUT}s"
    except httpx.HTTPError as e:
        return False, f"ACE-Step HTTP error: {e}"
    except OSError as e:
        return False, f"Failed to write track file: {e}"
