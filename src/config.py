"""Module 1 — Config & Constants"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from src/)
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR = _ROOT
RADIOS_DIR = ROOT_DIR / "radios"
OUTPUT_DIR = ROOT_DIR / os.getenv("OUTPUT_DIR", "output")
ERRORS_LOG = OUTPUT_DIR / "errors.log"

# ─── External services ────────────────────────────────────────────────────────
ACESTEP_HOST = os.getenv("ACESTEP_HOST", "http://localhost:8001").rstrip("/")
ACESTEP_TIMEOUT = int(os.getenv("ACESTEP_TIMEOUT", "600"))
ACESTEP_MODEL = os.getenv("ACESTEP_MODEL", "acestep/acestep-v15-turbo-shift3")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "90"))

# ─── Generation defaults ──────────────────────────────────────────────────────
DEFAULT_DURATION = int(os.getenv("DEFAULT_DURATION", "180"))
INFERENCE_STEPS = int(os.getenv("INFERENCE_STEPS", "8"))   # 8=turbo, 50=sft
LM_TEMPERATURE = float(os.getenv("LM_TEMPERATURE", "0.7"))  # lower = more precise
LM_CFG_SCALE = float(os.getenv("LM_CFG_SCALE", "3.0"))      # LM guidance strength

# ─── Hard limits (from ACE-Step 1.5 constants.py) ────────────────────────────
BPM_MIN = 30
BPM_MAX = 300
# Note: Tutorial says "common tempos 60-180 BPM are most reliable"
BPM_RELIABLE_MIN = 60
BPM_RELIABLE_MAX = 180

VALID_TIME_SIGS = [2, 3, 4, 6]  # 2/4, 3/4, 4/4, 6/8
VALID_KEYS = [
    "C Major", "C Minor", "C# Major", "C# Minor",
    "Db Major", "Db Minor", "D Major", "D Minor",
    "D# Major", "D# Minor", "Eb Major", "Eb Minor",
    "E Major", "E Minor", "F Major", "F Minor",
    "F# Major", "F# Minor", "Gb Major", "Gb Minor",
    "G Major", "G Minor", "G# Major", "G# Minor",
    "Ab Major", "Ab Minor", "A Major", "A Minor",
    "A# Major", "A# Minor", "Bb Major", "Bb Minor",
    "B Major", "B Minor",
]

# Languages (from ACE-Step 1.5 constants.py — 51 codes)
VALID_LANGUAGES = [
    "ar", "az", "bg", "bn", "ca", "cs", "da", "de", "el", "en",
    "es", "fa", "fi", "fr", "he", "hi", "hr", "ht", "hu", "id",
    "is", "it", "ja", "ko", "la", "lt", "ms", "ne", "nl", "no",
    "pa", "pl", "pt", "ro", "ru", "sa", "sk", "sr", "sv", "sw",
    "ta", "te", "th", "tl", "tr", "uk", "ur", "vi", "yue", "zh",
    "unknown",
]

# Taste profile history limits
MAX_LIKED_HISTORY = 20
MAX_DISLIKED_HISTORY = 20
MAX_SKIPPED_HISTORY = 10

APP_VERSION = "0.2.0"

# ─── Web server ──────────────────────────────────────────────────────────────
WEB_PORT = int(os.getenv("WEB_PORT", "8888"))

# ─── Dev mode ─────────────────────────────────────────────────────────────────
DEV_MODE = os.getenv("DEV_MODE", "1").strip() in ("1", "true", "yes")

# ─── Lyrics alignment ─────────────────────────────────────────────────────────
# Whisper model for lyrics forced alignment. "tiny" is fast (~10s/track on CPU).
# Set to "" or "none" in .env to disable alignment (falls back to estimation).
WHISPER_ALIGNMENT_MODEL = os.getenv("WHISPER_ALIGNMENT_MODEL", "tiny")
