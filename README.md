# personal-radio

Local AI radio that generates music continuously using ACE-Step + Ollama, tailored to your taste via natural language reactions.

## How it works

- You react to tracks in plain language ("more bass", "something darker", "I love this")
- An LLM (Ollama) translates your taste into music parameters
- ACE-Step generates the next track in the background while the current one plays
- Your taste profile evolves over time — liked, disliked, skipped history + explicit notes

## Requirements

- macOS Apple Silicon (M1/M2/M3/M4)
- [Ollama](https://ollama.com/download)
- [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5)
- Python 3.12 (for ACE-Step) + Python 3.14 (for this app via uv)

---

## Setup

### 1. Install Ollama

```bash
brew install ollama
ollama pull llama3.2:3b
ollama serve
```

### 2. Install ACE-Step

ACE-Step requires Python 3.11–3.12. If you only have 3.13+:

```bash
brew install python@3.12
```

Then:

```bash
git clone https://github.com/ace-step/ACE-Step-1.5.git ~/ACE-Step
cd ~/ACE-Step
python3.12 -m venv venv
source venv/bin/activate
pip install -e .
```

### 3. Start ACE-Step API server

```bash
cd ~/ACE-Step
./start_api_server_macos.sh
```

First run downloads model weights (~20–40 GB). Wait until you see:

```
API will be available at: http://127.0.0.1:8001
```

### 4. Install and run this app

```bash
git clone <this-repo> ~/code/personal-radio
cd ~/code/personal-radio
./setup.sh
uv run python radio.py
```

---

## Usage

```
[p] play/pause     [l] like     [d] dislike     [s] skip
[f] favorite       [n] notes    [r] reset        [q] quit
```

Type anything to react and steer the sound:

```
> more melancholic, keep the energy
> trap argentino, lyrics in spanish
> instrumental only, ambient, no drums
```

### Multiple radio stations

```
create radio <name>   — start a new station with its own taste profile
switch radio <name>   — switch active station
list radios           — see all stations
```

### Explicit notes (always respected by the LLM)

```
> lyrics must use orthodox christian themes: theotokos, repentance, theosis
> lyrics in rioplatense spanish, lunfardo slang, barrio themes
```

---

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `ACESTEP_HOST` | `http://localhost:8001` | ACE-Step API |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model |
| `DEFAULT_DURATION` | `60` | Track length in seconds |
| `DEFAULT_INFER_STEPS` | `27` | ACE-Step quality steps |

---

## Project structure

```
radio.py          — async main loop
src/
  config.py       — .env loading, constants
  manager.py      — Radio + RadioManager, taste.json I/O
  reactions.py    — keyword-based reaction parser
  llm.py          — Ollama param generation + JSON retry + fallback
  acestep.py      — ACE-Step HTTP client
  player.py       — afplay wrapper
  errors.py       — formatted error blocks + errors.log
  preflight.py    — startup health check
```

Each radio station lives in `radios/<name>/` with its own `taste.json`, `tracks/`, and `favorites/`.
