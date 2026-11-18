#!/bin/bash
# Changes the server's TLS certificate without cutting off agents, which trust only the
# certificates in their config.yaml (backend/agent_tls_trust.py has the agent side).
#
#   sudo scripts/tls_rollover.sh prepare    new certificate (self-signed, serverAuth, 825 days, not a CA:
#                                           macOS accepts it) + publish "current + new" to agents +
#                                           serve the new one on the probe port (8443) for agents to test
#   sudo scripts/tls_rollover.sh status     where the change stands (agent readiness: Platform health)
#   sudo scripts/tls_rollover.sh switch     nginx serves the new certificate (the old one is kept)
#   sudo scripts/tls_rollover.sh finish     agents stop trusting the old certificate; its key is deleted
#   sudo scripts/tls_rollover.sh rollback   undo the last step (switch -> prepared, prepared -> nothing)
#
# Switch only when Platform health shows every active agent ready. Agents outside this network reach the
# probe on port 8443, so that port must be open to them for their test to pass.
set -euo pipefail

TLS_DIR="${TLS_DIR:-/etc/omni/tls}"
NGINX_SSL_DIR="${NGINX_SSL_DIR:-/etc/nginx/ssl}"
NGINX_SITES="${NGINX_SITES:-/etc/nginx}"
NGINX="${NGINX:-nginx}"
RELOAD="${RELOAD:-systemctl reload nginx}"
PROBE_PORT="${PROBE_PORT:-8443}"
DAYS="${DAYS:-825}"
BACKEND="${BACKEND:-http://127.0.0.1:5000}"

CERT="$NGINX_SSL_DIR/omni.crt"
KEY="$NGINX_SSL_DIR/omni.key"
TRUST="$TLS_DIR/agent-trust.pem"
STATE="$TLS_DIR/rollover.json"
SITE="$NGINX_SITES/sites-available/omni-tls-probe"
SITE_LINK="$NGINX_SITES/sites-enabled/omni-tls-probe"

die() { echo "tls_rollover: $*" >&2; exit 1; }
fp() { openssl x509 -in "$1" -outform der | sha256sum | cut -c1-64; }
phase() { [ -f "$STATE" ] && sed -n 's/.*"phase": *"\([a-z]*\)".*/\1/p' "$STATE" || echo none; }
write_state() {  # phase next-fingerprint probe-port(or null)
    printf '{"phase": "%s", "next": ["%s"], "probePort": %s, "at": "%s"}\n' "$1" "$2" "$3" "$(date -u +%FT%TZ)" > "$STATE.tmp"
    chmod 644 "$STATE.tmp"
    mv "$STATE.tmp" "$STATE"
}
reload_nginx() { $NGINX -t >/dev/null 2>&1 || { $NGINX -t; return 1; }; $RELOAD; }

probe_site_on() {
    mkdir -p "$(dirname "$SITE")" "$(dirname "$SITE_LINK")"
    cat > "$SITE" <<EOF
# Written by scripts/tls_rollover.sh: the next certificate, for agents to test before the switch.
server {
    listen $PROBE_PORT ssl;
    ssl_certificate     $TLS_DIR/next.crt;
    ssl_certificate_key $TLS_DIR/next.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    location = /api/health { proxy_pass $BACKEND/api/health; }
    location / { return 404; }
}
EOF
    ln -sfn "$SITE" "$SITE_LINK"
}
probe_site_off() { rm -f "$SITE_LINK" "$SITE"; }

[ "$(id -u)" = 0 ] || [ -n "${TLS_ROLLOVER_SANDBOX:-}" ] || die "run it with sudo"
[ -f "$CERT" ] && [ -f "$KEY" ] || die "no certificate at $CERT"

