import threading
import time
import math
import random
import customtkinter as ctk
from tkinter import filedialog
from pynput import keyboard as kb_module
from pynput.keyboard import Key
import os

# ── Palette ───────────────────────────────────────────────────────────────────
C = {
    "bg":         "#09090f",
    "surface":    "#111019",
    "surface_hi": "#181628",
    "border":     "#1e1b35",
    "border_hi":  "#2e2a50",
    "blue":       "#a8c8ff",
    "pink":       "#ffafd0",
    "mint":       "#9defc8",
    "lavender":   "#c8b4fc",
    "text":       "#eae4ff",
    "text_mid":   "#6a6485",
    "text_dim":   "#26233c",
    "dark_text":  "#0c0a18",
}

# ── Key maps ──────────────────────────────────────────────────────────────────
_KEY_MAP = {
    "lshift":    Key.shift_l,
    "rshift":    Key.shift_r,
    "space":     Key.space,
    "enter":     Key.enter,
    "backspace": Key.backspace,
    "backspack": Key.backspace,
    "tab":       Key.tab,
    "lcontrol":  Key.ctrl_l,
    "rcontrol":  Key.ctrl_r,
    "caps":      Key.caps_lock,
    "lalt":      Key.alt_l,
    "ralt":      Key.alt_r,
    "esc":       Key.esc,
}

_SHIFT_MAP = {
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
    '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
    '_': '-', '+': '=', '{': '[', '}': ']',
    ':': ';', '"': "'", '<': ',', '>': '.', '?': '/',
    '~': '`',
}

# Adjacent keys on a standard QWERTY layout
_QWERTY_NEIGHBORS = {
    'q': ['w', 'a'],          'w': ['q', 'e', 'a', 's'],
    'e': ['w', 'r', 's', 'd'],'r': ['e', 't', 'd', 'f'],
    't': ['r', 'y', 'f', 'g'],'y': ['t', 'u', 'g', 'h'],
    'u': ['y', 'i', 'h', 'j'],'i': ['u', 'o', 'j', 'k'],
    'o': ['i', 'p', 'k', 'l'],'p': ['o', 'l'],
    'a': ['q', 'w', 's', 'z'],'s': ['a', 'w', 'e', 'd', 'z', 'x'],
    'd': ['s', 'e', 'r', 'f', 'x', 'c'], 'f': ['d', 'r', 't', 'g', 'c', 'v'],
    'g': ['f', 't', 'y', 'h', 'v', 'b'],'h': ['g', 'y', 'u', 'j', 'b', 'n'],
    'j': ['h', 'u', 'i', 'k', 'n', 'm'],'k': ['j', 'i', 'o', 'l', 'm'],
    'l': ['k', 'o', 'p'],     'z': ['a', 's', 'x'],
    'x': ['z', 's', 'd', 'c'],'c': ['x', 'd', 'f', 'v'],
    'v': ['c', 'f', 'g', 'b'],'b': ['v', 'g', 'h', 'n'],
    'n': ['b', 'h', 'j', 'm'],'m': ['n', 'j', 'k'],
}


# ── Color helpers ─────────────────────────────────────────────────────────────
def lerp(c1, c2, t):
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


def smoothstep(t):
    return t * t * (3 - 2 * t)


# ── Animator ──────────────────────────────────────────────────────────────────
class Animator:
    def __init__(self, app):
        self.app = app
        self._jobs = {}

    def tween(self, widget, from_c, to_c, steps=10, ms=15, _step=0):
        wid = id(widget)
        if _step == 0 and wid in self._jobs:
            self.app.after_cancel(self._jobs[wid])
        if _step >= steps:
            widget.configure(fg_color=to_c)
            self._jobs.pop(wid, None)
            return
        widget.configure(fg_color=lerp(from_c, to_c, smoothstep(_step / steps)))
        self._jobs[wid] = self.app.after(
            ms, lambda: self.tween(widget, from_c, to_c, steps, ms, _step + 1)
        )


# ── Macro / conversion helpers ────────────────────────────────────────────────
def _resolve_key(key_str):
    if key_str in _KEY_MAP:
        return _KEY_MAP[key_str]
    if len(key_str) == 1:
        return key_str
    return None


def _is_typeable(ch):
    return ch == '\n' or ch == '\t' or (len(ch) == 1 and ch.isprintable())


