#!/usr/bin/env bash
# Open-source services beside the platform, for the setup checklist's test items:
#   mailpit   - catches every email the platform sends: SMTP localhost:1025 (STARTTLS), web UI 127.0.0.1:8025
#   authentik - identity provider (SCIM pushes to Omni-Agent, events as a log source): http://127.0.0.1:9000
#   fleet     - device management on osquery, with this server enrolled through osquery: https://localhost:8412
#
#   sudo scripts/oss/oss.sh apply mailpit|authentik|fleet
#   sudo scripts/oss/oss.sh undo mailpit|authentik|fleet    # stops and removes it; its data stays unless PURGE=1
#   sudo scripts/oss/oss.sh wire authentik                  # test group and users, log-reader token, SCIM provider
#   sudo scripts/oss/oss.sh scim-token                      # paste the platform's SCIM token (not echoed); goes live
#   scripts/oss/oss.sh status
#
# Everything listens on loopback only (see `ss -ltn`). Passwords and tokens are generated into
# /opt/omni-oss/<service>/ (root, 0600) and never printed. Each apply adds the service's origin, with its pinned
# certificate, to OMNI_SELF_HOSTED in /etc/omni/self-hosted.env, which the backend reads through a systemd drop-in
# (backend/self_hosted.py); restart omni-backend afterwards so organizations may point their integrations at it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPT=/opt/omni-oss
PUB=/etc/omni/oss                      # public certificates the backend pins
ENVFILE=/etc/omni/self-hosted.env
DROPIN=/etc/systemd/system/omni-backend.service.d/20-self-hosted.conf
MAILPIT_VERSION=v1.33.0
MAILPIT_SHA256=d0ec50080cbf3e7c1fa2cda2ee68125d7894175811084b1f8f47c6cfc6f487c8   # mailpit-linux-amd64.tar.gz
OSQUERY_KEY_FPR=1484120AC4E9F8A1A577AEEE97A80C63C9D8B80B                          # pkg.osquery.io signing key

die() { echo "ERROR: $*" >&2; exit 1; }
need_root() { [ "$(id -u)" -eq 0 ] || die "run '$1' with sudo"; }
secret() { openssl rand -base64 64 | tr -dc 'A-Za-z0-9' | head -c "${1:-40}"; }
purged() { [ "${PURGE:-0}" = 1 ] && echo "$1" || true; }

# A self-signed certificate for localhost that cannot sign others (CA:FALSE): $1 = name, $2 = key owner.
self_cert() {
    local name="$1" owner="$2"
    install -d -m 755 "$PUB"
    [ -s "$PUB/$name.crt" ] && [ -s "$PUB/$name.key" ] && return 0
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 1825 -subj "/O=Omni-Agent OSS/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" -addext "basicConstraints=critical,CA:FALSE" \
        -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=serverAuth" \
        -keyout "$PUB/$name.key" -out "$PUB/$name.crt" 2>/dev/null
    chown "$owner" "$PUB/$name.key"; chmod 600 "$PUB/$name.key"; chmod 644 "$PUB/$name.crt"
}

# Add ($1 = add) or remove ($1 = remove) origin $2 (with optional pinned certificate $3) in OMNI_SELF_HOSTED.
origin() {
    install -d -m 755 /etc/omni
    [ -f "$ENVFILE" ] || install -m 600 /dev/null "$ENVFILE"
    python3 -I - "$ENVFILE" "$@" <<'PY'
import sys
path, op, origin = sys.argv[1], sys.argv[2], sys.argv[3]
entry = origin + ("|" + sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "")
lines = open(path).read().splitlines()
items = next((l.split("=", 1)[1].split(",") for l in lines if l.startswith("OMNI_SELF_HOSTED=")), [])
items = [i for i in items if i and i.split("|")[0] != origin] + ([entry] if op == "add" else [])
with open(path, "w") as f:
    f.write("# Written by scripts/oss/oss.sh: origins of self-hosted open-source services the backend may call.\n")
    f.write("OMNI_SELF_HOSTED=" + ",".join(items) + "\n")
PY
    if [ ! -f "$DROPIN" ]; then
        install -d "$(dirname "$DROPIN")"
        printf '[Service]\nEnvironmentFile=-%s\n' "$ENVFILE" > "$DROPIN"
        systemctl daemon-reload
    fi
    echo "OMNI_SELF_HOSTED now: $(sed -n 's/^OMNI_SELF_HOSTED=//p' "$ENVFILE")  (restart omni-backend to apply)"
}

