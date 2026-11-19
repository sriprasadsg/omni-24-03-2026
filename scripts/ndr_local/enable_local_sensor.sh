#!/usr/bin/env bash
# The platform server's own network sensor: Suricata watching this server's interface passively (no blocking),
# writing only alert and stats events to /var/log/suricata/eve.json, which backend/ndr_local.py reads.
#
#   scripts/ndr_local/enable_local_sensor.sh check          # no root: validates the config and loads the rules
#   sudo scripts/ndr_local/enable_local_sensor.sh apply     # installs, unmasks and starts Suricata, waits for stats
#   sudo scripts/ndr_local/enable_local_sensor.sh undo      # stops, masks and removes what apply installed
#   scripts/ndr_local/enable_local_sensor.sh status
#
# IFACE (default: the interface of the default route) and RULES (default /var/lib/suricata/rules/suricata.rules)
# can be set in the environment. Rules are ET Open as already pulled with suricata-update; refresh them with
# `sudo suricata-update && sudo suricatasc -c reload-rules`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$HERE/suricata-local.yaml"
INCLUDE=/etc/suricata/omni-local.yaml
DROPIN_DIR=/etc/systemd/system/suricata.service.d
DROPIN="$DROPIN_DIR/10-omni-local.conf"
EVE=/var/log/suricata/eve.json
RULES="${RULES:-/var/lib/suricata/rules/suricata.rules}"
IFACE="${IFACE:-$(ip -4 route show default | awk '{for (i = 1; i < NF; i++) if ($i == "dev") {print $(i + 1); exit}}')}"

die() { echo "ERROR: $*" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run '$1' with sudo"; }

# This interface's IPv4 network in CIDR form, e.g. 10.0.0.0/24 for 10.0.0.4/24.
home_net() {
    local cidr
    cidr="$(ip -4 -o addr show dev "$IFACE" | awk '{print $4; exit}')"
    [ -n "$cidr" ] || die "no IPv4 address on $IFACE"
    python3 -I -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$cidr"
}

# The include with this interface's network as HOME_NET, written to $1.
render() {
    local net
    net="$(home_net)"
    sed "s#HOME_NET: \"\[10.0.0.0/24\]\"#HOME_NET: \"[$net]\"#" "$TEMPLATE" > "$1"
    grep -q "HOME_NET: \"\[$net\]\"" "$1" || die "could not set HOME_NET in $1"
}

# Suricata prints "successfully loaded" even when an --include file is missing, so the dump is the proof.
verify() {
    local include="$1" dump net
    dump="$(suricata --dump-config -c /etc/suricata/suricata.yaml --include "$include" 2>/dev/null)"
    net="$(home_net)"
    grep -qx "vars.address-groups.HOME_NET = \[$net\]" <<<"$dump" || die "the include did not take effect (HOME_NET is not $net)"
    [ "$(grep -cE '^outputs\.[0-9]+\.[a-z-]+ = ' <<<"$dump")" -eq 1 ] || die "more than one output is enabled"
    grep -qx 'outputs.0.eve-log.types.0 = alert' <<<"$dump" && grep -qx 'outputs.0.eve-log.types.1 = stats' <<<"$dump" \
        && ! grep -q '^outputs.0.eve-log.types.2 ' <<<"$dump" || die "eve-log must write alert and stats only"
    [ -s "$RULES" ] || die "no rules at $RULES (run suricata-update)"
    echo "config: one eve-log output (alert, stats), HOME_NET [$net], interface $IFACE, rules $RULES"
}

check() (  # a subshell, so the temporary directory is removed on any exit
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    render "$tmp/omni-local.yaml"
    verify "$tmp/omni-local.yaml"
    echo "loading the rules (about a minute)..."
    suricata -T -c /etc/suricata/suricata.yaml --include "$tmp/omni-local.yaml" -S "$RULES" -l "$tmp" >"$tmp/test.out" 2>&1 \
        || { tail -5 "$tmp/test.out"; die "suricata -T failed"; }
    grep -E 'rules successfully loaded|Configuration provided' "$tmp/test.out" | tail -2
    echo "memory available: $(awk '/MemAvailable/ {printf "%d MB", $2 / 1024}' /proc/meminfo) (Suricata with ET Open uses about 1-1.5 GB)"
)

apply() {
    need_root apply
    check
    render "$INCLUDE"
    chmod 644 "$INCLUDE"
    mkdir -p "$DROPIN_DIR"
    cat > "$DROPIN" <<EOF
# Installed by scripts/ndr_local/enable_local_sensor.sh: passive IDS on $IFACE for the platform (backend/ndr_local.py).
[Service]
ExecStart=
ExecStart=/usr/bin/suricata -D --af-packet=$IFACE -c /etc/suricata/suricata.yaml --include $INCLUDE --pidfile /run/suricata.pid
Nice=10
CPUQuota=150%
MemoryMax=3G
EOF
    systemctl unmask suricata
    systemctl daemon-reload
    systemctl enable --now suricata
    echo "waiting for the first stats line in $EVE (up to 3 minutes; rules load first)..."
    for _ in $(seq 1 36); do
        if [ -s "$EVE" ] && grep -q '"event_type":"stats"' "$EVE"; then
            status
            echo "Suricata is watching $IFACE. The platform reads it within 30 seconds (Platform > NDR shows the sensor)."
            return 0
        fi
        sleep 5
    done
    systemctl --no-pager status suricata | tail -5
    die "no stats from Suricata yet; see /var/log/suricata/suricata.log, or run '$0 undo'"
}

undo() {
    need_root undo
    systemctl disable --now suricata 2>/dev/null || true
    rm -f "$DROPIN" "$INCLUDE"
    rmdir "$DROPIN_DIR" 2>/dev/null || true
    systemctl daemon-reload
    systemctl mask suricata
    echo "Suricata stopped and masked as before; $EVE is kept (logrotate ages it out)."
}

status() {
    echo "suricata: $(systemctl is-active suricata 2>/dev/null || true) ($(systemctl is-enabled suricata 2>/dev/null || true))"
    if [ -s "$EVE" ]; then
        local last
        last="$(grep '"event_type":"stats"' "$EVE" | tail -1 | python3 -I -c '
import json, sys
from datetime import datetime, timezone
line = sys.stdin.read().strip()
if line:
    e = json.loads(line); s = e["stats"]; eng = (s.get("detect") or {}).get("engines") or [{}]; cap = s.get("capture") or {}
    age = int((datetime.now(timezone.utc) - datetime.fromisoformat(e["timestamp"])).total_seconds())
    print("last stats", age, "s ago; rules", eng[-1].get("rules_loaded"), "packets", cap.get("kernel_packets"), "drops", cap.get("kernel_drops"))')"
        echo "${last:-no stats line yet}"
    else
        echo "no $EVE yet"
    fi
}

case "${1:-}" in
    check) check ;;
    apply) apply ;;
    undo) undo ;;
    status) status ;;
    *) die "usage: $0 check|apply|undo|status" ;;
esac