def _get_neighbor(ch):
    """Return a random QWERTY-adjacent key, or None if not on the map."""
    neighbors = _QWERTY_NEIGHBORS.get(ch.lower() if ch.isalpha() else ch)
    return random.choice(neighbors) if neighbors else None


def _char_to_lines(ch, t, hold):
    """Return .macro lines for a single character press+release at time t."""
    if ch == '\n':
        return [f"{t} enter", f"{t+hold} \\enter"]
    if ch == '\t':
        return [f"{t} tab",   f"{t+hold} \\tab"]
    if ch == ' ':
        return [f"{t} space", f"{t+hold} \\space"]
    if ch.isupper():
        lo = ch.lower()
        return [f"{t} lshift", f"{t} {lo}", f"{t+hold} \\{lo}", f"{t+hold} \\lshift"]
    if ch.islower() or ch.isdigit():
        return [f"{t} {ch}", f"{t+hold} \\{ch}"]
    if ch in _SHIFT_MAP:
        base = _SHIFT_MAP[ch]
        return [f"{t} lshift", f"{t} {base}", f"{t+hold} \\{base}", f"{t+hold} \\lshift"]
    if len(ch) == 1 and ch.isprintable():
        return [f"{t} {ch}", f"{t+hold} \\{ch}"]
    return []


def _gauss_clamp(mu, sigma, lo=1):
    """Gaussian sample clamped to a minimum value."""
    return max(lo, int(abs(random.gauss(mu, sigma))))


# Pre-character pause: hesitation before reaching a difficult key
# (probability, min_ms, max_ms)
_PRE_PAUSE = {
    "shifted":  (0.58, 30, 280),   # shift + anything in _SHIFT_MAP
    "upper":    (0.24, 12,  95),   # uppercase letter (shift reach)
    "digit":    (0.32, 18, 140),   # number row
    "punct":    (0.28, 12, 110),   # unshifted punctuation (,./;'[]-=` etc.)
}


def _pre_char_pause(ch):
    """Return ms to pause before pressing ch (time to locate/reach the key)."""
    if ch in _SHIFT_MAP:
        key = "shifted"
    elif ch.isupper():
        key = "upper"
    elif ch.isdigit():
        key = "digit"
    elif len(ch) == 1 and ch.isprintable() and not ch.isalpha() and ch not in ' \t\n':
        key = "punct"
    else:
        return 0
    prob, lo, hi = _PRE_PAUSE[key]
    if random.random() >= prob:
        return 0
    raw = int(random.expovariate(1 / max(1, (hi - lo) / 3)) + lo)
    return min(raw, hi)


# Regular pause: (probability, min_ms, max_ms)
_PAUSE_AFTER = {
    '\n': (0.80, 600,  5000),
    '.':  (0.65, 250,  2200),
    '!':  (0.60, 200,  1800),
    '?':  (0.60, 200,  1800),
    ';':  (0.45, 120,  1000),
    ':':  (0.42, 100,   900),
    ',':  (0.38,  80,   650),
    ' ':  (0.07,  15,   120),
}
_PAUSE_DEFAULT = (0.04, 10, 70)

# Large pause: (probability, min_ms, mean_extra_ms, hard_cap_ms)
_LARGE_PAUSE = {
    '\n': (0.28, 6_000,  12_000, 45_000),   # paragraph break
    '.':  (0.07, 3_000,   6_000, 18_000),   # end of sentence
    '!':  (0.07, 3_000,   6_000, 18_000),
    '?':  (0.07, 3_000,   6_000, 18_000),
}


def _humanize_pause(ch):
    """Return extra delay in ms after ch (regular + occasional very large pause)."""
    pause = 0

    # Regular pause
    prob, lo, hi = _PAUSE_AFTER.get(ch, _PAUSE_DEFAULT)
    if random.random() < prob:
        raw = int(random.expovariate(1 / max(1, (hi - lo) / 3)) + lo)
        pause += min(raw, hi)

    # Large pause (rare, context-dependent)
    if ch in _LARGE_PAUSE:
        lp_prob, lp_min, lp_mean, lp_cap = _LARGE_PAUSE[ch]
        if random.random() < lp_prob:
            raw = int(random.expovariate(1 / lp_mean) + lp_min)
            pause += min(raw, lp_cap)

    return pause


