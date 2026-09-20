#!/usr/bin/env python3
"""
Gemini Snap - macOS menu bar app.

  ⌥⌘1  screenshot the whole screen and answer now
  ⌥⌘3  add a screenshot to the batch   ⌥⌘4 send batch   ⌥⌘5 clear batch
  ⌥⌘2  hide / show the popup

Menu bar circle: 🔴 idle   🟡 working   🟢 answer ready
Hotkeys use Carbon RegisterEventHotKey (no special permissions).
Only Screen Recording permission is needed (for the screenshot).
"""
import base64
import ctypes
import json
import os
import subprocess
import tempfile
import threading
import time

import objc
import requests
import rumps
from AppKit import (
    NSApplication, NSBackingStoreBuffered, NSBezelStyleInline, NSButton, NSColor, NSFont,
    NSFloatingWindowLevel, NSMakeRect, NSPanel, NSPasteboard, NSPasteboardTypeString,
    NSScreen, NSScrollView, NSSound, NSTextField, NSTextView, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

# ----------------------------------------------------------------- settings
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
    "hotkey_capture": "alt+cmd+1",
    "hotkey_toggle": "alt+cmd+2",
    "hotkey_add": "alt+cmd+3",
    "hotkey_send": "alt+cmd+4",
    "hotkey_clear": "alt+cmd+5",
    "max_image_px": 1600,
}
RED, YELLOW, GREEN = "🔴", "🟡", "🟢"


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    if not cfg["api_key"]:
        try:
            with open(os.path.expanduser("~/.gemini_snap/config.json")) as f:
                cfg["api_key"] = json.load(f).get("api_key", "")
        except Exception:
            pass
    if os.environ.get("GEMINI_API_KEY"):
        cfg["api_key"] = os.environ["GEMINI_API_KEY"]
    return cfg


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


# ------------------------------------------------------------------ hotkeys
_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31,
    "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46, "space": 49,
}
_CARBON_MODS = {"cmd": 256, "shift": 512, "alt": 2048, "ctrl": 4096}
_SYMBOLS = {"cmd": "⌘", "shift": "⇧", "alt": "⌥", "ctrl": "⌃"}


def parse_hotkey(spec):
    parts = [p.strip().lower() for p in spec.split("+")]
    mods = 0
    for p in parts[:-1]:
        mods |= _CARBON_MODS[p]
    return _KEYCODES[parts[-1]], mods


def pretty(spec):
    parts = [p.strip().lower() for p in spec.split("+")]
    order = ["ctrl", "alt", "shift", "cmd"]
    mods = "".join(_SYMBOLS[m] for m in order if m in parts[:-1])
    return mods + parts[-1].upper()


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class _HotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HandlerProc = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class HotKeys:
    def __init__(self):
        c = self.c = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
        c.GetApplicationEventTarget.restype = ctypes.c_void_p
        c.InstallEventHandler.argtypes = [
            ctypes.c_void_p, _HandlerProc, ctypes.c_uint32,
            ctypes.POINTER(_EventTypeSpec), ctypes.c_void_p, ctypes.c_void_p,
        ]
        c.InstallEventHandler.restype = ctypes.c_int32
        c.GetEventParameter.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
        ]
        c.GetEventParameter.restype = ctypes.c_int32
        c.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, _HotKeyID, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_void_p,
        ]
        c.RegisterEventHotKey.restype = ctypes.c_int32
        self.actions = {}
        self.refs = []
        self._cb = _HandlerProc(self._handle)  # keep a reference!
        spec = _EventTypeSpec(0x6B657962, 5)  # 'keyb', kEventHotKeyPressed
        c.InstallEventHandler(
            c.GetApplicationEventTarget(), self._cb, 1, ctypes.byref(spec), None, None
        )

    def _handle(self, _call, event, _user):
        hk = _HotKeyID()
        self.c.GetEventParameter(
            event, 0x2D2D2D2D, 0x686B6964, None, ctypes.sizeof(hk), None, ctypes.byref(hk)
        )
        fn = self.actions.get(hk.id)
        if fn:
            AppHelper.callAfter(fn)
        return 0

    def register(self, spec, fn):
        kc, mods = parse_hotkey(spec)
        hid = len(self.actions) + 1
        ref = ctypes.c_void_p()
        st = self.c.RegisterEventHotKey(
            kc, mods, _HotKeyID(0x53414B59, hid),
            self.c.GetApplicationEventTarget(), 0, ctypes.byref(ref),
        )
        if st == 0:
            self.actions[hid] = fn
            self.refs.append(ref)
            return True
        return False


