#!/usr/bin/env python3
"""Tables for the manual 7-day check, built from the allowlisted lines (88.1 stage 2).

    python3 scripts/ndr_check/check_tables.py check-lines.jsonl --home-net 10.0.0.0/8 --assets assets.csv

Prints plain text: sensor health over the period, alerts per list under the current rules, alerts by class,
severity and signature prefix with what the noise cut hides, row counts per (signature, source, destination)
group and per device, and the unlisted internal addresses for the IT manager to review. A device count
includes every address on the list's side of an alert, so a scan's targets count too; "seen as a source"
counts only the addresses that sent something. The one-page report is
built from these numbers, and they decide the open questions on device matching (R7), the noise cut (R8) and
the row shape (R9).

The list rules are the design's, in this order. Each alert lands in exactly one list:

    Suppressed ............... severity 3 or higher, or the signature starts with "ET INFO " or "ET POLICY ",
                               or the class is "Not Suspicious Traffic"
    Unknown devices .......... an internal endpoint that is not in the asset list
    Alerts on your devices ... an internal endpoint that is in the asset list
    Outside your networks .... everything else

Internal means inside one of the --home-net networks. An IPv4 network's own address and its broadcast address
are not devices and never count as unknown (a /31 or /32 has neither). The asset list is a CSV with hostname,
ip (or ip_address) and owner columns; without one, every internal address is unlisted.
"""
import argparse
import csv
import ipaddress
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))

from ndr_sensors import window_deltas  # noqa: E402  (the platform's counter-growth rule, restarts included)

SUPPRESSED = "Suppressed"
UNKNOWN = "Unknown devices"
YOURS = "Alerts on your devices"
OUTSIDE = "Outside your networks"
LISTS = (UNKNOWN, YOURS, OUTSIDE, SUPPRESSED)
GROUP_WINDOW = timedelta(hours=24)
WHOLE_PERIOD = timedelta(days=3650)
TIME_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z")


def parse_time(text):
    """A Suricata timestamp ("2026-11-14T12:00:00.123456+0000") as an aware datetime, or None."""
    for pattern in TIME_FORMATS:
        try:
            return datetime.strptime(str(text), pattern)
        except ValueError:
            continue
    return None


def _address(text):
    try:
        return ipaddress.ip_address(str(text).strip())
    except ValueError:
        return None


def parse_networks(text):
    return [ipaddress.ip_network(part.strip(), strict=False) for part in text.split(",") if part.strip()]


def load_assets(path):
    """``{address: {"hostname", "owner"}}`` from the asset CSV. A row without a valid IP is skipped; when two
    rows share an IP the first one wins, unless only the later one names an owner."""
    assets = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            row = {(key or "").strip().lower(): (value or "").strip() for key, value in raw.items()}
            address = _address(row.get("ip") or row.get("ip_address") or "")
            if address is None:
                continue
            entry = {"hostname": row.get("hostname", ""), "owner": row.get("owner", "")}
            if address not in assets or (entry["owner"] and not assets[address]["owner"]):
                assets[address] = entry
    return assets


def endpoint_kind(text, nets, assets):
    """"known", "unknown", "non_device" (a subnet's network or broadcast address) or "outside"."""
    address = _address(text)
    inside = [net for net in nets if address is not None and address in net]
    if not inside:
        return "outside"
    if address in assets:
        return "known"
    if any(net.version == 4 and net.prefixlen <= 30 and address in (net.network_address, net.broadcast_address)
           for net in inside):
        return "non_device"
    return "unknown"


def is_suppressed(event):
    alert = event.get("alert") or {}
    severity = alert.get("severity")
    return ((isinstance(severity, int) and severity >= 3)
            or str(alert.get("signature", "")).startswith(("ET INFO ", "ET POLICY "))
            or alert.get("category") == "Not Suspicious Traffic")


def assign_list(event, nets, assets):
    """The one list an alert lands in."""
    if is_suppressed(event):
        return SUPPRESSED
    kinds = {endpoint_kind(event.get(side), nets, assets) for side in ("src_ip", "dest_ip")}
    if "unknown" in kinds:
        return UNKNOWN
    if "known" in kinds:
        return YOURS
    return OUTSIDE