def text_to_macro_lines(text, base_ms, humanize=False, total_ms=None, error_rate=0.5):
    """
    Convert text to .macro lines.

    base_ms    – ms between character press events (average when humanized)
    humanize   – randomise timing, LPM, inject typos, and add pauses
    total_ms   – if set, rescale timestamps so the macro ends at this duration
    error_rate – 0..1 scale on typo/extra-key probabilities (only with humanize)
    """
    pre_typo_prob   = 0.07 * error_rate   # max 7 % at slider = 1.0
    post_extra_prob = 0.025 * error_rate  # max 2.5 %
    lines = []
    t = 0

    # Drift state for sustained LPM variation
    drift = 1.0   # multiplier on base_ms; random-walks each character

    for ch in text:
        # Per-character timing with noticeable drift
        if humanize:
            drift += random.gauss(0.03, 0.24)         # large step + slight slow bias
            drift  = drift * 0.91 + 1.15 * 0.09     # mean-revert toward 1.15 (biased slow)
            drift  = max(0.55, min(4.20, drift))     # [0.55× … 4.2×] ≈ 100–730 LPM at 400
            ms   = max(10, base_ms * drift + random.gauss(0, base_ms * 0.06))
            hold = _gauss_clamp(ms * 0.28, ms * 0.10)
        else:
            ms   = base_ms
            hold = max(1, int(ms * 0.3))

        t += int(ms)

        # Humanize: pre-typo — type 1-3 wrong keys then backspace all of them
        if humanize and ch.isalpha() and random.random() < pre_typo_prob:
            n_wrong = random.choices([1, 2, 3], weights=[55, 33, 12])[0]
            wrong_keys = []
            for _ in range(n_wrong):
                w = _get_neighbor(ch) or random.choice('asdfghjkl')
                wrong_keys.append(w)
                w_hold = _gauss_clamp(hold, hold * 0.25)
                lines += [f"{t} {w}", f"{t + w_hold} \\{w}"]
                t += _gauss_clamp(ms * 0.55, ms * 0.15)

            # Brief "wait, that's wrong" micro-pause before correcting
            t += _gauss_clamp(ms * 0.35, ms * 0.12)

            for _ in wrong_keys:
                bs_hold = _gauss_clamp(hold * 0.9, hold * 0.2)
                lines += [f"{t} backspace", f"{t + bs_hold} \\backspace"]
                t += _gauss_clamp(ms * 0.42, ms * 0.10)

            t += _gauss_clamp(ms * 0.25, ms * 0.08)

        # Pre-character pause for difficult keys
        if humanize:
            t += _pre_char_pause(ch)

        char_lines = _char_to_lines(ch, t, hold)
        if not char_lines:
            continue
        lines += char_lines

        # Humanize: accidental extra key(s) after correct char → backspace all
        if humanize and ch.isalpha() and random.random() < post_extra_prob:
            t += _gauss_clamp(hold * 1.5, hold * 0.4)
            n_extra = random.choices([1, 2], weights=[72, 28])[0]
            extra_keys = []
            for _ in range(n_extra):
                e = _get_neighbor(ch) or random.choice('asdfghjkl')
                extra_keys.append(e)
                e_hold = _gauss_clamp(hold, hold * 0.25)
                lines += [f"{t} {e}", f"{t + e_hold} \\{e}"]
                t += _gauss_clamp(ms * 0.40, ms * 0.12)
            for _ in extra_keys:
                bs_hold = _gauss_clamp(hold * 0.9, hold * 0.2)
                lines += [f"{t} backspace", f"{t + bs_hold} \\backspace"]
                t += _gauss_clamp(ms * 0.38, ms * 0.10)

        # Humanize: natural pause after this character
        if humanize:
            t += _humanize_pause(ch)

    # Rescale all timestamps so the macro ends exactly at total_ms
    if total_ms and lines:
        max_t = max(int(line.split()[0]) for line in lines)
        if max_t > 0:
            scale = total_ms / max_t
            lines = [f"{int(int(l.split(' ', 1)[0]) * scale)} {l.split(' ', 1)[1]}"
                     for l in lines]

    return lines