# ------------------------------------------------------------------- OpenAI
_session = requests.Session()


def take_screenshot(cfg):
    path = os.path.join(tempfile.gettempdir(), "gemini_snap.jpg")
    if os.path.exists(path):
        os.remove(path)
    # -x no sound, -m main display only, jpg = small + fast
    subprocess.run(["screencapture", "-x", "-m", "-t", "jpg", path], check=False)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise RuntimeError("Screenshot failed. Give Terminal 'Screen Recording' permission.")
    px = str(int(cfg.get("max_image_px", 1600)))
    subprocess.run(["sips", "-Z", px, "-s", "formatOptions", "70", path],
                   capture_output=True, check=False)
    return path


def grab_b64(cfg):
    path = take_screenshot(cfg)
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def stream_answer(cfg, images, prompt, on_text):
    parts = [{"text": prompt}]
    for i, b64 in enumerate(images, 1):
        if len(images) > 1:
            parts.append({"text": f"Screenshot {i}:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    body = {"contents": [{"parts": parts}]}
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg['model']}:streamGenerateContent?alt=sse")
    with _session.post(url, headers={"x-goog-api-key": cfg["api_key"]},
                       json=body, stream=True, timeout=(10, 120)) as r:
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


# -------------------------------------------------------------------- popup
class PopupController(NSObject):
    def init(self):
        self = objc.super(PopupController, self).init()
        if self is None:
            return None
        self.w, self.h, self.margin = 420, 300, 16
        self.on_hide = None
        self.placed = False
        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.w, self.h), style, NSBackingStoreBuffered, False)
        p = self.panel
        p.setLevel_(NSFloatingWindowLevel)
        p.setOpaque_(False)
        p.setBackgroundColor_(NSColor.clearColor())
        p.setHasShadow_(True)
        p.setHidesOnDeactivate_(False)
        p.setFloatingPanel_(True)
        p.setMovableByWindowBackground_(True)
        p.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary)
        content = p.contentView()
        content.setWantsLayer_(True)
        layer = content.layer()
        layer.setCornerRadius_(12)
        layer.setMasksToBounds_(True)
        layer.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.11, 0.96).CGColor())

        close = NSButton.alloc().initWithFrame_(NSMakeRect(self.w - 34, self.h - 30, 26, 22))
        close.setTitle_("✕")
        close.setBezelStyle_(NSBezelStyleInline)
        close.setTarget_(self)
        close.setAction_("hideClicked:")
        content.addSubview_(close)
        copy = NSButton.alloc().initWithFrame_(NSMakeRect(self.w - 100, self.h - 30, 60, 22))
        copy.setTitle_("Copy")
        copy.setBezelStyle_(NSBezelStyleInline)
        copy.setTarget_(self)
        copy.setAction_("copyClicked:")
        content.addSubview_(copy)
        hint = NSTextField.labelWithString_("⠿  drag here to move")
        hint.setFrame_(NSMakeRect(12, self.h - 28, 200, 18))
        hint.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(0.6, 1.0))
        hint.setFont_(NSFont.systemFontOfSize_(11))
        content.addSubview_(hint)

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(10, 10, self.w - 20, self.h - 46))
        scroll.setHasVerticalScroller_(True)
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(0)
        tv = NSTextView.alloc().initWithFrame_(scroll.contentView().bounds())
        tv.setEditable_(False)
        tv.setSelectable_(True)
        tv.setDrawsBackground_(False)
        tv.setTextColor_(NSColor.whiteColor())
        tv.setFont_(NSFont.systemFontOfSize_(13))
        tv.setVerticallyResizable_(True)
        tv.setHorizontallyResizable_(False)
        tv.setAutoresizingMask_(2)
        tv.textContainer().setWidthTracksTextView_(True)
        scroll.setDocumentView_(tv)
        content.addSubview_(scroll)
        self.text_view = tv
        return self

    @objc.python_method
    def show(self, text):
        self.text_view.setString_(text)
        if not self.placed:  # bottom-right the first time only; afterwards stays where you drag it
            vf = NSScreen.mainScreen().visibleFrame()
            self.panel.setFrameOrigin_((vf.origin.x + vf.size.width - self.w - self.margin,
                                        vf.origin.y + self.margin))
            self.placed = True
        self.panel.orderFrontRegardless()

    @objc.python_method
    def hide(self):
        self.panel.orderOut_(None)
        if self.on_hide:
            self.on_hide()

    @objc.python_method
    def visible(self):
        return bool(self.panel.isVisible())

    @objc.python_method
    def text(self):
        return str(self.text_view.string())

    def hideClicked_(self, _sender):
        self.hide()

    def copyClicked_(self, _sender):
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(self.text(), NSPasteboardTypeString)