wait_for() {  # $1 = description, then a command that succeeds once ready; up to 5 minutes
    local what="$1"; shift
    for _ in $(seq 1 60); do "$@" >/dev/null 2>&1 && { echo "$what is up"; return 0; }; sleep 5; done
    die "$what did not come up; see the service's logs"
}

# ---------------------------------------------------------------------------------------------------- mailpit

mailpit_apply() {
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL -o "$tmp/mailpit.tgz" "https://github.com/axllent/mailpit/releases/download/$MAILPIT_VERSION/mailpit-linux-amd64.tar.gz"
    echo "$MAILPIT_SHA256  $tmp/mailpit.tgz" | sha256sum -c --quiet - || die "mailpit download does not match its published digest"
    tar -xzf "$tmp/mailpit.tgz" -C "$tmp" mailpit
    install -m 755 "$tmp/mailpit" /usr/local/bin/mailpit
    rm -rf "$tmp"
    id mailpit >/dev/null 2>&1 || useradd --system --home-dir /var/lib/mailpit --shell /usr/sbin/nologin mailpit
    install -d -o mailpit -g mailpit -m 700 /var/lib/mailpit
    self_cert mailpit mailpit
    cat > /etc/systemd/system/mailpit.service <<EOF
# Installed by scripts/oss/oss.sh: catches the platform's email for testing (nothing is delivered onward).
[Unit]
Description=Mailpit test mail catcher for Omni-Agent
After=network.target

[Service]
User=mailpit
ExecStart=/usr/local/bin/mailpit --listen 127.0.0.1:8025 --smtp 127.0.0.1:1025 --smtp-tls-cert $PUB/mailpit.crt --smtp-tls-key $PUB/mailpit.key --smtp-require-starttls --smtp-auth-accept-any --database /var/lib/mailpit/mailpit.db --disable-version-check
Restart=on-failure
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/mailpit
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable --now mailpit
    wait_for "Mailpit" curl -fsS http://127.0.0.1:8025/livez
    origin add smtp://localhost:1025 "$PUB/mailpit.crt"
    echo "Mail settings for the platform: host localhost, port 1025, TLS on, any user name and password."
    echo "Read the mail: ssh -L 8025:127.0.0.1:8025 <this server>, then open http://localhost:8025"
}

mailpit_undo() {
    systemctl disable --now mailpit 2>/dev/null || true
    rm -f /etc/systemd/system/mailpit.service /usr/local/bin/mailpit
    systemctl daemon-reload
    origin remove smtp://localhost:1025
    [ "${PURGE:-0}" = 1 ] && rm -rf /var/lib/mailpit "$PUB/mailpit.crt" "$PUB/mailpit.key"
    echo "Mailpit removed$(purged ' with its mail')."
}

# ---------------------------------------------------------------------------------------------------- authentik

compose() { docker compose --project-directory "$OPT/$1" -f "$OPT/$1/compose.yml" "${@:2}"; }

