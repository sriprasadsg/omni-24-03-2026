"""
Regression: ISSUE-004 — a rejected buffered heartbeat blocks the offline buffer forever
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro: agent/buffer.db held 53,373 queued heartbeats (7.9 GB) copied from older
hosts. After every successful heartbeat the agent resent the oldest one (hostname
security-test-vm), the backend answered 403 "Hardware ID mismatch", and the drain loop
broke without deleting it, so the same message was resent every cycle (a backend
SECURITY ALERT every ~9 s) and nothing behind it ever drained.

Value: protects=a permanently rejected or foreign-host message is removed and the queue
keeps draining, a transient 5xx keeps it, and the buffer is bounded; fails_when=the drain
loop breaks on 4xx without deleting, replays other hosts' heartbeats, or the buffer grows
without a cap; why_new=no agent test covers MessageBuffer or the drain loop; seam=none;
no_claim=backend acceptance of replayed heartbeats (requests.post is mocked; a real
SQLite file backs the buffer, encryption off).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent

URL = "http://127.0.0.1:5000/api/agents/agent-1/heartbeat"
HOST = "this-host"


def _resp(status):
    return MagicMock(status_code=status)


class MessageBufferDrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.buf = agent.MessageBuffer(db_path=os.path.join(self.tmp.name, "buffer.db"))
        self.host = patch.object(agent.socket, "gethostname", return_value=HOST)
        self.host.start()

    def tearDown(self):
        self.host.stop()
        self.tmp.cleanup()

    def _queued(self):
        return [json.loads(p)["seq"] for _, p in self.buf.get_messages(limit=10_000)]

    def test_rejected_message_is_dropped_and_queue_keeps_draining(self):
        self.buf.add_message({"hostname": HOST, "seq": 1})
        self.buf.add_message({"hostname": HOST, "seq": 2})
        with patch.object(agent.requests, "post", side_effect=[_resp(403), _resp(200)]) as post:
            agent._drain_buffer(self.buf, URL, {})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(self._queued(), [])

    def test_foreign_host_message_is_dropped_without_sending(self):
        self.buf.add_message({"hostname": "security-test-vm", "seq": 1})
        self.buf.add_message({"hostname": HOST, "seq": 2})
        with patch.object(agent.requests, "post", return_value=_resp(200)) as post:
            agent._drain_buffer(self.buf, URL, {})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["json"]["seq"], 2)
        self.assertEqual(self._queued(), [])

    def test_server_error_keeps_message_and_stops(self):
        self.buf.add_message({"hostname": HOST, "seq": 1})
        self.buf.add_message({"hostname": HOST, "seq": 2})
        with patch.object(agent.requests, "post", return_value=_resp(503)) as post:
            agent._drain_buffer(self.buf, URL, {})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(self._queued(), [1, 2])

    def test_buffer_keeps_only_the_newest_messages(self):
        cap = agent.MessageBuffer.MAX_MESSAGES
        for seq in range(cap + 5):
            self.buf.add_message({"hostname": HOST, "seq": seq})
        queued = self._queued()
        self.assertEqual(len(queued), cap)
        self.assertEqual(queued[0], 5)


if __name__ == "__main__":
    unittest.main()
