"""Route to the platform server and LAN scan details in the Network Discovery capability.

The route (network_discovery.route) is what the backend draws as hops between an endpoint's
gateway and the Omni-Agent server; open ports and the device type go with scanned devices.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from capabilities.network_discovery import (NetworkDiscoveryCapability, device_type, parse_traceroute,
                                            parse_tracepath)

# tracepath -n -m 6 1.1.1.1 on the Omniai-copy VM (2026-11-17), plus a hop printed twice.
TRACEPATH = """ 1?: [LOCALHOST]                      pmtu 1500
 1:  no reply
 2:  10.0.0.1                                              0.512ms
 2:  10.0.0.1                                              0.733ms
 6:  51.10.5.89                                            3.827ms asymm 11
     Too many hops: pmtu 1500
"""

TRACERT = """
Tracing route to 57.154.210.55 over a maximum of 20 hops

  1    <1 ms    <1 ms    <1 ms  192.168.0.1
  2     5 ms     4 ms     6 ms  100.64.0.1
  3     *        *        *     Request timed out.
  4    31 ms     *       32 ms  57.154.210.55

Trace complete.
"""


class RouteParsing(unittest.TestCase):
    def test_tracepath_skips_localhost_and_keeps_the_answering_line(self):
        self.assertEqual(parse_tracepath(TRACEPATH), [
            {"hop": 1, "ip": None, "rtt_ms": None},
            {"hop": 2, "ip": "10.0.0.1", "rtt_ms": 0.512},
            {"hop": 6, "ip": "51.10.5.89", "rtt_ms": 3.827},
        ])

    def test_tracert_and_traceroute_give_address_and_average_time(self):
        self.assertEqual(parse_traceroute(TRACERT), [
            {"hop": 1, "ip": "192.168.0.1", "rtt_ms": 1.0},
            {"hop": 2, "ip": "100.64.0.1", "rtt_ms": 5.0},
            {"hop": 3, "ip": None, "rtt_ms": None},
            {"hop": 4, "ip": "57.154.210.55", "rtt_ms": 31.5},
        ])
        self.assertEqual(parse_traceroute(" 1  192.168.0.1  0.512 ms\n 2  *\n"),
                         [{"hop": 1, "ip": "192.168.0.1", "rtt_ms": 0.5}, {"hop": 2, "ip": None, "rtt_ms": None}])

    def test_device_type_from_open_ports(self):
        self.assertEqual(device_type([53, 80, 443]), "Router/Firewall")
        self.assertEqual(device_type([631]), "Printer")
        self.assertEqual(device_type([]), "Unknown")


class RouteInCollect(unittest.TestCase):
    def test_no_trace_for_an_agent_on_the_server_itself(self):
        for url in ("http://localhost:5000", "http://127.0.0.1:5000", ""):
            self.assertIsNone(NetworkDiscoveryCapability({"api_base_url": url})._server_host())
        self.assertEqual(NetworkDiscoveryCapability({"api_base_url": "https://omni.example.com/api"})._server_host(), "omni.example.com")

    def test_collect_reports_the_last_trace_and_starts_one_in_the_background(self):
        import time
        cap = NetworkDiscoveryCapability({"api_base_url": "https://omni.example.com"})
        cap._last_scan_ts = time.time()  # no LAN scan in this test
        route = {"target": "omni.example.com", "reached": True, "hops": [{"hop": 1, "ip": "192.168.0.1", "rtt_ms": 1.0}]}
        with patch.object(NetworkDiscoveryCapability, "trace", return_value=route) as trace, \
                patch("capabilities.network_discovery.threading.Thread") as thread:
            self.assertNotIn("route", cap.collect())  # the trace has only been started
            thread.call_args.kwargs["target"]()       # ...and finishes in the background
            self.assertEqual(cap.collect()["route"], route)
            self.assertEqual(thread.call_count, 1)    # not traced again within 15 minutes
        trace.assert_called_once_with("omni.example.com")


if __name__ == "__main__":
    unittest.main()
