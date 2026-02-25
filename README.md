# meltfm

Local AI radio that generates music continuously using ACE-Step + Ollama, shaped by your taste in plain language.

## How it works

- React to tracks in plain language ("more bass", "something darker", "I love this")
- An LLM (Ollama) translates your reactions into music parameters
- ACE-Step generates the next track in the background while the current one plays
- Your taste profile evolves over time across as many radio stations as you want

## Requirements

- macOS Apple Silicon (M1/M2/M3/M4)
- [Homebrew](https://brew.sh)

Everything else is installed automatically.

---

## Setup (first time only)

### Step 1 — Install everything

```bash
git clone https://github.com/IFAKA/meltfm.git
cd meltfm
./setup.sh
```

Installs: `uv`, `python@3.12`, Ollama + LLM model, ACE-Step.

---

### Step 2 — Download ACE-Step model weights (~20–40 GB)

This is a one-time download. Open a **separate terminal** and run:

```bash
cd ~/ACE-Step
./start_api_server_macos.sh
```

Wait until you see:

```
API will be available at: http://127.0.0.1:8001
```

> Takes 30–60 min on first run. After that, ACE-Step starts in ~2 minutes.

Leave this terminal open.

---

### Step 3 — Run

In a new terminal:

```bash
radio
# or: uv run python radio.py
```

> From the second run onwards, ACE-Step starts automatically — you only need one terminal.

---

## Usage

```
[l] like    [d] dislike    [s] skip    [f] favorite
[n] notes   [r] reset      [q] quit
```

Type anything to react and steer the sound:

```
> more melancholic, keep the energy
> trap argentino, lyrics in spanish
> instrumental only, no drums, ambient
```

### Multiple radio stations

```
create radio <name>    — new station with its own taste profile
switch radio <name>    — switch active station
list radios            — see all stations
```

### Explicit notes (always respected by the LLM)

Add notes to permanently shape a station's sound:

```
> lyrics must use orthodox christian themes: theotokos, repentance, theosis
> lyrics in rioplatense spanish, lunfardo slang, barrio themes
> always instrumental, heavy 808s, dark trap
```

---

## Reset

To start fresh (removes all stations, tracks, taste profiles, and metrics):

```bash
rm -rf radios/
```

Next time you run `radio`, everything is recreated from scratch.

---

## Configuration

`.env` is created automatically from `.env.example`. Key options:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.2:3b` | LLM model for param generation |
| `DEFAULT_DURATION` | `60` | Track length in seconds |
| `DEFAULT_INFER_STEPS` | `27` | ACE-Step quality (higher = slower) |

---

## Project structure

```
radio.py        — async main loop
src/
  config.py     — config + constants
  manager.py    — radio stations + taste.json I/O
  reactions.py  — keyword-based reaction parser
  llm.py        — Ollama param generation + fallback
  acestep.py    — ACE-Step HTTP client
  player.py     — afplay wrapper
  errors.py     — error formatting + log
  preflight.py  — startup health check
radios/
  <name>/
    taste.json  — taste profile (liked/disliked/skipped + notes)
    tracks/     — generated .mp3 + .json recipe per track
    favorites/  — saved favorites
```
