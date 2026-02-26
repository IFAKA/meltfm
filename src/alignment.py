"""Forced lyrics alignment using stable-ts (stable_whisper).

After ACE-Step generates audio, this module aligns the known lyrics to the
audio using Whisper forced alignment, producing exact line-level timestamps.

Lazy-loads Whisper model on first call; cached for the process lifetime.
If stable_whisper is not installed or WHISPER_ALIGNMENT_MODEL is empty/none,
align_lyrics() returns [] gracefully — LyricsView falls back to estimation.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

from .config import WHISPER_ALIGNMENT_MODEL

logger = logging.getLogger(__name__)

# Module-level model cache — loaded once, reused for all tracks
_model = None
_model_lock: Optional[asyncio.Lock] = None

# Map ACE-Step vocal_language codes to Whisper language codes
_LANG_MAP: dict[str, Optional[str]] = {
    "yue": "zh",      # Cantonese → Chinese model
    "unknown": None,  # Let Whisper auto-detect
}


def _get_lock() -> asyncio.Lock:
    """Return (or create) the module-level asyncio.Lock."""
    global _model_lock
    if _model_lock is None:
        _model_lock = asyncio.Lock()
    return _model_lock


async def _load_model():
    """Lazy-load and cache the stable_whisper model."""
    global _model

    if _model is not None:
        return _model

    model_name = WHISPER_ALIGNMENT_MODEL.strip().lower()
    if not model_name or model_name == "none":
        return None

    async with _get_lock():
        if _model is not None:
            return _model

        try:
            import stable_whisper
            loop = asyncio.get_event_loop()
            loaded = await loop.run_in_executor(
                None, lambda: stable_whisper.load_model(model_name)
            )
            _model = loaded
            logger.info("stable_whisper model '%s' loaded", model_name)
        except ImportError:
            logger.warning(
                "stable-ts not installed — lyrics alignment disabled. "
                "Run: uv add stable-ts"
            )
            _model = None
        except Exception as e:
            logger.error("Failed to load stable_whisper model '%s': %s", model_name, e)
            _model = None

    return _model


def _parse_content_lines(lyrics: str) -> list[str]:
    """Extract singable lines, skipping [Section] markers.

    Must match the section-detection logic in LyricsView.tsx parseLyrics().
    """
    lines = []
    for line in lyrics.split("\n"):
        t = line.strip()
        if not t:
            continue
        if re.match(r"^\[.+\]$", t):
            continue
        lines.append(t)
    return lines


def _normalize(w: str) -> str:
    """Lowercase and strip non-alphanumeric chars for word matching."""
    return re.sub(r"[^\w]", "", w.lower())


def _group_words_into_lines(
    content_lines: list[str],
    flat_words: list[dict],
) -> list[dict]:
    """Map flat word timestamps (from alignment) back to lyric lines.

    Processes both sequences left-to-right. For each lyric line:
    - Tokenize into words
    - Greedily scan flat_words for matching tokens
    - Record start of first match and end of last match as the line's timestamps

    Accepts a line if at least half its tokens matched (handles vocal elisions,
    backing vocals, pronunciation variations).

    Returns list of {text, start, end} dicts. Lines that couldn't be matched
    get start=null, end=null (frontend falls back to estimation for those lines).
    """
    result = []
    word_idx = 0
    n_words = len(flat_words)

    for line_text in content_lines:
        tokens = [_normalize(w) for w in line_text.split() if _normalize(w)]
        if not tokens:
            result.append({"text": line_text, "start": None, "end": None})
            continue

        line_start = None
        line_end = None
        matched = 0
        scan = word_idx

        while scan < n_words and matched < len(tokens):
            w = _normalize(flat_words[scan].get("word", ""))
            if w == tokens[matched]:
                if matched == 0:
                    line_start = flat_words[scan].get("start")
                line_end = flat_words[scan].get("end")
                matched += 1
            elif matched > 0:
                # Broken partial match — reset, re-check this position as first token
                matched = 0
                line_start = None
                line_end = None
                w2 = _normalize(flat_words[scan].get("word", ""))
                if w2 == tokens[0]:
                    line_start = flat_words[scan].get("start")
                    line_end = flat_words[scan].get("end")
                    matched = 1
            scan += 1

        if line_start is not None and matched >= max(1, len(tokens) // 2):
            word_idx = scan
            result.append({
                "text": line_text,
                "start": round(float(line_start), 2),
                "end": round(float(line_end), 2),
            })
        else:
            result.append({"text": line_text, "start": None, "end": None})

    return result


async def align_lyrics(
    audio_path: Path,
    lyrics: str,
    vocal_language: Optional[str] = "en",
) -> list[dict]:
    """Run forced alignment on audio_path using the known lyrics.

    Returns list of {text, start, end} dicts — one per content line
    (section headers like [Verse] are excluded, matching the frontend).
    Returns [] on any failure; LyricsView will fall back to estimation.

    Args:
        audio_path: Path to the generated MP3 file.
        lyrics: Raw lyrics string (may include [Section] markers).
        vocal_language: ISO 639-1 code from LLM params (e.g. "en", "fr").
    """
    if not audio_path.exists():
        return []

    content_lines = _parse_content_lines(lyrics)
    if not content_lines:
        return []

    model = await _load_model()
    if model is None:
        return []

    # Resolve edge-case language codes
    lang = _LANG_MAP.get(vocal_language or "", vocal_language)

    # Join lines for the alignment call — stable-ts handles multi-line text
    full_text = "\n".join(content_lines)

    try:
        loop = asyncio.get_event_loop()

        def _run():
            return model.align(str(audio_path), full_text, language=lang)

        result = await loop.run_in_executor(None, _run)

        # Flatten all word objects from all segments
        flat_words: list[dict] = []
        for seg in result.segments:
            for w in getattr(seg, "words", None) or []:
                flat_words.append({
                    "word": getattr(w, "word", ""),
                    "start": getattr(w, "start", None),
                    "end": getattr(w, "end", None),
                })

        if not flat_words:
            logger.warning("align_lyrics: no words returned for %s", audio_path.name)
            return []

        timestamps = _group_words_into_lines(content_lines, flat_words)
        matched = sum(1 for t in timestamps if t["start"] is not None)
        logger.info(
            "align_lyrics: %d/%d lines matched for %s",
            matched, len(timestamps), audio_path.name,
        )
        return timestamps

    except Exception as e:
        logger.error("align_lyrics failed for %s: %s", audio_path.name, e)
        return []
