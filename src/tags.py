"""Tag whitelists, normalization, and validation for ACE-Step prompt pipeline.

Sourced from:
- Ace-Step_Data-Tool presets/moods.md (genre, mood, instrument, vocal, vocal_fx whitelists)
- Ace-Step_Data-Tool scripts/helpers/tag_processor.py (aliases, fuzzy matching, conflicts)
- Ace-Step_Data-Tool config/prompts.json (category limits, max_total_tags)
- ACE-Step 1.5 Tutorial.md (timbre/texture dimension, lyrics tags, caption structure)
"""
import difflib
import re
from dataclasses import dataclass, field

# ── Whitelists (from Ace-Step_Data-Tool presets/moods.md) ─────────────────────

GENRES = [
    "60s", "70s", "80's", "acid", "acid house", "acid lounge", "afrobeat",
    "ambiance", "ambient", "ambient rock", "ballad", "baroque", "big band",
    "bluegrass", "blues", "blues rock", "bollywood", "boogie-woogie", "bossa nova",
    "brit rock", "chill-out", "christmas", "cinematic", "classical", "country",
    "country folk", "dance", "dancehall", "deep-house", "disco", "dream pop",
    "drill", "drum and bass", "dubstep", "edm", "electro", "electronic",
    "europop", "experimental", "film score", "folk", "funk", "funky house",
    "garage", "grunge", "hardcore", "heavy metal", "hip hop", "house",
    "hybrid orchestral", "indie", "indie pop", "indie rock", "industrial",
    "jazz", "k-pop", "lo-fi", "mambo", "math rock", "metal", "neo soul",
    "new wave", "nu metal", "orchestral", "phonk", "pop", "post punk",
    "post rock", "progressive house", "psych rock", "psychedelic", "punk",
    "r&b", "rap", "reggae", "reggaeton", "rhumba", "rock", "rock and roll",
    "rockabilly", "salsa", "shoegaze", "singer songwriter", "ska", "soul",
    "swing", "synth pop", "synthwave", "techno", "trance", "trap", "trip hop",
    "vaporwave", "world",
]

MOODS = [
    "action", "adventurous", "aggressive", "ambient", "angelic", "angry",
    "atmospheric", "beautiful", "bouncy", "bright", "catchy", "charm",
    "cheerful", "childlike", "chilled", "cinematic", "clapping", "clumsy",
    "cold", "colorful", "confident", "cool", "courageous", "creepy", "cute",
    "danceable", "dancing", "danger", "daring", "dark", "deep", "depressing",
    "dirty", "downbeat", "dramatic", "dreamy", "driving", "dynamic",
    "emotional", "energetic", "epic", "ethereal", "euphoric", "evolving",
    "excited", "expansive", "experimental", "family", "feel good", "fierce",
    "frantic", "frightening", "frisky", "fun", "funny", "funky", "futuristic",
    "gangsta attitude", "gentle", "glamorous", "glitchy", "good time", "groovy",
    "hard", "hard-hitting", "haunting", "heavy", "heroic", "high-energy",
    "holiday", "hopeful", "humorous", "hypnotic", "inquisitive",
    "inspirational", "intense", "intimate", "joyful", "lonely", "lost", "love",
    "lustful", "magical", "meditative", "melancholic", "mellow", "melodic",
    "motivational", "mysterious", "narrative", "nervous", "nostalgic",
    "optimistic", "otherworldly", "party", "passionate", "peaceful", "playful",
    "poetic", "positive", "powerful", "rebellious", "relaxed", "relentless",
    "religious", "restless", "romantic", "royal", "sad", "scary", "sentimental",
    "sexy", "smooth", "soulful", "storytelling", "summer", "sunshine",
    "suspense", "thoughtful", "triumphant", "understated", "uplifting",
    "vicious", "vulnerable", "youth",
]

