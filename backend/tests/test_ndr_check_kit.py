"""The manual 7-day check kit under scripts/ndr_check (88.1, stage 2).

eve_allowlist.py must let nothing but the allowlisted fields out of the sensor box. check_tables.py must put
each alert in exactly one list and count rows, devices and sensor health the way the design says.
"""
import gzip
import importlib.util
import io
import ipaddress
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

KIT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "ndr_check"))


def _load(name):
    spec = importlib.util.spec_from_file_location("ndr_check_" + name, os.path.join(KIT_DIR, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


allowlist = _load("eve_allowlist")
tables = _load("check_tables")

NETS = [ipaddress.ip_network("10.0.1.0/24")]
ASSETS = {ipaddress.ip_address("10.0.1.10"): {"hostname": "pc-10", "owner": "Asha"}}
START = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)

RAW_ALERT = {
    "timestamp": "2026-11-07T09:00:00.000001+0000", "flow_id": 123, "in_iface": "eth1", "event_type": "alert",
    "src_ip": "10.0.1.50", "src_port": 51000, "dest_ip": "10.0.1.10", "dest_port": 445, "proto": "TCP",
    "app_proto": "smb", "community_id": "1:abc", "host": "sensor-1", "pcap_cnt": 7,
    "alert": {"action": "allowed", "gid": 1, "signature_id": 2001569, "rev": 15,
              "signature": "ET SCAN Behavioral Unusual Port 445 traffic", "category": "Misc activity",
              "severity": 3, "metadata": {"created_at": ["2010_07_30"]}, "rule": "alert tcp ..."},
    "payload": "c2VjcmV0", "payload_printable": "secret", "packet": "AAAA", "stream": 0,
    "http": {"hostname": "intranet", "url": "/login"}, "dns": {"query": [{"rrname": "example.org"}]},
    "tls": {"sni": "mail.example.org"}, "flow": {"pkts_toserver": 3}, "ether": {"src_mac": "00:11:22:33:44:55"},
}
RAW_STATS = {
    "timestamp": "2026-11-07T09:00:08.000000+0000", "event_type": "stats",
    "stats": {"uptime": 8,
              "capture": {"kernel_packets": 900, "kernel_drops": 3, "errors": 0},
              "decoder": {"pkts": 897, "bytes": 123456, "ipv4": 800},
              "flow": {"tcp": 12},
              "detect": {"engines": [{"id": 0, "last_reload": "2026-11-07T08:59:00+0000", "rules_loaded": 48211,
                                      "rules_failed": 2}], "alert": 5},
              "app_layer": {"flow": {"http": 4}}},
}


def _alert(src, dest, at=START, signature="ET SCAN Nmap probe", severity=2, category="Attempted Information Leak",
           signature_id=2000001, **fields):
    return {"event_type": "alert", "timestamp": at.strftime("%Y-%m-%dT%H:%M:%S.%f%z"), "src_ip": src,
            "dest_ip": dest, "alert": {"signature_id": signature_id, "signature": signature, "severity": severity,
                                       "category": category}, **fields}


def _stats(at, packets, uptime, drops=0):
    return {"event_type": "stats", "timestamp": at.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
            "stats": {"uptime": uptime, "capture": {"kernel_packets": packets, "kernel_drops": drops},
                      "detect": {"engines": [{"rules_loaded": 100, "rules_failed": 1}]}}}


# --- eve_allowlist.py ---------------------------------------------------------------------------------------

def test_an_alert_keeps_only_the_allowlisted_fields():
    assert allowlist.allow(RAW_ALERT) == {
        "event_type": "alert", "timestamp": "2026-11-07T09:00:00.000001+0000", "flow_id": 123,
        "src_ip": "10.0.1.50", "src_port": 51000, "dest_ip": "10.0.1.10", "dest_port": 445, "proto": "TCP",
        "app_proto": "smb",
        "alert": {"signature_id": 2001569, "rev": 15, "signature": "ET SCAN Behavioral Unusual Port 445 traffic",
                  "category": "Misc activity", "severity": 3, "action": "allowed"},
    }


def test_a_stats_event_keeps_only_the_allowlisted_counters():
    assert allowlist.allow(RAW_STATS) == {
        "event_type": "stats", "timestamp": "2026-11-07T09:00:08.000000+0000",
        "stats": {"uptime": 8, "capture": {"kernel_packets": 900, "kernel_drops": 3}, "decoder": {"pkts": 897},
                  "detect": {"engines": [{"rules_loaded": 48211, "rules_failed": 2}]}},
    }


@pytest.mark.parametrize("event_type", ["dns", "tls", "http", "flow", "fileinfo", "anomaly", None])
def test_every_other_event_type_is_dropped(event_type):
    assert allowlist.allow({"event_type": event_type, "src_ip": "10.0.1.50", "dns": {"rrname": "x"}}) is None


def test_a_listed_field_holding_an_object_is_dropped():
    event = {"event_type": "alert", "src_ip": {"smuggled": "payload"}, "alert": {"signature": ["a", "b"]}}

    assert allowlist.allow(event) == {"event_type": "alert", "alert": {}}


def test_a_half_written_line_is_counted_and_the_rest_still_filtered():
    lines = [json.dumps(RAW_ALERT), '{"event_type": "alert", "src_ip": "10.0.', json.dumps({"event_type": "dns"}),
             "", json.dumps(RAW_STATS)]
    out, counts = io.StringIO(), Counter()

    allowlist.filter_lines(lines, out, counts)

    kept = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [event["event_type"] for event in kept] == ["alert", "stats"]
    assert dict(counts) == {"read": 4, "alert": 1, "stats": 1, "skipped": 1, "unreadable": 1}


def test_rotated_gz_files_are_read_and_the_output_is_owner_only(tmp_path):
    plain, rotated, output = tmp_path / "eve.json", tmp_path / "eve.json.1.gz", tmp_path / "lines.jsonl"
    plain.write_text(json.dumps(RAW_ALERT) + "\n")
    with gzip.open(rotated, "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(RAW_STATS) + "\n")

    assert allowlist.main([str(rotated), str(plain), "-o", str(output)]) == 0

    assert [json.loads(line)["event_type"] for line in output.read_text().splitlines()] == ["stats", "alert"]
    assert "secret" not in output.read_text() and "intranet" not in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600


# --- check_tables.py ----------------------------------------------------------------------------------------

STREAM = "SURICATA STREAM excessive retransmissions"


@pytest.mark.parametrize("alert, expected", [
    (_alert("10.0.1.50", "10.0.1.10", severity=3, signature=STREAM), tables.SUPPRESSED),
    (_alert("10.0.1.50", "10.0.1.10", severity=4, signature=STREAM), tables.SUPPRESSED),
    (_alert("10.0.1.50", "10.0.1.10", severity=3, signature="ET SCAN Behavioral Unusual Port 445 traffic"),
     tables.UNKNOWN),
    (_alert("10.0.1.50", "10.0.1.10", severity=3, signature="GPL SCAN nmap XMAS"), tables.UNKNOWN),
    (_alert("10.0.1.50", "10.0.1.10", severity=1, signature="ET INFO Something seen"), tables.SUPPRESSED),
    (_alert("10.0.1.50", "10.0.1.10", severity=1, signature="ET POLICY Something seen"), tables.SUPPRESSED),
    (_alert("10.0.1.50", "10.0.1.10", severity=1, category="Not Suspicious Traffic"), tables.SUPPRESSED),
    (_alert("10.0.1.50", "8.8.8.8"), tables.UNKNOWN),
    (_alert("10.0.1.10", "10.0.1.50"), tables.UNKNOWN),
    (_alert("10.0.1.10", "8.8.8.8"), tables.YOURS),
    (_alert("8.8.8.8", "1.1.1.1"), tables.OUTSIDE),
    (_alert("10.0.1.10", "10.0.1.255"), tables.YOURS),
    (_alert("8.8.8.8", "10.0.1.0"), tables.OUTSIDE),
    (_alert("10.0.1.255", "10.0.1.50"), tables.UNKNOWN),
])
def test_each_alert_lands_in_the_one_list_the_rules_give(alert, expected):
    assert tables.assign_list(alert, NETS, ASSETS) == expected


@pytest.mark.parametrize("cidr, address", [("10.0.2.0/31", "10.0.2.0"), ("10.0.2.1/32", "10.0.2.1")])
def test_a_31_or_32_network_has_no_non_device_addresses(cidr, address):
    assert tables.endpoint_kind(address, [ipaddress.ip_network(cidr, strict=False)], {}) == "unknown"


def test_without_an_asset_list_every_internal_address_is_unlisted():
    assert tables.assign_list(_alert("10.0.1.10", "8.8.8.8"), NETS, {}) == tables.UNKNOWN


def test_a_group_takes_alerts_for_24_hours_then_a_new_one_starts():
    def at(offset):
        return (START + offset, _alert("10.0.1.50", "10.0.1.10", START + offset))

    assert tables.count_groups([at(timedelta(0)), at(timedelta(hours=24))]) == 1
    assert tables.count_groups([at(timedelta(0)), at(timedelta(hours=24, seconds=1))]) == 2


def test_one_host_sweeping_twenty_addresses_is_one_device_and_one_row_per_signature():
    sweep = [_alert("10.0.1.50", "10.0.1.%d" % host, START + timedelta(seconds=host)) for host in range(100, 120)]

    unknown = tables.summarise(sweep, NETS, ASSETS)["lists"][tables.UNKNOWN]

    assert (unknown["alerts"], unknown["groups"], unknown["deviceGroups"]) == (20, 20, 1)
    assert (unknown["devices"], unknown["targetsOnly"], unknown["sources"]) == (1, 20, 1)


def test_only_a_source_or_an_application_layer_tcp_destination_counts_as_a_device():
    events = [
        _alert("8.8.8.8", "10.0.1.60", proto="TCP", app_proto="http"),
        _alert("8.8.8.8", "10.0.1.61", proto="UDP", app_proto="snmp"),
        _alert("8.8.8.8", "10.0.1.62", proto="TCP"),
        _alert("10.0.1.63", "8.8.8.8", proto="UDP"),
    ]

    summary = tables.summarise(events, NETS, ASSETS)

    unknown = summary["lists"][tables.UNKNOWN]
    assert (unknown["alerts"], unknown["devices"], unknown["targetsOnly"]) == (4, 2, 2)
    assert {row["address"]: row["device"] for row in summary["unlisted"]} == {
        "10.0.1.60": True, "10.0.1.61": False, "10.0.1.62": False, "10.0.1.63": True}


def test_a_device_row_is_keyed_on_the_internal_end_source_first():
    assert tables.device_key(_alert("10.0.1.50", "10.0.1.10"), NETS) == (2000001, "10.0.1.50")
    assert tables.device_key(_alert("8.8.8.8", "10.0.1.10"), NETS) == (2000001, "10.0.1.10")


def test_the_targets_section_shows_twenty_and_counts_the_rest():
    sweep = [_alert("10.0.1.50", "10.0.1.%d" % host, START + timedelta(seconds=host)) for host in range(100, 130)]

    text = tables.render(tables.summarise(sweep, NETS, ASSETS))

    devices_part, targets_part = text.split("ADDRESSES ONLY SEEN AS TARGETS")
    assert "devices: 1 (1 seen as a source), plus 30 addresses only seen as targets" in devices_part
    assert "\n  10.0.1.50 " in devices_part.split("UNLISTED DEVICES")[1]
    assert "30 addresses, the 20 with the most alerts:" in targets_part
    assert sum(line.startswith("  10.0.1.1") for line in targets_part.splitlines()) == 20


def test_the_summary_counts_lists_classes_and_unlisted_addresses():
    events = [
        _alert("10.0.1.50", "10.0.1.10"),
        _alert("10.0.1.50", "10.0.1.10", START + timedelta(minutes=1), signature=STREAM,
               severity=3, category="Generic Protocol Command Decode", signature_id=2210054),
        _alert("10.0.1.10", "8.8.8.8", START + timedelta(minutes=2)),
        {"event_type": "alert", "timestamp": "not a time", "src_ip": "10.0.1.50", "dest_ip": "10.0.1.10"},
    ]

    summary = tables.summarise(events, NETS, ASSETS)

    assert {name: row["alerts"] for name, row in summary["lists"].items()} == {
        tables.UNKNOWN: 1, tables.YOURS: 1, tables.OUTSIDE: 0, tables.SUPPRESSED: 1}
    assert (summary["shown"], summary["internalOnly"], summary["unreadable"]) == (2, 1, 1)
    assert ("Generic Protocol Command Decode", 3, 1, 1) in summary["classes"]
    assert ("ET SCAN", 2, 0) in summary["prefixes"] and ("SURICATA STREAM", 1, 1) in summary["prefixes"]
    assert [(row["address"], row["shown"], row["hidden"], row["asSource"], row["signatures"], row["peers"])
            for row in summary["unlisted"]] == [("10.0.1.50", 1, 1, 2, 2, 1)]


def test_sensor_totals_count_from_suricatas_start_and_across_a_restart():
    stats = [_stats(START, 100, 10), _stats(START + timedelta(minutes=1), 300, 70, drops=6),
             _stats(START + timedelta(days=1), 50, 5), _stats(START + timedelta(days=1, minutes=1), 80, 65, drops=1)]

    health = tables.summarise(stats, NETS, ASSETS)["health"]

    assert health == {"events": 4, "days": 2, "packets": 300 + 80, "drops": 6 + 1, "rulesLoaded": 100,
                      "rulesFailed": 1}


def test_a_capture_replay_without_a_capture_section_uses_the_decoder_count():
    event = {"event_type": "stats", "timestamp": "2026-11-07T09:00:00.000000+0000",
             "stats": {"uptime": 3, "decoder": {"pkts": 4200}}}

    assert tables.summarise([event], NETS, ASSETS)["health"]["packets"] == 4200


def test_the_asset_list_prefers_the_row_that_names_an_owner(tmp_path):
    path = tmp_path / "assets.csv"
    path.write_text("Hostname,IP_Address,Owner\npc-10,10.0.1.10,\npc-10b,10.0.1.10,Asha\nbad,not-an-ip,Bo\n")

    assert tables.load_assets(str(path)) == {ipaddress.ip_address("10.0.1.10"): {"hostname": "pc-10b",
                                                                                 "owner": "Asha"}}


def test_an_empty_period_renders_without_numbers_to_divide():
    text = tables.render(tables.summarise([], NETS, {}), has_assets=False)

    assert "no readable events" in text
    assert "no alerts in the period" in text
    assert "every internal address counts as unlisted" in text


# --- enable.conf --------------------------------------------------------------------------------------------

def test_enable_conf_lists_the_sids_its_header_promises():
    with open(os.path.join(KIT_DIR, "enable.conf"), encoding="utf-8") as handle:
        lines = [line.strip() for line in handle]
    sids = [line for line in lines if line and not line.startswith("#")]
    promised = next(line for line in lines if 'say "Enabled ' in line)

    assert all(sid.isdigit() for sid in sids) and len(set(sids)) == len(sids)
    assert 'say "Enabled %d rules"' % len(sids) in promised
    assert {"2009582", "2001569"} <= set(sids)
    assert not {"2002911", "2001329"} & set(sids)
