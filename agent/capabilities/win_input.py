"""Windows SendInput replayer using ctypes (Phase 74).

Mirrors the Rust control_input.rs surface: every INTEGRATE input kind replayed,
nothing on the OPT-OUT list (INPUT_HARDWARE, BlockInput, low-level hooks) ever
emitted. ctypes struct layout matches winapi 0.3 INPUT union semantics.
"""

import ctypes
from ctypes import wintypes
from typing import NamedTuple

if not hasattr(ctypes, "windll"):
    raise ImportError("win_input.py is Windows-only")

user32 = ctypes.windll.user32

# Constants from winuser.h
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2  # never used (D-05)

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

XBUTTON1 = 0x0001
XBUTTON2 = 0x0002

WHEEL_DELTA = 120

# ctypes structs matching winapi 0.3 layout
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


class InputEvent(NamedTuple):
    """One decoded interactive-control input frame."""
    kind: str  # "mousemove", "mousedown", "mouseup", "wheel", "keydown", "keyup"
    x: float = 0.0
    y: float = 0.0
    button: int = 0
    down: bool = False
    delta_x: int = 0
    delta_y: int = 0
    vk: int = 0
    extended: bool = False
    unicode: int = 0


def control_input_replay(ev: InputEvent) -> None:
    """Replay one decoded event by synthesising native input (SendInput)."""
    send_input = user32.SendInput
    send_input.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    send_input.restype = wintypes.UINT

    def send(input_struct: INPUT) -> None:
        sent = send_input(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT))
        if sent == 0:
            err = ctypes.windll.kernel32.GetLastError()
            import logging
            logging.getLogger(__name__).warning("SendInput failed: error %d", err)

    inp = INPUT()
    inp.type = 0
    ctypes.memset(ctypes.byref(inp), 0, ctypes.sizeof(INPUT))

    if ev.kind == "mousemove":
        inp.type = INPUT_MOUSE
        mi = ctypes.cast(ctypes.byref(inp.union), ctypes.POINTER(MOUSEINPUT)).contents
        mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        mi.dx = int(round(ev.x * 65535.0))
        mi.dy = int(round(ev.y * 65535.0))
        send(inp)

    elif ev.kind in ("mousedown", "mouseup"):
        inp.type = INPUT_MOUSE
        mi = ctypes.cast(ctypes.byref(inp.union), ctypes.POINTER(MOUSEINPUT)).contents
        button = ev.button
        down = ev.down
        if button == 0:  # left
            mi.dwFlags = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
        elif button == 1:  # middle
            mi.dwFlags = MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP
        elif button == 2:  # right
            mi.dwFlags = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
        elif button in (3, 4):  # X1/X2 (back/forward)
            mi.dwFlags = MOUSEEVENTF_XDOWN if down else MOUSEEVENTF_XUP
            mi.mouseData = XBUTTON1 if button == 3 else XBUTTON2
        else:
            return
        send(inp)

    elif ev.kind == "wheel":
        def clamp(delta: int) -> int:
            val = delta * WHEEL_DELTA
            return max(-2147483648, min(2147483647, val))

        if ev.delta_y != 0:
            inp.type = INPUT_MOUSE
            mi = ctypes.cast(ctypes.byref(inp.union), ctypes.POINTER(MOUSEINPUT)).contents
            mi.dwFlags = MOUSEEVENTF_WHEEL
            mi.mouseData = clamp(ev.delta_y)
            send(inp)

        if ev.delta_x != 0:
            inp.type = INPUT_MOUSE
            mi = ctypes.cast(ctypes.byref(inp.union), ctypes.POINTER(MOUSEINPUT)).contents
            mi.dwFlags = MOUSEEVENTF_HWHEEL
            mi.mouseData = clamp(ev.delta_x)
            send(inp)

    elif ev.kind in ("keydown", "keyup"):
        inp.type = INPUT_KEYBOARD
        ki = ctypes.cast(ctypes.byref(inp.union), ctypes.POINTER(KEYBDINPUT)).contents
        ki.wVk = ev.vk & 0xFFFF
        if not ev.down:
            ki.dwFlags = KEYEVENTF_KEYUP
        if ev.extended:
            ki.dwFlags |= KEYEVENTF_EXTENDEDKEY
        # Full-surface text input: vk=0 + unicode -> KEYEVENTF_UNICODE in wScan
        if ev.vk == 0 and ev.unicode != 0:
            ki.wScan = ev.unicode & 0xFFFF
            ki.dwFlags |= KEYEVENTF_UNICODE
        send(inp)