INSTRUMENTS = [
    "808", "acoustic bass", "acoustic drums", "acoustic guitar", "acoustic piano",
    "action strings", "african drums", "arp", "arpeggio", "atmosphere",
    "bass drum", "bass guitar", "bells", "big drums", "celesta", "cello",
    "choir", "cinematic drums", "claps", "clarinet", "classical piano",
    "deep bass", "double bass", "drums", "electric bass", "electric guitar",
    "electric piano", "electronic drums", "epic drums", "epic strings",
    "ethnic instruments", "ethnic percussion", "fender rhodes", "flute",
    "grand piano", "guitar", "hard drums", "harpsichord", "heavy bass",
    "hi-hat", "horns", "industrial drums", "keyboard", "keys", "male choir",
    "mallet", "metal guitar", "muted guitar", "oboe", "ocarina", "orchestra",
    "organ", "church organ", "pads", "percussion", "piano", "pizzicato",
    "pizzicato strings", "pluck", "samples", "sitar", "snare",
    "spanish guitar", "staccato strings", "strings", "sub bass", "synth",
    "synth arp", "synth bass", "synth bell", "synth pad", "synthesizer",
    "tabla", "taiko drums", "timpani", "trombone", "trumpets", "tuba",
    "turntables", "viola", "violin", "vocoder", "voices", "vox", "whistle",
    "women choir", "woodwinds", "world instruments",
]

VOCALS = [
    "male vocal", "female vocal", "male rap", "female rap",
    "spoken word", "male feature vocal", "female feature vocal", "instrumental",
]

VOCAL_FX = [
    "autotune", "heavy-autotune", "subtle-autotune", "harmony", "vocal-harmony",
    "doubling", "vocal-doubling", "pitch-shift", "pitch-up", "pitch-down",
    "high-pitch", "low-pitch", "vocoder", "formant-shift", "delay", "robotic",
    "whisper", "echo", "chopped", "stutter", "reverse",
]

RAP_STYLES = [
    "lyrical rap", "fast rap", "cloud rap", "doubletime rap",
    "gangsta rap", "street rap", "mumble rap",
]

# Timbre/texture (from ACE-Step 1.5 Tutorial — Timbre Texture + Production Style)
TEXTURES = [
    "airy", "bright", "clean", "crisp", "crunchy", "dark", "deep", "distorted",
    "dusty", "ethereal", "fat", "fuzzy", "glitchy", "grainy", "gritty", "heavy",
    "hi-fi", "icy", "layered", "lo-fi", "lush", "muddy", "organic", "polished",
    "punchy", "raw", "reverberant", "rich", "saturated", "sharp", "shimmery",
    "silky", "smooth", "spacious", "tape-saturated", "thick", "thin", "tight",
    "vintage", "warm", "washy", "wet", "wide",
]

# ── Aliases (from tag_processor.py _build_alias_map) ─────────────────────────

