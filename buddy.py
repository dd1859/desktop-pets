#!/usr/bin/env python3
"""
Tiny Buddy - a 2D desktop pet cat / axolotl for Windows.

Sprites: "Cat || Pixel Asset Pack" and "Tiny Axolotl" by Pop Shop Packs
(https://pop-shop-packs.itch.io).  See assets/CREDITS.md for the license.

Run:      py buddy.py
Test:     py buddy.py --selftest
"""

from __future__ import annotations

import ctypes
import json
import math
import queue
import random
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageTk

# --------------------------------------------------------------------------- #
#  Constants / asset metadata
# --------------------------------------------------------------------------- #

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
CONFIG_PATH = APP_DIR / "config.json"

CELL = 16                     # every sprite is a 16 x 16 pixel cell
KEY = "#ff00ff"               # colour-key transparency (not used by the art)
RGB_KEY = (255, 0, 255)
IS_WINDOWS = sys.platform == "win32"

# Frame cells (row, column) inside the sheets.
# Cat sheet: 4 columns x 32 rows.  Direction rows, index 0..7:
#   down, down-left, left, up-left, up, up-right, right, down-right.
# Walk block starts at row 4, crouch block at 13, sit block at 22.
# Axolotl sheet: 8 columns x 16 rows, two mirrored halves.  Row 4 faces left,
# row 12 faces right (verified from the sprite geometry).
ANIMATIONS: dict[str, dict[str, dict]] = {
    "cat": {
        "walk": {
            "right": [(10, i) for i in range(4)],
            "left":  [(6, i) for i in range(4)],
            "fps": 10, "loop": True,
        },
        "stand": {
            "right": [(2, 2)],
            "left":  [(1, 2)],
            "fps": 1, "loop": True,
        },
        "sit": {
            "right": [(28, i) for i in range(4)],
            "left":  [(24, i) for i in range(4)],
            "fps": 9, "loop": False,
        },
        "sit_pose": {
            "right": [(28, 3)],
            "left":  [(24, 3)],
            "fps": 1, "loop": True,
        },
        "crouch": {                       # the pack's crouch/pounce - used to jump
            "right": [(19, i) for i in range(4)],
            "left":  [(15, i) for i in range(4)],
            "fps": 14, "loop": False,
        },
        "fall": {
            "right": [(10, 1), (10, 3)],
            "left":  [(6, 1), (6, 3)],
            "fps": 12, "loop": True,
        },
        "eat": {
            "right": [(28, i) for i in range(4)],
            "left":  [(24, i) for i in range(4)],
            "fps": 8, "loop": True,
        },
    },
    "axolotl": {
        "walk": {
            "right": [(12, i) for i in range(4)],
            "left":  [(4, i) for i in range(4)],
            "fps": 7, "loop": True,
        },
        "stand": {
            "right": [(12, 0)],
            "left":  [(4, 0)],
            "fps": 1, "loop": True,
        },
        "sit": {
            "right": [(12, i) for i in range(4)],
            "left":  [(4, i) for i in range(4)],
            "fps": 4, "loop": True,
        },
        "sit_pose": {
            "right": [(12, 0)],
            "left":  [(4, 0)],
            "fps": 1, "loop": True,
        },
        "crouch": {
            "right": [(12, i) for i in range(4)],
            "left":  [(4, i) for i in range(4)],
            "fps": 13, "loop": False,
        },
        "fall": {
            "right": [(12, i) for i in range(4)],
            "left":  [(4, i) for i in range(4)],
            "fps": 10, "loop": True,
        },
        "eat": {
            "right": [(12, i) for i in range(4)],
            "left":  [(4, i) for i in range(4)],
            "fps": 6, "loop": True,
        },
    },

"frog": {
    "walk": {
        "right": [(0, i) for i in range(5)],
        "left": [(0, i, True) for i in range(5)],
        "fps": 7,
        "loop": True,
    },
    "stand": {
        "right": [(0, 0)],
        "left": [(0, 0, True)],
        "fps": 1,
        "loop": True,
    },
    "sit": {
        "right": [(0, i) for i in range(5)],
        "left": [(0, i, True) for i in range(5)],
        "fps": 4,
        "loop": True,
    },
    "sit_pose": {
        "right": [(0, 0)],
        "left": [(0, 0, True)],
        "fps": 1,
        "loop": True,
    },
    "crouch": {
        "right": [(0, i) for i in range(5)],
        "left": [(0, i, True) for i in range(5)],
        "fps": 13,
        "loop": False,
    },
    "fall": {
        "right": [(0, i) for i in range(5)],
        "left": [(0, i, True) for i in range(5)],
        "fps": 10,
        "loop": True,
    },
    "eat": {
        "right": [(0, i) for i in range(5)],
        "left": [(0, i, True) for i in range(5)],
        "fps": 6,
        "loop": True,
    },
},

}

PHRASES = {
    "cat": ["I am hungry", "Zoomies soon?", "Purr purr", "Treat please"],
    "axolotl": ["Glub glub", "What's floating up there?", "Wiggle wiggle"],
    "frog": ["Ribbit ribbit", "Bouncy!", "Fly? Where fly?", "Croak!"],
}

DEFAULT_CONFIG = {
    "pet": "cat",
    "color": "orange-00",
    "name": "Mochi",
    "scale": 4,
    "follow": False,
    "mood": 80,
    "x": None,
    "y": None,
    "toy_kind": "tennis",
    "chatter": True,
}


# --------------------------------------------------------------------------- #
#  Windows helpers
# --------------------------------------------------------------------------- #

def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


def get_work_area(fallback_w: int, fallback_h: int) -> tuple[int, int, int, int]:
    """Desktop area minus the taskbar, in physical pixels."""
    if IS_WINDOWS:
        try:
            r = RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):
                return int(r.left), int(r.top), int(r.right), int(r.bottom)
        except Exception:
            pass
    return 0, 0, fallback_w, fallback_h - 48


def cursor_pos() -> tuple[int, int]:
    if IS_WINDOWS:
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    return 0, 0


def make_no_activate(win: tk.Misc) -> None:
    """Keep the pet from stealing keyboard focus from whatever you are doing."""
    if not IS_WINDOWS:
        return
    try:
        win.update_idletasks()
        u = ctypes.windll.user32
        u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetAncestor.restype = wintypes.HWND
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_int
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int]
        u.SetWindowLongW.restype = ctypes.c_int

        hwnd = u.GetAncestor(int(win.winfo_id()), 2)  # GA_ROOT
        if not hwnd:
            hwnd = int(win.winfo_id())
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
    except Exception:
        pass


def make_transparent(win: tk.Toplevel) -> None:
    try:
        win.tk.call("wm", "overrideredirect", win._w, 1)
    except tk.TclError:
        win.overrideredirect(True)
    win.configure(bg=KEY)
    win.wm_attributes("-topmost", 1)
    try:
        win.wm_attributes("-transparentcolor", KEY)
    except tk.TclError:
        pass


def geometry_string(x: float, y: float, w: int, h: int) -> str:
    sx = f"+{int(x)}" if x >= 0 else str(int(x))
    sy = f"+{int(y)}" if y >= 0 else str(int(y))
    return f"{w}x{h}{sx}{sy}"


# --------------------------------------------------------------------------- #
#  Global hotkey (Ctrl+Alt+B) - no extra dependencies
# --------------------------------------------------------------------------- #

class GlobalHotkey(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.events: "queue.Queue[str]" = queue.Queue()
        self.ok = False
        self._thread_id: Optional[int] = None

    def run(self) -> None:
        if not IS_WINDOWS:
            return
        u = ctypes.windll.user32
        u.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int,
                                     wintypes.UINT, wintypes.UINT]
        u.RegisterHotKey.restype = wintypes.BOOL
        MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
        try:
            self.ok = bool(u.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT,
                                            ord("B")))
        except Exception:
            self.ok = False
        if not self.ok:
            return
        self._thread_id = int(ctypes.windll.kernel32.GetCurrentThreadId())
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:          # WM_HOTKEY
                self.events.put("toggle")
        u.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if IS_WINDOWS and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)


# --------------------------------------------------------------------------- #
#  Small pixel-art helpers
# --------------------------------------------------------------------------- #

