"""Tag whitelists, normalization, and validation for ACE-Step prompt pipeline.

Adapted from:
- Ace-Step_Data-Tool presets/moods.md (whitelists)
- Ace-Step_Data-Tool tag_processor.py (normalization, fuzzy matching, ordering)
- ACE-Step 1.5 Tutorial.md (tag dimensions, vocal controls)
"""
import difflib
import re

# ── Whitelists ────────────────────────────────────────────────────────────────

GENRES = [
    "acoustic", "afrobeat", "ambient", "atmospheric", "bluegrass", "blues",
    "bossa nova", "breakbeat", "britpop", "celtic", "chillwave", "choir",
    "cinematic", "classical", "country", "dance", "dark ambient", "deep house",
    "disco", "downtempo", "dream pop", "drill", "drum and bass", "dub",
    "dubstep", "edm", "electro", "electronic", "emo", "ethereal", "experimental",
    "flamenco", "folk", "funk", "future bass", "garage", "gospel", "grime",
    "grunge", "hardcore", "hardstyle", "hip hop", "house", "idm", "indie",
    "indie folk", "indie pop", "indie rock", "industrial", "j-pop", "jazz",
    "k-pop", "latin", "lo-fi", "lounge", "math rock", "metal", "minimal",
    "neo soul", "new wave", "noise", "orchestral", "phonk", "pop", "pop rock",
    "post punk", "post rock", "progressive", "psych rock", "punk", "r&b",
    "rap", "reggae", "reggaeton", "rock", "shoegaze", "ska", "soul",
    "synthpop", "synth pop", "techno", "trance", "trap", "trip hop",
    "vaporwave", "world",
]

MOODS = [
    "adventurous", "aggressive", "ambient", "angelic", "angry", "anxious",
    "atmospheric", "beautiful", "blissful", "bouncy", "breezy", "bright",
    "brooding", "calm", "carefree", "celebratory", "cheerful", "cinematic",
    "contemplative", "cool", "cosmic", "cozy", "dark", "deep", "defiant",
    "delicate", "dramatic", "dreamy", "driving", "dynamic", "eerie",
    "elegant", "emotional", "energetic", "epic", "ethereal", "euphoric",
    "exotic", "fierce", "floating", "funky", "gentle", "gloomy", "graceful",
    "gritty", "groovy", "haunting", "heartfelt", "heavy", "hopeful",
    "hypnotic", "intense", "intimate", "introspective", "joyful", "lazy",
    "lively", "lonely", "lush", "majestic", "meditative", "melancholic",
    "mellow", "menacing", "mysterious", "nocturnal", "nostalgic", "ominous",
    "optimistic", "passionate", "peaceful", "playful", "powerful", "pulsing",
    "raw", "rebellious", "reflective", "relaxed", "romantic", "sad",
    "sensual", "serene", "shimmering", "smooth", "sombre", "soothing",
    "spacious", "spiritual", "sultry", "suspenseful", "sweet", "tender",
    "tense", "triumphant", "upbeat", "uplifting", "urgent", "vibrant",
    "warm", "wistful", "yearning",
]

INSTRUMENTS = [
    "808", "accordion", "acoustic guitar", "alto sax", "banjo", "bass",
    "bass guitar", "bassoon", "bells", "brass", "cello", "choir",
    "clarinet", "congas", "cymbals", "distorted guitar", "double bass",
    "drum machine", "drums", "electric bass", "electric guitar",
    "electric piano", "fiddle", "flute", "french horn", "glockenspiel",
    "harp", "harpsichord", "hi-hat", "horns", "keys", "kick drum",
    "mandolin", "marimba", "mellotron", "moog", "oboe", "organ",
    "pad", "percussion", "piano", "plucked strings", "rhodes",
    "sitar", "snare", "steel drum", "strings", "sub bass", "synth",
    "synth bass", "synth lead", "synth pad", "synth strings", "tabla",
    "tambourine", "tenor sax", "theremin", "timpani", "trombone",
    "trumpet", "tuba", "ukulele", "upright bass", "vibraphone", "viola",
    "violin", "vocoder", "woodwinds", "wurlitzer", "xylophone",
]

VOCALS = [
    "male vocal", "female vocal", "male rap", "female rap",
    "vocal harmony", "vocal chops", "spoken word", "instrumental",
]