def macro(file, stop_event, stats=None, pause_event=None, controller=None):
    if not file:
        return
    if controller is None:
        controller = kb_module.Controller()
    held_keys = []
    if stats is not None:
        stats['letter_times'] = []
        stats['current_ms']   = 0

    def release_all():
        for k in held_keys:
            try:
                controller.release(k)
            except Exception:
                pass
        held_keys.clear()

    events = []
    try:
        with open(file, "r") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                if len(parts) != 2:
                    release_all()
                    return
                try:
                    ms_val = int(parts[0])
                except ValueError:
                    release_all()
                    return
                key_str = parts[1]
                is_release = key_str.startswith("\\")
                if is_release:
                    key_str = key_str[1:]
                if not key_str:
                    release_all()
                    return
                key = _resolve_key(key_str)
                if key is None:
                    release_all()
                    return
                events.append((ms_val, is_release, key))
    except OSError:
        return

    events.sort(key=lambda e: e[0])
    start_time = time.perf_counter() * 1000

    for ms_val, is_release, key in events:
        if stop_event.is_set():
            break
        # Pause: block here and shift start_time forward by the pause duration
        if pause_event and pause_event.is_set():
            pause_begin = time.perf_counter() * 1000
            while pause_event.is_set() and not stop_event.is_set():
                time.sleep(0.02)
            start_time += time.perf_counter() * 1000 - pause_begin
        if stop_event.is_set():
            break
        target = start_time + ms_val
        while True:
            now = time.perf_counter() * 1000
            remaining = (target - now) / 1000
            if remaining <= 0:
                break
            if stop_event.is_set():
                break
            time.sleep(min(remaining, 0.005))
        if stop_event.is_set():
            break
        if is_release:
            if key in held_keys:
                controller.release(key)
                held_keys.remove(key)
        else:
            if key in held_keys:
                controller.release(key)
                held_keys.remove(key)
            controller.press(key)
            held_keys.append(key)
            if stats is not None:
                stats['current_ms'] = ms_val
                if isinstance(key, str) and key.isalpha():
                    stats['letter_times'].append(time.time())

    release_all()


def _get_macro_total_ms(file):
    """Scan a .macro file and return its last timestamp in ms (fast, no validation)."""
    try:
        max_t = 0
        with open(file, "r") as f:
            for line in f:
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    try:
                        max_t = max(max_t, int(parts[0]))
                    except ValueError:
                        pass
        return max_t
    except OSError:
        return 0


