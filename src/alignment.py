"""Lyrics alignment — gets exact timestamps for each line of the written lyrics.

Uses stable-ts (Whisper) to align the written lyrics against the generated audio.
model.align() is used when available: it takes the written lyrics as reference and
finds exactly when each phrase appears in the audio, producing accurate per-line
timestamps that match what the user sees in the LyricsView.

Falls back to model.transcribe() if align() is unavailable or fails.

Lazy-loads Whisper model on first call; cached for the process lifetime.
Returns [] if stable-ts is not installed or WHISPER_ALIGNMENT_MODEL is empty.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

from .config import WHISPER_ALIGNMENT_MODEL

logger = logging.getLogger(__name__)

_model = None
_model_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
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
            logger.warning("stable-ts not installed — lyrics sync disabled")
            _model = None
        except Exception as e:
            logger.error("Failed to load stable_whisper model: %s", e)
            _model = None

    return _model


# ACE-Step vocal_language codes that need remapping for Whisper
_LANG_MAP: dict[str, Optional[str]] = {
    "yue": "zh",
    "unknown": None,  # auto-detect
}

# Matches section markers like [Verse 1], [Chorus], [Bridge - whispered], etc.
_SECTION_MARKER_RE = re.compile(r"^\[.*\]$")


def _strip_section_markers(lyrics: str) -> str:
    """Remove section/structural markers before passing lyrics to align().

    Markers like [Verse 1] or [Chorus] are LLM/ACE-Step formatting — Whisper
    never hears them, so including them confuses forced alignment.
    """
    lines = [
        line for line in lyrics.splitlines()
        if line.strip() and not _SECTION_MARKER_RE.match(line.strip())
    ]
    return "\n".join(lines)


async def align_lyrics(
    audio_path: Path,
    lyrics: str,
    vocal_language: Optional[str] = "en",
) -> list[dict]:
    """Align written lyrics to audio and return per-segment timestamps.

    Uses model.align() (forced alignment) when available: maps written lyrics
    to the audio timeline, giving accurate timestamps for each line.
    Falls back to model.transcribe() if align() is unavailable.

    Returns list of {text, start, end} dicts — one per Whisper segment.
    Returns [] on any failure.
    """
    if not audio_path.exists():
        return []

    model = await _load_model()
    if model is None:
        return []

    lang = _LANG_MAP.get(vocal_language or "", vocal_language)

    try:
        loop = asyncio.get_event_loop()
        clean_lyrics = _strip_section_markers(lyrics)

        def _run():
            # Prefer forced alignment: align written lyrics to audio for accurate
            # per-line timestamps. Falls back to transcription if unavailable.
            if clean_lyrics and hasattr(model, "align"):
                try:
                    return model.align(str(audio_path), clean_lyrics, language=lang)
                except Exception as align_err:
                    logger.warning(
                        "align() failed for %s (%s) — falling back to transcribe",
                        audio_path.name, align_err,
                    )
            return model.transcribe(str(audio_path), language=lang)

        result = await loop.run_in_executor(None, _run)

        timestamps = []
        for seg in result.segments:
            text = seg.text.strip()
            if not text:
                continue
            timestamps.append({
                "text": text,
                "start": round(float(seg.start), 2),
                "end": round(float(seg.end), 2),
            })

        logger.info(
            "align_lyrics: %d segments transcribed for %s",
            len(timestamps), audio_path.name,
        )
        return timestamps

    except Exception as e:
        logger.error("align_lyrics failed for %s: %s", audio_path.name, e)
        return []
