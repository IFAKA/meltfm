# ai-radio

Local AI radio that generates music continuously using ACE-Step + Ollama, shaped by your taste in plain language.

## How it works

- React to tracks in plain language ("more bass", "something darker", "I love this")
- An LLM (Ollama) translates your reactions into music parameters
- ACE-Step generates the next track in the background while the current one plays
- Your taste profile evolves over time across as many radio stations as you want

## Requirements

- macOS Apple Silicon (M1/M2/M3/M4)
- [Homebrew](https://brew.sh)

Everything else is installed automatically by `setup.sh`.

---

## Install

```bash
git clone https://github.com/IFAKA/ai-radio.git
cd ai-radio
./setup.sh
```

`setup.sh` will automatically:
- Install `uv` and `python@3.12`
- Install and start Ollama, pull the LLM model
- Clone and install ACE-Step with the correct Python version
- Set up the `radio` shell alias

---

## Start ACE-Step (one-time, separate terminal)

ACE-Step runs as its own server. Start it once and leave it running:

```bash
cd ~/ACE-Step
./start_api_server_macos.sh
```

**First run downloads model weights (~20–40 GB)** — takes 30–60 min depending on your connection. Wait for:

```
API will be available at: http://127.0.0.1:8001
```

---

## Run

Once ACE-Step is up, in a new terminal:

```bash
radio
# or: uv run python radio.py
```

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
