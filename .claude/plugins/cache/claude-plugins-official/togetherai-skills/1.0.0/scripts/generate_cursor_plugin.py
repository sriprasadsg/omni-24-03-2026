#!/usr/bin/env python3
"""Generate .cursor-plugin/ manifests from .claude-plugin/plugin.json.

Usage:
    python scripts/generate_cursor_plugin.py              # Generate
    python scripts/generate_cursor_plugin.py --check      # Check if up-to-date

Uses .claude-plugin/plugin.json as the source of truth and generates
.cursor-plugin/plugin.json with the additional skills_directory field.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_PLUGIN = REPO_ROOT / ".claude-plugin" / "plugin.json"
CURSOR_PLUGIN = REPO_ROOT / ".cursor-plugin" / "plugin.json"


def generate() -> str:
    """Generate Cursor plugin.json from Claude plugin.json."""
    source = json.loads(CLAUDE_PLUGIN.read_text(encoding="utf-8"))
    # Add Cursor-specific field
    source["skills_directory"] = "skills"
    return json.dumps(source, indent=2) + "\n"


def main() -> int:
    check_mode = "--check" in sys.argv

    if not CLAUDE_PLUGIN.exists():
        print(f"ERROR: {CLAUDE_PLUGIN} not found")
        return 1

    content = generate()

    if check_mode:
        if not CURSOR_PLUGIN.exists():
            print("FAIL: .cursor-plugin/plugin.json does not exist")
            return 1
        current = CURSOR_PLUGIN.read_text(encoding="utf-8")
        if current != content:
            print(
                "FAIL: .cursor-plugin/plugin.json is out of date. "
                "Run: python scripts/generate_cursor_plugin.py"
            )
            return 1
        print("OK: .cursor-plugin/plugin.json is up to date")
        return 0

    CURSOR_PLUGIN.parent.mkdir(parents=True, exist_ok=True)
    CURSOR_PLUGIN.write_text(content, encoding="utf-8")
    print(f"Generated {CURSOR_PLUGIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
