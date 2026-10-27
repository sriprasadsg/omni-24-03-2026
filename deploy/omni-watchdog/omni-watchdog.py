#!/usr/bin/python3 -I
"""Entry point of the Omni-Agent AI platform watchdog (Phase 82).

Installed root-owned outside the checkout and started by omni-watchdog.service as
``python3 -I omni-watchdog.py``. Isolated mode does not put the script directory on sys.path, so
this file adds its own real directory (the package lives next to it) and calls the package.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from omni_watchdog.run import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
