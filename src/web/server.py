"""Starlette app — HTTP routes + WebSocket + static file serving."""
import asyncio
import json
import logging
import uuid
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, Response
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from ..config import (
    RADIOS_DIR, OLLAMA_HOST, OLLAMA_MODEL, ACESTEP_HOST, APP_VERSION, ROOT_DIR,
)
from ..manager import Radio, RadioManager
from ..engine import RadioEngine
from .state import RadioState

logger = logging.getLogger(__name__)

# Shared state
_state = RadioState()
_engine: RadioEngine | None = None

# Transfer tracking: client_id -> disconnect timer task
_transfer_timers: dict[str, asyncio.Task] = {}


# ── Health ───────────────────────────────────────────────────────────────────

async def health(request):
    checks = {}

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_HOST}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                has_model = any(
                    m == OLLAMA_MODEL or m.startswith(OLLAMA_MODEL.split(":")[0])
                    for m in models
                )
                checks["ollama"] = {"ok": True, "model": OLLAMA_MODEL, "model_available": has_model}
            else:
                checks["ollama"] = {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        checks["ollama"] = {"ok": False, "error": str(e)}

    # ACE-Step
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ACESTEP_HOST}/health")
            checks["acestep"] = {"ok": r.status_code == 200}
    except Exception as e:
        checks["acestep"] = {"ok": False, "error": str(e)}

    # Disk
    manager = RadioManager()
    radio = manager.current_radio()
    free_mb = radio.disk_free_mb()
    checks["disk"] = {"ok": free_mb >= 50, "free_mb": round(free_mb)}

    all_ok = all(c["ok"] for c in checks.values())
    return JSONResponse({
        "status": "ok" if all_ok else "degraded",
        "version": APP_VERSION,
        "checks": checks,
    })


# ── Radios ───────────────────────────────────────────────────────────────────

async def list_radios(request):
    manager = RadioManager()
    names = manager.list_radios()
    current = manager.current_radio().name
    radios = []
    for name in names:
        r = Radio(name)
        taste = r.load_taste()
        radios.append({
            "name": name,
            "track_count": r.get_track_count(),
            "last_played": r.get_last_played_fmt(),
            "is_current": name == current,
            "generation_count": taste.get("generation_count", 0),
            "favorite_count": len(list(r.favorites_dir.glob("*.mp3"))),
        })
    return JSONResponse({"radios": radios, "current": current})


async def radio_history(request):
    name = request.path_params["name"]
    limit = int(request.query_params.get("limit", "20"))
    r = Radio(name)
    history = r.get_history(limit)
    # Strip internal Path objects
    for item in history:
        item.pop("_mp3", None)
    return JSONResponse({"history": history})


# ── Audio serving ────────────────────────────────────────────────────────────

async def serve_audio(request):
    """Serve MP3 files with Range header support (required for Safari)."""
    radio_name = request.path_params["radio"]
    filename = request.path_params["filename"]

    # Security: prevent path traversal
    if ".." in radio_name or ".." in filename or "/" in filename:
        return Response("Forbidden", status_code=403)

    file_path = RADIOS_DIR / radio_name / "tracks" / filename
    if not file_path.exists():
        # Also check favorites
        file_path = RADIOS_DIR / radio_name / "favorites" / filename
        if not file_path.exists():
            return Response("Not found", status_code=404)

    return FileResponse(file_path, media_type="audio/mpeg")


# ── WebSocket ────────────────────────────────────────────────────────────────

