#!/usr/bin/env python3
"""
Gemini Snap for Windows - system tray app.

  Ctrl+Alt+1  screenshot the whole (primary) screen and answer now
  Ctrl+Alt+3  add a screenshot to the batch   Ctrl+Alt+4 send batch   Ctrl+Alt+5 clear batch
  Ctrl+Alt+2  hide / show the popup

Tray circle: red = idle, yellow = working, green = answer ready (number = screenshots in batch)
"""
import base64
import ctypes
import io
import json
import os
import queue
import threading
import time
import tkinter as tk
import traceback
from ctypes import wintypes
from tkinter import simpledialog

import mss
import pystray
import requests
from PIL import Image, ImageDraw, ImageFont

CONFIG_DIR = os.path.expanduser("~/.gemini_snap_v2")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "api_key": "",
    "model": "gemini-2.5-flash",
    "prompt_single": (
        "This is a screenshot of my screen. Reply with ONLY the final answer to the "
        "question(s) shown. No explanations, no reasoning, no restating the question, "
        "no extra words. If there are several questions, put each answer on its own line."
    ),
    "prompt_batch": (
        "You are given {n} screenshots in order. For each screenshot, reply with ONLY the "
        "final answer(s) to the question(s) it shows, one per line, numbered by screenshot: "
        "'1. answer', '2. answer', ... (use 2a, 2b if one screenshot has several questions). "
        "No explanations, no reasoning, no restating questions, no extra words."
    ),
    "hk_capture": "ctrl+alt+1",
    "hk_toggle": "ctrl+alt+2",
    "hk_add": "ctrl+alt+3",
    "hk_send": "ctrl+alt+4",
    "hk_clear": "ctrl+alt+5",
    "max_image_px": 1600,
}
RED, YELLOW, GREEN = (225, 50, 45), (240, 190, 0), (40, 190, 80)


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    if os.environ.get("GEMINI_API_KEY"):
        cfg["api_key"] = os.environ["GEMINI_API_KEY"]
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def log_error(text):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, "error.log"), "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------ hotkeys
MOD = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}
WM_HOTKEY = 0x0312


def parse_hotkey(spec):
    parts = [p.strip().lower() for p in spec.split("+")]
    mods = 0
    for p in parts[:-1]:
        mods |= MOD[p]
    key = parts[-1]
    vk = 0x20 if key == "space" else ord(key.upper())  # letters/digits: VK == ASCII
    return mods | 0x4000, vk  # 0x4000 = MOD_NOREPEAT


def pretty(spec):
    return "+".join(p.capitalize() if len(p) > 1 else p.upper() for p in spec.split("+"))


# ------------------------------------------------------------------- Gemini
_session = requests.Session()


def grab_b64(cfg):
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])  # primary monitor
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    px = int(cfg.get("max_image_px", 1600))
    img.thumbnail((px, px))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def stream_answer(cfg, images, prompt, on_text):
    parts = [{"text": prompt}]
    for i, b64 in enumerate(images, 1):
        if len(images) > 1:
            parts.append({"text": f"Screenshot {i}:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg['model']}:streamGenerateContent?alt=sse")
    with _session.post(url, headers={"x-goog-api-key": cfg["api_key"]},
                       json={"contents": [{"parts": parts}]},
                       stream=True, timeout=(10, 120)) as r:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
        r.encoding = "utf-8"
        full = ""
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            try:
                ps = json.loads(line[5:].strip())["candidates"][0]["content"]["parts"]
                chunk = "".join(p.get("text", "") for p in ps)
            except Exception:
                continue
            if chunk:
                full += chunk
                on_text(full)
    return full.strip() or "(empty answer)"


# ----------------------------------------------------------------- tray icon
def make_icon(color, count):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=color + (255,))
    if count:
        try:
            d.text((32, 32), str(count), fill="white", anchor="mm",
                   font=ImageFont.load_default(size=34))
        except Exception:
            pass
    return img


