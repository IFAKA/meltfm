"""Module 4 — LLM Param Generator

System prompt sourced from:
- ACE-Step 1.5 Tutorial.md (8 caption dimensions, lyrics structure, vocal controls)
- Ace-Step_Data-Tool config/prompts.json (category limits, tag ordering)
- ace-step-ui (generation parameter defaults, style presets)
"""
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
    BPM_RELIABLE_MIN,
    BPM_RELIABLE_MAX,
    VALID_TIME_SIGS,
    VALID_KEYS,
)
from .tags import (
    validate_and_order_tags,
    validate_and_order_tags_detailed,
    GENRES, MOODS, INSTRUMENTS, VOCALS, VOCAL_FX, RAP_STYLES, TEXTURES,
    _GENRE_SET, _INSTRUMENT_SET,
)

_SYSTEM_PROMPT = """\
You are a personal music director for an AI radio station.

Your job: given the listener's taste profile and their latest message, output the NEXT track parameters as JSON.

OUTPUT ONLY valid JSON — no markdown, no explanation, no code fences.

Required JSON fields:
{
  "tags": "ordered comma-separated tags covering dimensions below",
  "lyrics": "full song lyrics with section markers (see rules)",
  "bpm": <integer 30-300>,
  "key_scale": "<note> <Major|Minor>",
  "time_signature": <2|3|4|6>,
  "vocal_language": "en",
  "instrumental": <true|false>,
  "rationale": "one sentence: what you're doing and why"
}

=== 8 CAPTION DIMENSIONS (from ACE-Step Tutorial) ===

Tags MUST follow this category order: genre → mood → instruments → vocal → texture

1. Style/Genre (1-2 tags): the primary musical style
   Examples: indie rock, jazz, trip hop, drum and bass, ambient, hip hop, folk, techno, lo-fi, deep-house, trap, synthwave

2. Emotion/Mood (1-3 tags): the emotional character and atmosphere
   Examples: dreamy, nostalgic, energetic, melancholic, euphoric, dark, intimate, triumphant, hypnotic, peaceful, hard-hitting

3. Instruments (2-4 tags): the dominant sonic palette
   Examples: electric guitar, synth pad, drums, piano, 808, strings, acoustic guitar, horns, synth bass, fender rhodes

4. Vocal Type (1 tag): the vocal style
   Options: male vocal, female vocal, male rap, female rap, spoken word, male feature vocal, female feature vocal, instrumental

5. Timbre/Texture (0-2 tags): the sonic quality and production feel
   Examples: lo-fi, warm, crisp, airy, punchy, vintage, ethereal, gritty, lush, polished, raw, saturated

Optional dimensions (capture in tags when relevant):
6. Vocal FX (0-2): autotune, heavy-autotune, harmony, vocal-harmony, pitch-shift, vocoder, whisper, echo, stutter, reverse
7. Rap Style (0-1): lyrical rap, fast rap, cloud rap, doubletime rap, gangsta rap, street rap, mumble rap
8. Era/Production: vintage, 80's, modern, lo-fi, hi-fi (use texture or genre tags)

Total tags: 7-12. Max 14.

=== LYRICS RULES ===

Structure tags: [Intro], [Verse 1], [Verse 2], [Pre-Chorus], [Chorus], [Bridge], [Outro]
Dynamic tags: [Build], [Drop], [Breakdown]
Instrumental sections: [Instrumental], [Guitar Solo], [Piano Interlude], [Instrumental Break]
Special: [Fade Out], [Silence]

Rules:
- Write 2-4 lines per section (6-10 syllables per line for best results)
- Match the vocal_language
- Use vocal control in section markers: [Chorus - anthemic], [Bridge - whispered], [Verse 1 - raspy vocal]
- Parentheses = background vocals: "We rise together (together)"
- For instrumental tracks: set lyrics to "[inst]"

=== CRITICAL RULES ===

- Do NOT put BPM, key, or tempo words in tags — use the dedicated bpm/key_scale fields
- BPM reflects the genre's natural energy (e.g., trap ~140, jazz ~90, house ~125)
- Common tempos 60-180 BPM are most stable. Keys C, G, D, Am, Em are most reliable.
- If listener liked recent tracks: keep what worked, evolve subtly
- If listener said "reset" or "something different": bold departure
- If listener gave modifiers ("more bass", "slower"): apply them directly
- If taste profile has explicit_notes: respect them always
- Never exceed ranges: BPM [30-300], time_sig [2, 3, 4, 6], key like "F# Minor" or "C Major"
- Do NOT include any field other than the 8 listed above

=== EXAMPLES ===

Rock track:
{"tags": "indie rock, nostalgic, driving, electric guitar, drums, bass guitar, male vocal, warm", "lyrics": "[Verse 1]\\nWalking down the street at dusk\\nNeon signs reflect the rain\\n\\n[Chorus - anthemic]\\nWe were young and didn't know\\nHow fast the colors fade\\n\\n[Verse 2]\\nPhotographs in cardboard boxes\\nSmiling faces, other names\\n\\n[Outro - fading]\\nColors fade away", "bpm": 118, "key_scale": "D Major", "time_signature": 4, "vocal_language": "en", "instrumental": false, "rationale": "Nostalgic indie rock with warm guitar tones and driving energy"}

Electronic track:
{"tags": "deep-house, hypnotic, groovy, synth bass, drums, hi-hat, synth pad, instrumental, warm", "lyrics": "[inst]", "bpm": 124, "key_scale": "G Minor", "time_signature": 4, "vocal_language": "en", "instrumental": true, "rationale": "Deep hypnotic house groove with warm analog feel"}

Jazz track:
{"tags": "jazz, intimate, smooth, piano, double bass, drums, male vocal, vintage", "lyrics": "[Verse 1 - smooth]\\nSmoke curls above the piano keys\\nA melody only midnight sees\\n\\n[Chorus]\\nPlay it slow, play it low\\nLet the rhythm breathe\\n\\n[Instrumental Break]\\n\\n[Outro - whispered]\\nOne more song before the dawn", "bpm": 88, "key_scale": "Eb Major", "time_signature": 4, "vocal_language": "en", "instrumental": false, "rationale": "Intimate jazz club atmosphere with vintage warmth"}

Hip hop track:
{"tags": "hip hop, hard-hitting, confident, 808, drums, synth bass, male rap, gangsta rap, gritty", "lyrics": "[Verse 1 - aggressive]\\nRolling through the city streets at night\\nEvery corner got a story right\\nStack it up and never look behind\\nGrinding daily on the frontline\\n\\n[Chorus - anthemic]\\nWe don't stop we keep it moving\\nEvery day we stay improving\\n\\n[Verse 2]\\nFrom the bottom to the top we climb\\nEvery setback is a paradigm", "bpm": 142, "key_scale": "F Minor", "time_signature": 4, "vocal_language": "en", "instrumental": false, "rationale": "Hard-hitting hip hop with confident delivery and gritty 808s"}
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
                params = _validate_and_clamp(params)
                params = _inject_vocal_preference(params, user_message)
                return params
        except Exception:
            pass

    # Fallback: keyword extraction (use last_params as base instead of hardcoded defaults)
    result = _keyword_fallback(user_message, last_params=last_params)
    result = _inject_vocal_preference(result, user_message)
    return result


def _build_context(
    user_message: str,
    taste_context: str,
    last_params: Optional[dict],
    recent_params: Optional[list[dict]],
) -> str:
    parts = ["=== TASTE PROFILE ===", taste_context]

    if last_params:
        parts.append("\n=== LAST TRACK ===")
        last_info = {
            k: last_params[k] for k in ["tags", "bpm", "key_scale", "instrumental", "rationale"]
            if k in last_params
        }
        # Extract vocal type from tags for explicit visibility
        if last_params.get("tags"):
            for v in VOCALS:
                if v in last_params["tags"]:
                    last_info["vocal_type"] = v
                    break
        parts.append(json.dumps(last_info, indent=2))

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
    """Ensure all fields are valid. Clamp out-of-range values. Normalize tags.
    Attaches params["_warnings"] with transparency info (stripped before recipe write).
    """
    warnings: list[str] = []

    # BPM — clamp to ACE-Step range
    try:
        bpm = int(params.get("bpm", 120))
        clamped = max(BPM_MIN, min(BPM_MAX, bpm))
        if clamped != bpm:
            warnings.append(f"BPM {bpm} → {clamped} (clamped to {BPM_MIN}-{BPM_MAX})")
        params["bpm"] = clamped
    except (TypeError, ValueError):
        warnings.append(f"BPM invalid → defaulted to 120")
        params["bpm"] = 120

    # Time signature
    try:
        ts = int(params.get("time_signature", 4))
        if ts not in VALID_TIME_SIGS:
            warnings.append(f"Time sig {ts} → 4 (not in {VALID_TIME_SIGS})")
            ts = 4
        params["time_signature"] = ts
    except (TypeError, ValueError):
        params["time_signature"] = 4

    # Key/scale — accept if it looks like "<note> <Major|Minor>"
    ks = params.get("key_scale", "")
    if not isinstance(ks, str) or not re.match(r"^[A-G][b#]?\s+(Major|Minor)$", ks.strip()):
        if ks:
            warnings.append(f"Key '{ks}' → A Minor (invalid format)")
        params["key_scale"] = "A Minor"

    # Tags — normalize and validate through whitelist pipeline (with transparency)
    raw_tags = params.get("tags", "")
    if isinstance(raw_tags, str) and raw_tags.strip():
        tag_result = validate_and_order_tags_detailed(raw_tags)
        params["tags"] = tag_result.tags
        for orig, reason in tag_result.dropped:
            warnings.append(f"Tag '{orig}' dropped ({reason})")
        for orig, matched in tag_result.fuzzy_matched:
            warnings.append(f"Tag '{orig}' → '{matched}' (fuzzy)")
        for tag, reason in tag_result.truncated:
            warnings.append(f"Tag '{tag}' truncated ({reason})")
    else:
        warnings.append("No tags → defaulted to 'atmospheric, experimental'")
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
            warnings.append("No lyrics → defaulted to placeholder")
            params["lyrics"] = "[Verse 1]\nla la la\n\n[Chorus]\nla la la"

    # Remove old field if present
    params.pop("lyric_theme", None)

    if warnings:
        params["_warnings"] = warnings

    return params


_VOCAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Instrumental detection (check first — "no singing" should override vocal matches)
    (re.compile(r"\bno\s+(?:singing|vocals?|voice)\b", re.I), "instrumental"),
    (re.compile(r"\bwithout\s+(?:singing|vocals?|voice)\b", re.I), "instrumental"),
    (re.compile(r"\binstrumental\s+only\b", re.I), "instrumental"),
    # Female vocal
    (re.compile(r"\bwom[ae]n?\s+sing", re.I), "female vocal"),
    (re.compile(r"\bgirl\s+(?:sing|vocal|voice)", re.I), "female vocal"),
    (re.compile(r"\bfemale\s+(?:sing|vocal|voice|singer)", re.I), "female vocal"),
    # Male vocal
    (re.compile(r"\bguy\s+(?:sing|vocal|voice)", re.I), "male vocal"),
    (re.compile(r"\bmale\s+(?:sing|vocal|voice|singer)", re.I), "male vocal"),
    (re.compile(r"\bman\s+sing", re.I), "male vocal"),
    # Rap
    (re.compile(r"\bfemale\s+rap", re.I), "female rap"),
    (re.compile(r"\bgive\s+me\s+a\s+rapper\b", re.I), "male rap"),
    (re.compile(r"\b(?:male\s+)?rapper\b", re.I), "male rap"),
    (re.compile(r"\bmale\s+rap\b", re.I), "male rap"),
    # Spoken word
    (re.compile(r"\bspoken\s+word\b", re.I), "spoken word"),
]


def _inject_vocal_preference(params: dict, user_message: str) -> dict:
    """Detect vocal preference from user message and patch tags if LLM missed it.

    Uses regex patterns to catch natural phrasing like "woman singing jazz",
    "give me a rapper", "no vocals", "instrumental only", etc.
    """
    if not user_message:
        return params

    msg = user_message.lower()
    vocal_pref = None

    # Match against pattern list (first match wins)
    for pattern, vocal_type in _VOCAL_PATTERNS:
        if pattern.search(msg):
            vocal_pref = vocal_type
            break

    if not vocal_pref:
        return params

    tags = params.get("tags", "")
    # Already has the right vocal? Skip.
    if vocal_pref in tags:
        return params

    # Replace any existing vocal tag with the preferred one
    tag_list = [t.strip() for t in tags.split(",")]
    tag_list = [t for t in tag_list if t not in VOCALS]
    tag_list.append(vocal_pref)
    params["tags"] = validate_and_order_tags(", ".join(tag_list))
    params["instrumental"] = False

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


def _word_boundary_match(term: str, text: str) -> bool:
    """Check if term appears in text as a whole word/phrase (not substring)."""
    pattern = r"(?:^|[\s,.])" + re.escape(term) + r"(?:[\s,.]|$)"
    return bool(re.search(pattern, text))


_FALLBACK_LYRICS = {
    "chill": (
        "[Verse 1 - smooth]\nDrifting through the evening air\n"
        "Nothing but the sound of rain\n\n"
        "[Chorus]\nLet it wash away\nLet it all just fade"
    ),
    "energy": (
        "[Verse 1 - powerful]\nFeel the fire burning bright\n"
        "Every step we take ignites\n\n"
        "[Chorus - anthemic]\nWe don't stop we rise\nHigher every time"
    ),
    "sad": (
        "[Verse 1 - gentle]\nEmpty rooms and fading light\n"
        "Echoes of a different time\n\n"
        "[Chorus]\nWhere did all the colors go\nI still see them in the snow"
    ),
    "default": (
        "[Verse 1]\nWalking down an open road\n"
        "Carrying an easy load\n\n"
        "[Chorus]\nLa la la la la\nLa la la la la"
    ),
}


def _keyword_fallback(user_message: str, last_params: Optional[dict] = None) -> dict:
    """Safe defaults extracted from keywords in the user's message.
    Uses tags.py whitelists for matching, runs result through validate_and_order_tags.
    When last_params is available, uses it as a starting point instead of hardcoded defaults.
    """
    msg = user_message.lower()
    found_genres: list[str] = []
    found_moods: list[str] = []
    found_instruments: list[str] = []
    found_vocal: str = "instrumental"
    found_textures: list[str] = []
    found_rap: list[str] = []

    # Match genres from whitelist (word boundary to avoid "thin" in "something")
    for g in sorted(GENRES, key=len, reverse=True):  # longest first
        if _word_boundary_match(g, msg):
            found_genres.append(g)
            if len(found_genres) >= 2:
                break

    # Match moods from whitelist
    for m in sorted(MOODS, key=len, reverse=True):
        if _word_boundary_match(m, msg):
            found_moods.append(m)
            if len(found_moods) >= 3:
                break

    # Match instruments from whitelist
    for i in sorted(INSTRUMENTS, key=len, reverse=True):
        if _word_boundary_match(i, msg):
            found_instruments.append(i)
            if len(found_instruments) >= 4:
                break

    # Match vocal type (check aliases first: "female singer" → "female vocal")
    vocal_aliases = {
        "female singer": "female vocal", "male singer": "male vocal",
        "female voice": "female vocal", "male voice": "male vocal",
        "female vocals": "female vocal", "male vocals": "male vocal",
        "with vocals": "female vocal",
    }
    for alias, target in vocal_aliases.items():
        if alias in msg:
            found_vocal = target
            break
    else:
        for v in VOCALS:
            if _word_boundary_match(v, msg):
                found_vocal = v
                break

    # Match rap styles
    for r in RAP_STYLES:
        if _word_boundary_match(r, msg):
            found_rap.append(r)
            if len(found_rap) >= 1:
                break

    # Match textures
    for t in sorted(TEXTURES, key=len, reverse=True):
        if _word_boundary_match(t, msg):
            found_textures.append(t)
            if len(found_textures) >= 2:
                break

    # Apply mood→instrument mapping if we have a mood but no instruments
    if found_moods and not found_instruments:
        for mood_key, instruments in _MOOD_INSTRUMENT_MAP.items():
            if mood_key in msg:
                found_instruments = instruments[:3]
                break

    # Use last_params as base when nothing was matched from the message
    base_bpm = last_params.get("bpm", 110) if last_params else 110
    base_key = last_params.get("key_scale", "A Minor") if last_params else "A Minor"

    if not found_genres and last_params and last_params.get("tags"):
        # Extract genres from last track's tags as fallback
        last_tags = [t.strip() for t in last_params["tags"].split(",")]
        last_genres = [t for t in last_tags if t in _GENRE_SET]
        if last_genres:
            found_genres = last_genres[:2]
    if not found_genres:
        found_genres = ["atmospheric"]

    if not found_moods:
        found_moods = ["experimental"]
    if not found_instruments and last_params and last_params.get("tags"):
        last_tags = [t.strip() for t in last_params["tags"].split(",")]
        last_instruments = [t for t in last_tags if t in _INSTRUMENT_SET]
        if last_instruments:
            found_instruments = last_instruments[:3]
    if not found_instruments:
        found_instruments = ["synth pad", "drums"]

    # Assemble and run through validation pipeline for dedup/ordering/limits
    tags_parts = (found_genres[:2] + found_moods[:3] + found_instruments[:4]
                  + [found_vocal] + found_rap[:1] + found_textures[:2])
    raw_tags = ", ".join(tags_parts)
    tags = validate_and_order_tags(raw_tags)

    # BPM: relative adjustments from base instead of fixed values
    bpm = base_bpm
    if any(w in msg for w in ["slow", "chill", "relax", "ambient", "mellow", "sleep", "dream"]):
        bpm = max(BPM_MIN, base_bpm - 30)
    elif any(w in msg for w in ["fast", "energy", "pump", "hype", "dance", "party", "trap"]):
        bpm = min(BPM_MAX, base_bpm + 30)

    is_instrumental = found_vocal == "instrumental"

    # Select mood-appropriate lyrics for vocal tracks
    lyrics = "[inst]"
    if not is_instrumental:
        detected_mood = "default"
        for mood_key in ("chill", "energy", "sad"):
            if mood_key in msg:
                detected_mood = mood_key
                break
        lyrics = _FALLBACK_LYRICS.get(detected_mood, _FALLBACK_LYRICS["default"])

    return {
        "tags": tags,
        "lyrics": lyrics,
        "bpm": bpm,
        "key_scale": base_key,
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