def count_groups(timed_alerts):
    """Rows made by grouping ``(time, alert)`` pairs on (signature, source, destination) in rolling 24-hour
    windows, each anchored at its group's first alert."""
    anchors = {}
    groups = 0
    for at, event in sorted(timed_alerts, key=lambda pair: pair[0]):
        key = ((event.get("alert") or {}).get("signature_id"), event.get("src_ip"), event.get("dest_ip"))
        if key not in anchors or at - anchors[key] > GROUP_WINDOW:
            anchors[key] = at
            groups += 1
    return groups


def _sensor_totals(timed_stats):
    """Packets, drops and rule counts over the period, counted from Suricata's start and across restarts."""
    samples = [{"sampledAt": timed_stats[0][0] - timedelta(microseconds=1)}] if timed_stats else []
    for at, event in timed_stats:
        body = event.get("stats") or {}
        capture = body.get("capture") or {}
        # A capture replay (suricata -r) has no capture section; its decoder count stands in.
        packets = capture.get("kernel_packets", (body.get("decoder") or {}).get("pkts"))
        samples.append({"sampledAt": at, "packets": packets, "drops": capture.get("kernel_drops"),
                        "uptime": body.get("uptime")})
    packets, drops = window_deltas(samples, WHOLE_PERIOD)
    engines = (((timed_stats[-1][1].get("stats") or {}).get("detect") or {}).get("engines") or []
               if timed_stats else [])
    return {"events": len(timed_stats),
            "days": len({at.astimezone(timezone.utc).date() for at, _ in timed_stats}),
            "packets": packets, "drops": drops,
            "rulesLoaded": sum(engine.get("rules_loaded") or 0 for engine in engines),
            "rulesFailed": sum(engine.get("rules_failed") or 0 for engine in engines)}


def summarise(events, nets, assets):
    """Every number the tables show, from the allowlisted events."""
    timed = sorted(((at, event) for event in events if (at := parse_time(event.get("timestamp")))),
                   key=lambda pair: pair[0])
    alerts = [pair for pair in timed if pair[1].get("event_type") == "alert"]
    by_list = defaultdict(list)
    classes, prefixes = defaultdict(Counter), defaultdict(Counter)
    unlisted = {}
    internal_only = 0
    for at, event in alerts:
        name = assign_list(event, nets, assets)
        by_list[name].append((at, event))
        alert = event.get("alert") or {}
        signature = str(alert.get("signature", ""))
        tally = "hidden" if name == SUPPRESSED else "shown"
        classes[(alert.get("category") or "(none)", alert.get("severity"))][tally] += 1
        prefixes[" ".join(signature.split()[:2]) or "(none)"][tally] += 1
        kinds = {side: endpoint_kind(event.get(side), nets, assets) for side in ("src_ip", "dest_ip")}
        if name != SUPPRESSED and "outside" not in kinds.values():
            internal_only += 1
        for side, other in (("src_ip", "dest_ip"), ("dest_ip", "src_ip")):
            if kinds[side] == "unknown":
                row = unlisted.setdefault(event.get(side), {"shown": 0, "hidden": 0, "asSource": 0,
                                                            "signatures": set(), "peers": set(),
                                                            "first": at, "last": at})
                row[tally] += 1
                row["asSource"] += side == "src_ip"
                row["signatures"].add(alert.get("signature_id"))
                row["peers"].add(event.get(other))
                row["last"] = at

    def devices(name, sides):
        kind = {UNKNOWN: "unknown", YOURS: "known"}.get(name)
        return len({event.get(side) for _, event in by_list[name] for side in sides
                    if endpoint_kind(event.get(side), nets, assets) == kind})

    return {
        "unreadable": len(events) - len(timed),
        "period": (timed[0][0], timed[-1][0]) if timed else None,
        "health": _sensor_totals([pair for pair in timed if pair[1].get("event_type") == "stats"]),
        "lists": {name: {"alerts": len(by_list[name]), "groups": count_groups(by_list[name]),
                         "devices": devices(name, ("src_ip", "dest_ip")), "sources": devices(name, ("src_ip",))}
                  for name in LISTS},
        "shown": sum(len(by_list[name]) for name in LISTS if name != SUPPRESSED),
        "internalOnly": internal_only,
        "classes": sorted(((category, severity, tally["shown"] + tally["hidden"], tally["hidden"])
                           for (category, severity), tally in classes.items()), key=lambda row: -row[2]),
        "prefixes": sorted(((prefix, tally["shown"] + tally["hidden"], tally["hidden"])
                            for prefix, tally in prefixes.items()), key=lambda row: -row[1]),
        "unlisted": sorted(({"address": address, "shown": row["shown"], "hidden": row["hidden"],
                             "asSource": row["asSource"], "signatures": len(row["signatures"]),
                             "peers": len(row["peers"]),
                             "first": row["first"], "last": row["last"]} for address, row in unlisted.items()),
                           key=lambda row: -(row["shown"] + row["hidden"])),
    }