# ── Tab builders ──────────────────────────────────────────────────────────────
def build_run_tab(tab, app, anim):
    selected_file    = [None]
    # state: "idle" | "countdown" | "running" | "paused" | "resume_countdown"
    state            = ["idle"]
    stop_event       = threading.Event()
    pause_event      = threading.Event()
    pulse_job        = [None]
    countdown_job    = [None]
    poll_job         = [None]
    pulse_start_time = [0.0]
    btn_color        = [C["blue"]]
    term_color       = [C["surface"]]
    stats_dict       = {}
    macro_total_ms   = [0]
    macro_wall_start = [0.0]
    pause_wall_start = [0.0]
    paused_total_s   = [0.0]

    # ── Pulse animation ───────────────────────────────────────────────────────
    def pulse_step():
        if state[0] != "running":
            return
        elapsed = (time.time() - pulse_start_time[0]) * 1000
        phase = (math.sin(elapsed / 800 * math.pi) + 1) / 2
        color = lerp(C["blue"], C["pink"], phase)
        btn_color[0] = color
        btn_run.configure(fg_color=color)
        pulse_job[0] = app.after(30, pulse_step)

    # ── Live stats polling ────────────────────────────────────────────────────
    def poll_stats():
        if state[0] == "idle":
            return
        paused_now = (time.time() - pause_wall_start[0]
                      if state[0] in ("paused", "resume_countdown") else 0.0)
        elapsed_s = time.time() - macro_wall_start[0] - paused_total_s[0] - paused_now
        remaining = max(0.0, macro_total_ms[0] / 1000 - elapsed_s)

        if remaining >= 3600:
            time_str = f"{int(remaining // 3600)}h {int(remaining % 3600 // 60)}m"
        elif remaining >= 60:
            time_str = f"{int(remaining // 60)}m {int(remaining % 60)}s"
        else:
            time_str = f"{remaining:.1f}s"

        now    = time.time()
        times  = stats_dict.get('letter_times', [])
        recent = [t for t in times if now - t <= 5.0]
        if len(recent) >= 2:
            span = max(0.1, recent[-1] - recent[0])
            lpm  = (len(recent) - 1) / span * 60
        else:
            lpm = 0.0

        stat_time_lbl.configure(text=time_str)
        stat_lpm_lbl.configure(text=str(int(lpm)))
        stat_wpm_lbl.configure(text=str(int(lpm / 5)))
        poll_job[0] = app.after(200, poll_stats)

    # ── Layout helpers ────────────────────────────────────────────────────────
    def show_action_only():
        """Idle: single centered Run Macro button."""
        btn_terminate.pack_forget()
        btn_run.configure(width=180)

    def show_action_and_terminate():
        """Running/paused: action button + terminate button side by side."""
        btn_run.configure(width=140)
        if not btn_terminate.winfo_ismapped():
            btn_terminate.pack(side="left", padx=(6, 0))

    # ── Reset to idle ─────────────────────────────────────────────────────────
    def reset_ui():
        state[0] = "idle"
        pause_event.clear()
        pause_wall_start[0] = 0.0
        paused_total_s[0]   = 0.0
        for job in (pulse_job[0], countdown_job[0], poll_job[0]):
            if job:
                app.after_cancel(job)
        pulse_job[0] = countdown_job[0] = poll_job[0] = None
        anim.tween(btn_run, btn_color[0], C["blue"])
        btn_color[0] = C["blue"]
        btn_run.configure(text="Run Macro")
        show_action_only()
        stat_time_lbl.configure(text="—")
        stat_lpm_lbl.configure(text="—")
        stat_wpm_lbl.configure(text="—")

    # ── Hover effects ─────────────────────────────────────────────────────────
    def on_enter_run(_):
        if state[0] == "idle":
            anim.tween(btn_run, btn_color[0], C["lavender"])
            btn_color[0] = C["lavender"]
            btn_run.configure(cursor="hand2")

    def on_leave_run(_):
        if state[0] == "idle":
            anim.tween(btn_run, btn_color[0], C["blue"])
            btn_color[0] = C["blue"]

    def on_enter_term(_):
        anim.tween(btn_terminate, term_color[0], C["surface_hi"])
        term_color[0] = C["surface_hi"]
        btn_terminate.configure(cursor="hand2", border_color=C["pink"])

    def on_leave_term(_):
        anim.tween(btn_terminate, term_color[0], C["surface"])
        term_color[0] = C["surface"]
        btn_terminate.configure(border_color=lerp(C["pink"], C["border"], 0.5))

    def on_enter_file(_):
        anim.tween(btn_file, C["surface"], C["surface_hi"])
        btn_file.configure(cursor="hand2", border_color=C["border_hi"])

    def on_leave_file(_):
        anim.tween(btn_file, C["surface_hi"], C["surface"])
        btn_file.configure(border_color=C["border"])

    # ── File selection ────────────────────────────────────────────────────────
    def on_select_file():
        path = filedialog.askopenfilename(
            title="Select a macro file",
            filetypes=[("Macro files", "*.macro"), ("All files", "*.*")],
        )
        if path:
            selected_file[0] = path
            file_label.configure(text=os.path.basename(path), text_color=C["blue"])

    # ── Start countdown ───────────────────────────────────────────────────────
    def do_countdown(n):
        if state[0] not in ("countdown",):
            return
        if n > 0:
            color = lerp(C["lavender"], C["pink"], (5 - n) / 4.0)
            btn_color[0] = color
            btn_run.configure(text=f"Starting in {n}...", fg_color=color)
            countdown_job[0] = app.after(1000, lambda: do_countdown(n - 1))
        else:
            state[0] = "running"
            btn_run.configure(text="Pause")
            pulse_start_time[0] = time.time()
            pulse_step()
            stop_event.clear()
            pause_event.clear()
            stats_dict.clear()
            macro_total_ms[0]   = _get_macro_total_ms(selected_file[0])
            macro_wall_start[0] = time.time()
            poll_stats()
            # Create Controller on the main thread — macOS HIToolbox APIs
            # (TSMGetInputSourceProperty) require the main thread during init.
            _controller = kb_module.Controller()
            _file = selected_file[0]
            threading.Thread(
                target=lambda: [
                    macro(_file, stop_event, stats_dict, pause_event, _controller),
                    app.after(0, reset_ui),
                ],
                daemon=True,
            ).start()

    # ── Resume countdown (after pause) ────────────────────────────────────────
    def do_resume_countdown(n):
        if state[0] != "resume_countdown":
            return
        if n > 0:
            color = lerp(C["lavender"], C["blue"], (5 - n) / 4.0)
            btn_color[0] = color
            btn_run.configure(text=f"Resuming in {n}...", fg_color=color)
            countdown_job[0] = app.after(1000, lambda: do_resume_countdown(n - 1))
        else:
            paused_total_s[0] += time.time() - pause_wall_start[0]
            state[0] = "running"
            btn_run.configure(text="Pause")
            btn_color[0] = C["blue"]
            pulse_start_time[0] = time.time()
            pulse_step()
            pause_event.clear()   # unblock the macro thread

    # ── Action button click ───────────────────────────────────────────────────
    def on_action_click():
        s = state[0]
        if s == "idle":
            if not selected_file[0]:
                file_label.configure(text="please select a file first", text_color=C["pink"])
                return
            state[0] = "countdown"
            show_action_and_terminate()
            do_countdown(5)
        elif s == "running":
            # Pause
            state[0] = "paused"
            pause_wall_start[0] = time.time()
            pause_event.set()
            if pulse_job[0]:
                app.after_cancel(pulse_job[0])
                pulse_job[0] = None
            anim.tween(btn_run, btn_color[0], C["lavender"])
            btn_color[0] = C["lavender"]
            btn_run.configure(text="Continue")
        elif s == "paused":
            # Start resume countdown
            state[0] = "resume_countdown"
            do_resume_countdown(5)
        elif s == "resume_countdown":
            # Cancel resume, go back to paused
            if countdown_job[0]:
                app.after_cancel(countdown_job[0])
                countdown_job[0] = None
            state[0] = "paused"
            anim.tween(btn_run, btn_color[0], C["lavender"])
            btn_color[0] = C["lavender"]
            btn_run.configure(text="Continue")

    # ── Terminate button click ────────────────────────────────────────────────
    def on_terminate_click():
        pause_event.clear()   # unblock thread so it can see stop_event
        stop_event.set()
        reset_ui()

    # ── Layout ────────────────────────────────────────────────────────────────
    frame = ctk.CTkFrame(tab, fg_color="transparent")
    frame.place(relx=0.5, rely=0.5, anchor="center")

    ctk.CTkLabel(
        frame, text="MACRO  RUNNER",
        font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
        text_color=C["text_dim"],
    ).pack(pady=(0, 16))

    btn_file = ctk.CTkButton(
        frame, text="Select File",
        width=130, height=36, corner_radius=18,
        fg_color=C["surface"], hover=False,
        border_width=1, border_color=C["border"],
        text_color=C["blue"],
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        command=on_select_file,
    )
    btn_file.pack()
    btn_file.bind("<Enter>", on_enter_file)
    btn_file.bind("<Leave>", on_leave_file)

    file_label = ctk.CTkLabel(
        frame, text="no file selected",
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=C["text_dim"], wraplength=320,
    )
    file_label.pack(pady=(6, 14))

    # Stats bar
    stats_frame = ctk.CTkFrame(
        frame, fg_color=C["surface"],
        corner_radius=10, border_width=1, border_color=C["border"],
    )
    stats_frame.pack(pady=(0, 14))

    _stat_font_lbl = ctk.CTkFont(family="Segoe UI", size=9,  weight="bold")
    _stat_font_val = ctk.CTkFont(family="Segoe UI", size=15, weight="bold")

    for col, (header, color, attr) in enumerate([
        ("time left", C["lavender"], "stat_time_lbl"),
        ("LPM",       C["blue"],     "stat_lpm_lbl"),
        ("WPM",       C["mint"],     "stat_wpm_lbl"),
    ]):
        if col > 0:
            ctk.CTkFrame(
                stats_frame, width=1, fg_color=C["border"],
            ).grid(row=0, column=col * 2 - 1, rowspan=2, sticky="ns", pady=8)

        ctk.CTkLabel(
            stats_frame, text=header,
            font=_stat_font_lbl, text_color=C["text_dim"],
        ).grid(row=0, column=col * 2, padx=20, pady=(8, 1))

        val_lbl = ctk.CTkLabel(
            stats_frame, text="—",
            font=_stat_font_val, text_color=color,
        )
        val_lbl.grid(row=1, column=col * 2, padx=20, pady=(0, 8))

        if attr == "stat_time_lbl":
            stat_time_lbl = val_lbl
        elif attr == "stat_lpm_lbl":
            stat_lpm_lbl = val_lbl
        else:
            stat_wpm_lbl = val_lbl

    # Button row — btn_run always visible; btn_terminate shown only when active
    btn_row = ctk.CTkFrame(frame, fg_color="transparent")
    btn_row.pack()

    btn_run = ctk.CTkButton(
        btn_row, text="Run Macro",
        width=180, height=50, corner_radius=14,
        fg_color=C["blue"], hover=False,
        text_color=C["dark_text"],
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        command=on_action_click,
    )
    btn_run.pack(side="left")
    btn_run.bind("<Enter>", on_enter_run)
    btn_run.bind("<Leave>", on_leave_run)

    btn_terminate = ctk.CTkButton(
        btn_row, text="Terminate",
        width=100, height=38, corner_radius=10,
        fg_color=C["surface"], hover=False,
        border_width=1, border_color=lerp(C["pink"], C["border"], 0.5),
        text_color=C["pink"],
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        command=on_terminate_click,
    )
    # Not packed initially — shown by show_action_and_terminate()
    btn_terminate.bind("<Enter>", on_enter_term)
    btn_terminate.bind("<Leave>", on_leave_term)


