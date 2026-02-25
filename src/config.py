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

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "90"))

# ─── Generation defaults ──────────────────────────────────────────────────────
DEFAULT_DURATION = int(os.getenv("DEFAULT_DURATION", "120"))
DEFAULT_INFER_STEPS = int(os.getenv("DEFAULT_INFER_STEPS", "27"))

# ─── Hard limits ──────────────────────────────────────────────────────────────
BPM_MIN = 60
BPM_MAX = 180
VALID_TIME_SIGS = [3, 4, 6]
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

# Taste profile history limits
MAX_LIKED_HISTORY = 20
MAX_DISLIKED_HISTORY = 20
MAX_SKIPPED_HISTORY = 10

APP_VERSION = "0.1.0"

# ─── Dev mode ─────────────────────────────────────────────────────────────────
DEV_MODE = os.getenv("DEV_MODE", "1").strip() in ("1", "true", "yes")