# ---------------------------------------------------------------------- app
class App:
    W, H = 420, 300

    def __init__(self):
        self.cfg = load_config()
        self.busy = False
        self.queue = []
        self.state = RED
        self.placed = False
        self.uiq = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.build_popup()

        P = self.post
        self.icon = pystray.Icon(
            "gemini_snap", make_icon(RED, 0), "Gemini Snap",
            menu=pystray.Menu(
                pystray.MenuItem(f"Ask now  ({pretty(self.cfg['hk_capture'])})", lambda: P(self.capture)),
                pystray.MenuItem(f"Add screenshot to batch  ({pretty(self.cfg['hk_add'])})", lambda: P(self.add_shot)),
                pystray.MenuItem(f"Send batch  ({pretty(self.cfg['hk_send'])})", lambda: P(self.send_batch)),
                pystray.MenuItem(f"Clear batch  ({pretty(self.cfg['hk_clear'])})", lambda: P(self.clear_batch)),
                pystray.MenuItem(f"Show / Hide answer  ({pretty(self.cfg['hk_toggle'])})", lambda: P(self.toggle)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Set Gemini API Key...", lambda: P(self.set_key)),
                pystray.MenuItem("Set Model...", lambda: P(self.set_model)),
                pystray.MenuItem("Quit", lambda: P(self.quit)),
            ),
        )
        self.icon.run_detached()

        self.problems = []
        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        self.root.after(30, self.pump)
        self.root.after(400, self.startup_message)

    # ---- thread-safe UI plumbing
    def post(self, fn, *args):
        self.uiq.put((fn, args))

    def pump(self):
        try:
            while True:
                fn, args = self.uiq.get_nowait()
                try:
                    fn(*args)
                except Exception:
                    log_error(traceback.format_exc())
        except queue.Empty:
            pass
        self.root.after(30, self.pump)

    # ---- global hotkeys (Win32 RegisterHotKey, no extra packages / no admin)
    def hotkey_loop(self):
        u = ctypes.windll.user32
        actions = {}
        for i, (name, fn) in enumerate((("capture", self.capture), ("toggle", self.toggle),
                                        ("add", self.add_shot), ("send", self.send_batch),
                                        ("clear", self.clear_batch)), 1):
            spec = self.cfg[f"hk_{name}"]
            try:
                mods, vk = parse_hotkey(spec)
                ok = u.RegisterHotKey(None, i, mods, vk)
            except Exception:
                ok = False
            if ok:
                actions[i] = fn
            else:
                self.problems.append(f"{pretty(spec)} is already used by another app")
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam in actions:
                self.post(actions[msg.wParam])

    def startup_message(self):
        c = self.cfg
        m = (f"Ready.\n{pretty(c['hk_capture'])}  screenshot + answer now\n"
             f"{pretty(c['hk_add'])}  add screenshot to batch\n"
             f"{pretty(c['hk_send'])}  send batch (all answers in a row)\n"
             f"{pretty(c['hk_clear'])}  clear batch\n{pretty(c['hk_toggle'])}  hide / show this popup")
        if not c["api_key"]:
            m += "\n\nFirst: right-click the tray circle (bottom-right, maybe under the ^ arrow) -> Set Gemini API Key..."
        if self.problems:
            m += "\n\n! " + "\n! ".join(self.problems)
        self.show(m)

    # ---- popup
    def build_popup(self):
        bg, hd = "#1c1c1e", "#2a2a2d"
        t = self.pop = tk.Toplevel(self.root)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(bg=bg)
        t.withdraw()
        header = tk.Frame(t, bg=hd, height=28)
        header.pack(fill="x")
        lbl = tk.Label(header, text="::  drag here to move", fg="#999999", bg=hd,
                       font=("Segoe UI", 9))
        lbl.pack(side="left", padx=8, pady=4)
        tk.Button(header, text="X", command=self.hide, bd=0, bg=hd, fg="white",
                  activebackground="#c0392b", activeforeground="white", width=3,
                  cursor="hand2").pack(side="right")
        tk.Button(header, text="Copy", command=self.copy, bd=0, bg=hd, fg="white",
                  activebackground="#444", activeforeground="white", width=6,
                  cursor="hand2").pack(side="right")
        for w in (header, lbl):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        body = tk.Frame(t, bg=bg)
        body.pack(fill="both", expand=True)
        sb = tk.Scrollbar(body)
        sb.pack(side="right", fill="y")
        self.text = tk.Text(body, wrap="word", bg=bg, fg="white", bd=0, padx=10, pady=8,
                            font=("Segoe UI", 11), yscrollcommand=sb.set,
                            highlightthickness=0, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        sb.config(command=self.text.yview)

    def _drag_start(self, e):
        self._dx, self._dy = e.x_root - self.pop.winfo_x(), e.y_root - self.pop.winfo_y()

    def _drag_move(self, e):
        self.pop.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def show(self, text):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.config(state="disabled")
        if not self.placed:  # bottom-right the first time; afterwards stays where you drag it
            x = self.root.winfo_screenwidth() - self.W - 16
            y = self.root.winfo_screenheight() - self.H - 70
            self.pop.geometry(f"{self.W}x{self.H}+{x}+{y}")
            self.placed = True
        self.pop.deiconify()
        self.pop.attributes("-topmost", True)

    def hide(self):
        self.pop.withdraw()
        if not self.busy:
            self.set_state(RED)

    def is_visible(self):
        return self.pop.state() == "normal"

    def current_text(self):
        return self.text.get("1.0", "end").strip()

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_text())

    def toggle(self):
        if self.is_visible():
            self.hide()
        elif self.current_text():
            self.show(self.current_text())
            if not self.busy:
                self.set_state(GREEN)

    # ---- status
    def set_state(self, color):
        self.state = color
        n = len(self.queue)
        self.icon.icon = make_icon(color, n)
        self.icon.title = "Gemini Snap" + (f" ({n} in batch)" if n else "")

    def need_key(self):
        if self.cfg["api_key"]:
            return True
        self.show("No API key yet.\nRight-click the tray circle -> Set Gemini API Key...")
        return False

    # ---- single
    def capture(self):
        if self.busy or not self.need_key():
            return
        self.busy = True
        self.set_state(YELLOW)
        self.pop.withdraw()  # keep the popup out of the screenshot
        threading.Thread(target=self._worker, args=(False,), daemon=True).start()

    # ---- batch
    def add_shot(self):
        if self.busy:
            return
        if len(self.queue) >= 20:
            self.show("Batch is full (20). Send it or clear it first.")
            return
        self.busy = True
        self._was_visible = self.is_visible()
        self.pop.withdraw()
        threading.Thread(target=self._add_worker, daemon=True).start()

    def _add_worker(self):
        try:
            time.sleep(0.2)
            self.post(self._added, grab_b64(self.cfg), None)
        except Exception as e:
            self.post(self._added, None, str(e))

    def _added(self, b64, err):
        self.busy = False
        if b64:
            self.queue.append(b64)
            try:
                import winsound
                winsound.Beep(1000, 60)
            except Exception:
                pass
        self.set_state(RED)
        if err:
            self.show(f"Error: {err}")
        elif self._was_visible:
            self.pop.deiconify()

    def send_batch(self):
        if self.busy:
            return
        if not self.queue:
            self.show(f"Batch is empty. Press {pretty(self.cfg['hk_add'])} to add screenshots first.")
            return
        if not self.need_key():
            return
        self.busy = True
        self.set_state(YELLOW)
        threading.Thread(target=self._worker, args=(True,), daemon=True).start()

    def clear_batch(self):
        if self.busy:
            return
        self.queue = []
        self.set_state(RED)

    # ---- shared worker
    def _worker(self, use_queue):
        try:
            if use_queue:
                images = list(self.queue)
            else:
                time.sleep(0.2)
                images = [grab_b64(self.cfg)]
            prompt = (self.cfg["prompt_single"] if len(images) == 1
                      else self.cfg["prompt_batch"].replace("{n}", str(len(images))))
            text = stream_answer(self.cfg, images, prompt, lambda t: self.post(self.show, t))
            self.post(self._done, text, True, use_queue)
        except Exception as e:
            s = str(e)
            hint = ""
            if "400" in s or "401" in s or "403" in s:
                hint = "\n\nCheck your API key (tray circle -> Set Gemini API Key...)"
            elif "404" in s or "model" in s.lower():
                hint = "\n\nTry another model (tray circle -> Set Model...), e.g. gemini-2.5-flash or gemini-flash-latest"
            elif "429" in s:
                hint = "\n\nRate limit hit (free tier). Wait a minute and try again"
            self.post(self._done, f"Error: {s}{hint}", False, use_queue)

    def _done(self, text, ok, use_queue):
        self.busy = False
        if ok and use_queue:
            self.queue = []  # on failure the batch is kept so you can retry
        self.set_state(GREEN if ok else RED)
        self.show(text)

    # ---- settings
    def _ask(self, title, msg, key):
        v = simpledialog.askstring(title, msg, initialvalue=self.cfg[key], parent=self.root)
        if v and v.strip():
            self.cfg[key] = v.strip()
            save_config(self.cfg)

    def set_key(self):
        self._ask("Gemini API Key", "Paste your free key from aistudio.google.com/apikey:", "api_key")

    def set_model(self):
        self._ask("Model", "Model name (gemini-2.5-flash = fast, gemini-2.5-pro = smarter):", "model")

    def quit(self):
        self.icon.stop()
        self.root.quit()


if __name__ == "__main__":
    try:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # sharp popup + full-resolution screenshot
        except Exception:
            pass
        App().root.mainloop()
    except Exception:
        log_error(traceback.format_exc())
        raise
