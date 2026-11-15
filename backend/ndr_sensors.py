"""Network sensor records and the one rule for whether a sensor is watching (88.1, stage 1).

A sensor is one passive Suricata box. Its record lives in ``ndr_sensors``: ``{tenantId, sensorId, name, homeNet,
tokenHash, createdAt, lastStatsAt, packets, drops, uptime, rulesLoaded, rulesFailed, forwarderDropped,
suricataVersion, silentSince, retiredAt}``. One sample of its cumulative counters per minute lives in
``ndr_sensor_stats``: ``{tenantId, sensorId, sampledAt, packets, drops, uptime}``. Nothing writes either
collection yet (ingest arrives with stage 3), so today every tenant reads as NO_SENSOR.

``sensor_health`` is the only place that decides a sensor's state, and ``day_coverage`` the only place that says
what kept a sensor from watching over the last 24 hours. The NDR summary route reads the first and the
``ids_ips_enabled`` compliance check the second, as will the silence notice and the report, so they cannot
disagree about the same sensor.

    no record ............................................. NO_SENSOR
    retiredAt set ......................................... REMOVED
    never sent stats ...................................... AWAITING_FIRST_REPORT
    last stats 5 minutes old or more ...................... SILENT
    stats fresh, but no packet growth or drops above 5% ... DEGRADED
    stats fresh, packets growing, drops at most 5% ........ LIVE

    precedence: REMOVED > SILENT > DEGRADED > LIVE

Freshness is judged by ``lastStatsAt`` (when the platform received the stats). Growth is judged on the samples'
own timeline: the window ends at the newest sample, so a sensor whose clock is off still reads correctly.

Suricata's counters are cumulative and restart from zero when Suricata restarts. ``window_deltas`` walks the
samples in time order and treats a sample whose ``packets`` or ``uptime`` is lower than the one before it as the
start of a new segment, counted from zero. A window holding a single sample shows no growth, so a sensor reads
DEGRADED for its first minute after it starts or resumes.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

NO_SENSOR = "no_sensor"
AWAITING_FIRST_REPORT = "awaiting_first_report"
LIVE = "live"
DEGRADED = "degraded"
SILENT = "silent"
REMOVED = "removed"

# Why a sensor is DEGRADED, or what kept it from watching for a day.
NO_PACKET_GROWTH = "no_packet_growth"
DROPPING_PACKETS = "dropping_packets"
NEVER_REPORTED = "never_reported"
NO_RECENT_STATS = "no_recent_stats"
NO_RULES_LOADED = "no_rules_loaded"

SILENT_AFTER = timedelta(minutes=5)
HEALTH_WINDOW = timedelta(minutes=5)
COVERAGE_WINDOW = timedelta(hours=24)
DROP_RATIO_LIMIT = 0.05

# One sample a minute: the newest samples that cover each window, whatever the sensor's own clock says.
HEALTH_SAMPLES = 6
COVERAGE_SAMPLES = 24 * 60 + 1
MAX_SENSORS = 100


def _utc(value: Any) -> Optional[datetime]:
    """A timezone-aware UTC datetime; a naive one is UTC, as MongoDB returns it. None for anything else."""
    if not isinstance(value, datetime):
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _count(record: Dict[str, Any], field: str) -> int:
    value = record.get(field)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def window_deltas(samples: Iterable[Dict[str, Any]], window: timedelta) -> Tuple[int, int]:
    """Packets and drops counted over the ``window`` that ends at the newest sample, as ``(packets, drops)``.

    ``samples`` may be in any order and may reach further back than the window. Samples without a ``sampledAt``
    are ignored.
    """
    points = sorted(((at, sample) for sample in samples if (at := _utc(sample.get("sampledAt")))),
                    key=lambda point: point[0])
    if not points:
        return 0, 0
    since = points[-1][0] - window
    packets = drops = 0
    previous: Optional[Dict[str, Any]] = None
    for at, sample in points:
        if at < since:
            continue
        if previous is not None:
            restarted = (_count(sample, "packets") < _count(previous, "packets")
                         or _count(sample, "uptime") < _count(previous, "uptime"))
            base = {} if restarted else previous
            packets += _count(sample, "packets") - _count(base, "packets")
            drops += _count(sample, "drops") - _count(base, "drops")
        previous = sample
    return packets, drops


def _health(state: str, last: Optional[datetime] = None, reason: Optional[str] = None,
            packets: int = 0, drop_ratio: Optional[float] = None) -> Dict[str, Any]:
    return {"state": state, "reason": reason, "lastStatsAt": last, "packets": packets, "dropRatio": drop_ratio}


def sensor_health(sensor: Optional[Dict[str, Any]], samples: Iterable[Dict[str, Any]],
                  now: datetime) -> Dict[str, Any]:
    """The state of one sensor at ``now``: ``{state, reason, lastStatsAt, packets, dropRatio}``.

    ``sensor`` is its ``ndr_sensors`` record, or None when the tenant has none. ``samples`` are its newest
    ``ndr_sensor_stats`` rows, enough to cover ``HEALTH_WINDOW``. ``reason`` is set only for DEGRADED;
    ``packets`` and ``dropRatio`` describe the health window and are only measured while stats are fresh.
    """
    if sensor is None:
        return _health(NO_SENSOR)
    last = _utc(sensor.get("lastStatsAt"))
    if sensor.get("retiredAt"):
        return _health(REMOVED, last)
    if last is None:
        return _health(AWAITING_FIRST_REPORT)
    if _utc(now) - last >= SILENT_AFTER:
        return _health(SILENT, last)
    packets, drops = window_deltas(samples, HEALTH_WINDOW)
    if not packets:
        return _health(DEGRADED, last, NO_PACKET_GROWTH)
    ratio = drops / packets
    if ratio > DROP_RATIO_LIMIT:
        return _health(DEGRADED, last, DROPPING_PACKETS, packets, ratio)
    return _health(LIVE, last, None, packets, ratio)


def _coverage(reason: Optional[str], packets: int = 0, drop_ratio: Optional[float] = None) -> Dict[str, Any]:
    return {"reason": reason, "packets": packets, "dropRatio": drop_ratio}


def day_coverage(sensor: Dict[str, Any], samples: Iterable[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """What, if anything, kept ``sensor`` from watching over the last 24 hours: ``{reason, packets, dropRatio}``.

    ``reason`` is None for a sensor that reported within 24 hours, has rules loaded, saw its packet count grow
    and dropped under 5% of those packets. Otherwise it is the first that applies of NEVER_REPORTED,
    NO_RECENT_STATS, NO_RULES_LOADED, NO_PACKET_GROWTH and DROPPING_PACKETS (5% or more, a stricter line than
    DEGRADED's "above 5%"). A retired sensor is the caller's to leave out.
    """
    last = _utc(sensor.get("lastStatsAt"))
    if last is None:
        return _coverage(NEVER_REPORTED)
    if _utc(now) - last >= COVERAGE_WINDOW:
        return _coverage(NO_RECENT_STATS)
    if _count(sensor, "rulesLoaded") <= 0:
        return _coverage(NO_RULES_LOADED)
    packets, drops = window_deltas(samples, COVERAGE_WINDOW)
    if not packets:
        return _coverage(NO_PACKET_GROWTH)
    ratio = drops / packets
    return _coverage(DROPPING_PACKETS if ratio >= DROP_RATIO_LIMIT else None, packets, ratio)


async def sensors_with_samples(db, samples: int) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Every sensor ``db`` lets the caller see (through the tenant-scoped database: the current tenant's), each
    with its newest ``samples`` stats samples. The token hash never leaves the database through here."""
    sensors = await db.ndr_sensors.find({}, {"_id": 0, "tokenHash": 0}).to_list(length=MAX_SENSORS)
    return [(sensor, await db.ndr_sensor_stats.find({"sensorId": sensor.get("sensorId")}, {"_id": 0})
             .sort("sampledAt", -1).to_list(length=samples)) for sensor in sensors]