authentik_apply() {
    command -v docker >/dev/null || die "Docker is not installed (apt-get install docker.io docker-compose-v2)"
    install -d -m 700 "$OPT/authentik"
    install -d -m 755 "$OPT/authentik/data" "$OPT/authentik/certs" "$OPT/authentik/custom-templates" "$OPT/authentik/omni"
    install -m 644 "$HERE/authentik/compose.yml" "$OPT/authentik/compose.yml"
    # trust the platform's own certificate (SCIM goes to https://10.0.0.4) on top of the public CAs
    cat /etc/ssl/certs/ca-certificates.crt /etc/nginx/ssl/omni.crt > "$OPT/authentik/omni/ca-bundle.pem"
    if [ ! -s "$OPT/authentik/.env" ]; then
        umask 077
        { echo "PG_PASS=$(secret 40)"; echo "AUTHENTIK_SECRET_KEY=$(secret 60)"
          echo "AUTHENTIK_BOOTSTRAP_EMAIL=akadmin@omni.local"; echo "AUTHENTIK_BOOTSTRAP_PASSWORD=$(secret 24)"
          echo "AUTHENTIK_BOOTSTRAP_TOKEN=$(secret 60)"; } > "$OPT/authentik/.env"
        umask 022
    fi
    chmod 600 "$OPT/authentik/.env"
    compose authentik pull -q
    compose authentik up -d
    wait_for "authentik" curl -fsS http://127.0.0.1:9000/-/health/ready/
    origin add http://127.0.0.1:9000
    echo "authentik admin: akadmin, password AUTHENTIK_BOOTSTRAP_PASSWORD in $OPT/authentik/.env (sudo to read)."
    echo "Admin UI: ssh -L 9000:127.0.0.1:9000 <this server>, then open http://localhost:9000/if/admin/"
}

authentik_undo() {
    [ -f "$OPT/authentik/compose.yml" ] && compose authentik down $([ "${PURGE:-0}" = 1 ] && echo -v) || true
    origin remove http://127.0.0.1:9000
    [ "${PURGE:-0}" = 1 ] && rm -rf "$OPT/authentik"
    echo "authentik stopped$(purged ' and its data deleted')."
}

# ---------------------------------------------------------------------------------------------------- fleet

fleet_api() {  # $1 method, $2 path, $3 JSON body (optional, sent on stdin so no password is in argv); uses $FLEET_TOKEN
    printf '%s' "${3:-}" | curl -fsS --cacert "$PUB/fleet.crt" -X "$1" "https://localhost:8412$2" -H 'Content-Type: application/json' \
        ${FLEET_TOKEN:+-H "Authorization: Bearer $FLEET_TOKEN"} ${3:+--data-binary @-}
}