def _when(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render(summary, has_assets=True, unreadable_lines=0):
    """The tables as plain text."""
    health, lists = summary["health"], summary["lists"]
    lines = ["PERIOD"]
    if summary["period"] is None:
        lines.append("  no readable events")
    else:
        lines.append("  %s to %s" % (_when(summary["period"][0]), _when(summary["period"][1])))
    lines.append("  lines not readable: %d" % (summary["unreadable"] + unreadable_lines))

    ratio = "%.2f%%" % (100.0 * health["drops"] / health["packets"]) if health["packets"] else "n/a"
    lines += ["", "SENSOR HEALTH (counted since Suricata started)",
              "  stats events: %d on %d calendar days" % (health["events"], health["days"]),
              "  packets seen: %d   drops: %d (%s)" % (health["packets"], health["drops"], ratio),
              "  rules loaded: %d   failed: %d" % (health["rulesLoaded"], health["rulesFailed"])]

    lines += ["", "ALERTS BY LIST (current rules)"]
    if not has_assets:
        lines.append("  no asset list given: every internal address counts as unlisted")
    for name in LISTS:
        row = lists[name]
        devices = ("   %d devices (%d seen as a source)" % (row["devices"], row["sources"])
                   if name in (UNKNOWN, YOURS) else "")
        lines.append("  %-24s %6d alerts   %5d rows per signature/source/destination%s"
                     % (name, row["alerts"], row["groups"], devices))
    lines.append("  both endpoints internal: %d of %d shown alerts" % (summary["internalOnly"], summary["shown"]))
    if not summary["shown"] and not lists[SUPPRESSED]["alerts"]:
        lines.append("  no alerts in the period")

    lines += ["", "BY CLASS AND SEVERITY", "  %-48s %4s %7s %7s" % ("class", "sev", "alerts", "hidden")]
    lines += ["  %-48s %4s %7d %7d" % (str(category)[:48], severity, total, hidden)
              for category, severity, total, hidden in summary["classes"]]
    lines += ["", "BY SIGNATURE PREFIX", "  %-32s %7s %7s" % ("prefix", "alerts", "hidden")]
    lines += ["  %-32s %7d %7d" % (prefix[:32], total, hidden) for prefix, total, hidden in summary["prefixes"]]

    lines += ["", "UNLISTED INTERNAL ADDRESSES (for the IT manager to review)",
              "  an address never seen as a source may only be a scan target, with no device behind it",
              "  %-40s %6s %6s %6s %5s %5s  %-20s %s"
              % ("address", "shown", "hidden", "as src", "sigs", "peers", "first", "last")]
    lines += ["  %-40s %6d %6d %6d %5d %5d  %-20s %s"
              % (row["address"], row["shown"], row["hidden"], row["asSource"], row["signatures"], row["peers"],
                 _when(row["first"]), _when(row["last"])) for row in summary["unlisted"]]
    if not summary["unlisted"]:
        lines.append("  none")
    return "\n".join(lines) + "\n"


def load_events(paths):
    """The JSON objects in the lines files, and how many lines were not JSON objects."""
    events, unreadable = [], 0
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    event = None
                if isinstance(event, dict):
                    events.append(event)
                else:
                    unreadable += 1
    return events, unreadable


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tables for the manual 7-day check.")
    parser.add_argument("lines", nargs="+", help="files written by eve_allowlist.py")
    parser.add_argument("--home-net", required=True, help="internal networks, comma separated, e.g. 10.0.0.0/8")
    parser.add_argument("--assets", help="asset list CSV with hostname, ip and owner columns")
    args = parser.parse_args(argv)

    events, unreadable = load_events(args.lines)
    assets = load_assets(args.assets) if args.assets else {}
    summary = summarise(events, parse_networks(args.home_net), assets)
    sys.stdout.write(render(summary, has_assets=bool(args.assets), unreadable_lines=unreadable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
