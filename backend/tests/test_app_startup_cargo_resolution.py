"""Regression test: sudoers' secure_path strips ~/.cargo/bin from PATH, so
shutil.which("cargo") under `sudo ./start-all-services.sh` silently resolved
to an ancient distro cargo package (e.g. 1.75) instead of rustup's — too old
to parse a Cargo.lock written by a modern cargo, failing the background
Windows-agent pre-build with a confusing lock-file-version error on every
single startup. _resolve_cargo_binary() must prefer rustup's cargo whenever
it's present, matching agent_rust_builder.py's existing _CARGO_BIN precedent."""
import sys, os
from pathlib import Path, PosixPath
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app_startup


def test_prefers_rustup_cargo_when_present():
    with patch.object(Path, "home", return_value=PosixPath("/root")), \
         patch.object(Path, "exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/cargo"):
        assert app_startup._resolve_cargo_binary() == "/root/.cargo/bin/cargo"


def test_falls_back_to_path_cargo_when_rustup_cargo_absent():
    with patch.object(Path, "home", return_value=PosixPath("/root")), \
         patch.object(Path, "exists", return_value=False), \
         patch("shutil.which", return_value="/usr/bin/cargo"):
        assert app_startup._resolve_cargo_binary() == "/usr/bin/cargo"


def test_returns_none_when_neither_cargo_exists():
    with patch.object(Path, "home", return_value=PosixPath("/root")), \
         patch.object(Path, "exists", return_value=False), \
         patch("shutil.which", return_value=None):
        assert app_startup._resolve_cargo_binary() is None