VOCAL_FX = [
    "autotune", "chorus effect", "delay throw", "distorted vocal",
    "double tracked", "echo", "falsetto", "filtered vocal",
    "harmony", "layered vocals", "megaphone", "octave vocal",
    "pitch-shift", "reverb vocal", "robotic vocal", "slap-back",
    "telephone vocal", "vocoder", "vocal fry", "whisper vocal",
    "wide stereo vocal",
]

TEXTURES = [
    "airy", "analog", "atmospheric", "bitcrushed", "bright", "clean",
    "compressed", "crisp", "crunchy", "dark", "deep", "dense", "digital",
    "distorted", "dry", "dusty", "ethereal", "fat", "filtered", "fizzy",
    "full", "fuzzy", "glitchy", "grainy", "gritty", "heavy", "hollow",
    "icy", "layered", "light", "lo-fi", "lush", "metallic", "muddy",
    "organic", "polished", "punchy", "raw", "resonant", "reverberant",
    "rich", "saturated", "sharp", "shimmery", "silky", "smooth", "soft",
    "spacious", "sparse", "stuttered", "tape-saturated", "thick", "thin",
    "tight", "tinny", "vintage", "warm", "washy", "wet", "wide",
]

# ── Aliases (from tag_processor.py _build_alias_map) ─────────────────────────

ALIASES: dict[str, str] = {
    "hip-hop": "hip hop",
    "hiphop": "hip hop",
    "dnb": "drum and bass",
    "d&b": "drum and bass",
    "d'n'b": "drum and bass",
    "rnb": "r&b",
    "r'n'b": "r&b",
    "rhythm and blues": "r&b",
    "lofi": "lo-fi",
    "lo fi": "lo-fi",
    "synthwave": "synth pop",
    "electronica": "electronic",
    "alt rock": "indie rock",
    "alternative": "indie rock",
    "alternative rock": "indie rock",
    "death metal": "metal",
    "black metal": "metal",
    "thrash metal": "metal",
    "heavy metal": "metal",
    "nu metal": "metal",
    "prog rock": "progressive",
    "progressive rock": "progressive",
    "prog": "progressive",
    "psychedelic": "psych rock",
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
    "indiefolk": "indie folk",
    "synthpop": "synth pop",
    "futuregarage": "garage",
    "future garage": "garage",
    "latin pop": "latin",
    "cumbia": "latin",
    "salsa": "latin",
    "samba": "bossa nova",
    "bossanova": "bossa nova",
    "african": "afrobeat",
    "afropop": "afrobeat",
    "afro": "afrobeat",
    "goth": "dark ambient",
    "dark wave": "dark ambient",
    "darkwave": "dark ambient",
    "chillout": "downtempo",
    "chill out": "downtempo",
    "bass music": "dubstep",
    "uk garage": "garage",
    "ukg": "garage",
    "male vocals": "male vocal",
    "female vocals": "female vocal",
    "male singer": "male vocal",
    "female singer": "female vocal",
    "male voice": "male vocal",
    "female voice": "female vocal",
    "no vocals": "instrumental",
    "no singing": "instrumental",
    "without vocals": "instrumental",
    "vocal": "vocal harmony",
    "vocals": "vocal harmony",
    "backing vocals": "vocal harmony",
    "synths": "synth",
    "synthesizer": "synth",
    "synthesizers": "synth",
    "pads": "synth pad",
    "string pad": "synth strings",
    "lead synth": "synth lead",
    "bass synth": "synth bass",
    "electric bass guitar": "electric bass",
    "acoustic bass": "upright bass",
    "standup bass": "upright bass",
    "stand-up bass": "upright bass",
    "sax": "alto sax",
    "saxophone": "alto sax",
    "soprano sax": "alto sax",
    "ep": "electric piano",
    "e-piano": "electric piano",
    "fender rhodes": "rhodes",
    "wurli": "wurlitzer",
    "keyboard": "keys",
    "keyboards": "keys",
    "bongos": "congas",
    "hand drums": "congas",
    "djembe": "congas",
    "string section": "strings",
    "violins": "strings",
    "cellos": "strings",
    "violas": "strings",
    "brass section": "brass",
    "horn section": "horns",
    "woodwind": "woodwinds",
    "wind instruments": "woodwinds",
    "click": "hi-hat",
    "ride cymbal": "cymbals",
    "crash cymbal": "cymbals",
    "steel drums": "steel drum",
    "steel pan": "steel drum",
    "pitched down": "pitch-shift",
    "pitch shifted": "pitch-shift",
    "auto-tune": "autotune",
    "auto tune": "autotune",
    "talk box": "vocoder",
    "talkbox": "vocoder",
}

