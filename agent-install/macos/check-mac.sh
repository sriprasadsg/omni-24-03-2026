#!/bin/bash
# Checks that this Mac can build, sign and notarise the agent, and whether macOS accepts the
# platform's TLS certificate (the agent trusts only that certificate).
#   agent-install/macos/check-mac.sh https://<platform address>
set -u
URL="${1:?usage: check-mac.sh https://<platform address>}"
HOSTPORT="${URL#https://}"
HOSTPORT="${HOSTPORT%%/*}"
HOST="${HOSTPORT%%:*}"
case "$HOSTPORT" in *:*) PORT="${HOSTPORT##*:}" ;; *) PORT=443 ;; esac

echo "== macOS $(sw_vers -productVersion) on $(uname -m)"
for tool in cargo rustup pkgbuild productbuild lipo codesign; do
    printf '%-13s %s\n' "$tool" "$(command -v "$tool" || echo MISSING)"
done
xcrun --find notarytool >/dev/null 2>&1 && echo "notarytool    ok" || echo "notarytool    MISSING (install the Xcode Command Line Tools)"

echo "== Developer ID certificates in the keychain"
security find-identity -v -p basic | grep -E "Developer ID (Application|Installer)" || echo "none found"

echo "== The platform certificate, checked the way macOS checks a TLS server"
TMP="$(mktemp -d)"
if echo | openssl s_client -connect "$HOST:$PORT" -servername "$HOST" 2>/dev/null | openssl x509 -out "$TMP/server.pem" 2>/dev/null; then
    openssl x509 -in "$TMP/server.pem" -noout -subject -startdate -enddate
    if security verify-cert -c "$TMP/server.pem" -r "$TMP/server.pem" -p ssl -n "$HOST" -L; then
        echo "RESULT: macOS accepts this certificate when it is pinned"
    else
        echo "RESULT: macOS rejects this certificate (reason above)"
    fi
else
    echo "Could not read a certificate from $HOST:$PORT"
fi
rm -rf "$TMP"
