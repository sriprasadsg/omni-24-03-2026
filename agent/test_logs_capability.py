"""Linux log collection keeps its journal entries when a web log is unreadable, and tails web logs.

Value: protects=one unreadable or huge web log never replaces the machine's logs with an error;
fails_when=logger or datetime is undefined again (every Linux log became "Linux log error: name 'logger' is not
defined"), or a web log is read whole; no_claim=Windows collection, the server's parsing.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from capabilities import logs as logs_mod

REAL_TAIL = logs_mod.tail_lines


def _journal():
    line = json.dumps({"__REALTIME_TIMESTAMP": "1", "PRIORITY": "6", "MESSAGE": "sshd started"})
    return MagicMock(returncode=0, stdout=line + "\n")


class LinuxLogsTest(unittest.TestCase):
    def _collect(self, readable_paths, opener=None):
        cap = logs_mod.LogsCapability.__new__(logs_mod.LogsCapability)
        with patch.object(logs_mod.subprocess, "run", return_value=_journal()), \
                patch.object(logs_mod.os.path, "exists", side_effect=lambda p: p in readable_paths), \
                patch.object(logs_mod, "tail_lines", side_effect=opener or logs_mod.tail_lines):
            return cap._collect_linux_logs()

    def test_an_unreadable_web_log_keeps_the_journal(self):
        def denied(path, count):
            raise PermissionError("denied")
        out = self._collect({"/var/log/nginx/access.log"}, denied)
        self.assertEqual([e["source"] for e in out], ["journal"])
        self.assertNotIn("Linux log error", json.dumps(out))

    def test_a_web_log_is_tailed_with_aware_timestamps(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".log") as f:
            f.write("x" * 40000 + "\n" + "\n".join(f"GET /{i}" for i in range(10)) + "\n")
        try:
            self.assertEqual(logs_mod.tail_lines(f.name, 5), [f"GET /{i}" for i in range(5, 10)])
            out = self._collect({"/var/log/nginx/access.log"}, lambda p, n: REAL_TAIL(f.name, n))
        finally:
            os.unlink(f.name)
        web = [e for e in out if e["source"] == "web_log:access.log"]
        self.assertEqual([e["message"] for e in web], [f"GET /{i}" for i in range(5, 10)])
        self.assertTrue(web[0]["timestamp"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
