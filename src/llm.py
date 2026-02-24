"""Module 4 — LLM Param Generator"""
import json
import re
import random
from typing import Optional

import httpx

from .config import (
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT,
    BPM_MIN,
    BPM_MAX,
    VALID_TIME_SIGS,
    VALID_KEYS,
)

_SYSTEM_PROMPT = """\
You are a personal music director for an AI radio.

Your job: given the listener's taste profile and their latest message, output the NEXT track parameters as JSON.

OUTPUT ONLY valid JSON — no markdown, no explanation, no code fences.

Required JSON fields:
{
  "tags": "5-12 comma-separated tags: genres, instruments, moods, techniques",
  "bpm": <integer 60-180>,
  "key_scale": "<note> <Major|Minor>",
  "time_signature": <3|4|6>,
  "vocal_language": "en",
  "instrumental": <true|false>,
  "lyric_theme": "2-4 short thematic phrases or key words for vocal content — write in the same language as vocal_language. ONLY set when instrumental=false, else set to empty string.",
  "rationale": "one sentence: what you're doing and why"
}

Rules:
- BPM reflects the dominant genre's natural energy
- If listener liked recent tracks: keep what worked, evolve subtly
- If listener said "reset" or "something different": bold departure
- If listener gave modifiers ("more bass", "slower"): apply them directly
- If taste profile has explicit_notes: respect them always
- Vibe descriptions → genre tags + mood tags
- Instrument-only requests → set instrumental=true
- Contradictions → find musical middle ground
- Never exceed ranges: BPM [60-180], time_sig must be one of [3, 4, 6], key must be a standard key like "F# Minor" or "C Major"
- lyric_theme: only for vocal tracks — write 2-4 short phrases in the vocal_language that capture the thematic vibe (e.g. "Lord have mercy, Theotokos intercede, repentance, seek salvation"). NOT full lyrics. Always empty string for instrumentals.
- Do NOT include any field other than the 8 listed above
"""

_STRICT_SUFFIX = "\n\nCRITICAL: Output ONLY the JSON object. No words before or after. Start with { and end with }."


async def generate_params(
    user_message: str,
    taste_context: str,
    last_params: Optional[dict],
    recent_params: Optional[list[dict]] = None,
) -> dict:
    """
    Call Ollama to generate next track params.
    Retries 3× on bad JSON, then falls back to keyword extraction.
    """
    context = _build_context(user_message, taste_context, last_params, recent_params)

    for attempt in range(3):
        suffix = _STRICT_SUFFIX if attempt > 0 else ""
        try:
            raw = await _call_ollama(context + suffix)
            params = _parse_json(raw)
            if params:
                return _validate_and_clamp(params)
        except Exception:
            pass

    # Fallback: keyword extraction
    return _keyword_fallback(user_message)


def _build_context(
    user_message: str,
    taste_context: str,
    last_params: Optional[dict],
    recent_params: Optional[list[dict]],
) -> str:
    parts = ["=== TASTE PROFILE ===", taste_context]

    if last_params:
        parts.append("\n=== LAST TRACK ===")
        parts.append(json.dumps({
            k: last_params[k] for k in ["tags", "bpm", "key_scale", "instrumental", "rationale"]
            if k in last_params
        }, indent=2))

    if recent_params and len(recent_params) > 1:
        parts.append("\n=== RECENT TRACK PATTERNS (avoid repeating) ===")
        for p in recent_params[-3:]:
            parts.append(f"  {p.get('tags', '')} | {p.get('bpm')} BPM | {p.get('key_scale', '')}")

    parts.append(f"\n=== USER MESSAGE ===\n{user_message or '(no message — continue evolving the sound)'}")
    parts.append("\n=== YOUR RESPONSE (JSON only) ===")

    return "\n".join(parts)


async def _call_ollama(user_content: str) -> str:
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        response = await client.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
                "options": {"temperature": 0.8},
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()


def _parse_json(raw: str) -> Optional[dict]:
    """Try to extract a JSON object from the response."""
    # Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _validate_and_clamp(params: dict) -> dict:
    """Ensure all fields are valid. Clamp out-of-range values."""
    # BPM
    try:
        bpm = int(params.get("bpm", 120))
        params["bpm"] = max(BPM_MIN, min(BPM_MAX, bpm))
    except (TypeError, ValueError):
        params["bpm"] = 120

    # Time signature
    try:
        ts = int(params.get("time_signature", 4))
        params["time_signature"] = ts if ts in VALID_TIME_SIGS else 4
    except (TypeError, ValueError):
        params["time_signature"] = 4

    # Key/scale — accept if it looks like "<note> <Major|Minor>"
    ks = params.get("key_scale", "")
    if not isinstance(ks, str) or not re.match(r"^[A-G][b#]?\s+(Major|Minor)$", ks.strip()):
        params["key_scale"] = "A Minor"

    # Tags
    if not isinstance(params.get("tags"), str) or not params["tags"].strip():
        params["tags"] = "experimental, atmospheric"

    # Instrumental
    params["instrumental"] = bool(params.get("instrumental", True))

    # vocal_language default
    if not params.get("vocal_language"):
        params["vocal_language"] = "en"

    # Rationale
    if not isinstance(params.get("rationale"), str):
        params["rationale"] = "Evolving the sound"

    # Seed
    params.setdefault("seed", random.randint(0, 99999))

    # lyric_theme: stripped for instrumentals, capped at 200 chars otherwise
    if params.get("instrumental", True):
        params["lyric_theme"] = ""
    elif not isinstance(params.get("lyric_theme"), str) or not params["lyric_theme"].strip():
        params["lyric_theme"] = ""   # fallback: acestep.py will use "la la la"
    else:
        params["lyric_theme"] = params["lyric_theme"].strip()[:200]

    return params


def _keyword_fallback(user_message: str) -> dict:
    """Safe defaults extracted from keywords in the user's message."""
    msg = user_message.lower()
    tags = []

    genre_keywords = [
        "jazz", "blues", "rock", "pop", "electronic", "ambient", "classical",
        "hip hop", "hip-hop", "drill", "trap", "techno", "house", "reggae",
        "folk", "soul", "funk", "metal", "punk", "indie", "r&b", "rnb",
        "ethiopian", "afrobeat", "latin", "bossa nova", "flamenco",
        "dark", "bright", "slow", "fast", "heavy", "light", "mellow",
    ]
    for kw in genre_keywords:
        if kw in msg:
            tags.append(kw)

    bpm = 110
    if any(w in msg for w in ["slow", "chill", "relax", "ambient", "mellow"]):
        bpm = 80
    elif any(w in msg for w in ["fast", "energy", "pump", "hype", "dance"]):
        bpm = 140

    return {
        "tags": ", ".join(tags[:8]) if tags else "atmospheric, experimental",
        "bpm": bpm,
        "key_scale": "A Minor",
        "time_signature": 4,
        "vocal_language": "en",
        "instrumental": True,
        "rationale": f"Keyword fallback from: '{user_message[:60]}'",
        "seed": random.randint(0, 99999),
    }


def params_are_too_similar(params: dict, recent: list[dict], threshold: int = 3) -> bool:
    """Detect if LLM is stuck generating near-identical params."""
    if len(recent) < threshold:
        return False
    last = recent[-threshold:]
    for prev in last:
        if (
            abs((params.get("bpm") or 0) - (prev.get("bpm") or 0)) > 20
            or params.get("key_scale") != prev.get("key_scale")
        ):
            return False
    return True