# ── Category config ───────────────────────────────────────────────────────────

CATEGORY_LIMITS: dict[str, tuple[int, int]] = {
    "genre":       (1, 2),
    "mood":        (1, 3),
    "instruments": (2, 4),
    "vocal":       (1, 1),
    "texture":     (0, 2),
}

MAX_TOTAL_TAGS = 14
TAG_ORDER = ["genre", "mood", "instruments", "vocal", "texture"]

# Build lookup sets for fast categorization
_GENRE_SET = set(GENRES)
_MOOD_SET = set(MOODS)
_INSTRUMENT_SET = set(INSTRUMENTS)
_VOCAL_SET = set(VOCALS)
_VOCAL_FX_SET = set(VOCAL_FX)
_TEXTURE_SET = set(TEXTURES)

# Combined whitelist for fuzzy matching
_ALL_TAGS: dict[str, str] = {}
for tag in GENRES:
    _ALL_TAGS[tag] = "genre"
for tag in MOODS:
    _ALL_TAGS[tag] = "mood"
for tag in INSTRUMENTS:
    _ALL_TAGS[tag] = "instruments"
for tag in VOCALS:
    _ALL_TAGS[tag] = "vocal"
for tag in VOCAL_FX:
    _ALL_TAGS[tag] = "vocal"
for tag in TEXTURES:
    _ALL_TAGS[tag] = "texture"

# Words to strip from tags (BPM/key/tempo shouldn't be in tags)
_STRIP_PATTERNS = re.compile(
    r"\b\d+\s*bpm\b|\bbpm\b|\btempo\b|\bkey of\b|"
    r"\b[A-G][b#]?\s*(?:major|minor)\b|\bfast tempo\b|\bslow tempo\b",
    re.IGNORECASE,
)


def normalize_tag(tag: str) -> tuple[str | None, str | None]:
    """Normalize a single tag: lowercase, alias, fuzzy match.

    Returns (normalized_tag, category) or (None, None) if invalid.
    """
    tag = tag.strip().lower()
    if not tag or len(tag) < 2:
        return None, None

    # Strip BPM/key/tempo mentions
    if _STRIP_PATTERNS.search(tag):
        return None, None

    # Apply alias
    if tag in ALIASES:
        tag = ALIASES[tag]

    # Exact match
    if tag in _ALL_TAGS:
        return tag, _ALL_TAGS[tag]

    # Fuzzy match (cutoff=0.88 from Data-Tool)
    candidates = list(_ALL_TAGS.keys())
    matches = difflib.get_close_matches(tag, candidates, n=1, cutoff=0.88)
    if matches:
        matched = matches[0]
        return matched, _ALL_TAGS[matched]

    return None, None


def categorize_tags(raw_tags: str) -> dict[str, list[str]]:
    """Split comma-separated tags and categorize each one."""
    result: dict[str, list[str]] = {cat: [] for cat in TAG_ORDER}
    seen: set[str] = set()

    for raw in raw_tags.split(","):
        normalized, category = normalize_tag(raw)
        if normalized and category and normalized not in seen:
            seen.add(normalized)
            result[category].append(normalized)

    return result


def resolve_conflicts(tags_by_category: dict[str, list[str]]) -> dict[str, list[str]]:
    """Resolve mutual exclusions (from Data-Tool).

    - 'instrumental' in vocal excludes all other vocal tags and vice versa.
    """
    vocals = tags_by_category.get("vocal", [])
    if "instrumental" in vocals and len(vocals) > 1:
        tags_by_category["vocal"] = ["instrumental"]
    return tags_by_category


def validate_and_order_tags(raw_tags: str) -> str:
    """Full pipeline: split → normalize → categorize → resolve conflicts → enforce limits → order → rejoin."""
    by_cat = categorize_tags(raw_tags)
    by_cat = resolve_conflicts(by_cat)

    # Enforce per-category limits
    for cat in TAG_ORDER:
        _, max_count = CATEGORY_LIMITS[cat]
        by_cat[cat] = by_cat[cat][:max_count]

    # Assemble in order
    ordered: list[str] = []
    for cat in TAG_ORDER:
        ordered.extend(by_cat[cat])

    # Enforce total limit
    ordered = ordered[:MAX_TOTAL_TAGS]

    if not ordered:
        return "atmospheric, experimental"

    return ", ".join(ordered)
