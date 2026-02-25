# meltfm

```
  ▁ ▂ ▁ ▃ ▅ ▇ █ ▇ ▅ ▃ ▁ ▂ ▅ ▇ █ ▅ ▃ ▂ ▁
```

Local AI radio that generates music continuously using ACE-Step + Ollama, shaped by your taste in plain language. Runs as a PWA — open it in your browser, phone, or install it as an app.

## How it works

- React to tracks in plain language ("more bass", "something darker", "I love this")
- An LLM (Ollama) translates your reactions into music parameters
- ACE-Step generates the next track in the background while the current one plays
- Your taste profile evolves over time across as many radio stations as you want

## Requirements

- macOS Apple Silicon (M1/M2/M3/M4)
- [Homebrew](https://brew.sh)
- Node.js 18+ (for building the frontend)

Everything else is installed automatically.

---

## Setup (first time only)

### Step 1 — Install everything

```bash
git clone https://github.com/IFAKA/meltfm.git
cd meltfm
./setup.sh
```

Installs: `uv`, `python@3.12`, Ollama + LLM model, ACE-Step, Node deps, and builds the frontend.

---

### Step 2 — Download ACE-Step model weights (~20-40 GB)

This is a one-time download. Open a **separate terminal** and run:

```bash
cd ~/ACE-Step
./start_api_server_macos.sh
```

Wait until you see:

```
API will be available at: http://127.0.0.1:8001
```

> Takes 30-60 min on first run. After that, ACE-Step starts in ~2 minutes.

Leave this terminal open.

---

### Step 3 — Run

```bash
radio
# or: uv run python radio.py
```

Open **http://localhost:8888** in your browser. Tap "Start listening" and you're in.

> From the second run onwards, ACE-Step starts automatically — you only need one terminal.

---

## Usage

Everything happens in the browser:

- **Like / Dislike** — tap the buttons to steer the sound
- **Skip** — jump to the next track
- **Save** — favorite a track
- **React** — type anything in the input ("trap argentino", "more melancholic, keep the energy", "instrumental only, no drums")
- **Switch radios** — tap the radio name in the header to create/switch stations

### Explicit notes (always respected by the LLM)

Add notes via the reaction input to permanently shape a station's sound:

```
lyrics must use orthodox christian themes: theotokos, repentance, theosis
lyrics in rioplatense spanish, lunfardo slang, barrio themes
always instrumental, heavy 808s, dark trap
```

---

## Development

```bash
# Terminal 1: Python API server
uv run python radio.py

# Terminal 2: Vite dev server (HMR, proxies API to Python)
cd web && npm run dev
```

The Vite dev server runs on port 5173 and proxies `/api/*`, `/ws`, `/audio/*` to the Python backend on 8888.

### Rebuild frontend for production

```bash
cd web && npm run build
```

Output goes to `web/dist/`, served by the Python server automatically.

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
| `WEB_PORT` | `8888` | Server port |

---

## Project structure

```
radio.py          — server entry point (uvicorn launcher)
src/
  engine.py       — core async radio loop (generates, plays, learns)
  config.py       — config + constants
  manager.py      — radio stations + taste.json I/O
  reactions.py    — keyword-based reaction parser
  llm.py          — Ollama param generation + fallback
  acestep.py      — ACE-Step HTTP client
  player.py       — afplay wrapper
  errors.py       — error formatting + log
  preflight.py    — startup health check
  web/
    server.py     — Starlette app (REST + WebSocket + static files)
    state.py      — observable state for WS broadcasts
web/              — React frontend (Vite + TypeScript + Tailwind)
  src/
    App.tsx       — single-screen layout
    hooks/        — useRadio (WS + state)
    components/   — NowPlaying, Controls, ReactionInput, History, etc.
    lib/          — WebSocket client, audio manager
radios/
  <name>/
    taste.json    — taste profile (liked/disliked/skipped + notes)
    tracks/       — generated .mp3 + .json recipe per track
    favorites/    — saved favorites
```