async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = str(uuid.uuid4())
    queue = _state.subscribe(client_id)
    logger.info("WS connected: %s", client_id)

    # Send initial sync
    if _engine:
        snapshot = _engine.get_snapshot()
        await websocket.send_json({"type": "sync", "data": snapshot})

    # Two tasks: one reads from client, one writes from queue
    async def _reader():
        try:
            while True:
                data = await websocket.receive_json()
                await _handle_ws_message(client_id, data)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error("WS reader error: %s", e)

    async def _writer():
        try:
            while True:
                event, data = await queue.get()
                await websocket.send_json({"type": event, "data": data})
        except Exception:
            pass

    reader_task = asyncio.create_task(_reader())
    writer_task = asyncio.create_task(_writer())

    try:
        done, pending = await asyncio.wait(
            [reader_task, writer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        _state.unsubscribe(client_id)
        logger.info("WS disconnected: %s", client_id)
        # Cancel any transfer timer for this client
        timer = _transfer_timers.pop(client_id, None)
        if timer:
            timer.cancel()


async def _handle_ws_message(client_id: str, data: dict):
    """Route incoming WebSocket messages to engine methods."""
    if not _engine:
        return

    msg_type = data.get("type", "")

    if msg_type == "reaction":
        text = data.get("text", "").strip()
        if text:
            await _engine.submit_reaction(text)

    elif msg_type == "pause":
        await _engine.pause()

    elif msg_type == "resume":
        await _engine.resume()

    elif msg_type == "toggle_pause":
        await _engine.toggle_pause()

    elif msg_type == "skip":
        await _engine.skip()

    elif msg_type == "save":
        await _engine.save()

    elif msg_type == "like":
        await _engine.like()

    elif msg_type == "dislike":
        await _engine.dislike()

    elif msg_type == "volume":
        level = data.get("level", 80)
        await _engine.set_volume(int(level))

    elif msg_type == "seek":
        delta = data.get("delta", 0)
        await _engine.seek(float(delta))

    elif msg_type == "switch_radio":
        name = data.get("name", "").strip()
        if name:
            await _engine.switch_radio(name)

    elif msg_type == "create_radio":
        name = data.get("name", "").strip()
        vibe = data.get("vibe", "").strip()
        if name:
            await _engine.create_radio(name, vibe)

    elif msg_type == "delete_radio":
        name = data.get("name", "").strip()
        if name:
            await _engine.delete_radio(name)

    elif msg_type == "first_vibe":
        text = data.get("text", "").strip()
        await _engine.set_first_vibe(text)

    elif msg_type == "track_ended":
        # Browser audio ended — engine should advance
        _engine._reaction_event.set()

    else:
        logger.warning("Unknown WS message type: %s", msg_type)


# ── SPA fallback ─────────────────────────────────────────────────────────────

async def spa_fallback(request):
    """Serve static files from dist/, fall back to index.html for SPA routing."""
    dist_dir = ROOT_DIR / "web" / "dist"

    # Try to serve the exact file first (sw.js, manifest.webmanifest, etc.)
    path = request.path_params.get("path", "")
    if path:
        file_path = dist_dir / path
        if file_path.is_file() and dist_dir in file_path.resolve().parents:
            return FileResponse(file_path)

    # SPA fallback — serve index.html
    index = dist_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return Response("Frontend not built. Run: cd web && npm run build", status_code=503)


# ── App factory ──────────────────────────────────────────────────────────────

def create_app() -> Starlette:
    global _engine

    _engine = RadioEngine(_state)

    routes = [
        Route("/api/health", health),
        Route("/api/radios", list_radios),
        Route("/api/radios/{name}/history", radio_history),
        Route("/audio/{radio}/{filename}", serve_audio),
        WebSocketRoute("/ws", websocket_endpoint),
    ]

    # Serve static frontend if built
    dist_dir = ROOT_DIR / "web" / "dist"
    if dist_dir.exists() and (dist_dir / "assets").exists():
        routes.append(Mount("/assets", app=StaticFiles(directory=str(dist_dir / "assets")), name="assets"))

    # SPA fallback must be last — also handles root
    routes.append(Route("/", spa_fallback))
    routes.append(Route("/{path:path}", spa_fallback))

    app = Starlette(
        routes=routes,
        on_startup=[_on_startup],
        on_shutdown=[_on_shutdown],
    )

    return app


async def _on_startup():
    """Start the radio engine as a background task."""
    if _engine:
        asyncio.create_task(_engine.run())
        logger.info("Radio engine started")


async def _on_shutdown():
    """Graceful shutdown."""
    if _engine:
        await _engine.stop()
        logger.info("Radio engine stopped")