case "${1:-status}" in
prepare)
    [ "$(phase)" = none ] || [ "$(phase)" = finished ] || die "a change is already $(phase); see status, or rollback"
    install -d -m 755 "$TLS_DIR"
    san="$(openssl x509 -in "$CERT" -noout -ext subjectAltName | tail -n +2 | sed 's/IP Address:/IP:/g; s/ //g')"
    cn="$(openssl x509 -in "$CERT" -noout -subject -nameopt multiline | sed -n 's/^ *commonName *= *//p')"
    [ -n "$san" ] || die "the current certificate has no subjectAltName to copy"
    umask 077
    openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days "$DAYS" -keyout "$TLS_DIR/next.key" -out "$TLS_DIR/next.crt" \
        -subj "/O=OmniAgent/CN=${cn:-omni-agent}" -addext "subjectAltName=$san" \
        -addext "basicConstraints=critical,CA:FALSE" -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
        -addext "extendedKeyUsage=serverAuth" 2>/dev/null
    umask 022
    chmod 644 "$TLS_DIR/next.crt"
    { cat "$CERT"; echo; cat "$TLS_DIR/next.crt"; } | sed '/^$/d' > "$TRUST"
    chmod 644 "$TRUST"
    probe_site_on
    if ! reload_nginx; then probe_site_off; rm -f "$TRUST"; die "nginx refused the probe site; nothing published"; fi
    write_state prepared "$(fp "$TLS_DIR/next.crt")" "$PROBE_PORT"
    echo "Prepared. Agents get the new certificate with their next heartbeat and test it on port $PROBE_PORT."
    echo "Next certificate: $(fp "$TLS_DIR/next.crt") ($(openssl x509 -in "$TLS_DIR/next.crt" -noout -enddate))"
    ;;
status)
    echo "phase:   $(phase)"
    echo "served:  $(fp "$CERT")  $(openssl x509 -in "$CERT" -noout -enddate)"
    [ -f "$TLS_DIR/next.crt" ] && echo "next:    $(fp "$TLS_DIR/next.crt")  $(openssl x509 -in "$TLS_DIR/next.crt" -noout -enddate)"
    [ -f "$TRUST" ] && echo "agents asked to trust: $(grep -c 'BEGIN CERTIFICATE' "$TRUST") certificate(s)"
    if [ -L "$SITE_LINK" ] && command -v curl >/dev/null; then
        code="$(curl -s -o /dev/null -w '%{http_code}' --cacert "$TLS_DIR/next.crt" "https://127.0.0.1:$PROBE_PORT/api/health" || true)"
        echo "probe on port $PROBE_PORT from this server: HTTP $code"
    fi
    echo "Agent readiness: Platform health > Certificate change."
    ;;
switch)
    [ "$(phase)" = prepared ] || die "switch needs a prepared change (phase: $(phase))"
    cp -p "$CERT" "$TLS_DIR/previous.crt"
    cp -p "$KEY" "$TLS_DIR/previous.key"
    chmod 600 "$TLS_DIR/previous.key"
    install -m 644 "$TLS_DIR/next.crt" "$CERT"
    install -m 600 "$TLS_DIR/next.key" "$KEY"
    probe_site_off
    if ! reload_nginx; then
        install -m 644 "$TLS_DIR/previous.crt" "$CERT"; install -m 600 "$TLS_DIR/previous.key" "$KEY"
        probe_site_on; reload_nginx || true
        die "nginx refused the new certificate; the old one is back"
    fi
    write_state switched "$(fp "$CERT")" null
    echo "Switched: nginx serves $(fp "$CERT"). Agents still trust the old certificate too; run finish once all report in."
    ;;
finish)
    [ "$(phase)" = switched ] || die "finish needs a switched change (phase: $(phase))"
    sed '/^$/d' "$CERT" > "$TRUST"
    chmod 644 "$TRUST"
    rm -f "$TLS_DIR/previous.key" "$TLS_DIR/next.key"
    write_state finished "$(fp "$CERT")" null
    echo "Finished: agents are asked to trust only $(fp "$CERT"). The old key is deleted."
    ;;
rollback)
    case "$(phase)" in
    switched)
        install -m 644 "$TLS_DIR/previous.crt" "$CERT"
        install -m 600 "$TLS_DIR/previous.key" "$KEY"
        probe_site_on
        reload_nginx || die "nginx refused the old certificate; check $CERT"
        write_state prepared "$(fp "$TLS_DIR/next.crt")" "$PROBE_PORT"
        echo "Rolled back to the old certificate; the change is prepared again."
        ;;
    prepared)
        probe_site_off
        reload_nginx || true
        rm -f "$TRUST" "$STATE" "$TLS_DIR/next.crt" "$TLS_DIR/next.key"
        echo "Change withdrawn. Agents that already took the list also trust the unused new certificate until the next change."
        ;;
    *) die "nothing to roll back (phase: $(phase))" ;;
    esac
    ;;
*) die "usage: tls_rollover.sh prepare|status|switch|finish|rollback" ;;
esac
