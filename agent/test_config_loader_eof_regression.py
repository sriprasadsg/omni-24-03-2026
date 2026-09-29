"""Regression for the 2026-09-28 startup crash:

    Enter API Base URL [http://localhost:5000]:
    Traceback (most recent call last):
      File "agent.py", line 2202, in <module>
        main()
      File "agent.py", line 1996, in main
        cfg = load_config()
      File "agent.py", line 181, in load_config
        api_base_url = input("Enter API Base URL...").strip()
    EOFError: EOF when reading a line

start-all-services.sh launches agent.py with no attached TTY. With no
config.yaml on disk and no CLI/env values supplied, load_config()
unconditionally called input() and the whole agent process crashed the
instant stdin hit EOF.

Fix: detect sys.stdin.isatty() up front. Non-interactive + no registration
key -> fail fast with sys.exit(1) and a clear message instead of calling
input(). Non-interactive + registration key already supplied (env/CLI) ->
skip the API-base-URL prompt entirely and fall back to its default.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import agent


class TestLoadConfigNonInteractiveRegression(unittest.TestCase):
    def setUp(self):
        self._mgr = MagicMock()
        self._mgr.load_encrypted_config.return_value = {}
        self._patches = [
            patch.object(agent, "SecurityManager", return_value=self._mgr),
            patch.object(agent, "save_config"),
            patch.object(agent, "setup_secure_logging"),
            patch("sys.argv", ["agent.py"]),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        for key in ("OMNI_AGENT_API_URL", "OMNI_AGENT_REGISTRATION_KEY"):
            os.environ.pop(key, None)
        self.addCleanup(os.environ.pop, "OMNI_AGENT_API_URL", None)
        self.addCleanup(os.environ.pop, "OMNI_AGENT_REGISTRATION_KEY", None)

    def test_non_interactive_no_registration_key_exits_cleanly_instead_of_eof_crash(self):
        with patch.object(sys.stdin, "isatty", return_value=False), \
             patch("builtins.input", side_effect=EOFError("EOF when reading a line")):
            with self.assertRaises(SystemExit) as ctx:
                agent.load_config()
            self.assertEqual(ctx.exception.code, 1)

    def test_non_interactive_with_registration_key_env_skips_prompt_and_uses_default_url(self):
        os.environ["OMNI_AGENT_REGISTRATION_KEY"] = "test-key-123"

        with patch.object(sys.stdin, "isatty", return_value=False), \
             patch("builtins.input", side_effect=EOFError("EOF when reading a line")):
            config = agent.load_config()

        self.assertEqual(config["api_base_url"], "http://localhost:5000")
        self.assertEqual(config["registration_key"], "test-key-123")

    def test_interactive_session_still_prompts_as_before(self):
        # Sanity check the fix didn't remove interactive behavior: a real
        # TTY should still hit input() for both prompts.
        with patch.object(sys.stdin, "isatty", return_value=True), \
             patch("builtins.input", side_effect=["http://example.test:5000", "interactive-key"]):
            config = agent.load_config()

        self.assertEqual(config["api_base_url"], "http://example.test:5000")
        self.assertEqual(config["registration_key"], "interactive-key")


if __name__ == "__main__":
    unittest.main()
