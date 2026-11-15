#!/usr/bin/env python3
"""Keep only the allowlisted fields of Suricata's eve.json (manual 7-day check, 88.1 stage 2).

Runs on the sensor box with the standard library only (Python 3.8 or newer):

    python3 eve_allowlist.py /var/log/suricata/eve.json* -o check-lines.jsonl

Reads plain or .gz files (or stdin with "-"), keeps alert and stats events, and writes one JSON object per line
holding nothing but these fields:

    alert: timestamp, flow_id, src_ip, src_port, dest_ip, dest_port, proto, app_proto,
           alert.signature_id, alert.rev, alert.signature, alert.category, alert.severity, alert.action
    stats: timestamp, stats.uptime, stats.capture.kernel_packets, stats.capture.kernel_drops,
           stats.decoder.pkts, stats.detect.engines[].rules_loaded, stats.detect.engines[].rules_failed

Every other event type and field is dropped, and a listed field is kept only when it holds a plain value (text,
a number or true/false). A line that is not valid JSON, such as a half-written last line, is counted and
skipped. The counts are printed to stderr when the run ends. The output file is created readable by its owner
only.
"""
import argparse
import gzip
import json
import os
import sys
from collections import Counter

ALERT_FIELDS = ("timestamp", "flow_id", "src_ip", "src_port", "dest_ip", "dest_port", "proto", "app_proto")
ALERT_DETAIL_FIELDS = ("signature_id", "rev", "signature", "category", "severity", "action")
CAPTURE_FIELDS = ("kernel_packets", "kernel_drops")
DECODER_FIELDS = ("pkts",)
ENGINE_FIELDS = ("rules_loaded", "rules_failed")


def _plain(source, fields):
    """The listed fields of ``source`` that hold a plain value."""
    if not isinstance(source, dict):
        return {}
    return {field: source[field] for field in fields if isinstance(source.get(field), (str, int, float, bool))}


def _section(source, name):
    value = source.get(name) if isinstance(source, dict) else None
    return value if isinstance(value, dict) else {}


def allow_alert(event):
    kept = {"event_type": "alert"}
    kept.update(_plain(event, ALERT_FIELDS))
    kept["alert"] = _plain(event.get("alert"), ALERT_DETAIL_FIELDS)
    return kept


def allow_stats(event):
    stats = _section(event, "stats")
    engines = _section(stats, "detect").get("engines")
    body = _plain(stats, ("uptime",))
    body["capture"] = _plain(stats.get("capture"), CAPTURE_FIELDS)
    body["decoder"] = _plain(stats.get("decoder"), DECODER_FIELDS)
    body["detect"] = {"engines": [_plain(engine, ENGINE_FIELDS) for engine in engines]
                      if isinstance(engines, list) else []}
    kept = {"event_type": "stats"}
    kept.update(_plain(event, ("timestamp",)))
    kept["stats"] = body
    return kept


def allow(event):
    """The allowlisted copy of one EVE event, or None for an event that is not kept."""
    if not isinstance(event, dict):
        return None
    if event.get("event_type") == "alert":
        return allow_alert(event)
    if event.get("event_type") == "stats":
        return allow_stats(event)
    return None


def filter_lines(lines, out, counts):
    """Write the allowlisted copy of every alert and stats line to ``out``; tally what happened in ``counts``."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        counts["read"] += 1
        try:
            kept = allow(json.loads(line))
        except ValueError:
            counts["unreadable"] += 1
            continue
        if kept is None:
            counts["skipped"] += 1
            continue
        counts[kept["event_type"]] += 1
        out.write(json.dumps(kept, separators=(",", ":")) + "\n")


def _open_input(path):
    if path == "-":
        return sys.stdin
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def _open_output(path):
    if not path:
        return sys.stdout
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keep only the allowlisted fields of Suricata's eve.json.")
    parser.add_argument("paths", nargs="+", help='eve.json files, plain or .gz; "-" reads stdin')
    parser.add_argument("-o", "--output", help="file to write (default: stdout)")
    args = parser.parse_args(argv)

    counts = Counter()
    out = _open_output(args.output)
    try:
        for path in args.paths:
            source = _open_input(path)
            try:
                filter_lines(source, out, counts)
            finally:
                if source is not sys.stdin:
                    source.close()
    finally:
        if out is not sys.stdout:
            out.close()
    print("read {read} lines: kept {alert} alerts and {stats} stats events, skipped {skipped} other events, "
          "{unreadable} unreadable lines".format(**{key: counts[key] for key in
                                                    ("read", "alert", "stats", "skipped", "unreadable")}),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
