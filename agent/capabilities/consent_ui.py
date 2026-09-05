"""Endpoint consent and revocation control for remote desktop control.

The agent runs as a Session-0 service and cannot draw an interactive window
itself. This module spawns PowerShell WinForms UI *into the active console
session* using `CreateProcessAsUserW` with a token obtained from
`WTSQueryUserToken(WTSGetActiveConsoleSessionId())` — the same mechanism as
`chat_ui.rs`. Two surfaces live here:

  * a consent dialog (Surface 2) that must be accepted before any input is
    replayed (D-01), naming the requesting admin and tenant (D-03);
  * a persistent stop-control bar (Surface 3) letting the endpoint user end
    control with one click at any time (D-09).

The untrusted requester identity travels to PowerShell only through a
per-session JSON config file read with `ConvertFrom-Json` (T-74-08), never
interpolated into script text or the command line. Nothing is persisted
across sessions (D-04). pywin32 is used for the FFI surface.

The two embedded PowerShell constants live in the sibling `consent_scripts.py`
purely for the 500-line source cap; all Python logic and the public surface
stay here.
"""

import os
import json
import time
import platform
import tempfile
from enum import Enum
from typing import Optional

if platform.system() == "Windows":
    import win32api
    import win32con
    import win32process
    import win32security
    import win32profile
    import win32ts
    import pywintypes
else:
    win32api = win32con = win32process = win32security = win32profile = win32ts = pywintypes = None


class ConsentDecision(Enum):
    Accept = "accept"
    Decline = "decline"
    Timeout = "timeout"


class ConsentError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _data_dir() -> str:
    """Directory holding per-session config files and decision/stop sentinels."""
    if platform.system() != "Windows":
        return tempfile.gettempdir()
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    return os.path.join(base, "OmniAgent")


def _ensure_scripts_installed() -> None:
    """Write the embedded scripts to data_dir() so spawned processes can launch them. Idempotent."""
    from . import consent_scripts

    d = _data_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "consent_ui.ps1"), "w") as f:
        f.write(consent_scripts.CONSENT_UI_PS)
    with open(os.path.join(d, "stop_bar.ps1"), "w") as f:
        f.write(consent_scripts.STOP_BAR_PS)


def _parse_decision(body: str) -> Optional[ConsentDecision]:
    """Parse a decision-file body into a ConsentDecision. Unrecognised body returns None."""
    body = body.strip().lower()
    if body == "accept":
        return ConsentDecision.Accept
    if body == "decline":
        return ConsentDecision.Decline
    if body == "timeout":
        return ConsentDecision.Timeout
    return None


def _spawn_in_active_session(cmdline: str) -> None:
    """Launch cmdline as the interactive console user on winsta0\\default (Windows only)."""
    if platform.system() != "Windows":
        raise ConsentError("no interactive desktop session (non-Windows platform)")

    session_id = win32ts.WTSGetActiveConsoleSessionId()
    if session_id == 0xFFFFFFFF:
        raise ConsentError("no active console session (no user logged on)")

    try:
        user_token = win32ts.WTSQueryUserToken(session_id)
    except pywintypes.error as e:
        raise ConsentError(f"WTSQueryUserToken failed ({e.winerror})")

    try:
        primary_token = win32security.DuplicateTokenEx(
            user_token,
            win32con.MAXIMUM_ALLOWED,
            None,
            win32con.SecurityImpersonation,
            win32con.TokenPrimary,
        )
    except pywintypes.error as e:
        win32api.CloseHandle(user_token)
        raise ConsentError(f"DuplicateTokenEx failed ({e.winerror})")
    win32api.CloseHandle(user_token)

    try:
        env = win32profile.CreateEnvironmentBlock(primary_token, False)
        have_env = True
    except pywintypes.error:
        env = None
        have_env = False

    startup = win32process.STARTUPINFO()
    startup.cb = win32process.sizeof(startup)
    startup.lpDesktop = "winsta0\\default"

    flags = win32con.CREATE_UNICODE_ENVIRONMENT | win32con.CREATE_NO_WINDOW

    try:
        hProcess, hThread, _, _ = win32process.CreateProcessAsUser(
            primary_token,
            None,
            cmdline,
            None,
            None,
            False,
            flags,
            env,
            None,
            startup,
        )
    except pywintypes.error as e:
        if have_env and env:
            win32profile.DestroyEnvironmentBlock(env)
        win32api.CloseHandle(primary_token)
        raise ConsentError(f"CreateProcessAsUserW failed ({e.winerror})")

    if have_env and env:
        win32profile.DestroyEnvironmentBlock(env)
    win32api.CloseHandle(primary_token)
    win32api.CloseHandle(hThread)
    win32api.CloseHandle(hProcess)