fleet_apply() {
    command -v docker >/dev/null || die "Docker is not installed (apt-get install docker.io docker-compose-v2)"
    local dir="$OPT/fleet"
    install -d -m 700 "$dir"; install -d -m 755 "$dir/certs"
    install -m 644 "$HERE/fleet/compose.yml" "$dir/compose.yml"
    self_cert fleet root
    install -m 644 "$PUB/fleet.crt" "$dir/certs/fleet.crt"
    install -m 644 "$PUB/fleet.key" "$dir/certs/fleet.key"   # readable inside the container; $dir itself is root-only
    if [ ! -s "$dir/.env" ]; then
        umask 077
        { echo "MYSQL_ROOT_PASSWORD=$(secret 40)"; echo "MYSQL_PASSWORD=$(secret 40)"
          echo "FLEET_ADMIN_PASSWORD=$(secret 20)Aa1!"; echo "FLEET_API_PASSWORD=$(secret 20)Aa1!"
          echo "FLEET_ENROLL_SECRET=$(secret 40)"; } > "$dir/.env"
        umask 022
    fi
    chmod 600 "$dir/.env"
    compose fleet pull -q
    compose fleet up -d
    wait_for "Fleet" curl -fsS --cacert "$PUB/fleet.crt" https://localhost:8412/healthz
    # shellcheck disable=SC1091
    set -a; . "$dir/.env"; set +a
    local login="{\"email\":\"admin@omni.local\",\"password\":\"$FLEET_ADMIN_PASSWORD\"}" answer
    if ! answer="$(fleet_api POST /api/v1/fleet/login "$login")"; then   # first run: Fleet has no admin yet
        fleet_api POST /api/v1/setup "{\"admin\":{\"admin\":true,\"email\":\"admin@omni.local\",\"name\":\"Omni Admin\",\"password\":\"$FLEET_ADMIN_PASSWORD\"},\"org_info\":{\"org_name\":\"Omni-Agent\"},\"server_url\":\"https://localhost:8412\"}" >/dev/null
        answer="$(fleet_api POST /api/v1/fleet/login "$login")"
    fi
    FLEET_TOKEN="$(python3 -I -c 'import json,sys; print(json.load(sys.stdin)["token"])' <<<"$answer")"
    fleet_api POST /api/v1/fleet/spec/enroll_secret "{\"spec\":{\"secrets\":[{\"secret\":\"$FLEET_ENROLL_SECRET\"}]}}" >/dev/null
    if ! fleet_api GET /api/v1/fleet/users | grep -q 'omni-connector@omni.local'; then   # the platform's read/refetch user
        fleet_api POST /api/v1/fleet/users/admin "{\"name\":\"Omni-Agent connector\",\"email\":\"omni-connector@omni.local\",\"password\":\"$FLEET_API_PASSWORD\",\"global_role\":\"maintainer\",\"api_only\":true}" >/dev/null
    fi
    # a user an admin creates must reset its password before it may call the API; an API-only user never signs in
    local uid
    uid="$(fleet_api GET /api/v1/fleet/users | python3 -I -c 'import json,sys; print(next(u["id"] for u in json.load(sys.stdin)["users"] if u["email"] == "omni-connector@omni.local"))')"
    fleet_api POST "/api/v1/fleet/users/$uid/require_password_reset" '{"require":false}' >/dev/null
    FLEET_TOKEN="" fleet_api POST /api/v1/fleet/login "{\"email\":\"omni-connector@omni.local\",\"password\":\"$FLEET_API_PASSWORD\"}" \
        | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["token"])' > "$dir/connector-token"
    chmod 600 "$dir/connector-token"
    osquery_enroll "$FLEET_ENROLL_SECRET"
    origin add https://localhost:8412 "$PUB/fleet.crt"
    echo "Fleet connector token for the platform: $dir/connector-token (sudo to read). Address: https://localhost:8412"
    echo "Fleet UI: ssh -L 8412:127.0.0.1:8412 <this server>, then https://localhost:8412 (admin@omni.local, FLEET_ADMIN_PASSWORD in $dir/.env)"
}

# osquery (Apache-2.0/GPL-2.0) from osquery's own signed apt repository, enrolled to the local Fleet.
osquery_enroll() {
    if ! command -v osqueryd >/dev/null; then
        local key=/usr/share/keyrings/osquery.gpg tmp
        tmp="$(mktemp -d)"
        curl -fsSL https://pkg.osquery.io/deb/pubkey.gpg -o "$tmp/key.asc"
        gpg --batch --no-default-keyring --keyring "$tmp/k.gpg" --import "$tmp/key.asc" 2>/dev/null
        gpg --batch --no-default-keyring --keyring "$tmp/k.gpg" --list-keys --with-colons | grep -q "^fpr:::::::::$OSQUERY_KEY_FPR:" \
            || die "osquery's signing key does not have the expected fingerprint"
        gpg --batch --no-default-keyring --keyring "$tmp/k.gpg" --export > "$key"; rm -rf "$tmp"
        echo "deb [arch=amd64 signed-by=$key] https://pkg.osquery.io/deb deb main" > /etc/apt/sources.list.d/osquery.list
        apt-get update -q -o Dir::Etc::sourcelist=sources.list.d/osquery.list -o Dir::Etc::sourceparts=- >/dev/null
        DEBIAN_FRONTEND=noninteractive apt-get install -y -q osquery >/dev/null
    fi
    install -m 600 /dev/null /etc/osquery/enroll_secret; printf '%s' "$1" > /etc/osquery/enroll_secret
    cat > /etc/osquery/osquery.flags <<EOF
--tls_hostname=localhost:8412
--tls_server_certs=$PUB/fleet.crt
--enroll_secret_path=/etc/osquery/enroll_secret
--host_identifier=uuid
--enroll_tls_endpoint=/api/osquery/enroll
--config_plugin=tls
--config_tls_endpoint=/api/v1/osquery/config
--config_refresh=60
--logger_plugin=tls
--logger_tls_endpoint=/api/v1/osquery/log
--disable_distributed=false
--distributed_plugin=tls
--distributed_interval=60
--distributed_tls_read_endpoint=/api/v1/osquery/distributed/read
--distributed_tls_write_endpoint=/api/v1/osquery/distributed/write
--watchdog_level=0
--watchdog_memory_limit=250
--watchdog_utilization_limit=20
EOF
    systemctl enable osqueryd >/dev/null 2>&1; systemctl restart osqueryd
    echo "osqueryd: $(systemctl is-active osqueryd), enrolling to https://localhost:8412"
}

