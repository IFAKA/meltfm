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
from .tags import validate_and_order_tags, GENRES, MOODS, INSTRUMENTS, VOCALS, TEXTURES

_SYSTEM_PROMPT = """\
You are a personal music director for an AI radio station.

Your job: given the listener's taste profile and their latest message, output the NEXT track parameters as JSON.

OUTPUT ONLY valid JSON — no markdown, no explanation, no code fences.

Required JSON fields:
{
  "tags": "ordered comma-separated tags covering 5 dimensions (see below)",
  "lyrics": "full song lyrics with section markers (see rules)",
  "bpm": <integer 60-180>,
  "key_scale": "<note> <Major|Minor>",
  "time_signature": <3|4|6>,
  "vocal_language": "en",
  "instrumental": <true|false>,
  "rationale": "one sentence: what you're doing and why"
}

=== TAG DIMENSIONS (order matters!) ===

Tags MUST follow this order: genre → mood → instruments → vocal → texture

1. Genre (1-2): the primary musical style
   Examples: indie rock, jazz, trip hop, drum and bass, ambient, hip hop, folk, techno

2. Mood (1-3): the emotional character
   Examples: dreamy, nostalgic, energetic, melancholic, euphoric, dark, intimate, triumphant

3. Instruments (2-4): the dominant sonic palette
   Examples: electric guitar, synth pad, drums, piano, 808, strings, acoustic guitar, brass

4. Vocal (1): the vocal type
   Options: male vocal, female vocal, male rap, female rap, vocal harmony, vocal chops, spoken word, instrumental

5. Texture (0-2): the sonic quality / production feel
   Examples: lo-fi, warm, crisp, airy, punchy, vintage, ethereal, gritty, lush

Total tags: 7-12. Max 14.

=== LYRICS RULES ===

- Use section markers: [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]
- Write 2-4 lines per section, matching the vocal_language
- Capture the mood and theme, not perfect poetry
- For instrumental tracks: set lyrics to "[inst]"
- Vocal control tags go in section markers: [Chorus - anthemic], [Bridge - whispered], [Verse 1 - raspy vocal]

=== CRITICAL RULES ===

- Do NOT put BPM, key, or tempo words in tags — use the dedicated bpm/key_scale fields
- BPM reflects the genre's natural energy (e.g., trap ~140, jazz ~90, house ~125)
- If listener liked recent tracks: keep what worked, evolve subtly
- If listener said "reset" or "something different": bold departure
- If listener gave modifiers ("more bass", "slower"): apply them directly
- If taste profile has explicit_notes: respect them always
- Never exceed ranges: BPM [60-180], time_sig [3, 4, 6], key like "F# Minor" or "C Major"
- Do NOT include any field other than the 8 listed above

=== EXAMPLES ===

Rock track:
{"tags": "indie rock, nostalgic, electric guitar, drums, bass guitar, male vocal, warm", "lyrics": "[Verse 1]\\nWalking down the street at dusk\\nNeon signs reflect the rain\\n\\n[Chorus - anthemic]\\nWe were young and didn't know\\nHow fast the colors fade\\n\\n[Verse 2]\\nPhotographs in cardboard boxes\\nSmiling faces, other names", "bpm": 118, "key_scale": "D Major", "time_signature": 4, "vocal_language": "en", "instrumental": false, "rationale": "Nostalgic indie rock with warm guitar tones"}

Electronic track:
{"tags": "deep house, hypnotic, groovy, synth bass, drums, hi-hat, synth pad, instrumental, warm", "lyrics": "[inst]", "bpm": 124, "key_scale": "G Minor", "time_signature": 4, "vocal_language": "en", "instrumental": true, "rationale": "Deep hypnotic house groove with warm analog feel"}

Jazz track:
{"tags": "jazz, intimate, smooth, piano, upright bass, drums, alto sax, male vocal, vintage", "lyrics": "[Verse 1 - smooth]\\nSmoke curls above the piano keys\\nA melody only midnight sees\\n\\n[Chorus]\\nPlay it slow, play it low\\nLet the rhythm breathe", "bpm": 88, "key_scale": "Eb Major", "time_signature": 4, "vocal_language": "en", "instrumental": false, "rationale": "Intimate jazz club atmosphere with vintage warmth"}
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

    # Extract first {...} block (handle nested braces)
    depth = 0
    start = None
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(raw[start:i + 1])
                except json.JSONDecodeError:
                    start = None

    return None


def _validate_and_clamp(params: dict) -> dict:
    """Ensure all fields are valid. Clamp out-of-range values. Normalize tags."""
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

    # Tags — normalize and validate through whitelist pipeline
    raw_tags = params.get("tags", "")
    if isinstance(raw_tags, str) and raw_tags.strip():
        params["tags"] = validate_and_order_tags(raw_tags)
    else:
        params["tags"] = "atmospheric, experimental"

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

    # Lyrics: instrumental → [inst], vocal → keep LLM lyrics (capped)
    if params.get("instrumental", True):
        params["lyrics"] = "[inst]"
    else:
        lyrics = params.get("lyrics", "")
        # Accept lyric_theme as fallback for backwards compat
        if not lyrics:
            lyrics = params.get("lyric_theme", "")
        if isinstance(lyrics, str) and lyrics.strip():
            params["lyrics"] = lyrics.strip()[:1000]
        else:
            params["lyrics"] = "[Verse 1]\nla la la\n\n[Chorus]\nla la la"

    # Remove old field if present
    params.pop("lyric_theme", None)

    return params


# ── Mood-to-instrument mapping for keyword fallback ───────────────────────────

_MOOD_INSTRUMENT_MAP = {
    "chill":  ["synth pad", "electric piano", "drums"],
    "energy": ["drums", "synth bass", "electric guitar"],
    "focus":  ["piano", "synth pad", "strings"],
    "sad":    ["piano", "strings", "cello"],
    "happy":  ["acoustic guitar", "piano", "drums"],
    "party":  ["drums", "synth bass", "808"],
    "sleep":  ["synth pad", "piano", "strings"],
}


def _keyword_fallback(user_message: str) -> dict:
    """Safe defaults extracted from keywords in the user's message.
    Uses tags.py whitelists for matching, produces properly ordered tags."""
    msg = user_message.lower()
    found_genres: list[str] = []
    found_moods: list[str] = []
    found_instruments: list[str] = []
    found_vocal: str = "instrumental"
    found_textures: list[str] = []

    # Match genres from whitelist
    for g in GENRES:
        if g in msg:
            found_genres.append(g)
            if len(found_genres) >= 2:
                break

    # Match moods from whitelist
    for m in MOODS:
        if m in msg:
            found_moods.append(m)
            if len(found_moods) >= 3:
                break

    # Match instruments from whitelist
    for i in INSTRUMENTS:
        if i in msg:
            found_instruments.append(i)
            if len(found_instruments) >= 4:
                break

    # Match vocal type
    for v in VOCALS:
        if v in msg:
            found_vocal = v
            break

    # Match textures
    for t in TEXTURES:
        if t in msg:
            found_textures.append(t)
            if len(found_textures) >= 2:
                break

    # Apply mood→instrument mapping if we have a mood but no instruments
    if found_moods and not found_instruments:
        for mood_key, instruments in _MOOD_INSTRUMENT_MAP.items():
            if mood_key in msg:
                found_instruments = instruments[:3]
                break

    # Defaults if nothing matched
    if not found_genres:
        found_genres = ["atmospheric"]
    if not found_moods:
        found_moods = ["experimental"]
    if not found_instruments:
        found_instruments = ["synth pad", "drums"]

    # Assemble in proper order
    tags_parts = found_genres[:2] + found_moods[:3] + found_instruments[:4] + [found_vocal] + found_textures[:2]
    tags = ", ".join(tags_parts)

    # BPM heuristic
    bpm = 110
    if any(w in msg for w in ["slow", "chill", "relax", "ambient", "mellow", "sleep", "dream"]):
        bpm = 80
    elif any(w in msg for w in ["fast", "energy", "pump", "hype", "dance", "party", "trap"]):
        bpm = 140

    is_instrumental = found_vocal == "instrumental"

    # Basic lyrics for vocal tracks
    lyrics = "[inst]"
    if not is_instrumental:
        lyrics = "[Verse 1]\nla la la\n\n[Chorus]\nla la la"

    return {
        "tags": tags,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": "A Minor",
        "time_signature": 4,
        "vocal_language": "en",
        "instrumental": is_instrumental,
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
