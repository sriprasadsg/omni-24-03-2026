"""Protected operating-system paths (Phase 83, D-28 / T-83-46 / T-83-49).

A file under one of these paths is never quarantined automatically: the sweep turns the decision into an
approval card and sends ``allow_protected`` true only on that card, and the agent refuses the path without
it. The lists are the contract's ``protectedPaths`` (``shared/agent-response-contract.json``), the same
ones the Rust agent compares with, so the two sides cannot drift.

The match is deliberately wider than the agent's, and it fails toward a card:
* Windows: the path is lower-cased, ``/`` becomes ``\\``, ``.`` and ``..`` are resolved, a trailing dot or
  space on a segment is dropped, and a prefix such as ``windows\\system32`` matches anywhere in the path
  on whole segments (any drive, any depth), so ``C:/WINDOWS/System32/x.exe`` and ``D:\\Windows\\SysWOW64\\x``
  both match and ``C:\\windows\\system3\\x`` does not.
* Linux: repeated ``/`` are collapsed, ``.`` and ``..`` are resolved with ``posixpath.normpath`` (a
  traversal like ``/tmp/../usr/bin/x`` is matched on where it lands), and the prefix match is on whole
  segments, so ``/etc/passwd`` matches ``/etc/`` and ``/etcetera/x`` does not. A path that is not absolute
  cannot be placed, so it counts as protected.
* An unknown platform checks both lists. An empty or non-text path counts as protected.

Pure functions; nothing here reads a database or the file system.
"""
import ntpath
import posixpath
import re
from typing import Any, List, Optional, Tuple

from .agent_support import CONTRACT


def _lists() -> Tuple[List[str], List[str]]:
    paths = CONTRACT.get("protectedPaths") or {}
    return list(paths.get("windows") or []), list(paths.get("linux") or [])


def _windows_segments(path: str) -> List[str]:
    text = path.lower().replace("/", "\\")
    text = re.sub(r"^\\\\[?.]\\", "", text)                 # \\?\C:\... and \\.\C:\... name the same path
    text = ntpath.normpath(text)
    return [seg.rstrip(". ") for seg in text.split("\\") if seg.rstrip(". ")]


def _windows_protected(path: str, prefixes: List[str]) -> bool:
    segments = _windows_segments(path)
    for prefix in prefixes:
        want = [seg for seg in prefix.lower().replace("/", "\\").split("\\") if seg]
        if want and any(segments[i:i + len(want)] == want for i in range(len(segments) - len(want) + 1)):
            return True
    return False


def _linux_protected(path: str, prefixes: List[str]) -> bool:
    if not path.startswith("/"):
        return True                                          # cannot be placed: a person decides
    clean = posixpath.normpath(re.sub(r"/+", "/", path))
    if not clean.startswith("/"):
        return True
    return any(clean == prefix.rstrip("/") or (clean + "/").startswith(prefix if prefix.endswith("/") else prefix + "/")
               for prefix in prefixes)


def kind_of(platform: Any) -> Optional[str]:
    """``windows`` or ``linux`` for the agent's reported platform text, else None."""
    text = str(platform or "").casefold()
    if "win" in text:
        return "windows"
    if "linux" in text or "ubuntu" in text or "debian" in text or "centos" in text or "rhel" in text:
        return "linux"
    return None


def is_protected(path: Any, platform: Any = None) -> bool:
    """True when ``path`` is under a protected operating-system path for this platform (or for either, when
    the platform is unknown), or cannot be judged."""
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        return True
    windows, linux = _lists()
    kind = kind_of(platform)
    if kind == "windows":
        return _windows_protected(path, windows)
    if kind == "linux":
        return _linux_protected(path, linux)
    return _windows_protected(path, windows) or _linux_protected(path, linux)
