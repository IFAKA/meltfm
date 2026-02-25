"""Terminal input — raw character reading, keyboard shortcuts, cursor navigation."""
import asyncio
import select as _sel
import sys
import termios
import time
import tty
from typing import Optional

from .ui import fmt_time, fmt_countdown


def _read_one_char() -> str:
    """Read exactly one character from stdin without requiring Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_one_char_timeout(timeout: float = 0.3) -> str | None:
    """Read one char if available within timeout, else return None."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        readable, _, _ = _sel.select([sys.stdin], [], [], timeout)
        if readable:
            return sys.stdin.read(1)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_nav_key() -> str:
    """Read one logical keypress in raw mode; return a normalised action string."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            readable, _, _ = _sel.select([sys.stdin], [], [], 0.05)
            if readable:
                nxt = sys.stdin.read(1)
                if nxt == "[":
                    readable2, _, _ = _sel.select([sys.stdin], [], [], 0.05)
                    if readable2:
                        n2 = sys.stdin.read(1)
                        if n2 == "A":
                            return "up"
                        if n2 == "B":
                            return "down"
                return "ignore"
            return "esc"   # bare Escape
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def get_user_input(
    player=None,
    prompt_suffix: str = "",
    gen_task: Optional[asyncio.Task] = None,
    gen_start: Optional[float] = None,
    status_params: Optional[dict] = None,
    sleep_deadline: Optional[float] = None,
    break_event: Optional[asyncio.Event] = None,
) -> str:
    """Read input with cursor navigation, live generation progress, and in-place updates.

    Supports full cursor movement (left/right), insert at cursor, and backspace at cursor.

    Shortcuts:
      Space (empty buffer) or Ctrl+P -> toggle pause / resume
      up / down arrows               -> volume up / down
      left / right arrows (empty buf) -> seek +/-5s in current track
      left / right arrows (with text) -> move cursor within input
    """
    SPINNERS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    loop = asyncio.get_event_loop()
    buf = [""]  # text buffer (mutable so closures can read/write it)
    pos = [0]   # cursor position within buf[0]
    has_hint = gen_task is not None
    _gen_start = gen_start or time.monotonic()

    if prompt_suffix and not has_hint:
        sys.stdout.write(f"  \033[2m{prompt_suffix}\033[0m\n")
        sys.stdout.flush()

    if has_hint:
        if gen_task.done():
            sys.stdout.write("  ✓ ready\n")
        else:
            sys.stdout.write(f"  {SPINNERS[0]} generating...  0s\n")
        sys.stdout.flush()

    sys.stdout.write("  ❯ ")
    sys.stdout.flush()

    stop_ev = asyncio.Event()

    def _reposition():
        """After writing full buffer to stdout, move cursor back to pos."""
        behind = len(buf[0]) - pos[0]
        if behind > 0:
            sys.stdout.write(f"\033[{behind}D")

    def _draw_hint(text: str):
        """Overwrite hint line (1 above prompt) without disrupting input."""
        sys.stdout.write(f"\033[1A\r  {text}\033[K\033[1B\r  ❯ {buf[0]}")
        _reposition()
        sys.stdout.flush()

    def _draw_status(volume: int):
        """Rewrite the status line in-place with updated volume/pause/progress."""
        if not status_params or not player:
            return
        p = status_params
        name = p.get("id", "?") + "  " + p.get("tags", "")[:30]
        bpm = p.get("bpm", "?")
        key = p.get("key_scale", "?")
        is_p = player.is_paused()
        icon_col = "\033[33m" if is_p else "\033[32m"
        icon = "⏸" if is_p else "♫"

        el = player.elapsed
        dur = player.duration
        if dur and dur > 0:
            bar_len = 20
            filled = min(bar_len, int(el / dur * bar_len))
            bar = f"\033[32m{'━' * filled}\033[2m{'·' * (bar_len - filled)}\033[0m"
            # Cap displayed elapsed so it doesn't exceed duration
            shown_el = min(el, dur)
            progress = f"  {fmt_time(shown_el)}/{fmt_time(dur)} {bar}"
        else:
            progress = ""

        sleep_tag = ""
        if sleep_deadline is not None:
            sleep_tag = f"  ·  \033[33m⏾ Sleep {fmt_countdown(sleep_deadline)}\033[0m"

        line = (
            f"  {icon_col}{icon}\033[0m{progress}  \033[2m{name}"
            f"  ·  {bpm} BPM  ·  {key}  ·  Vol: {volume}%\033[0m{sleep_tag}"
        )
        n = 2 if has_hint else 1
        sys.stdout.write(f"\033[{n}A\r{line}\033[K\033[{n}B\r  ❯ {buf[0]}")
        _reposition()
        sys.stdout.flush()

    def _delete_word_back():
        """Ctrl+W / Option+Backspace — delete one word before the cursor."""
        if pos[0] == 0:
            return
        p = pos[0]
        while p > 0 and buf[0][p - 1] == " ":
            p -= 1
        while p > 0 and buf[0][p - 1] != " ":
            p -= 1
        removed = pos[0] - p
        buf[0] = buf[0][:p] + buf[0][pos[0]:]
        pos[0] = p
        tail = buf[0][p:]
        sys.stdout.write(f"\033[{removed}D{tail}{' ' * removed}\033[{len(tail) + removed}D")
        sys.stdout.flush()

    def _kill_to_start():
        """Ctrl+U / Cmd+Backspace — delete everything before the cursor."""
        if pos[0] == 0:
            return
        buf[0] = buf[0][pos[0]:]
        pos[0] = 0
        sys.stdout.write(f"\r  ❯ {buf[0]}\033[K")
        sys.stdout.flush()

    def _go_home():
        """Ctrl+A — move cursor to start of line."""
        if pos[0] > 0:
            sys.stdout.write(f"\033[{pos[0]}D")
            sys.stdout.flush()
            pos[0] = 0

    def _go_end():
        """Ctrl+E — move cursor to end of line."""
        behind = len(buf[0]) - pos[0]
        if behind > 0:
            sys.stdout.write(f"\033[{behind}C")
            sys.stdout.flush()
            pos[0] = len(buf[0])

    async def _spinner():
        i = 0
        while not stop_ev.is_set():
            await asyncio.sleep(0.25)
            if stop_ev.is_set():
                break
            elapsed = time.monotonic() - _gen_start
            if gen_task.done():
                _draw_hint(f"✓ ready  {elapsed:.0f}s")
                break
            _draw_hint(f"{SPINNERS[i % len(SPINNERS)]} generating...  {elapsed:.0f}s")
            i += 1

    async def _progress_tick():
        """Periodically redraw the status line with updated playback progress."""
        while not stop_ev.is_set():
            await asyncio.sleep(1)
            if stop_ev.is_set():
                break
            if player and status_params and (player.is_playing() or player.is_paused()):
                _draw_status(player._volume)

    spinner_t: Optional[asyncio.Task] = None
    if has_hint and not gen_task.done():
        spinner_t = asyncio.create_task(_spinner())

    progress_t: Optional[asyncio.Task] = None
    if player and status_params and (player.is_playing() or player.is_paused()):
        progress_t = asyncio.create_task(_progress_tick())

    try:
        while True:
            if break_event:
                if break_event.is_set():
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return buf[0].strip()
                ch = await loop.run_in_executor(None, _read_one_char_timeout)
                if ch is None:
                    continue
            else:
                ch = await loop.run_in_executor(None, _read_one_char)

            # ── Space (empty buffer) or Ctrl+P → pause / resume ──────────────
            if ch == "\x10" or (ch == " " and not buf[0]):
                if player and (player.is_playing() or player.is_paused()):
                    player.toggle_pause()
                    if status_params:
                        _draw_status(player._volume)
                    elif has_hint:
                        label = "⏸ paused — Space to resume" if player.is_paused() else "▶ resumed"
                        _draw_hint(label)
                    else:
                        label = "⏸ paused" if player.is_paused() else "▶ resumed"
                        sys.stdout.write(f"\r  {label}  ❯ {buf[0]}\033[K")
                        _reposition()
                        sys.stdout.flush()
                continue

            # ── Escape sequences ──────────────────────────────────────────────
            if ch == "\x1b":
                next1 = await loop.run_in_executor(None, _read_one_char)
                if next1 == "[":
                    next2 = await loop.run_in_executor(None, _read_one_char)
                    if next2 == "A":           # ↑ volume up
                        if player:
                            vol = player.volume_up()
                            if status_params:
                                _draw_status(vol)
                            elif has_hint:
                                _draw_hint(f"Vol: {vol}%")
                            else:
                                sys.stdout.write(f"\r  Vol: {vol}%  ❯ {buf[0]}\033[K")
                                _reposition()
                                sys.stdout.flush()
                    elif next2 == "B":         # ↓ volume down
                        if player:
                            vol = player.volume_down()
                            if status_params:
                                _draw_status(vol)
                            elif has_hint:
                                _draw_hint(f"Vol: {vol}%")
                            else:
                                sys.stdout.write(f"\r  Vol: {vol}%  ❯ {buf[0]}\033[K")
                                _reposition()
                                sys.stdout.flush()
                    elif next2 == "C":         # → seek forward / cursor right
                        if not buf[0] and player and (player.is_playing() or player.is_paused()):
                            new_pos = player.seek(5)
                            if status_params:
                                _draw_status(player._volume)
                            elif has_hint:
                                _draw_hint(f"▶▶ {fmt_time(new_pos)}")
                            else:
                                sys.stdout.write(f"\r  ▶▶ {fmt_time(new_pos)}  ❯ \033[K")
                                sys.stdout.flush()
                        elif pos[0] < len(buf[0]):
                            pos[0] += 1
                            sys.stdout.write("\033[1C")
                            sys.stdout.flush()
                    elif next2 == "D":         # ← seek backward / cursor left
                        if not buf[0] and player and (player.is_playing() or player.is_paused()):
                            new_pos = player.seek(-5)
                            if status_params:
                                _draw_status(player._volume)
                            elif has_hint:
                                _draw_hint(f"◀◀ {fmt_time(new_pos)}")
                            else:
                                sys.stdout.write(f"\r  ◀◀ {fmt_time(new_pos)}  ❯ \033[K")
                                sys.stdout.flush()
                        elif pos[0] > 0:
                            pos[0] -= 1
                            sys.stdout.write("\033[1D")
                            sys.stdout.flush()
                elif next1 == "\x7f":          # Option+Backspace → delete word back
                    _delete_word_back()
                continue

            # ── Enter ─────────────────────────────────────────────────────────
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return buf[0].strip()

            # ── Backspace (delete char before cursor) ─────────────────────────
            if ch == "\x7f":
                if pos[0] > 0:
                    buf[0] = buf[0][:pos[0] - 1] + buf[0][pos[0]:]
                    pos[0] -= 1
                    tail = buf[0][pos[0]:]
                    sys.stdout.write(f"\b{tail} \033[{len(tail) + 1}D")
                    sys.stdout.flush()
                continue

            # ── Ctrl+C ────────────────────────────────────────────────────────
            if ch == "\x03":
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise KeyboardInterrupt

            # ── Ctrl+D ────────────────────────────────────────────────────────
            if ch == "\x04":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "quit"

            # ── Ctrl+W → delete word before cursor ───────────────────────────
            if ch == "\x17":
                _delete_word_back()
                continue

            # ── Ctrl+U → delete to start of line ─────────────────────────────
            if ch == "\x15":
                _kill_to_start()
                continue

            # ── Ctrl+A → go to beginning ──────────────────────────────────────
            if ch == "\x01":
                _go_home()
                continue

            # ── Ctrl+E → go to end ────────────────────────────────────────────
            if ch == "\x05":
                _go_end()
                continue

            # ── Printable characters (insert at cursor position) ──────────────
            if ch >= " ":
                buf[0] = buf[0][:pos[0]] + ch + buf[0][pos[0]:]
                pos[0] += 1
                tail = buf[0][pos[0]:]
                sys.stdout.write(ch + tail)
                if tail:
                    sys.stdout.write(f"\033[{len(tail)}D")
                sys.stdout.flush()

    finally:
        stop_ev.set()
        if spinner_t and not spinner_t.done():
            spinner_t.cancel()
        if progress_t and not progress_t.done():
            progress_t.cancel()