ALIASES: dict[str, str] = {
    # Genre aliases
    "hip-hop": "hip hop",
    "hiphop": "hip hop",
    "chill out": "chill-out",
    "chillout": "chill-out",
    "drum n bass": "drum and bass",
    "drum'n'bass": "drum and bass",
    "dnb": "drum and bass",
    "d&b": "drum and bass",
    "d'n'b": "drum and bass",
    "deep house": "deep-house",
    "synthpop": "synth pop",
    "electropop": "synth pop",
    "electro-pop": "synth pop",
    "rnb": "r&b",
    "r'n'b": "r&b",
    "r and b": "r&b",
    "rhythm and blues": "r&b",
    "film scores": "film score",
    "feel-good": "feel good",
    "high energy": "high-energy",
    "hard hitting": "hard-hitting",
    "lofi": "lo-fi",
    "lo fi": "lo-fi",
    "alt rock": "indie rock",
    "alternative": "indie rock",
    "alternative rock": "indie rock",
    "death metal": "heavy metal",
    "black metal": "heavy metal",
    "thrash metal": "metal",
    "prog rock": "progressive house",
    "progressive rock": "progressive house",
    "prog": "progressive house",
    "psychedelic rock": "psych rock",
    "psych": "psych rock",
    "neosoul": "neo soul",
    "neo-soul": "neo soul",
    "triphop": "trip hop",
    "trip-hop": "trip hop",
    "postrock": "post rock",
    "post-rock": "post rock",
    "postpunk": "post punk",
    "post-punk": "post punk",
    "indierock": "indie rock",
    "indiepop": "indie pop",
    "indiefolk": "folk",
    "bossanova": "bossa nova",
    "samba": "bossa nova",
    "african": "afrobeat",
    "afropop": "afrobeat",
    "afro": "afrobeat",
    "goth": "industrial",
    "dark wave": "industrial",
    "darkwave": "industrial",
    "electronica": "electronic",
    "bass music": "dubstep",
    "uk garage": "garage",
    "ukg": "garage",
    "latin pop": "salsa",
    "cumbia": "salsa",
    "latin": "salsa",
    # Instrument aliases
    "string section": "strings",
    "strings section": "strings",
    "brass": "horns",
    "brass section": "horns",
    "horn section": "horns",
    "basses": "bass guitar",
    "kicks": "bass drum",
    "choirs": "choir",
    "synths": "synth",
    "synthesizers": "synth",
    "pads": "synth pad",
    "string pad": "strings",
    "lead synth": "synth",
    "bass synth": "synth bass",
    "electric bass guitar": "electric bass",
    "acoustic bass guitar": "acoustic bass",
    "standup bass": "double bass",
    "stand-up bass": "double bass",
    "upright bass": "double bass",
    "sax": "woodwinds",
    "saxophone": "woodwinds",
    "alto sax": "woodwinds",
    "tenor sax": "woodwinds",
    "soprano sax": "woodwinds",
    "ep": "electric piano",
    "e-piano": "electric piano",
    "rhodes": "fender rhodes",
    "wurlitzer": "electric piano",
    "wurli": "electric piano",
    "keyboards": "keyboard",
    "bongos": "percussion",
    "hand drums": "percussion",
    "djembe": "african drums",
    "violins": "strings",
    "cellos": "strings",
    "violas": "strings",
    "woodwind": "woodwinds",
    "wind instruments": "woodwinds",
    "click": "hi-hat",
    "ride cymbal": "percussion",
    "crash cymbal": "percussion",
    "cymbals": "percussion",
    "steel drums": "percussion",
    "steel pan": "percussion",
    "tambourine": "percussion",
    "marimba": "mallet",
    "xylophone": "mallet",
    "vibraphone": "mallet",
    "glockenspiel": "bells",
    # Vocal aliases
    "male vocals": "male vocal",
    "female vocals": "female vocal",
    "male singer": "male vocal",
    "female singer": "female vocal",
    "male voice": "male vocal",
    "female voice": "female vocal",
    "no vocals": "instrumental",
    "no vocal": "instrumental",
    "no singing": "instrumental",
    "without vocals": "instrumental",
    "vocals": "singing",   # maps to non-whitelisted "singing" → gets dropped (real Data-Tool behavior)
    "vocal": "singing",    # same — bare "vocal" is too ambiguous
    "spoken": "spoken word",
    "spokenword": "spoken word",
    "backing vocals": "vocal-harmony",
    # Vocal FX aliases
    "pitched down": "pitch-down",
    "pitch shifted": "pitch-shift",
    "auto-tune": "autotune",
    "auto tune": "autotune",
    "talk box": "vocoder",
    "talkbox": "vocoder",
}

# ── Category config (from Data-Tool config/prompts.json) ─────────────────────

CATEGORY_LIMITS: dict[str, tuple[int, int]] = {
    "genre":       (1, 2),    # Data-Tool: (2,2) — relaxed min for generation
    "mood":        (1, 3),    # Data-Tool: (3,3) — relaxed min for generation
    "instruments": (2, 4),    # Data-Tool: (3,4) — relaxed min for generation
    "vocal":       (1, 1),    # Data-Tool: (1,1)
    "vocal_fx":    (0, 2),    # Data-Tool: (0,2)
    "rap_style":   (0, 1),    # Data-Tool: (0,1)
    "texture":     (0, 2),    # From Tutorial — not in Data-Tool
}

MAX_TOTAL_TAGS = 14
TAG_ORDER = ["genre", "mood", "instruments", "vocal", "vocal_fx", "rap_style", "texture"]

# ── Lookup structures ────────────────────────────────────────────────────────