# ---------------------------------------------------------------------- app
class ScreenAsk(rumps.App):
    def __init__(self):
        super().__init__(RED, quit_button="Quit")
        self.cfg = load_config()
        self.busy = False
        self.state = RED
        self.queue = []
        self._was_visible = False
        self.popup = PopupController.alloc().init()
        self.popup.on_hide = self._popup_hidden
        self.k = {n: pretty(self.cfg[f"hotkey_{n}"])
                  for n in ("capture", "toggle", "add", "send", "clear")}
        k = self.k
        self.menu = [
            rumps.MenuItem(f"Ask now (1 screenshot)   {k['capture']}", callback=lambda _: self.capture()),
            None,
            rumps.MenuItem(f"Add screenshot to batch   {k['add']}", callback=lambda _: self.add_shot()),
            rumps.MenuItem(f"Send batch   {k['send']}", callback=lambda _: self.send_batch()),
            rumps.MenuItem(f"Clear batch   {k['clear']}", callback=lambda _: self.clear_batch()),
            None,
            rumps.MenuItem(f"Show / Hide answer   {k['toggle']}", callback=lambda _: self.toggle()),
            None,
            rumps.MenuItem("Set Gemini API Key…", callback=self.set_key),
            rumps.MenuItem("Set Model…", callback=self.set_model),
        ]
        AppHelper.callAfter(self._startup)

    # ---- status circle (+ number of screenshots waiting in the batch)
    def set_state(self, sym):
        self.state = sym
        self.title = sym + (f" {len(self.queue)}" if self.queue else "")

    def _startup(self):
        k = self.k
        problems = []
        try:
            self.hotkeys = HotKeys()
            for name, fn in (("capture", self.capture), ("toggle", self.toggle),
                             ("add", self.add_shot), ("send", self.send_batch),
                             ("clear", self.clear_batch)):
                if not self.hotkeys.register(self.cfg[f"hotkey_{name}"], fn):
                    problems.append(f"{k[name]} is already used by another app")
        except Exception as e:
            problems.append(f"hotkeys failed: {e}")
        try:
            from Quartz import CGPreflightScreenCaptureAccess, CGRequestScreenCaptureAccess
            if not CGPreflightScreenCaptureAccess():
                CGRequestScreenCaptureAccess()
                problems.append("Allow 'Screen Recording' for this app (or Terminal) in System Settings "
                                "→ Privacy & Security, then restart this app")
        except Exception:
            pass
        msg = (f"Ready.\n{k['capture']}  screenshot + answer now\n"
               f"{k['add']}  add screenshot to batch\n{k['send']}  send batch (all answers in a row)\n"
               f"{k['clear']}  clear batch\n{k['toggle']}  hide / show this popup")
        if not self.cfg["api_key"]:
            msg += "\n\nFirst: click the circle in the menu bar → Set Gemini API Key…"
        if problems:
            msg += "\n\n⚠️ " + "\n⚠️ ".join(problems)
        self.popup.show(msg)

    def _popup_hidden(self):
        if not self.busy:
            self.set_state(RED)

    def _need_key(self):
        if self.cfg["api_key"]:
            return True
        self.popup.show("No API key yet.\nMenu bar circle → Set Gemini API Key…")
        return False

    def toggle(self):
        if self.popup.visible():
            self.popup.hide()
        elif self.popup.text():
            self.popup.show(self.popup.text())
            if not self.busy:
                self.set_state(GREEN)

    # ---- single: screenshot now and answer
    def capture(self):
        if self.busy or not self._need_key():
            return
        self.busy = True
        self.set_state(YELLOW)
        self.popup.panel.orderOut_(None)  # keep the popup out of the screenshot
        threading.Thread(target=self._worker, args=(False,), daemon=True).start()

    # ---- batch: add screenshots, then send them all at once
    def add_shot(self):
        if self.busy:
            return
        if len(self.queue) >= 20:
            self.popup.show("Batch is full (20). Send it or clear it first.")
            return
        self.busy = True
        self._was_visible = self.popup.visible()
        self.popup.panel.orderOut_(None)
        threading.Thread(target=self._add_worker, daemon=True).start()

    def _add_worker(self):
        try:
            time.sleep(0.15)
            AppHelper.callAfter(self._added, grab_b64(self.cfg), None)
        except Exception as e:
            AppHelper.callAfter(self._added, None, str(e))

    def _added(self, b64, err):
        self.busy = False
        if b64:
            self.queue.append(b64)
            try:
                NSSound.soundNamed_("Tink").play()
            except Exception:
                pass
        self.set_state(RED)
        if err:
            self.popup.show(f"Error: {err}")
        elif self._was_visible:
            self.popup.panel.orderFrontRegardless()

    def send_batch(self):
        if self.busy:
            return
        if not self.queue:
            self.popup.show(f"Batch is empty. Press {self.k['add']} to add screenshots first.")
            return
        if not self._need_key():
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
                time.sleep(0.15)
                images = [grab_b64(self.cfg)]
            if len(images) == 1:
                prompt = self.cfg["prompt_single"]
            else:
                prompt = self.cfg["prompt_batch"].replace("{n}", str(len(images)))
            text = stream_answer(self.cfg, images, prompt,
                                 lambda t: AppHelper.callAfter(self.popup.show, t))
            AppHelper.callAfter(self._done, text, True, use_queue)
        except Exception as e:
            s = str(e)
            hint = ""
            if "400" in s or "401" in s or "403" in s:
                hint = "\n\nCheck your API key (menu bar circle → Set Gemini API Key…)"
            elif "404" in s or "model" in s.lower():
                hint = "\n\nTry another model (menu bar circle → Set Model…), e.g. gemini-2.5-flash or gemini-flash-latest"
            elif "429" in s:
                hint = "\n\nRate limit hit (free tier). Wait a minute and try again"
            AppHelper.callAfter(self._done, f"Error: {s}{hint}", False, use_queue)

    def _done(self, text, ok, use_queue):
        self.busy = False
        if ok and use_queue:
            self.queue = []  # on failure the batch is kept so you can just retry
        self.set_state(GREEN if ok else RED)
        self.popup.show(text)

    def _ask(self, title, msg, key, width):
        r = rumps.Window(msg, title, default_text=self.cfg[key], ok="Save",
                         cancel="Cancel", dimensions=(width, 24)).run()
        if r.clicked and r.text.strip():
            self.cfg[key] = r.text.strip()
            save_config(self.cfg)

    def set_key(self, _):
        self._ask("Gemini API Key", "Paste your free key from aistudio.google.com/apikey:",
                  "api_key", 360)

    def set_model(self, _):
        self._ask("Model", "Model name (gemini-2.5-flash = fast, gemini-2.5-pro = smarter):",
                  "model", 300)


if __name__ == "__main__":
    NSApplication.sharedApplication().setActivationPolicy_(1)
    ScreenAsk().run()
