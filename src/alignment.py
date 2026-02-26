"""Lyrics transcription — gets exact timestamps for what was actually sung.

Uses stable-ts (Whisper) to transcribe the generated audio. The transcribed
text IS the source of truth — it matches what you hear, not what was written.
Segments are broadcast as lyrics_sync and replace the written lyrics in the UI.

Lazy-loads Whisper model on first call; cached for the process lifetime.
Returns [] if stable-ts is not installed or WHISPER_ALIGNMENT_MODEL is empty.
"""
import asyncio
import logging
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


async def align_lyrics(
    audio_path: Path,
    lyrics: str,
    vocal_language: Optional[str] = "en",
) -> list[dict]:
    """Transcribe audio and return line-level timestamps of what was actually sung.

    Returns list of {text, start, end} dicts — one per Whisper segment.
    The text is the transcribed lyric (what was sung), not the written lyric.
    Returns [] on any failure; LyricsView falls back to estimation.
    """
    if not audio_path.exists():
        return []

    model = await _load_model()
    if model is None:
        return []

    lang = _LANG_MAP.get(vocal_language or "", vocal_language)

    try:
        loop = asyncio.get_event_loop()

        def _run():
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