def request_consent(
    session_id: str,
    requester_name: str,
    requester_email: str,
    tenant_name: str,
    timeout_secs: int = 60,
) -> ConsentDecision:
    """Ask the interactive endpoint user to accept or decline remote control."""
    if platform.system() != "Windows":
        raise ConsentError("no interactive desktop session (non-Windows platform)")

    _ensure_scripts_installed()
    d = _data_dir()

    cfg = {
        "session_id": session_id,
        "requester_name": requester_name,
        "requester_email": requester_email,
        "tenant_name": tenant_name,
        "timeout_secs": timeout_secs,
    }
    cfg_path = os.path.join(d, f"consent_{session_id}.json")
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)

    cmdline = (
        f'powershell.exe -NoProfile -WindowStyle Hidden '
        f'-ExecutionPolicy Bypass -File "{os.path.join(d, "consent_ui.ps1")}" "{cfg_path}"'
    )

    try:
        _spawn_in_active_session(cmdline)
    except ConsentError:
        try:
            os.remove(cfg_path)
        except OSError:
            pass
        raise

    decision_path = os.path.join(d, f"consent_{session_id}.decision")
    deadline = time.time() + timeout_secs
    decision = ConsentDecision.Timeout

    while time.time() < deadline:
        if os.path.exists(decision_path):
            try:
                with open(decision_path, "r") as f:
                    body = f.read()
                parsed = _parse_decision(body)
                if parsed is not None:
                    decision = parsed
                    break
            except OSError:
                pass
        time.sleep(0.2)

    try:
        os.remove(cfg_path)
    except OSError:
        pass
    try:
        os.remove(decision_path)
    except OSError:
        pass

    return decision


def show_stop_bar(session_id: str, requester_name: str) -> None:
    """Show the persistent stop-control bar (Surface 3)."""
    if platform.system() != "Windows":
        raise ConsentError("no interactive desktop session (non-Windows platform)")

    _ensure_scripts_installed()
    d = _data_dir()

    cfg = {"session_id": session_id, "requester_name": requester_name}
    cfg_path = os.path.join(d, f"stop_{session_id}.json")
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)

    cmdline = (
        f'powershell.exe -NoProfile -WindowStyle Hidden '
        f'-ExecutionPolicy Bypass -File "{os.path.join(d, "stop_bar.ps1")}" "{cfg_path}"'
    )

    try:
        _spawn_in_active_session(cmdline)
    except ConsentError:
        try:
            os.remove(cfg_path)
        except OSError:
            pass
        raise


def stop_requested(session_id: str) -> bool:
    """Whether the endpoint user has clicked Stop Control (the .stop sentinel exists)."""
    if platform.system() != "Windows":
        return False
    sentinel = os.path.join(_data_dir(), f"stop_{session_id}.stop")
    return os.path.exists(sentinel)


def hide_stop_bar(session_id: str) -> None:
    """Hide the stop-control bar and clear all session residue."""
    if platform.system() != "Windows":
        return
    d = _data_dir()
    os.makedirs(d, exist_ok=True)

    # Signal the bar to self-close; clear every sentinel/config file.
    close_path = os.path.join(d, f"stop_{session_id}.close")
    try:
        with open(close_path, "w") as f:
            f.write("close")
    except OSError:
        pass

    for suffix in (".stop", ".json", ".close", ".json", ".decision"):
        prefix = "stop_" if not suffix.endswith(".json") or not suffix.endswith(".decision") else "consent_"
        path = os.path.join(d, f"{prefix}{session_id}{suffix}")
        try:
            os.remove(path)
        except OSError:
            pass