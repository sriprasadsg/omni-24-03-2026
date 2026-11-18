#!/bin/bash
# Builds the macOS agent installer on a Mac: one universal omni-agent (Apple silicon + Intel), signed
# with the hardened runtime, in an installer package that is signed, notarised and stapled.
#
#   agent-install/macos/build-pkg.sh                     unsigned, for a test install on this Mac only
#   agent-install/macos/build-pkg.sh --app "Developer ID Application: NAME (TEAMID)" \
#       --installer "Developer ID Installer: NAME (TEAMID)" --notary-profile omni-notary
#
# --notary-profile names credentials saved once with:
#   xcrun notarytool store-credentials omni-notary --apple-id <id> --team-id <TEAMID>
# Output: agent-install/macos/out/omni-agent-<version>-macos.pkg, to copy to backend/static/.
set -euo pipefail

APP_ID="" INSTALLER_ID="" NOTARY=""
while [ $# -gt 0 ]; do
    case "$1" in
        --app) APP_ID="$2"; shift 2 ;;
        --installer) INSTALLER_ID="$2"; shift 2 ;;
        --notary-profile) NOTARY="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
[ "$(uname)" = Darwin ] || { echo "Run this on a Mac." >&2; exit 1; }
if [ -n "$NOTARY" ] && { [ -z "$APP_ID" ] || [ -z "$INSTALLER_ID" ]; }; then
    echo "Notarisation needs both --app and --installer." >&2; exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
CRATE="$(cd "$HERE/../omni-agent-rs" && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$CRATE/Cargo.toml" | head -1)"
OUT="$HERE/out"
WORK="$OUT/work"
APPDIR="$WORK/root/Library/Application Support/OmniAgent"
rm -rf "$WORK"
mkdir -p "$APPDIR" "$WORK/root/Library/LaunchDaemons" "$WORK/scripts"
export MACOSX_DEPLOYMENT_TARGET=11.0

for target in aarch64-apple-darwin x86_64-apple-darwin; do
    rustup target add "$target" >/dev/null
    cargo build --release --locked --manifest-path "$CRATE/Cargo.toml" --target "$target"
done
lipo -create -output "$APPDIR/omni-agent" \
    "$CRATE/target/aarch64-apple-darwin/release/omni-agent" "$CRATE/target/x86_64-apple-darwin/release/omni-agent"
install -m 755 "$HERE/uninstall.sh" "$APPDIR/uninstall.sh"
install -m 644 "$HERE/com.omniagent.agent.plist" "$WORK/root/Library/LaunchDaemons/com.omniagent.agent.plist"
install -m 755 "$HERE/scripts/preinstall" "$HERE/scripts/postinstall" "$WORK/scripts/"

if [ -n "$APP_ID" ]; then
    codesign --force --timestamp --options runtime --entitlements "$HERE/entitlements.plist" \
        --identifier com.omniagent.agent --sign "$APP_ID" "$APPDIR/omni-agent"
    codesign --verify --strict --verbose=2 "$APPDIR/omni-agent"
fi

pkgbuild --root "$WORK/root" --scripts "$WORK/scripts" --identifier com.omniagent.agent \
    --version "$VERSION" --install-location / --ownership recommended "$WORK/component.pkg"
PKG="$OUT/omni-agent-$VERSION-macos.pkg"
rm -f "$PKG"
if [ -n "$INSTALLER_ID" ]; then
    productbuild --package "$WORK/component.pkg" --sign "$INSTALLER_ID" --timestamp "$PKG"
else
    productbuild --package "$WORK/component.pkg" "$PKG"
fi

if [ -n "$NOTARY" ]; then
    xcrun notarytool submit "$PKG" --keychain-profile "$NOTARY" --wait
    xcrun stapler staple "$PKG"
    spctl --assess --type install --verbose=2 "$PKG"
fi
lipo -archs "$APPDIR/omni-agent"
shasum -a 256 "$PKG"
echo "Built $PKG"