def build_convert_tab(tab, anim):
    btn_color = [C["surface"]]

    # ── Helpers ───────────────────────────────────────────────────────────────
    def on_enter_conv(_):
        anim.tween(btn_convert, btn_color[0], C["surface_hi"])
        btn_color[0] = C["surface_hi"]
        btn_convert.configure(cursor="hand2", border_color=C["border_hi"])

    def on_leave_conv(_):
        anim.tween(btn_convert, btn_color[0], C["surface"])
        btn_color[0] = C["surface"]
        btn_convert.configure(border_color=C["border"])

    def on_mode_change(value):
        if value == "LPM":
            input_label.configure(text="Letters per minute")
            value_entry.delete(0, "end")
            value_entry.insert(0, "300")
        else:
            input_label.configure(text="Total seconds")
            value_entry.delete(0, "end")
            value_entry.insert(0, "30")

    def on_convert():
        text = text_box.get("1.0", "end-1c")
        if not text.strip():
            status.configure(text="Paste some text first.", text_color=C["pink"])
            return

        try:
            val = float(value_entry.get())
            if val <= 0:
                raise ValueError
        except ValueError:
            mode_label = "LPM" if mode_var.get() == "LPM" else "total seconds"
            status.configure(text=f"Enter a valid positive {mode_label}.", text_color=C["pink"])
            return

        total_ms_constraint = None
        if mode_var.get() == "LPM":
            base_ms = 60_000 / val
        else:
            typeable = sum(1 for ch in text if _is_typeable(ch))
            if typeable == 0:
                status.configure(text="No typeable characters found.", text_color=C["pink"])
                return
            base_ms = (val * 1000) / typeable
            if humanize_var.get():
                total_ms_constraint = val * 1000

        lines = text_to_macro_lines(
            text, base_ms,
            humanize=humanize_var.get(),
            total_ms=total_ms_constraint,
            error_rate=error_rate_var.get(),
        )
        if not lines:
            status.configure(text="No typeable characters found.", text_color=C["pink"])
            return

        save_path = filedialog.asksaveasfilename(
            title="Save macro file",
            defaultextension=".macro",
            filetypes=[("Macro files", "*.macro"), ("All files", "*.*")],
        )
        if not save_path:
            return

        with open(save_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        status.configure(
            text=f"Saved  {os.path.basename(save_path)}",
            text_color=C["mint"],
        )

    # ── Layout ────────────────────────────────────────────────────────────────
    frame = ctk.CTkFrame(tab, fg_color="transparent")
    frame.pack(fill="both", expand=True, padx=10, pady=(8, 4))

    ctk.CTkLabel(
        frame, text="TEXT  TO  MACRO",
        font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
        text_color=C["text_dim"],
    ).pack(pady=(0, 8))

    text_box = ctk.CTkTextbox(
        frame, width=340, height=165, corner_radius=12,
        fg_color=C["surface"], border_color=C["border"], border_width=1,
        text_color=C["text"], font=ctk.CTkFont(family="Segoe UI", size=12),
        scrollbar_button_color=C["border_hi"],
        scrollbar_button_hover_color=C["text_mid"],
    )
    text_box.pack(pady=(0, 10))

    # Mode toggle
    mode_var = ctk.StringVar(value="LPM")
    mode_btn = ctk.CTkSegmentedButton(
        frame,
        values=["LPM", "Total Time"],
        variable=mode_var,
        command=on_mode_change,
        width=220, height=28,
        corner_radius=8,
        fg_color=C["surface"],
        selected_color=C["surface_hi"],
        selected_hover_color=C["surface_hi"],
        unselected_color=C["surface"],
        unselected_hover_color=C["surface"],
        text_color=C["text_mid"],
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
    )
    mode_btn.pack(pady=(0, 6))

    # Input row
    input_row = ctk.CTkFrame(frame, fg_color="transparent")
    input_row.pack(pady=(0, 8))

    input_label = ctk.CTkLabel(
        input_row, text="Letters per minute",
        font=ctk.CTkFont(family="Segoe UI", size=12),
        text_color=C["text_mid"],
    )
    input_label.pack(side="left", padx=(0, 12))

    value_entry = ctk.CTkEntry(
        input_row, width=72, height=30, corner_radius=10,
        fg_color=C["surface"], border_color=C["border"], border_width=1,
        text_color=C["text"], font=ctk.CTkFont(family="Segoe UI", size=12),
        justify="center",
    )
    value_entry.insert(0, "300")
    value_entry.pack(side="left")

    # Humanize checkbox + error rate slider
    humanize_var = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(
        frame,
        text="Humanize",
        variable=humanize_var,
        checkbox_width=18, checkbox_height=18, corner_radius=5,
        fg_color=C["lavender"], hover_color=C["blue"],
        border_color=C["border_hi"], border_width=1,
        text_color=C["text_mid"],
        font=ctk.CTkFont(family="Segoe UI", size=12),
    ).pack(pady=(0, 6))

    error_row = ctk.CTkFrame(frame, fg_color="transparent")
    error_row.pack(pady=(0, 4))

    error_rate_var = ctk.DoubleVar(value=0.5)

    ctk.CTkLabel(
        error_row, text="Error rate",
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=C["text_mid"], width=68, anchor="e",
    ).pack(side="left", padx=(0, 8))

    error_slider = ctk.CTkSlider(
        error_row,
        from_=0, to=1,
        variable=error_rate_var,
        width=160, height=14,
        corner_radius=6,
        fg_color=C["surface"],
        progress_color=C["pink"],
        button_color=C["lavender"],
        button_hover_color=C["blue"],
        command=lambda v: error_pct_lbl.configure(text=f"{int(v * 100)}%"),
    )
    error_slider.pack(side="left", padx=(0, 8))

    error_pct_lbl = ctk.CTkLabel(
        error_row, text="50%",
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=C["pink"], width=34, anchor="w",
    )
    error_pct_lbl.pack(side="left")

    status = ctk.CTkLabel(
        frame, text="",
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=C["text_dim"], wraplength=320,
    )
    status.pack(pady=(0, 8))

    btn_convert = ctk.CTkButton(
        frame, text="Save as .macro",
        width=160, height=40, corner_radius=12,
        fg_color=C["surface"], hover=False,
        border_width=1, border_color=C["border"],
        text_color=C["mint"],
        font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        command=on_convert,
    )
    btn_convert.pack()
    btn_convert.bind("<Enter>", on_enter_conv)
    btn_convert.bind("<Leave>", on_leave_conv)


# ── Entry point ───────────────────────────────────────────────────────────────
def run():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("Macro")
    app.geometry("420x560")
    app.resizable(False, False)
    app.configure(fg_color=C["bg"])

    app.update_idletasks()
    sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
    app.geometry(f"420x560+{(sw - 420) // 2}+{(sh - 560) // 2}")

    anim = Animator(app)

    tabs = ctk.CTkTabview(
        app,
        width=400, height=536,
        fg_color=C["bg"],
        segmented_button_fg_color=C["bg"],
        segmented_button_selected_color=C["surface_hi"],
        segmented_button_selected_hover_color=C["surface_hi"],
        segmented_button_unselected_color=C["bg"],
        segmented_button_unselected_hover_color=C["surface"],
        text_color=C["text_mid"],
        border_color=C["border"],
        border_width=1,
    )
    tabs.pack(fill="both", expand=True, padx=10, pady=10)
    tabs.add("Run")
    tabs.add("Convert")

    build_run_tab(tabs.tab("Run"), app, anim)
    build_convert_tab(tabs.tab("Convert"), anim)

    app.mainloop()