fleet_undo() {
    systemctl disable --now osqueryd 2>/dev/null || true
    [ -f "$OPT/fleet/compose.yml" ] && compose fleet down $([ "${PURGE:-0}" = 1 ] && echo -v) || true
    origin remove https://localhost:8412
    if [ "${PURGE:-0}" = 1 ]; then
        DEBIAN_FRONTEND=noninteractive apt-get remove -y -q osquery >/dev/null 2>&1 || true
        rm -rf "$OPT/fleet" /etc/apt/sources.list.d/osquery.list /usr/share/keyrings/osquery.gpg "$PUB/fleet.crt" "$PUB/fleet.key"
    fi
    echo "Fleet and osqueryd stopped$(purged ', data and osquery removed')."
}

# ---------------------------------------------------------------------------------------------------- status

status() {
    local docker=(docker); [ "$(id -u)" -eq 0 ] || docker=(sudo -n docker)
    printf '%-10s %s\n' mailpit "$(systemctl is-active mailpit 2>/dev/null || true)"
    for s in authentik fleet; do
        if [ -f "$OPT/$s/compose.yml" ] && command -v docker >/dev/null; then
            printf '%-10s %s\n' "$s" "$("${docker[@]}" compose --project-directory "$OPT/$s" -f "$OPT/$s/compose.yml" ps --format '{{.Service}}={{.State}}' 2>/dev/null | tr '\n' ' ')"
        else
            printf '%-10s %s\n' "$s" "not installed"
        fi
    done
    printf '%-10s %s\n' osqueryd "$(systemctl is-active osqueryd 2>/dev/null || true)"
    echo "listening: $(ss -ltn | awk 'NR > 1 {print $4}' | grep -E ':(1025|8025|9000|9443|8412)$' | sort -u | tr '\n' ' ')"
    [ -r "$ENVFILE" ] && echo "self-hosted origins: $(sed -n 's/^OMNI_SELF_HOSTED=//p' "$ENVFILE")" || echo "self-hosted origins: (sudo to read $ENVFILE)"
}

authentik_wire() {
    [ -f "$OPT/authentik/compose.yml" ] || die "apply authentik first"
    python3 -I "$HERE/authentik_setup.py" "${SCIM_URL:-https://10.0.0.4/api/scim/v2}"
}

scim_token() {  # the platform's SCIM token (Settings > SSO > SCIM) for authentik's provider; read without echo
    local token
    read -rsp "Paste the Omni-Agent SCIM token (omni_scim_...): " token; echo
    [[ "$token" =~ ^omni_scim_[A-Za-z0-9_-]{20,}$ ]] || die "that is not an Omni-Agent SCIM token"
    install -m 600 /dev/null "$OPT/authentik/omni-scim-token"; printf '%s' "$token" > "$OPT/authentik/omni-scim-token"
    authentik_wire
}

case "${1:-}:${2:-}" in
    apply:mailpit|apply:authentik|apply:fleet) need_root apply; "${2}_apply" ;;
    undo:mailpit|undo:authentik|undo:fleet) need_root undo; "${2}_undo" ;;
    wire:authentik) need_root wire; authentik_wire ;;
    scim-token:*) need_root scim-token; scim_token ;;
    status:*) status ;;
    *) die "usage: $0 apply|undo mailpit|authentik|fleet, or $0 status" ;;
esac