_GENRE_SET = set(GENRES)
_MOOD_SET = set(MOODS)
_INSTRUMENT_SET = set(INSTRUMENTS)
_VOCAL_SET = set(VOCALS)
_VOCAL_FX_SET = set(VOCAL_FX)
_RAP_STYLE_SET = set(RAP_STYLES)
_TEXTURE_SET = set(TEXTURES)

# Combined whitelist for fuzzy matching: tag → category
# Built in REVERSE priority order so higher-priority categories overwrite lower ones.
# Priority: genre > mood > instruments > vocal > rap_style > vocal_fx > texture
_ALL_TAGS: dict[str, str] = {}
for _tag in TEXTURES:
    _ALL_TAGS[_tag] = "texture"
for _tag in VOCAL_FX:
    _ALL_TAGS[_tag] = "vocal_fx"
for _tag in RAP_STYLES:
    _ALL_TAGS[_tag] = "rap_style"
for _tag in VOCALS:
    _ALL_TAGS[_tag] = "vocal"
for _tag in INSTRUMENTS:
    _ALL_TAGS[_tag] = "instruments"
for _tag in MOODS:
    _ALL_TAGS[_tag] = "mood"
for _tag in GENRES:
    _ALL_TAGS[_tag] = "genre"

# Patterns to strip from tags (BPM/key/tempo/time sig don't belong in tags)
_STRIP_PATTERNS = re.compile(
    r"\b\d+\s*bpm\b|\bbpm\b|\btempo\b|\bkey of\b|"
    r"\b[A-G][b#]?\s*(?:major|minor)\b|\bfast tempo\b|\bslow tempo\b|"
    r"\btime\s+\d/\d\b",
    re.IGNORECASE,
)


def normalize_tag(tag: str) -> tuple[str | None, str | None]:
    """Normalize a single tag: lowercase, collapse whitespace, alias, fuzzy match.

    Pipeline adapted from Data-Tool tag_processor.py:
    1. Lowercase + whitespace collapse
    2. Drop if matches BPM/key/tempo pattern
    3. Alias lookup
    4. Direct whitelist match
    5. Fuzzy match (SequenceMatcher >= 0.88)

    Returns (normalized_tag, category) or (None, None) if invalid.
    """
    tag = tag.strip().lower()
    tag = re.sub(r"\s+", " ", tag)  # collapse whitespace
    tag = tag.replace("\u2018", "'").replace("\u2019", "'")  # smart quotes
    if not tag or len(tag) < 2:
        return None, None

    # Strip BPM/key/tempo mentions
    if _STRIP_PATTERNS.search(tag):
        return None, None

    # Apply alias
    if tag in ALIASES:
        tag = ALIASES[tag]

    # Direct match
    if tag in _ALL_TAGS:
        return tag, _ALL_TAGS[tag]

    # Fuzzy match (cutoff=0.88 from Data-Tool)
    candidates = list(_ALL_TAGS.keys())
    matches = difflib.get_close_matches(tag, candidates, n=1, cutoff=0.88)
    if matches:
        matched = matches[0]
        return matched, _ALL_TAGS[matched]

    return None, None


@dataclass
class TagResult:
    """Result of tag validation with transparency info."""
    tags: str
    dropped: list[tuple[str, str]] = field(default_factory=list)      # (original, reason)
    fuzzy_matched: list[tuple[str, str]] = field(default_factory=list) # (original, matched_to)
    truncated: list[tuple[str, str]] = field(default_factory=list)     # (tag, category) — over limit


def categorize_tags(raw_tags: str) -> dict[str, list[str]]:
    """Split comma-separated tags and categorize each one."""
    result: dict[str, list[str]] = {cat: [] for cat in TAG_ORDER}
    seen: set[str] = set()

    for raw in raw_tags.split(","):
        normalized, category = normalize_tag(raw)
        if normalized and category and normalized not in seen:
            seen.add(normalized)
            if category in result:
                result[category].append(normalized)

    return result