_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def pixel_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    font = None
    for name in ("segoeui.ttf", "arial.ttf", "tahoma.ttf"):
        try:
            font = ImageFont.truetype(name, size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def make_photo(img: Image.Image) -> ImageTk.PhotoImage:
    """Composite RGBA art on the colour key and return a Tk image."""
    bg = Image.new("RGB", img.size, RGB_KEY)
    bg.paste(img, (0, 0), img)
    return ImageTk.PhotoImage(bg)


def make_toy_image(scale: int, kind: str = 'core') -> Image.Image:
    w, h = 12, 12
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = {
        'core': ((255, 105, 92),  (255, 205, 140)),
        'tennis': ((185, 235, 95), (245, 245, 235)),
        'baseball': ((240, 240, 242), (220, 60, 70)),
        'soccer': ((245, 245, 245), (42, 45, 50)),
        'golf': ((248, 248, 248), (130, 200, 170)),
    }.get(kind, ((255, 105, 92), (255, 205, 140)))
    outline = (80, 50, 30, 255)
    ball, stripe = (*c[0], 255), (*c[1], 255)
    d.ellipse((0, 0, w - 1, h - 1), fill=ball, outline=outline, width=1)
    if kind == 'tennis':
        d.chord((0, 2, w - 1, 10), 20, 160, fill=stripe, outline=outline)
        d.chord((0, 2, w - 1, 10), 200, 340, fill=stripe, outline=outline)
    elif kind == 'baseball':
        d.arc((0, 0, w - 1, h - 1), 45, 135, fill=outline, width=1)
        d.arc((0, 0, w - 1, h - 1), 200, 315, fill=outline, width=1)
        d.ellipse((6, 4, 8, 6), fill=stripe)
    elif kind == 'soccer':
        d.polygon([(6, 0), (9, 3), (8, 7), (4, 7), (3, 3)], fill=stripe, outline=outline)
        d.line((0, 4, w - 1, 4), fill=stripe)
    else:
        d.ellipse((2, 3, 7, 7), fill=stripe)
        d.ellipse((6, 4, 10, 8), fill=((190, 160, 100, 255)))
    return img.resize((w * scale, h * scale), Image.NEAREST)

def make_treat_image(scale: int) -> Image.Image:
    """A tiny pixel fish, drawn in code so the pet has something to eat."""
    w, h = 13, 9
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    outline = (86, 48, 28, 255)
    body = (255, 158, 92, 255)
    light = (255, 198, 128, 255)
    d.ellipse((1, 2, 9, 8), fill=body, outline=outline)
    d.polygon([(9, 5), (12, 1), (12, 8)], fill=(247, 124, 76, 255), outline=outline)
    d.ellipse((2, 2, 7, 5), fill=light)
    d.point((3, 4), fill=(28, 24, 24, 255))
    d.point((4, 4), fill=(28, 24, 24, 255))
    return img.resize((w * scale, h * scale), Image.NEAREST)


def make_paw_image(size: int = 52) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = (255, 205, 140, 255)
    edge = (104, 66, 38, 255)
    d.ellipse((10, 22, 42, 48), fill=pad, outline=edge, width=2)
    for cx, cy, rx, ry in ((12, 18, 7, 8), (25, 12, 7, 8), (38, 18, 7, 8), (45, 30, 5, 6)):
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=pad, outline=edge, width=2)
    return img


