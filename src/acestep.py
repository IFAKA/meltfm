"""Module 5 — ACE-Step Interface (ACE-Step 1.5 OpenRouter API)"""
import base64
import httpx

from .config import ACESTEP_HOST, ACESTEP_TIMEOUT, DEFAULT_DURATION


async def check_server(host: str = ACESTEP_HOST) -> bool:
    """GET /health — returns True if server is up."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{host}/health")
            return r.status_code == 200
    except Exception:
        return False


def _build_content(params: dict) -> str:
    """Build message content for ACE-Step 1.5 tagged mode."""
    tags = params.get("tags", "")
    instrumental = params.get("instrumental", True)

    if instrumental:
        return f"<prompt>{tags}</prompt>"

    theme = params.get("lyric_theme", "").strip()
    if theme:
        lines = [ln.strip() for ln in theme.replace(",", "\n").split("\n") if ln.strip()]
        lyrics_body = "\n".join(lines[:4])
    else:
        lyrics_body = "la la la"

    return f"<prompt>{tags}</prompt><lyrics>[verse]\n{lyrics_body}</lyrics>"


async def generate_track(params: dict, output_path) -> tuple[bool, str]:
    """
    POST /v1/chat/completions to ACE-Step 1.5.
    Saves audio bytes to output_path.
    Returns (success, error_message).
    """
    instrumental = params.get("instrumental", True)

    audio_config = {
        "duration": DEFAULT_DURATION,
        "instrumental": instrumental,
    }
    if params.get("bpm"):
        audio_config["bpm"] = params["bpm"]
    if params.get("key_scale"):
        audio_config["key_scale"] = params["key_scale"]
    if params.get("time_signature"):
        ts = params["time_signature"]
        # API expects "4/4" format; our LLM returns int (3, 4, 6)
        ts_map = {3: "3/4", 4: "4/4", 6: "6/8"}
        audio_config["time_signature"] = ts_map.get(int(ts), f"{ts}/4")
    if not instrumental and params.get("vocal_language"):
        audio_config["vocal_language"] = params["vocal_language"]

    payload = {
        "model": "acemusic/acestep-v15-turbo",
        "messages": [{"role": "user", "content": _build_content(params)}],
        "audio_config": audio_config,
        "seed": params.get("seed", -1),
    }

    try:
        async with httpx.AsyncClient(timeout=ACESTEP_TIMEOUT) as client:
            r = await client.post(f"{ACESTEP_HOST}/v1/chat/completions", json=payload)
            if r.status_code != 200:
                return False, f"ACE-Step HTTP {r.status_code}: {r.text[:200]}"

            data = r.json()
            audio_list = data["choices"][0]["message"].get("audio") or []
            if not audio_list:
                return False, "ACE-Step returned no audio"

            audio_url = audio_list[0].get("audio_url", {}).get("url", "")
            if not audio_url or not audio_url.startswith("data:"):
                return False, f"ACE-Step returned unexpected audio format: {audio_url[:80]}"

            audio_bytes = base64.b64decode(audio_url.split(",", 1)[1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_bytes)
            return True, ""

    except httpx.TimeoutException:
        return False, f"ACE-Step generation timed out after {ACESTEP_TIMEOUT}s"
    except httpx.HTTPError as e:
        return False, f"ACE-Step HTTP error: {e}"
    except (KeyError, IndexError) as e:
        return False, f"ACE-Step unexpected response format: {e}"
    except OSError as e:
        return False, f"Failed to write track file: {e}"