def _categorize_tags_detailed(raw_tags: str) -> tuple[dict[str, list[str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """Like categorize_tags but also returns drop/fuzzy info."""
    result: dict[str, list[str]] = {cat: [] for cat in TAG_ORDER}
    seen: set[str] = set()
    dropped: list[tuple[str, str]] = []
    fuzzy_matched: list[tuple[str, str]] = []

    for raw in raw_tags.split(","):
        raw_stripped = raw.strip()
        if not raw_stripped:
            continue
        normalized, category = normalize_tag(raw_stripped)
        if normalized is None:
            dropped.append((raw_stripped, "not in whitelist"))
            continue
        if normalized != raw_stripped.strip().lower().replace("\u2018", "'").replace("\u2019", "'"):
            # Was fuzzy-matched or aliased
            clean = re.sub(r"\s+", " ", raw_stripped.strip().lower())
            if clean != normalized and clean not in ALIASES:
                fuzzy_matched.append((raw_stripped, normalized))
        if normalized in seen:
            continue
        seen.add(normalized)
        if category in result:
            result[category].append(normalized)

    return result, dropped, fuzzy_matched


def resolve_conflicts(tags_by_category: dict[str, list[str]]) -> dict[str, list[str]]:
    """Resolve mutual exclusions (from Data-Tool tag_processor.py).

    Conflict rules:
    - instrumental conflicts with all vocal types (male/female vocal/rap, spoken word)
    - male vocal conflicts with female vocal (and vice versa)
    - male rap conflicts with female rap (and vice versa)

    Priority order: rap > vocal > spoken word > instrumental
    """
    vocals = tags_by_category.get("vocal", [])
    if len(vocals) <= 1:
        return tags_by_category

    # Priority: rap types > vocal types > spoken word > instrumental
    priority = ["male rap", "female rap", "male vocal", "female vocal",
                "male feature vocal", "female feature vocal", "spoken word", "instrumental"]

    # If instrumental is present with any vocal type, drop instrumental
    if "instrumental" in vocals and len(vocals) > 1:
        vocals = [v for v in vocals if v != "instrumental"]

    # If conflicting pairs exist, keep highest priority
    conflict_pairs = [
        ({"male vocal", "female vocal"}),
        ({"male rap", "female rap"}),
    ]
    for pair in conflict_pairs:
        present = [v for v in vocals if v in pair]
        if len(present) > 1:
            # Keep the one that appears first in priority
            keeper = min(present, key=lambda v: priority.index(v) if v in priority else 99)
            vocals = [v for v in vocals if v not in pair or v == keeper]

    tags_by_category["vocal"] = vocals[:1]  # max 1 vocal type
    return tags_by_category


def validate_and_order_tags_detailed(raw_tags: str) -> TagResult:
    """Full pipeline with transparency: returns TagResult with drop/fuzzy/truncation info."""
    by_cat, dropped, fuzzy_matched = _categorize_tags_detailed(raw_tags)
    by_cat = resolve_conflicts(by_cat)

    truncated: list[tuple[str, str]] = []

    # Enforce per-category max limits
    for cat in TAG_ORDER:
        _, max_count = CATEGORY_LIMITS[cat]
        if len(by_cat[cat]) > max_count:
            for tag in by_cat[cat][max_count:]:
                truncated.append((tag, f"{cat} limit ({max_count})"))
            by_cat[cat] = by_cat[cat][:max_count]

    # Assemble in order
    ordered: list[str] = []
    for cat in TAG_ORDER:
        ordered.extend(by_cat[cat])

    # Enforce total limit
    if len(ordered) > MAX_TOTAL_TAGS:
        for tag in ordered[MAX_TOTAL_TAGS:]:
            truncated.append((tag, f"total limit ({MAX_TOTAL_TAGS})"))
        ordered = ordered[:MAX_TOTAL_TAGS]

    tags_str = ", ".join(ordered) if ordered else "atmospheric, experimental"
    return TagResult(tags=tags_str, dropped=dropped, fuzzy_matched=fuzzy_matched, truncated=truncated)


def validate_and_order_tags(raw_tags: str) -> str:
    """Full pipeline: split → normalize → categorize → resolve conflicts → enforce limits → order → rejoin."""
    return validate_and_order_tags_detailed(raw_tags).tags