def rounded_bubble(text: str, font_size: int = 12,
                   padding: tuple[int, int] = (10, 6)) -> Image.Image:
    font = pixel_font(font_size)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = probe.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    w = tw + padding[0] * 2
    h = th + padding[1] * 2 + 6
    img = Image.new("RGBA", (w, h + 7), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=8,
                        fill=(255, 247, 230, 255), outline=(128, 92, 54, 255))
    d.polygon([(w // 2 - 5, h - 1), (w // 2 + 5, h - 1), (w // 2, h + 6)],
              fill=(255, 247, 230, 255), outline=(128, 92, 54, 255))
    d.text((padding[0] - bbox[0], padding[1] - bbox[1]), text,
           font=font, fill=(58, 42, 28, 255))
    return img


# --------------------------------------------------------------------------- #
#  Treat / heart effects
# --------------------------------------------------------------------------- #

class ToyBall:
    def __init__(self, app: "BuddyApp", x: int, y: int, kind: Optional[str] = None) -> None:
        self.app = app
        self.kind = kind or app.toy_kind
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.photo = app.toy_photos.get(self.kind, app.toy_photo)
        self._drag_off = (0, 0)
        self._last_drag = None
        self._grabbed = False
        self.win = tk.Toplevel(app.root)
        make_transparent(self.win)
        self.canvas = tk.Canvas(self.win, width=self.photo.width(),
                                height=self.photo.height(), bg=KEY,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.item = self.canvas.create_image(0, 0, anchor="nw",
                                             image=self.photo)
        for w in (self.win, self.canvas):
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
        self.win.geometry(geometry_string(self.x, self.y, self.photo.width(),
                                           self.photo.height()))
        self.win.deiconify()
        make_no_activate(self.win)

    @property
    def ground(self) -> float:
        return self.app.work_bottom - self.photo.height()

    def update(self, dt: float) -> None:
        if not getattr(self, "_grabbed", False):
            self.vy += 900 * dt
            self.vx *= 0.99
            self.vy *= 0.99
            self.x += self.vx * dt
            self.y += self.vy * dt

            if self.y + self.photo.height() // 2 >= self.ground + (self.photo.height() // 2):
                self.y = self.ground
                self._bounce_floor()
            if self.y < self.app.work_top:
                self.y = float(self.app.work_top)
                self.vy = -self.vy * 0.75
            if self.x <= self.app.work_left:
                self.x = float(self.app.work_left)
                self.vx = -self.vx * 0.75
            if self.x >= self.app.work_right - self.photo.width():
                self.x = float(self.app.work_right - self.photo.width())
                self.vx = -self.vx * 0.75
        self.win.geometry(geometry_string(self.x, self.y,
                                          self.photo.width(),
                                          self.photo.height()))
        if abs(self.vx) < 3 and abs(self.vy) < 3 and self.y >= self.ground - 1:
            self.vx = 0
            self.vy = 0

    def _bounce_floor(self) -> None:
        if self.vy < -1:
            self.vy = -self.vy * 0.75
            if abs(self.vy) < 1:
                self.vy = 0
        else:
            self.vy = 0

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def on_press(self, event) -> None:
        self._drag_off = (event.x_root - self.x, event.y_root - self.y)
        self._last_drag = (event.x_root, event.y_root, getattr(event, "timestamp", 0) or 0)
        self._dragged = False

    def on_drag(self, event) -> None:
        self._dragged = True
        prev = self._last_drag or (event.x_root, event.y_root, getattr(event, "timestamp", 0) or 0)
        dt = max(0.016, (getattr(event, "timestamp", 0) or 0 - prev[2]) / 1000.0)
        self._vx = (event.x_root - prev[0]) / dt
        self._vy = (event.y_root - prev[1]) / dt
        tx = event.x_root - self._drag_off[0]
        ty = event.y_root - self._drag_off[1]
        self.x = max(self.app.work_left, min(self.app.work_right - self.photo.width(), tx))
        self.y = max(self.app.work_top, min(self.app.work_bottom - self.photo.height(), ty))
        self.win.geometry(geometry_string(self.x, self.y, self.photo.width(), self.photo.height()))
        self._last_drag = (event.x_root, event.y_root, getattr(event, "timestamp", 0) or 0)

    def on_release(self, event) -> None:
        if getattr(self, "_dragged", False):
            self._dragged = False
            self.vx = getattr(self, "_vx", 0.0)
            self.vy = getattr(self, "_vy", 0.0)
            if abs(self.vx) < 20 and abs(self.vy) < 20:
                if type(self).__name__ == "ToyBall":
                    self.vx = 260.0
                    self.vy = -300.0
                else:
                    self.vx = 0.0
                    self.vy = 0.0

class Treat:
    def __init__(self, app: "BuddyApp", x: int, y: int) -> None:
        self.app = app
        self.x = float(x)
        self.y = float(y)
        self.vy = 0.0
        self.landed = False
        self.photo = app.treat_photo
        self.win = tk.Toplevel(app.root)
        make_transparent(self.win)
        self.canvas = tk.Canvas(self.win, width=self.photo.width(),
                                height=self.photo.height(), bg=KEY,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.item = self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        for w in (self.win, self.canvas):
            w.bind("<ButtonPress-1>", self.on_press)
            w.bind("<B1-Motion>", self.on_drag)
            w.bind("<ButtonRelease-1>", self.on_release)
        self.win.geometry(geometry_string(self.x, self.y,
                                          self.photo.width(), self.photo.height()))
        self.win.deiconify()
        make_no_activate(self.win)

    @property
    def ground(self) -> float:
        return self.app.work_bottom - self.photo.height()

    def update(self, dt: float) -> None:
        if not self.landed:
            self.vy += 1500 * dt
            self.y += self.vy * dt
            if self.y >= self.ground:
                self.y = self.ground
                self.landed = True
                self.vy = 0
        gx = self.x
        self.win.geometry(geometry_string(gx, self.y,
                                          self.photo.width(), self.photo.height()))

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def on_press(self, event) -> None:
        self._drag_off = (event.x_root - self.x, event.y_root - self.y)
        self._last_drag = (event.x_root, event.y_root, getattr(event, "timestamp", 0) or 0)
        self._dragged = False

    def on_drag(self, event) -> None:
        self._dragged = True
        prev = self._last_drag or (event.x_root, event.y_root, getattr(event, "timestamp", 0) or 0)
        dt = max(0.016, (getattr(event, "timestamp", 0) or 0 - prev[2]) / 1000.0)
        self._vx = (event.x_root - prev[0]) / dt
        self._vy = (event.y_root - prev[1]) / dt
        tx = event.x_root - self._drag_off[0]
        ty = event.y_root - self._drag_off[1]
        self.x = max(self.app.work_left, min(self.app.work_right - self.photo.width(), tx))
        self.y = max(self.app.work_top, min(self.app.work_bottom - self.photo.height(), ty))
        self.win.geometry(geometry_string(self.x, self.y, self.photo.width(), self.photo.height()))
        self._last_drag = (event.x_root, event.y_root, getattr(event, "timestamp", 0) or 0)

    def on_release(self, event) -> None:
        if getattr(self, "_dragged", False):
            self._dragged = False
            self.vx = getattr(self, "_vx", 0.0)
            self.vy = getattr(self, "_vy", 0.0)
            if abs(self.vx) < 20 and abs(self.vy) < 20:
                if type(self).__name__ == "ToyBall":
                    self.vx = 260.0
                    self.vy = -300.0
                else:
                    self.vx = 0.0
                    self.vy = 0.0


class Heart:
    def __init__(self, app: "BuddyApp", x: int, y: int) -> None:
        self.app = app
        self.life = 0.0
        self.win = tk.Toplevel(app.root)
        make_transparent(self.win)
        lbl = tk.Label(self.win, text="\u2665", fg="#ff5c8a", bg=KEY,
                       font=("Segoe UI", 15, "bold"))
        lbl.pack()
        self.win.geometry(geometry_string(x, y, 22, 26))
        self.win.deiconify()
        make_no_activate(self.win)
        self.x, self.y = float(x), float(y)

    def update(self, dt: float) -> bool:
        self.life += dt
        self.y -= 26 * dt
        self.win.geometry(geometry_string(self.x, self.y, 22, 26))
        return self.life < 1.1


# --------------------------------------------------------------------------- #
#  Dialogs
# --------------------------------------------------------------------------- #

class PromptDialog(tk.Toplevel):
    def __init__(self, app: "BuddyApp", title: str, label: str,
                 initial: str, on_ok) -> None:
        super().__init__(app.root)
        self.app = app
        self.on_ok = on_ok
        self.title(title)
        self.configure(bg="#f7efe2", padx=14, pady=12)
        self.resizable(False, False)
        self.wm_attributes("-topmost", True)
        tk.Label(self, text=label, bg="#f7efe2", fg="#3a2c1e",
                 font=("Segoe UI", 10)).pack(anchor="w")
        self.entry = tk.Entry(self, font=("Segoe UI", 11), width=30)
        self.entry.pack(fill="x", pady=(6, 12))
        self.entry.insert(0, initial)
        self.entry.select_range(0, "end")
        row = tk.Frame(self, bg="#f7efe2")
        row.pack(fill="x")
        tk.Button(row, text="Cancel", command=self.destroy,
                  bg="#ead9bf", relief="flat", padx=12).pack(side="right")
        tk.Button(row, text="Save", command=self.save,
                  bg="#ffd79a", relief="flat", padx=14).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        w, h = 360, 150
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        self.after(60, self._focus)

    def _focus(self) -> None:
        self.lift()
        self.focus_force()
        self.entry.focus_set()

    def save(self) -> None:
        value = self.entry.get().strip()
        self.destroy()
        if value:
            self.on_ok(value)


class BuddyPicker(tk.Toplevel):
    """Pick species + colour + name."""

    def __init__(self, app: "BuddyApp") -> None:
        super().__init__(app.root)
        self.app = app
        self.title("Choose your buddy")
        self.configure(bg="#f7efe2")
        self.wm_attributes("-topmost", True)
        self.minsize(620, 540)
        self.pet_var = tk.StringVar(value=app.pet_type)
        self.color_var = tk.StringVar(value=app.color)
        self.thumbs: dict[tuple[str, str], ImageTk.PhotoImage] = {}
        self._swatch_frames: dict[str, tk.Frame] = {}

        head = tk.Frame(self, bg="#f7efe2")
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text="Choose your buddy", bg="#f7efe2", fg="#3a2c1e",
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        tk.Label(head, text="Sprites by Pop Shop Packs", bg="#f7efe2",
                 fg="#9a8267", font=("Segoe UI", 8)).pack(side="right")

        species = tk.Frame(self, bg="#f7efe2")
        species.pack(fill="x", padx=16, pady=(2, 8))
        for key in ("cat", "axolotl", "frog"):
            tk.Radiobutton(
                species, text=app.manifest["pets"][key]["label"],
                variable=self.pet_var, value=key, command=self.rebuild,
                bg="#f7efe2", activebackground="#f7efe2", selectcolor="#ffd79a",
                font=("Segoe UI", 10), indicatoron=False, padx=16, pady=5,
                relief="flat", bd=0,
            ).pack(side="left", padx=(0, 8))

        wrap = tk.Frame(self, bg="#f7efe2")
        wrap.pack(fill="both", expand=True, padx=16)
        self.canvas = tk.Canvas(wrap, bg="#efe2cf", highlightthickness=0)
        bar = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.grid_frame = tk.Frame(self.canvas, bg="#efe2cf")
        self.window_id = self.canvas.create_window((0, 0), window=self.grid_frame,
                                                   anchor="nw")
        self.grid_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<MouseWheel>", self._wheel)

        bottom = tk.Frame(self, bg="#f7efe2")
        bottom.pack(fill="x", padx=16, pady=12)
        tk.Label(bottom, text="Name", bg="#f7efe2", fg="#3a2c1e",
                 font=("Segoe UI", 10)).pack(side="left")
        self.name_entry = tk.Entry(bottom, font=("Segoe UI", 11), width=18)
        self.name_entry.pack(side="left", padx=8)
        self.name_entry.insert(0, app.name)
        tk.Button(bottom, text="Cancel", command=self.destroy, bg="#ead9bf",
                  relief="flat", padx=14, pady=4).pack(side="right")
        tk.Button(bottom, text="Save", command=self.save, bg="#ffd79a",
                  relief="flat", padx=18, pady=4).pack(side="right", padx=8)

        self.rebuild()
        self.update_idletasks()
        w, h = 660, 560
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        self.after(80, lambda: (self.lift(), self.focus_force()))

    def _wheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def rebuild(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self._swatch_frames.clear()
        pet = self.pet_var.get()
        colors = self.app.manifest["pets"][pet]["colors"]
        if self.app.color_for(pet) != self.color_var.get():
            # keep the current selection if this species has that colour
            ids = {c["id"] for c in colors}
            if self.color_var.get() not in ids:
                self.color_var.set(self.app.config.get("color", colors[0]["id"])
                                   if self.app.config.get("pet") == pet else colors[0]["id"])
        columns = 5
        for i, color in enumerate(colors):
            cell = tk.Frame(self.grid_frame, bg="#efe2cf")
            cell.grid(row=i // columns, column=i % columns, padx=7, pady=7)
            thumb = self.app.thumbnail(pet, color["id"])
            lbl = tk.Label(cell, image=thumb, bg="#efe2cf", bd=0)
            lbl.pack()
            name = tk.Label(cell, text=color["label"], bg="#efe2cf", fg="#4a3826",
                            font=("Segoe UI", 8))
            name.pack()
            for widget in (cell, lbl, name):
                widget.bind("<Button-1>", lambda e, c=color["id"]: self.select(c))
            self._swatch_frames[color["id"]] = cell
        self.update_selection()
        self.grid_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0)

    def update_selection(self) -> None:
        for cid, frame in self._swatch_frames.items():
            frame.configure(bg="#ffd79a" if cid == self.color_var.get() else "#efe2cf",
                            highlightthickness=2,
                            highlightbackground="#ffd79a" if cid == self.color_var.get() else "#efe2cf")
            for child in frame.winfo_children():
                child.configure(bg=frame["bg"])

    def select(self, cid: str) -> None:
        self.color_var.set(cid)
        self.update_selection()

    def save(self) -> None:
        name = self.name_entry.get().strip() or self.app.name
        self.app.apply_identity(self.pet_var.get(), self.color_var.get(), name)
        self.destroy()


# --------------------------------------------------------------------------- #
#  Main application
# --------------------------------------------------------------------------- #

class BuddyApp:
    # states
    IDLE, WALK, SIT, CLIMB, HANG, FALL, LAND, JUMP, EAT, FOLLOW, DRAG = (
        "idle", "walk", "sit", "climb", "hang", "fall", "land", "jump", "eat",
        "follow", "drag",
    )

    def __init__(self, root: tk.Tk, config_path: Optional[str] = None,
                  own_hotkey: bool = False) -> None:
        self.root = root
        self.alive = True
        self.manifest = json.loads((ASSETS_DIR / "manifest.json").read_text("utf-8"))
        self.config_path = config_path or "config.json"
        self.own_hotkey = own_hotkey
        self.config = self.load_config()
        self.pet_type = self.config["pet"]
        self.color = self.color_for(self.pet_type, self.config["color"])
        self.cell = int(self.manifest["pets"][self.pet_type]["sheet"].get("cell", 16))
        self.name = str(self.config.get("name") or self.default_name(self.pet_type))[:24]
        self.scale = max(2, min(7, int(self.config.get("scale", 4))))
        self.size = self.cell * self.scale
        self.follow_mode = bool(self.config.get("follow", False))
        self.mood = int(self.config.get("mood", 80))
        self.chatter = bool(self.config.get("chatter", True))
        self._next_chatter = time.perf_counter() + random.uniform(60, 120)

        self.work_left, self.work_top, self.work_right, self.work_bottom = get_work_area(
            root.winfo_screenwidth(), root.winfo_screenheight())
        self.body_bottom_px = self.resting_bottom_pixels(self.pet_type)
        self.ground_y = self.work_bottom - self.body_bottom_px * self.scale
        self.top_y = self.work_top + 2

        # animation / physics state
        self.x = float(self.config.get("x") if self.config.get("x") is not None
                       else (self.work_left + self.work_right - self.size) / 2)
        self.y = float(self.config.get("y") if self.config.get("y") is not None
                       else self.ground_y)
        self.x = max(self.work_left, min(self.work_right - self.size, self.x))
        self.y = max(self.top_y, min(self.ground_y, self.y))
        self.facing = 1
        self.state = self.IDLE if abs(self.y - self.ground_y) < 1 else self.FALL
        self.state_t = 0.0
        self.anim_name = "stand"
        self.anim_t = 0.0
        self.anim_index = 0
        self.anim_done = False
        self.vy = 0.0
        self.target_x = self.x
        self.arrive_action: Optional[str] = None
        self.climb_side: Optional[str] = None
        self.climb_rot = 0
        self.hang_time = 0.0
        self.next_decision = 1.5
        self._rev_play = False
        self.climb_cooldown = 12.0
        self.pending_climb: Optional[str] = None
        self.jump_phase = 0
        self.squash = 0.0
        self.drag_off = (0, 0)
        self.drag_moved = False
        self.last_geom = (None, None)
        self._photo: Optional[ImageTk.PhotoImage] = None
        self._hover_job: Optional[str] = None
        self._tag_job: Optional[str] = None
        self._card_job: Optional[str] = None
        self._tick_id: Optional[str] = None
        self._poll_id: Optional[str] = None
        self._tag_win: Optional[tk.Toplevel] = None
        self._tag_size: tuple[int, int] = (0, 0)
        self._tag_follows_pet = True
        self._action_card: Optional[tk.Toplevel] = None
        self._clones: list = []
        self._picker: Optional[BuddyPicker] = None
        self._hidden = False
        self._treats: list[Treat] = []
        self._toys: list[ToyBall] = []
        self._toy_score: int = 0
        self._fetch_busy_until: float = 0.0
        self._hearts: list[Heart] = []
        self._last_tick = time.perf_counter()
        self._last_save = time.perf_counter()

        self.walk_speed = 120 * (self.scale / 4)
        self.climb_speed = 90 * (self.scale / 4)
        self.gravity = 2400 * (self.scale / 4)
        self.jump_speed = math.sqrt(2 * self.gravity * 115 * (self.scale / 4))

        # caches
        self._sheets: dict[tuple[str, str], Image.Image] = {}
        self._frames: dict[tuple, ImageTk.PhotoImage] = {}
        self._thumbs: dict[tuple[str, str], ImageTk.PhotoImage] = {}
        self.treat_photo = make_photo(make_treat_image(max(2, self.scale - 1)))
        self.toy_photo = make_photo(make_toy_image(max(3, self.scale)))
        self.toy_photos = {
            key: make_photo(make_toy_image(max(3, self.scale), key))
            for key in ("core", "tennis", "baseball", "soccer", "golf")
        }
        hmay = self._extract_hamu_ball(self.scale)
        if hmay is not None:
            self.toy_photos["hamu"] = hmay
        self.toy_kind = str(self.config.get("toy_kind", "tennis"))
        if self.toy_kind not in self.toy_photos:
            self.toy_kind = "tennis"
        self.toy_photo = self.toy_photos[self.toy_kind]
        self.paw_photo = make_photo(make_paw_image(52))

        # windows
        self.win = tk.Toplevel(root)
        make_transparent(self.win)
        self.canvas = tk.Canvas(self.win, width=self.size, height=self.size,
                                bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.image_id = self.canvas.create_image(self.size // 2, self.size // 2,
                                                 image=self.frame_photo())
        self.win.geometry(geometry_string(self.x, self.y, self.size, self.size))
        self.win.deiconify()
        make_no_activate(self.win)
        self._bind_pet_events()

        # dock (shown while hidden)
        self.dock = tk.Toplevel(root)
        make_transparent(self.dock)
        dock_canvas = tk.Canvas(self.dock, width=52, height=52, bg=KEY,
                                highlightthickness=0, bd=0)
        dock_canvas.pack()
        dock_canvas.create_image(26, 26, image=self.paw_photo)
        dock_canvas.bind("<Button-1>", lambda e: self.show_pet())
        self.dock.geometry(geometry_string(self.work_right - 68,
                                           self.work_bottom - 68, 52, 52))
        self.dock.withdraw()

        self.hotkey = GlobalHotkey()
        if self.own_hotkey:
            self.hotkey.start()

        self._tick_id = self.root.after(33, self._safe_tick)
        if self.own_hotkey:
            self._poll_id = self.root.after(120, self._safe_poll)

    # ------------------------------------------------------------------ #
    #  Config / identity
    # ------------------------------------------------------------------ #

    def load_config(self) -> dict:
        cfg = dict(DEFAULT_CONFIG)
        paths = (APP_DIR / self.config_path, Path.home() / ".tiny_buddy.json")
        for path in paths:
            try:
                if path.exists():
                    cfg.update(json.loads(path.read_text("utf-8")))
                    break
            except Exception:
                continue
        return cfg

    def save_config(self) -> None:
        self.config.update({
            "pet": self.pet_type,
            "color": self.color,
            "name": self.name,
            "scale": self.scale,
            "follow": self.follow_mode,
            "mood": self.mood,
            "toy_kind": self.toy_kind,
            "chatter": self.chatter,
            "x": int(self.x),
            "y": int(self.y),
        })
        for path in (APP_DIR / self.config_path, Path.home() / ".tiny_buddy.json"):
            try:
                path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
                break
            except Exception:
                continue

    def default_name(self, pet: str) -> str:
        return self.manifest["pets"][pet].get("default_name", "Buddy")

    def color_for(self, pet: str, wanted: Optional[str] = None) -> str:
        colors = self.manifest["pets"][pet]["colors"]
        ids = {c["id"] for c in colors}
        if wanted in ids:
            return wanted
        if pet == self.pet_type and self.color in ids:
            return self.color
        return colors[0]["id"]

    def resting_bottom_pixels(self, pet: str) -> int:
        try:
            color = self.color_for(pet)
            sheet = self.sheet(pet, color)
            entry = ANIMATIONS[pet]["walk"]["right"][0]
            row, col = entry[0], entry[1]
            cell = sheet.crop((col * self.cell, row * self.cell,
                               col * self.cell + self.cell, row * self.cell + self.cell))
            bbox = cell.getbbox()
            return bbox[3] if bbox else self.cell
        except Exception:
            return 16 if pet == "cat" else 11

    def sheet(self, pet: str, color: str) -> Image.Image:
        key = (pet, color)
        if key not in self._sheets:
            entry = next(c for c in self.manifest["pets"][pet]["colors"]
                         if c["id"] == color)
            path = ASSETS_DIR / entry["file"]
            self._sheets[key] = Image.open(path).convert("RGBA")
        return self._sheets[key]

    def frame_cells(self, anim: str) -> list[tuple[int, int, bool]]:
        definition = ANIMATIONS[self.pet_type][anim]
        side = "right" if self.facing >= 0 else "left"
        cells = definition[side]
        out = []
        for c in cells:
            if len(c) == 2:
                out.append((c[0], c[1], False))
            else:
                out.append((c[0], c[1], bool(c[2])))
        return out

    def anim_fps(self, anim: str) -> float:
        return ANIMATIONS[self.pet_type][anim]["fps"]

    def anim_loops(self, anim: str) -> bool:
        return ANIMATIONS[self.pet_type][anim]["loop"]

    def frame_photo(self, anim: Optional[str] = None, index: Optional[int] = None,
                    rot: int = 0, squash: float = 0.0) -> ImageTk.PhotoImage:
        anim = anim or self.anim_name
        cells = self.frame_cells(anim)
        if index is None:
            index = self.anim_index
        index %= len(cells)
        cell_entry = cells[index]
        row, col = cell_entry[0], cell_entry[1]
        mirror = bool(cell_entry[2]) if len(cell_entry) > 2 else False
        sq = round(squash, 2)
        key = (self.pet_type, self.color, row, col, rot, sq, int(mirror))
        if key in self._frames:
            return self._frames[key]

        sheet = self.sheet(self.pet_type, self.color)
        cell = sheet.crop((col * self.cell, row * self.cell, col * self.cell + self.cell, row * self.cell + self.cell))
        if mirror:
            cell = cell.transpose(Image.FLIP_LEFT_RIGHT)
        if rot:
            cell = cell.rotate(rot, resample=Image.NEAREST, expand=False)
            bbox = cell.getbbox()
            if bbox:
                l, t, r, b = bbox
                shifted = Image.new("RGBA", cell.size, (0, 0, 0, 0))
                if self.climb_side == "left":  # snug on the chosen wall
                    shifted.paste(cell.crop(bbox), (0, 0))
                else:                            # snug the other edge
                    shifted.paste(cell.crop(bbox), (self.cell - (r - l), 0))
                cell = shifted
        if sq:
            new_h = max(2, int(self.size * (1.0 - 0.22 * sq)))
            cell = cell.resize((self.size, new_h), Image.NEAREST)
            canvas = Image.new("RGBA", (self.size, self.size), (0, 0, 0, 0))
            canvas.paste(cell, (0, self.size - new_h))
            cell = canvas
        else:
            cell = cell.resize((self.size, self.size), Image.NEAREST)
        photo = make_photo(cell)
        self._frames[key] = photo
        return photo

    def thumbnail(self, pet: str, color: str) -> ImageTk.PhotoImage:
        key = (pet, color)
        if key in self._thumbs:
            return self._thumbs[key]
        row, col = ANIMATIONS[pet]["walk"]["right"][0]
        sheet = self.sheet(pet, color)
        cell = sheet.crop((col * self.cell, row * self.cell, col * self.cell + self.cell, row * self.cell + self.cell))
        cell = cell.resize((self.cell * 3, self.cell * 3), Image.NEAREST)
        photo = make_photo(cell)
        self._thumbs[key] = photo
        return photo

    def _extract_hamu_ball(self, scale: int) -> Optional[ImageTk.PhotoImage]:
        path = ASSETS_DIR / "toys" / "balls.png"
        if not path.exists():
            return None
        try:
            im = Image.open(path).convert("RGBA")
            seen: set[tuple[int, int]] = set()
            boxes: list[tuple[int, int, int, int]] = []
            for yy in range(im.height):
                for xx in range(im.width):
                    if im.getpixel((xx, yy))[3] > 0 and \
                            (xx, yy) not in seen:
                        stack = [(xx, yy)]
                        comp = []
                        while stack:
                            cx, cy = stack.pop()
                            if not (0 <= cx < im.width and 0 <= cy < im.height):
                                continue
                            if im.getpixel((cx, cy))[3] <= 0 or \
                                    (cx, cy) in seen:
                                continue
                            seen.add((cx, cy))
                            comp.append((cx, cy))
                            stack.extend(((cx + 1, cy), (cx - 1, cy),
                                          (cx, cy + 1), (cx, cy - 1)))
                        if comp:
                            xs = [a for a, _ in comp]
                            ys = [b for _, b in comp]
                            boxes.append((min(xs), min(ys), max(xs) + 1,
                                          max(ys) + 1))
            if not boxes:
                return None
            boxes.sort(key=lambda b: (b[1], b[0]))
            crop = im.crop(boxes[0])
            side = max(24, scale * 5)
            crop = crop.resize((side, side), Image.NEAREST)
            return make_photo(crop)
        except Exception:
            return None

    def apply_identity(self, pet: str, color: str, name: str) -> None:
        self.pet_type = pet
        self.color = self.color_for(pet, color)
        self.cell = int(self.manifest["pets"][pet]["sheet"].get("cell", 16))
        self.name = name
        self.body_bottom_px = self.resting_bottom_pixels(pet)
        self.ground_y = self.work_bottom - self.body_bottom_px * self.scale
        if self.state in (self.IDLE, self.WALK, self.SIT, self.FOLLOW, self.EAT):
            self.y = float(self.ground_y)
        self._frames.clear()
        self._thumbs.clear()
        self.save_config()
        self.show_name_tag(text=self.name, duration=1.8)

    def set_scale(self, scale: int) -> None:
        scale = max(2, min(7, int(scale)))
        if scale == self.scale:
            return
        old_bottom = self.y + self.size
        self.scale = scale
        self.size = self.cell * scale
        self.body_bottom_px = self.resting_bottom_pixels(self.pet_type)
        self.ground_y = self.work_bottom - self.body_bottom_px * self.scale
        self.top_y = self.work_top + 2
        self.y = self.ground_y if self.state in (self.IDLE, self.WALK, self.SIT,
                                                 self.FOLLOW, self.EAT) else old_bottom - self.size
        self.x = max(self.work_left, min(self.work_right - self.size, self.x))
        self.walk_speed = 120 * (self.scale / 4)
        self.climb_speed = 90 * (self.scale / 4)
        self.gravity = 2400 * (self.scale / 4)
        self.jump_speed = math.sqrt(2 * self.gravity * 115 * (self.scale / 4))
        self._frames.clear()
        self.treat_photo = make_photo(make_treat_image(max(2, self.scale - 1)))
        self.toy_photos = {
            key: make_photo(make_toy_image(max(3, self.scale), key))
            for key in ("core", "tennis", "baseball", "soccer", "golf") + (
                ("hamu",) if True else ()
            )
        }
        if (ASSETS_DIR / "toys/balls.png").exists():
            hmay = self._extract_hamu_ball(self.scale)
            if hmay is not None:
                self.toy_photos["hamu"] = hmay
        if self.toy_kind not in self.toy_photos:
            self.toy_kind = "tennis"
        self.toy_photo = self.toy_photos[self.toy_kind]
        self.canvas.configure(width=self.size, height=self.size)
        self.canvas.coords(self.image_id, self.size // 2, self.size // 2)
        self.win.geometry(geometry_string(self.x, self.y, self.size, self.size))
        self.save_config()

    # ------------------------------------------------------------------ #
    #  Animation helpers
    # ------------------------------------------------------------------ #

    def set_anim(self, name: str, restart: bool = False) -> None:
        if self.anim_name == name and not restart:
            return
        self.anim_name = name
        self.anim_index = 0
        self.anim_t = 0.0
        self.anim_done = False

    def update_anim(self, dt: float) -> None:
        self._rev_play = (self.state == self.CLIMB and self.climb_side == "right")
        cells = self.frame_cells(self.anim_name)
        self.anim_t += dt
        fps = max(0.1, self.anim_fps(self.anim_name))
        index = int(self.anim_t * fps)
        n = len(cells)
        if self.anim_loops(self.anim_name):
            base = index % n
            if getattr(self, "_rev_play", False) and self.state == self.CLIMB:
                self.anim_index = (n - 1) - base
            else:
                self.anim_index = base
        else:
            self.anim_index = min(index, n - 1)
            if getattr(self, "_rev_play", False) and self.state == self.CLIMB:
                self.anim_index = max(0, n - 1 - min(index, n - 1))
            self.anim_done = self.anim_index >= n - 1

    # ------------------------------------------------------------------ #
    #  Behaviour
    # ------------------------------------------------------------------ #

    def start_walk(self, target_x: float, arrive: Optional[str] = None) -> None:
        self.state = self.WALK
        self.state_t = 0.0
        self.target_x = max(self.work_left, min(self.work_right - self.size, target_x))
        self.arrive_action = arrive
        self.set_anim("walk", restart=True)

    def start_sit(self, duration: float = 6.0) -> None:
        self.state = self.SIT
        self.state_t = 0.0
        self.sit_duration = duration
        self.set_anim("sit", restart=True)

    def start_climb(self, side: str, y_from: Optional[float] = None) -> None:
        self.state = self.CLIMB
        self.state_t = 0.0
        self.climb_side = side
        self._rev_play = False
        if side == "left":
            self.x = float(self.work_left)
            self.facing = -1
            self.climb_rot = -90
        else:
            self.x = float(self.work_right - self.size)
            self.facing = 1
            self.climb_rot = 90
        if y_from is None:
            self.y = float(self.ground_y)
        else:
            self.y = max(float(self.top_y), min(float(self.ground_y), float(y_from)))
        self.set_anim("walk", restart=True)
        self.arrive_action = None
        self.climb_cooldown = 18.0

    def start_jump(self) -> None:
        if self.state in (self.CLIMB, self.HANG, self.FALL, self.DRAG, self.JUMP):
            return
        self.state = self.JUMP
        self.state_t = 0.0
        self.jump_phase = 0
        self.vy = 0.0
        self.set_anim("crouch", restart=True)

    def start_fall(self) -> None:
        self.state = self.FALL
        self.state_t = 0.0
        self.vy = 0.0
        self.set_anim("fall", restart=True)

    def start_follow(self) -> None:
        self.state = self.FOLLOW
        self.state_t = 0.0
        self.set_anim("walk", restart=True)

    def pet_it(self) -> None:
        self.mood = min(100, self.mood + 4)
        self.spawn_hearts(3)
        self.show_name_tag(text=f"{self.name} \u2665", duration=1.6)
        self.save_config()

    def feed(self) -> None:
        if self._hidden:
            self.show_pet()
        tw = self.treat_photo.width()
        low = self.work_left + 20
        high = max(low + 1, self.work_right - tw - 20)
        tx = random.randint(low, high)
        treat = Treat(self, tx, self.work_top + 30)
        self._treats.append(treat)
        self.show_name_tag(text=f"{self.name} wants a snack!", duration=1.6)

    def toy(self, kind: Optional[str] = None) -> None:
        if kind is not None and kind in self.toy_photos:
            self.toy_kind = kind
        if self._hidden:
            self.show_pet()
        for old in self._toys:
            try:
                old.destroy()
            except Exception:
                pass
        self._toys.clear()
        cx, _ = cursor_pos()
        tx = max(self.work_left + 20, min(self.work_right - 30,
                                         cx if self.work_left <= cx <= self.work_right else
                                         self.work_left + (self.work_right - self.work_left) // 2))
        ball = ToyBall(self, tx, self.work_top + 20, self.toy_kind)
        self._toys.append(ball)
        self._fetch_busy_until = time.perf_counter() + 30.0
        self.toy_photo = self.toy_photos[self.toy_kind]
        self.show_name_tag(text="Fetch! Good luck!", duration=1.4)

    def toy_stop(self) -> None:
        self._fetch_busy_until = time.perf_counter()
        score = self._toy_score
        self._toy_score = 0
        for t in self._toys:
            try:
                t.destroy()
            except Exception:
                pass
        self._toys.clear()
        self.state = self.IDLE
        self.state_t = 0.0
        self.next_decision = 0.6
        self.set_anim("stand")
        self.show_name_tag(text=f"Toy put away. Score {score}.", duration=1.6)

    def _kick_toy(self) -> None:
        if not self._toys:
            return
        # only reward grounded contact, not mid-air bounces into walls
        if self.state in (self.CLIMB, self.HANG, self.JUMP) or \
                abs(self.y - self.ground_y) > self.size * 0.45:
            return
        toy = self._toys[-1]
        direction = 1 if toy.x + toy.photo.width() / 2 > self.x + self.size / 2 else -1
        toy.vx = direction * random.uniform(260, 420)
        toy.vy = -random.uniform(90, 200)
        self._toy_score += 1
        self._fetch_busy_until = time.perf_counter() + 4.0
        if self._toy_score % 5 == 0:
            self.show_name_tag(f"Fetch! ({self._toy_score})", 1.6)
        else:
            self.spawn_hearts(1)

    def eat(self) -> None:
        if not self._treats:
            return
        treat = min(self._treats, key=lambda t: abs((t.x + t.photo.width() / 2) -
                                                   (self.x + self.size / 2)))
        self._treats.remove(treat)
        treat.destroy()
        self.mood = min(100, self.mood + 12)
        self.spawn_hearts(3)
        self.save_config()

    def spawn_hearts(self, count: int) -> None:
        for i in range(count):
            hx = int(self.x + self.size * (0.3 + 0.2 * i))
            hy = int(self.y) - 10
            self._hearts.append(Heart(self, hx, hy))

    def choose_action(self) -> None:
        self.climb_cooldown = max(0.0, self.climb_cooldown)
        _busy = bool(self._toys) or time.perf_counter() < self._fetch_busy_until
        if (not _busy) and self.climb_cooldown <= 0 and random.random() < 0.24:
            side = "left" if self.x + self.size / 2 < (self.work_left + self.work_right) / 2 else "right"
            wall_x = self.work_left if side == "left" else self.work_right - self.size
            self.pending_climb = side
            self.start_walk(wall_x, arrive="climb")
            return
        r = random.random()
        if r < 0.5:
            tx = random.randint(self.work_left, max(self.work_left, self.work_right - self.size))
            self.start_walk(tx)
        elif r < 0.82:
            self.start_sit(random.uniform(3.5, 8.0))
        else:
            self.state = self.IDLE
            self.state_t = 0.0
            self.next_decision = random.uniform(1.5, 3.5)
            self.set_anim("stand", restart=True)

    def think(self, dt: float) -> None:
        self.climb_cooldown = max(0.0, self.climb_cooldown - dt)
        if self._hidden:
            return
        if self.state in (self.JUMP, self.FALL, self.LAND, self.CLIMB,
                          self.HANG, self.DRAG, self.EAT):
            return

        # food always wins
        if self._treats:
            treat = min(self._treats, key=lambda t: abs((t.x + t.photo.width() / 2) -
                                                        (self.x + self.size / 2)))
            tx = treat.x + treat.photo.width() / 2 - self.size / 2
            if not treat.landed or abs(tx - self.x) > 6:
                if self.state != self.WALK or abs(self.target_x - tx) > 4:
                    self.start_walk(tx, arrive="eat")
                # keep advancing while walking (state machine cross-task fix)
                if self.state == self.WALK:
                    dx = self.target_x - self.x
                    if abs(dx) <= 1.5:
                        self.x = self.target_x
                        if treat.landed:
                            self.state = self.EAT
                            self.state_t = 0.0
                            self.set_anim("eat", restart=True)
                    else:
                        self.facing = 1 if dx > 0 else -1
                        step = self.walk_speed * dt
                        self.x += max(-step, min(step, dx))
                        self.set_anim("walk")
            else:
                if self.state != self.EAT:
                    self.state = self.EAT
                    self.state_t = 0.0
                    self.set_anim("eat", restart=True)
            return

        if self._toys:
            toy = self._toys[-1]
            tx = toy.x + toy.photo.width() / 2 - self.size / 2
            if abs(tx - self.x) > 12:
                if self.state != self.WALK or abs(self.target_x - tx) > 24:
                    self.start_walk(tx, arrive="chase")
                else:
                    self.target_x = tx  # keep tracking without restarting anim
                if self.state == self.WALK:
                    dx = self.target_x - self.x
                    if abs(dx) <= 1.5:
                        self.x = self.target_x
                    else:
                        self.facing = 1 if dx > 0 else -1
                        step = (self.walk_speed + 0.15 * abs(self.target_x - self.x)) * dt
                        self.x += max(-step, min(step, dx))
                        self.set_anim("walk")
            else:
                if self.state in (self.IDLE, self.WALK):
                    self._kick_toy()
                    self.state = self.IDLE
                    self.next_decision = 0.15
                    self.set_anim("stand", restart=True)
            return

        if self.follow_mode:
            if self.state != self.FOLLOW:
                self.start_follow()
            return

        if self.state == self.FOLLOW:
            self.state = self.IDLE
            self.state_t = 0.0
            self.next_decision = 0.2
            self.set_anim("stand", restart=True)

        if self.state == self.IDLE:
            if self.chatter and time.perf_counter() >= getattr(self, "_next_chatter", 0.0):
                self._next_chatter = time.perf_counter() + random.uniform(180, 360)
                phrase = random.choice(PHRASES.get(self.pet_type, PHRASES["cat"]))
                self.show_name_tag(phrase, 3.0)
            if self.state_t >= getattr(self, "next_decision", 2.0):
                self.choose_action()
        elif self.state == self.SIT:
            if self.state_t >= self.sit_duration:
                self.state = self.IDLE
                self.state_t = 0.0
                self.next_decision = random.uniform(1.0, 3.0)
                self.set_anim("stand", restart=True)
        elif self.state == self.WALK:
            dx = self.target_x - self.x
            if abs(dx) <= 1.5:
                self.x = self.target_x
                self.state = self.IDLE
                self.state_t = 0.0
                if self.arrive_action == "climb" and getattr(self, "pending_climb", None):
                    self.start_climb(self.pending_climb)
                    self.pending_climb = None
                elif self.arrive_action == "eat":
                    self.state = self.EAT
                    self.state_t = 0.0
                    self.set_anim("eat", restart=True)
                elif self.arrive_action == "chase":
                    self._kick_toy()
                    self.state = self.IDLE
                    self.state_t = 0.0
                    self.next_decision = 0.2
                    self.set_anim("stand", restart=True)
                else:
                    self.next_decision = random.uniform(1.4, 3.6)
                    self.set_anim("stand", restart=True)
                self.arrive_action = None
            else:
                self.facing = 1 if dx > 0 else -1
                step = self.walk_speed * dt
                self.x += max(-step, min(step, dx))
                self.set_anim("walk")

    def update_state(self, dt: float) -> None:
        self.state_t += dt
        if self.state == self.FOLLOW:
            cx, cy = cursor_pos()
            tx = max(self.work_left, min(self.work_right - self.size,
                                         cx - self.size / 2))
            dx = tx - self.x
            if abs(dx) > 12:
                self.facing = 1 if dx > 0 else -1
                step = self.walk_speed * dt
                self.x += max(-step, min(step, dx))
                self.set_anim("walk")
            else:
                if cx > self.x + self.size / 2:
                    self.facing = 1
                elif cx < self.x + self.size / 2:
                    self.facing = -1
                self.set_anim("sit_pose")
        elif self.state == self.CLIMB:
            self.set_anim("walk")
            self.y -= self.climb_speed * dt
            if self.y <= self.top_y:
                self.y = self.top_y
                self.state = self.HANG
                self.state_t = 0.0
                self.hang_time = 0.0
                self.set_anim("stand", restart=True)
        elif self.state == self.HANG:
            self.hang_time += dt
            if self.hang_time >= 10.0:
                self.facing = 1 if self.climb_side == "left" else -1
                self.start_fall()
        elif self.state == self.FALL:
            self.vy += self.gravity * dt
            self.y += self.vy * dt
            if self.y >= self.ground_y:
                self.y = float(self.ground_y)
                self.state = self.LAND
                self.state_t = 0.0
                self.squash = 0.18
                self.set_anim("stand", restart=True)
        elif self.state == self.LAND:
            if self.state_t >= 0.18:
                self.state = self.IDLE
                self.state_t = 0.0
                self.squash = 0.0
                self.next_decision = random.uniform(1.0, 3.0)
                self.set_anim("stand", restart=True)
        elif self.state == self.JUMP:
            if self.jump_phase == 0:
                if self.state_t >= 0.36:
                    self.jump_phase = 1
                    self.vy = -self.jump_speed
                    self.set_anim("stand", restart=True)
            else:
                self.vy += self.gravity * dt
                self.y += self.vy * dt
                if self.y >= self.ground_y:
                    self.y = float(self.ground_y)
                    self.state = self.LAND
                    self.state_t = 0.0
                    self.squash = 0.18
                    self.set_anim("stand", restart=True)
        elif self.state == self.EAT:
            if self.state_t >= 0.9:
                self.eat()
                self.state = self.IDLE
                self.state_t = 0.0
                self.next_decision = 0.3
                self.set_anim("stand", restart=True)
        # keep the pet on screen
        self.x = max(self.work_left, min(self.work_right - self.size, self.x))
        if self.y > self.ground_y:
            self.y = float(self.ground_y)

    # ------------------------------------------------------------------ #
    #  Main loop
    # ------------------------------------------------------------------ #

    def tick(self) -> None:
        if not self.alive:
            return
        now = time.perf_counter()
        dt = min(0.08, now - self._last_tick)
        self._last_tick = now
        try:
            if not self._hidden:
                self.update_state(dt)
                self.think(dt)
            self.update_anim(dt)
            self.update_effects(dt)
            self.draw()
            if time.perf_counter() - self._last_save > 30.0:
                self.save_config()
                self._last_save = time.perf_counter()
        except tk.TclError:
            return

    def update_effects(self, dt: float) -> None:
        for treat in list(self._treats):
            treat.update(dt)
        for toy in list(self._toys):
            toy.update(dt)
        for heart in list(self._hearts):
            if not heart.update(dt):
                try:
                    heart.win.destroy()
                except tk.TclError:
                    pass
                self._hearts.remove(heart)

    def draw(self) -> None:
        rot = self.climb_rot if self.state in (self.CLIMB, self.HANG) else 0
        squash = 0.0
        if self.state == self.LAND:
            squash = max(0.0, 1.0 - self.state_t / 0.18)
        photo = self.frame_photo(rot=rot, squash=squash)
        self.canvas.itemconfigure(self.image_id, image=photo)
        self._photo = photo
        ix, iy = int(self.x), int(self.y)
        if (ix, iy) != self.last_geom:
            self.win.geometry(geometry_string(ix, iy, self.size, self.size))
            self.last_geom = (ix, iy)
        if self._tag_win is not None:
            self.position_tag()

    # ------------------------------------------------------------------ #
    #  Menus / interaction
    # ------------------------------------------------------------------ #

    def _bind_pet_events(self) -> None:
        for widget in (self.win, self.canvas):
            widget.bind("<ButtonPress-1>", self.on_press)
            widget.bind("<B1-Motion>", self.on_drag)
            widget.bind("<ButtonRelease-1>", self.on_release)
            widget.bind("<Button-3>", self.on_context_menu)
            widget.bind("<Enter>", self.on_enter)
            widget.bind("<Leave>", self.on_leave)
            widget.bind("<Key-f>", lambda e: self.toggle_follow())
            widget.bind("<Key-s>", lambda e: self.start_sit(10.0))
            widget.bind("<Key-j>", lambda e: self.start_jump())
            widget.bind("<Key-t>", lambda e: self.feed())
            widget.bind("<Key-g>", lambda e: self.toy())
            widget.bind("<Key-x>", lambda e: self.toy_stop())
            widget.bind("<space>", lambda e: self.pet_it())
            widget.bind("<Key-h>", lambda e: self.hide_pet())

    def on_press(self, event) -> None:
        self.drag_off = (event.x_root - int(self.x), event.y_root - int(self.y))
        self.drag_moved = False
        self.press_root = (event.x_root, event.y_root)

    def on_drag(self, event) -> None:
        if abs(event.x_root - self.press_root[0]) > 5 or \
                abs(event.y_root - self.press_root[1]) > 5:
            self.drag_moved = True
        if not self.drag_moved:
            return
        self.close_action_card()
        self.state = self.DRAG
        self.state_t = 0.0
        self.x = event.x_root - self.drag_off[0]
        self.y = event.y_root - self.drag_off[1]
        self.x = max(self.work_left, min(self.work_right - self.size, self.x))
        self.y = max(self.top_y, min(self.ground_y, self.y))
        # snap to a wall edge when inside the narrow wall zone
        if self.x <= self.work_left + self.size * 0.35:
            self.x = float(self.work_left)
        elif self.x >= self.work_right - self.size * 1.35:
            self.x = float(self.work_right - self.size)
        self.win.geometry(geometry_string(self.x, self.y, self.size, self.size))
        self.last_geom = (int(self.x), int(self.y))

    def _wall_side_for(self) -> Optional[str]:
        if self.x <= self.work_left + 6:
            return "left"
        if self.x >= self.work_right - self.size - 6:
            return "right"
        return None

    def on_release(self, event) -> None:
        if self.drag_moved:
            self.drag_moved = False
            side = self._wall_side_for()
            if side and abs(self.y - self.ground_y) > 2:
                self.start_climb(side, y_from=self.y)
                return
            self.state = self.IDLE
            self.state_t = 0.0
            self.next_decision = 0.6
            if abs(self.y - self.ground_y) > 2:
                self.start_fall()
            else:
                self.set_anim("stand", restart=True)
            return
        self.open_action_card()

    def on_context_menu(self, event) -> None:
        self.close_action_card()
        menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
        menu.add_command(label=self.name, state="disabled")
        menu.add_separator()
        menu.add_command(label="Sit", command=lambda: self.start_sit(10.0))
        menu.add_command(label="Jump", command=self.start_jump)
        menu.add_checkbutton(label="Follow cursor", command=self.toggle_follow,
                             variable=tk.BooleanVar(value=self.follow_mode))
        menu.add_command(label="Feed a treat", command=self.feed)
        toy_menu = tk.Menu(menu, tearoff=0)
        for kind in ("core", "tennis", "baseball", "soccer", "golf"):
            toy_menu.add_command(label=kind.capitalize(),
                                 command=lambda k=kind: self.toy(k))
        menu.add_cascade(label="Throw a ball", menu=toy_menu)
        menu.add_command(label="Throw a fetch toy", command=self.toy)
        menu.add_command(label="Stop the toy", command=self.toy_stop)
        menu.add_separator()
        menu.add_command(label="Rename\u2026", command=self.prompt_rename)
        menu.add_command(label="Change buddy / colour\u2026", command=self.open_picker)
        size_menu = tk.Menu(menu, tearoff=0)
        for label, value in (("Small", 3), ("Medium", 4), ("Large", 5), ("Huge", 6)):
            size_menu.add_command(label=label,
                                  command=lambda v=value: self.set_scale(v))
        menu.add_cascade(label="Size", menu=size_menu)
        menu.add_separator()
        menu.add_command(label="Chatter: " + ("on" if self.chatter else "off"), command=self.toggle_chatter)
        menu.add_command(label="Add another buddy", command=self.add_buddy)
        menu.add_command(label="Hide buddy", command=self.hide_pet)
        menu.add_command(label="Show name tag", command=lambda: self.show_name_tag(self.name, 2.5))
        menu.add_separator()
        menu.add_command(label="Quit", command=self.quit_app)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def on_enter(self, event) -> None:
        self._schedule_tag()

    def on_leave(self, event) -> None:
        if self._hover_job:
            try:
                self.root.after_cancel(self._hover_job)
            except Exception:
                pass
            self._hover_job = None
        if self._action_card is None:
            self.hide_name_tag()

    def _schedule_tag(self) -> None:
        if self._hover_job:
            return
        self._hover_job = self.root.after(420, self._show_hover_tag)

    def _show_hover_tag(self) -> None:
        self._hover_job = None
        if self.state != self.DRAG and not self._hidden:
            self.show_name_tag(self.name, None)

    # ------------------------------------------------------------------ #
    #  Name bubble
    # ------------------------------------------------------------------ #

    def show_name_tag(self, text: str, duration: Optional[float] = 2.0,
                      sub: Optional[str] = None) -> None:
        self.hide_name_tag()
        label = text if not sub else f"{text}  {sub}"
        img = rounded_bubble(label, 12)
        photo = make_photo(img)
        win = tk.Toplevel(self.root)
        make_transparent(win)
        canvas = tk.Canvas(win, width=img.width, height=img.height, bg=KEY,
                           highlightthickness=0, bd=0)
        canvas.pack()
        canvas.create_image(0, 0, anchor="nw", image=photo)
        win._photo_ref = photo  # type: ignore[attr-defined]
        win.geometry(geometry_string(0, 0, img.width, img.height))
        if self._tag_job:
            try:
                self.root.after_cancel(self._tag_job)
            except Exception:
                pass
            self._tag_job = None
        win.deiconify()
        make_no_activate(win)
        self._tag_win = win
        self._tag_size = (img.width, img.height)
        self._tag_follows_pet = True
        self.position_tag()
        if duration:
            self._tag_job = self.root.after(int(duration * 1000), self._hide_tag_safe)

    def position_tag(self) -> None:
        if self._tag_win is None or not self._tag_follows_pet:
            return
        try:
            w, h = self._tag_size
            if w <= 1 or h <= 1:
                return
            tx = int(self.x + self.size / 2 - w / 2)
            ty = int(self.y - h - 4)
            tx = max(self.work_left, min(self.work_right - w, tx))
            ty = max(self.work_top, ty)
            self._tag_win.geometry(geometry_string(tx, ty, w, h))
        except tk.TclError:
            self._tag_win = None

    def _hide_tag_safe(self) -> None:
        if not self.alive:
            return
        self.hide_name_tag()
        self._tag_job = None

    def hide_name_tag(self) -> None:
        if self._tag_job is not None:
            try:
                self.root.after_cancel(self._tag_job)
            except Exception:
                pass
            self._tag_job = None
        if self._tag_win is not None:
            try:
                self._tag_win.destroy()
            except tk.TclError:
                pass
            self._tag_win = None

    # ------------------------------------------------------------------ #
    #  Action card
    # ------------------------------------------------------------------ #

    def open_action_card(self) -> None:
        self.close_action_card()
        self.hide_name_tag()
        card = tk.Toplevel(self.root)
        try:
            card.tk.call("wm", "overrideredirect", card._w, 1)
        except tk.TclError:
            card.overrideredirect(True)
        card.configure(bg="#e7d6bd")
        card.wm_attributes("-topmost", True)
        outer = tk.Frame(card, bg="#e7d6bd", padx=2, pady=2)
        outer.pack()
        body = tk.Frame(outer, bg="#fff7e8", padx=12, pady=10)
        body.pack()
        header = tk.Frame(body, bg="#fff7e8")
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text=self.name, bg="#fff7e8", fg="#3a2c1e",
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(header, text="\u00d7", command=self.close_action_card,
                  bg="#fff7e8", activebackground="#ffe3b8", relief="flat",
                  bd=0, padx=5, cursor="hand2").pack(side="right")
        grid = tk.Frame(body, bg="#fff7e8")
        grid.pack()

        follow_label = "Follow: on" if self.follow_mode else "Follow"
        buttons = [
            ("Sit", lambda: self.start_sit(10.0)),
            ("Jump", self.start_jump),
            (follow_label, self.toggle_follow),
            ("Treat", self.feed),
            ("Fetch", self.toy),
            ("Stop toy", self.toy_stop),
            ("Pet", self.pet_it),
            ("Rename", self.prompt_rename),
            ("Colours", self.open_picker),
            ("Hide", self.hide_pet),
        ]
        for i, (label, command) in enumerate(buttons):
            btn = tk.Button(grid, text=label, command=lambda c=command: (self.close_action_card(), c()),
                            bg="#ffe9c7", activebackground="#ffd79a", fg="#4a3624",
                            relief="flat", bd=0, padx=14, pady=7, width=9,
                            cursor="hand2", font=("Segoe UI", 9))
            btn.grid(row=i // 2, column=i % 2, padx=3, pady=3)

        self._action_card = card
        card.update_idletasks()
        w = card.winfo_reqwidth()
        h = card.winfo_reqheight()
        x = int(self.x + self.size / 2 - w / 2)
        y = int(self.y - h - 8)
        x = max(self.work_left + 4, min(self.work_right - w - 4, x))
        if y < self.work_top + 4:
            y = int(self.y + self.size + 8)
        card.geometry(geometry_string(x, y, w, h))
        card.deiconify()
        self._card_job = self.root.after(7000, lambda c=card: self.close_action_card(c))

    def close_action_card(self, card: Optional[tk.Toplevel] = None) -> None:
        target = card or self._action_card
        if self._card_job is not None:
            try:
                self.root.after_cancel(self._card_job)
            except Exception:
                pass
            self._card_job = None
        if target is not None:
            try:
                target.destroy()
            except tk.TclError:
                pass
            if target is self._action_card:
                self._action_card = None

    def prompt_rename(self) -> None:
        self.close_action_card()
        PromptDialog(self, "Rename buddy", "What should your buddy be called?",
                     self.name, self.apply_name)

    def add_buddy(self) -> None:
        try:
            chosen = random.choice(("cat", "axolotl", "frog"))
            spec = self.manifest["pets"][chosen]
            cid = random.choice(spec["colors"])["id"]
            clone = BuddyApp(
                self.root,
                config_path=("buddy_" + self.name + "_" +
                            chosen + ".json"),
                own_hotkey=False,
            )
            clone.pet_type = chosen
            clone.color = clone.color_for(chosen, cid)
            clone.cell = int(spec["sheet"].get("cell", 16))
            clone.name = ("Buddy " + str(random.randint(2, 99)))
            clone.scale = max(2, min(7, self.scale))
            clone.size = clone.cell * clone.scale
            clone.x += random.choice((-1, 1)) * (clone.size * 4)
            clone.y = clone.ground_y if clone.state in (
                clone.IDLE, clone.WALK, clone.SIT, clone.FOLLOW, clone.EAT) \
                else clone.ground_y
            # apply geometry after mapping so the clone fills the whole window
            clone.win.geometry(geometry_string(clone.x, clone.y, clone.size, clone.size))
            clone.win.update_idletasks()
            clone.win.after(60, lambda w=clone.win: (w.deiconify(), make_no_activate(w)))
            clone.save_config()
            self._clones.append(clone)
            self.show_name_tag("Added " + clone.name + "!", 1.6)
        except Exception as exc:
            print("add_buddy failure", exc)
            import traceback
            traceback.print_exc()

    def apply_name(self, name: str) -> None:
        self.name = name
        self.save_config()
        self.show_name_tag(self.name, 1.6)

    def toggle_chatter(self) -> None:
        self.chatter = not self.chatter
        if self.chatter:
            self._next_chatter = time.perf_counter() + random.uniform(30, 90)
        self.save_config()
        self.show_name_tag("Chatter on" if self.chatter else "Chatter off", 1.6)

    def open_picker(self) -> None:
        self.close_action_card()
        if self._picker is not None:
            try:
                self._picker.lift()
                return
            except tk.TclError:
                self._picker = None
        self._picker = BuddyPicker(self)

    def toggle_follow(self) -> None:
        self.follow_mode = not self.follow_mode
        if self.follow_mode:
            self.start_follow()
        else:
            self.state = self.IDLE
            self.state_t = 0.0
            self.next_decision = 0.8
            self.set_anim("stand", restart=True)
        self.save_config()
        self.show_name_tag("Following your cursor" if self.follow_mode else "Wandering again",
                           duration=1.6)

    # ------------------------------------------------------------------ #
    #  Hide / show / quit
    # ------------------------------------------------------------------ #

    def hide_pet(self) -> None:
        self.close_action_card()
        self.hide_name_tag()
        self._hidden = True
        self.win.withdraw()
        for treat in self._treats:
            treat.win.withdraw()
        for toy in self._toys:
            toy.win.withdraw()
        self.dock.deiconify()
        make_no_activate(self.dock)
        self.show_toast(f"{self.name} is tucked away \u00b7 Ctrl+Alt+B to bring them back")

    def show_pet(self) -> None:
        self._hidden = False
        try:
            self.dock.withdraw()
            self.win.deiconify()
            self.win.lift()
            for treat in self._treats:
                treat.win.deiconify()
            for toy in self._toys:
                toy.win.deiconify()
        except tk.TclError:
            pass
        self.state = self.FALL if self.y < self.ground_y - 2 else self.IDLE
        self.state_t = 0.0
        self.set_anim("fall" if self.state == self.FALL else "stand", restart=True)

    def show_toast(self, text: str) -> None:
        # reuse the name bubble, anchored near the dock
        self.hide_name_tag()
        img = rounded_bubble(text, 11)
        photo = make_photo(img)
        win = tk.Toplevel(self.root)
        make_transparent(win)
        canvas = tk.Canvas(win, width=img.width, height=img.height, bg=KEY,
                           highlightthickness=0, bd=0)
        canvas.pack()
        canvas.create_image(0, 0, anchor="nw", image=photo)
        win._photo_ref = photo  # type: ignore[attr-defined]
        x = self.work_right - img.width - 12
        y = self.work_bottom - img.height - 80
        win.geometry(geometry_string(x, y, img.width, img.height))
        win.deiconify()
        make_no_activate(win)
        self._tag_win = win
        self._tag_size = (img.width, img.height)
        self._tag_follows_pet = False
        self._tag_job = self.root.after(4200, self._hide_tag_safe)

    def quit_app(self) -> None:
        for clone in list(self._clones):
            try:
                clone.alive = False
                clone.save_config()
                clone.win.destroy()
            except Exception:
                pass
        self._clones.clear()
        self.alive = False
        for attr in ("_tick_id", "_poll_id", "_hover_job", "_tag_job", "_card_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        self.save_config()
        try:
            self.hotkey.stop()
        except Exception:
            pass
        for treat in self._treats:
            treat.destroy()
        for toy in self._toys:
            toy.destroy()
        for heart in self._hearts:
            try:
                heart.win.destroy()
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _safe_tick(self) -> None:
        if not self.alive:
            return
        try:
            self.tick()
        except tk.TclError:
            return
        if self.alive:
            self._tick_id = self.root.after(33, self._safe_tick)

    def _safe_poll(self) -> None:
        if not self.alive:
            return
        try:
            self.poll_hotkey()
        except tk.TclError:
            return
        if self.alive:
            self._poll_id = self.root.after(120, self._safe_poll)

    def poll_hotkey(self) -> None:
        if not self.alive:
            return
        try:
            while True:
                event = self.hotkey.events.get_nowait()
                if event == "toggle":
                    if self._hidden:
                        self.show_pet()
                    else:
                        self.hide_pet()
        except queue.Empty:
            pass
        if not self.hotkey.ok and not getattr(self, "_hotkey_warned", False) and \
                self.hotkey.is_alive() and self.hotkey._thread_id:
            self._hotkey_warned = True


# --------------------------------------------------------------------------- #
#  Self-test / entry point
# --------------------------------------------------------------------------- #

def selftest() -> int:
    print("Tiny Buddy self-test")
    if not (ASSETS_DIR / "manifest.json").exists():
        print("FAIL: assets/manifest.json missing")
        return 1
    manifest = json.loads((ASSETS_DIR / "manifest.json").read_text("utf-8"))
    ok = True
    for pet, meta in manifest["pets"].items():
        if pet not in ANIMATIONS:
            print(f"FAIL: no animation map for {pet}")
            ok = False
            continue
        sheet_sizes = set()
        for color in meta["colors"]:
            path = ASSETS_DIR / color["file"]
            if not path.exists():
                print(f"FAIL: missing {path}")
                ok = False
                continue
            with Image.open(path) as img:
                sheet_sizes.add(img.size)
        print(f"{pet}: {len(meta['colors'])} colours, sheets {sorted(sheet_sizes)}")
        for name, definition in ANIMATIONS[pet].items():
            for side in ("left", "right"):
                for cell in definition[side]:
                    row, col = cell[0], cell[1]
                    if row < 0 or col < 0:
                        print(f"FAIL: bad cell {pet}/{name}/{side} {(row, col)}")
                        ok = False
        _cells = [c for d in ANIMATIONS[pet].values() for side in ("left", "right") for c in d[side]]
        rows = max(c[0] for c in _cells)
        cols = max(c[1] for c in _cells)
        print(f"  max cell used: row {rows}, col {cols}")
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    try:
        BuddyApp(root)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("Tiny Buddy", f"Could not start Tiny Buddy:\n\n{exc}")
        except Exception:
            pass
        return
    root.mainloop()


if __name__ == "__main__":
    main()
