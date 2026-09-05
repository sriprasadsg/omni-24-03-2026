"""Browser→agent interactive-control input layer (Phase 74, Option A wire
contract): frame parsing at the trust boundary, the per-session
authorisation gate, and the Windows SendInput replayer import.

Split out of `remote_access.py` purely for the 500-line source cap; the
session orchestration (consent flow, tunnel wiring, screenshot loop) lives
in `remote_access`, this module is the pure input surface. Everything the
plan's full-surface matrix allows is replayed (D-05: mouse buttons/wheel,
keyboard incl. extended keys and Unicode text input); what is forbidden —
`INPUT_HARDWARE`, the SAS secret, `BlockInput`/low-level hooks (D-08) — is
simply never emitted, so there is nothing to call `SendInput` with (see
COVERAGE.md matrix).
"""

import json
from enum import Enum
from typing import Optional, Union
from dataclasses import dataclass


class InputKind(str, Enum):
    MOUSEMOVE = "mousemove"
    MOUSEDOWN = "mousedown"
    MOUSEUP = "mouseup"
    WHEEL = "wheel"
    KEYDOWN = "keydown"
    KEYUP = "keyup"


INPUT_KINDS = {k.value for k in InputKind}


@dataclass
class InputEvent:
    """One decoded interactive-control input frame."""
    kind: str
    x: float = 0.0
    y: float = 0.0
    button: int = 0
    down: bool = False
    delta_x: int = 0
    delta_y: int = 0
    vk: int = 0
    extended: bool = False
    unicode: Optional[int] = None


def parse_input_frame(raw: str) -> InputEvent:
    """Parse and validate one browser→agent input frame.

    Rejects at the boundary:
    - any `kind` outside the enumerated set
    - `x`/`y` outside 0.0..=1.0 inclusive
    - `vk` outside 0..=254
    - a non-`input` `type`
    Returns InputEvent or raises ValueError with a short reason.
    """
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}")

    if value.get("type") != "input":
        raise ValueError("frame type is not 'input'")

    kind = value.get("kind", "")
    if kind not in INPUT_KINDS:
        raise ValueError(f"unknown input kind: {kind}")

    def coord(key: str) -> float:
        n = value.get(key)
        if not isinstance(n, (int, float)):
            raise ValueError(f"missing or non-numeric {key}")
        if not (0.0 <= n <= 1.0):
            raise ValueError(f"{key} {n} out of range 0.0..=1.0")
        return float(n)

    def int_opt(key: str) -> Optional[int]:
        n = value.get(key)
        if n is None:
            return None
        if not isinstance(n, int):
            raise ValueError(f"{key} must be integer")
        return n

    def vk_opt(key: str) -> Optional[int]:
        n = int_opt(key)
        if n is not None and not (0 <= n <= 254):
            raise ValueError(f"{key} {n} out of range 0..=254")
        return n

    if kind == "mousemove":
        return InputEvent(kind=kind, x=coord("x"), y=coord("y"))
    elif kind == "mousedown":
        return InputEvent(kind=kind, down=True, button=vk_opt("button") or 0)
    elif kind == "mouseup":
        return InputEvent(kind=kind, down=False, button=vk_opt("button") or 0)
    elif kind == "wheel":
        return InputEvent(kind=kind, delta_x=int_opt("deltaX") or 0, delta_y=int_opt("deltaY") or 0)
    elif kind == "keydown":
        return InputEvent(
            kind=kind,
            down=True,
            vk=vk_opt("vk") or 0,
            extended=value.get("extended") is True,
            unicode=vk_opt("unicode"),
        )
    elif kind == "keyup":
        return InputEvent(
            kind=kind,
            down=False,
            vk=vk_opt("vk") or 0,
            extended=value.get("extended") is True,
            unicode=vk_opt("unicode"),
        )
    else:
        raise ValueError(f"unknown input kind: {kind}")


class ConsentGate:
    """Per-session authorisation gate for input replay (T-74-02).

    Platform-independent so the accept→active→stop lifecycle is unit-tested
    on Linux. The control read loop concedes once after the endpoint user
    accepts, then consults `authorised()` before EVERY SendInput; the
    endpoint stop bar revokes, after which no further input is replayed
    until a fresh session grants consent again (D-12).
    """

    def __init__(self):
        self.accepted = False
        self.stopped = False

    def concede(self) -> None:
        """Mark consent granted (called once after the endpoint user accepts)."""
        self.accepted = True

    def revoke(self) -> None:
        """Mark control revoked (the stop sentinel appeared). Irreversible within
        this session — a reconnect must obtain fresh consent (D-12)."""
        self.stopped = True

    def authorised(self) -> bool:
        """Whether input may be replayed RIGHT NOW. Refuses until accepted and
        never re-authorises after a stop."""
        return self.accepted and not self.stopped


def replay_input_event(ev: InputEvent) -> None:
    """Replay one decoded event by synthesising native input.

    On Windows, delegates to win_input.control_input_replay.
    On non-Windows, logs a warning and does nothing (unsupported_platform).
    """
    import platform
    import logging

    if platform.system() == "Windows":
        try:
            from .win_input import control_input_replay as win_replay, InputEvent as WinInputEvent
            win_ev = WinInputEvent(
                kind=ev.kind,
                x=ev.x,
                y=ev.y,
                button=ev.button,
                down=ev.down,
                delta_x=ev.delta_x,
                delta_y=ev.delta_y,
                vk=ev.vk,
                extended=ev.extended,
                unicode=ev.unicode or 0,
            )
            win_replay(win_ev)
        except ImportError:
            logging.getLogger(__name__).warning("win_input not available on this Windows build")
    else:
        logging.getLogger(__name__).warning("control_input_replay called on non-Windows (unsupported_platform)")


# --- Tests ---

if __name__ == "__main__":
    # Basic self-test
    import sys

    # Test parse_input_frame
    assert parse_input_frame('{"type":"input","kind":"mousemove","x":0.25,"y":0.75}') == InputEvent("mousemove", x=0.25, y=0.75)
    assert parse_input_frame('{"type":"input","kind":"mousedown","button":2}') == InputEvent("mousedown", down=True, button=2)
    assert parse_input_frame('{"type":"input","kind":"mouseup","button":4}') == InputEvent("mouseup", down=False, button=4)
    assert parse_input_frame('{"type":"input","kind":"wheel","deltaX":2,"deltaY":-1}') == InputEvent("wheel", delta_x=2, delta_y=-1)
    assert parse_input_frame('{"type":"input","kind":"keydown","vk":17,"extended":true}') == InputEvent("keydown", down=True, vk=17, extended=True)
    assert parse_input_frame('{"type":"input","kind":"keyup","vk":0,"unicode":65}') == InputEvent("keyup", down=False, vk=0, unicode=65)

    # Test ConsentGate
    gate = ConsentGate()
    assert not gate.authorised()
    gate.concede()
    assert gate.authorised()
    gate.revoke()
    assert not gate.authorised()

    gate2 = ConsentGate()
    gate2.revoke()
    assert not gate2.authorised()
    gate2.concede()
    assert not gate2.authorised()

    print("All self-tests passed")