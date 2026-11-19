#!/usr/bin/env bash
# Integration keys for the backend (Wave 6), asked for here so they never pass through a chat or a log.
#
#   sudo scripts/integration_keys.sh virustotal smtp   ask for each (secret input hidden), save, restart the backend
#   sudo scripts/integration_keys.sh show              which variables are set (names only)
#
# Values go to /etc/omni/integrations.env (root only), which systemd loads into omni-backend through the drop-in
# /etc/systemd/system/omni-backend.service.d/30-integrations.conf; like the MongoDB URL, they win over .env.
# SMTP is written under both names the code reads (SMTP_PASS and SMTP_PASSWORD, SMTP_FROM and SMTP_FROM_EMAIL).
# Test each one afterwards on Platform health > Integrations.
set -euo pipefail

FILE="${INTEGRATIONS_FILE:-/etc/omni/integrations.env}"
DROPIN="${INTEGRATIONS_DROPIN:-/etc/systemd/system/omni-backend.service.d/30-integrations.conf}"

[ "$(id -u)" = 0 ] || [ -n "${INTEGRATIONS_SANDBOX:-}" ] || { echo "run it with sudo"; exit 1; }
[ $# -gt 0 ] || { echo "usage: $0 virustotal|smtp ... | show"; exit 2; }

declare -A NEW=()

ask() {  # $1 = prompt, $2 = default (shown), $3 = "secret" to hide input; prints the answer
  local answer tty=/dev/tty
  [ -n "${INTEGRATIONS_SANDBOX:-}" ] && tty=/dev/stdin   # the sandbox test feeds answers on stdin
  if [ "${3:-}" = secret ]; then read -rsp "$1: " answer <"$tty"; echo >&2
  else read -rp "$1${2:+ [$2]}: " answer <"$tty"; fi
  printf '%s' "${answer:-${2:-}}"
}

set_var() {  # $1 = name, $2 = value; refuses newlines (one variable per line)
  case "$2" in *$'\n'*) echo "$1: a value cannot contain a line break"; exit 1 ;; esac
  NEW["$1"]="$2"
}

for what in "$@"; do
  case "$what" in
  virustotal)
    key=$(ask "VirusTotal API key (input hidden)" "" secret)
    [ -n "$key" ] || { echo "no key entered; VirusTotal unchanged"; continue; }
    [[ "$key" =~ ^[0-9a-f]{64}$ ]] || echo "note: a VirusTotal key is usually 64 hex characters; saving it as entered"
    set_var VIRUSTOTAL_API_KEY "$key"
    ;;
  smtp)
    host=$(ask "SMTP server (e.g. smtp.gmail.com, smtp.office365.com, smtp.sendgrid.net)" "")
    [ -n "$host" ] || { echo "no server entered; SMTP unchanged"; continue; }
    port=$(ask "Port (587 = STARTTLS, 465 = TLS from the start)" "587")
    user=$(ask "User name" "")
    pass=$(ask "Password or app password (input hidden)" "" secret)
    default_from=""; [[ "$user" == *@* ]] && default_from="$user"
    from=$(ask "From address" "$default_from")
    [ -n "$user" ] && [ -n "$pass" ] && [ -n "$from" ] || { echo "user, password and from address are all needed; SMTP unchanged"; continue; }
    [[ "$port" =~ ^[0-9]+$ ]] || { echo "port must be a number; SMTP unchanged"; continue; }
    set_var SMTP_HOST "$host"; set_var SMTP_PORT "$port"; set_var SMTP_USER "$user"
    set_var SMTP_PASS "$pass"; set_var SMTP_PASSWORD "$pass"; set_var SMTP_FROM "$from"; set_var SMTP_FROM_EMAIL "$from"
    if [ "$port" = 465 ]; then set_var SMTP_USE_TLS true; set_var SMTP_STARTTLS false
    else set_var SMTP_USE_TLS false; set_var SMTP_STARTTLS true; fi
    [ "$port" = 465 ] && echo "note: some senders here always use STARTTLS; port 587 works with all of them"
    ;;
  show)
    [ -f "$FILE" ] && sed -n 's/^\([A-Z_]*\)=.*/\1 is set/p' "$FILE" || echo "nothing set yet ($FILE)"
    exit 0
    ;;
  *) echo "unknown: $what (virustotal, smtp or show)"; exit 2 ;;
  esac
done

[ ${#NEW[@]} -gt 0 ] || { echo "nothing to save"; exit 0; }

# Keep the other variables, replace these. systemd reads "NAME=value" in double quotes with \\ and \" escaped;
# nothing else in it is special ($ stays literal).
install -d -m 755 "$(dirname "$FILE")"
tmp=$(mktemp "$FILE.XXXXXX")
chmod 600 "$tmp"
if [ -f "$FILE" ]; then
  while IFS= read -r line; do
    name="${line%%=*}"
    [ -n "${NEW[$name]+x}" ] || printf '%s\n' "$line"
  done < "$FILE" > "$tmp"
fi
for name in "${!NEW[@]}"; do
  value="${NEW[$name]//\\/\\\\}"; value="${value//\"/\\\"}"
  printf '%s="%s"\n' "$name" "$value" >> "$tmp"
done
mv "$tmp" "$FILE"

if [ ! -f "$DROPIN" ]; then
  install -d -m 755 "$(dirname "$DROPIN")"
  printf '[Service]\n# Integration keys (scripts/integration_keys.sh); they win over .env.\nEnvironmentFile=-%s\n' "$FILE" > "$DROPIN"
fi
echo "saved: $(printf '%s ' "${!NEW[@]}")"

[ -n "${INTEGRATIONS_SANDBOX:-}" ] && exit 0
systemctl daemon-reload
systemctl restart omni-backend
for _ in $(seq 1 60); do
  [ "$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/api/health)" = 200 ] && {
    echo "backend restarted; test them on Platform health > Integrations"; exit 0; }
  sleep 1
done
echo "the backend did not answer within 60 s: check logs/backend.log"; exit 1
